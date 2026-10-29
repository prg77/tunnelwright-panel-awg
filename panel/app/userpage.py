"""Страница пользователя: личная ссылка /u/<токен> с конфигом, QR и инструкцией.

Текст страницы — шаблон из настроек панели: упрощённая разметка (заголовки #, списки,
**жирный**, `код`, [ссылки](https://…)) и подстановки {name}, {ip}, {portal}, {expires},
{traffic}, {quota}. Всё, что пишет администратор, экранируется — HTML в шаблоне не исполняется.
"""
import html
import io
import re
import secrets
import time
import zoneinfo
from collections import defaultdict, deque
from datetime import datetime, timezone

import segno

from . import clients, db, nodes, quotas, routing

SETTING = "user_page"
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{20,64}")
MAX_TEMPLATE = 20000
MISS_LIMIT, MISS_WINDOW = 30, 900   # неверных токенов с одного IP за 15 минут

DEFAULT_TEMPLATE = """# Привет, {name}!
Это ваша личная страница доступа к VPN «{portal}».

## Как подключиться
1. Установите приложение:
  - Android — [AmneziaWG в Google Play](https://play.google.com/store/apps/details?id=org.amnezia.awg)
  - iPhone, iPad, Mac — [AmneziaWG в App Store](https://apps.apple.com/app/amneziawg/id6478942365)
  - Windows — [WireSock Secure Connect](https://www.wiresock.net/) или [AmneziaWG](https://github.com/amnezia-vpn/amneziawg-windows-client/releases/latest)
2. Отсканируйте QR-код в приложении или скачайте файл конфигурации и импортируйте его.
3. Включите подключение.

**Не пересылайте эту ссылку** — по ней можно получить ваш ключ доступа.
"""

PLACEHOLDERS = {
    "name": "имя клиента", "ip": "адрес в VPN", "portal": "название панели",
    "expires": "срок доступа", "traffic": "трафик за месяц", "quota": "квота за месяц",
}

_misses: dict[str, deque] = defaultdict(deque)


# ── настройки ──────────────────────────────────────────────────
def settings() -> dict:
    s = db.get_setting(SETTING, {}) or {}
    return {"enabled": s.get("enabled", True), "template": s.get("template") or DEFAULT_TEMPLATE,
            "show_qr": s.get("show_qr", True), "custom": bool(s.get("template"))}


def save_settings(enabled=None, template=None, show_qr=None) -> dict:
    s = db.get_setting(SETTING, {}) or {}
    if enabled is not None:
        s["enabled"] = bool(enabled)
    if show_qr is not None:
        s["show_qr"] = bool(show_qr)
    if template is not None:
        template = template.replace("\r\n", "\n").strip()
        if len(template) > MAX_TEMPLATE:
            raise ValueError(f"шаблон — не больше {MAX_TEMPLATE} символов")
        s["template"] = "" if template == DEFAULT_TEMPLATE.strip() else template
    db.set_setting(SETTING, s)
    return settings()


# ── ссылки ─────────────────────────────────────────────────────
def link(client_id: int) -> str | None:
    r = db.one("SELECT token FROM user_links WHERE client_id=?", (client_id,))
    return r["token"] if r else None


def all_links() -> dict[str, dict]:
    return {str(r["client_id"]): {"token": r["token"], "last_seen": r["last_seen"]}
            for r in db.query("SELECT * FROM user_links")}


def issue(client_id: int, regenerate: bool = False) -> str:
    """Токен клиента; regenerate — новый токен, старая ссылка перестаёт работать."""
    cur = link(client_id)
    if cur and not regenerate:
        return cur
    token = secrets.token_urlsafe(24)
    db.execute("INSERT INTO user_links(client_id, token, created_at) VALUES(?,?,?) "
               "ON CONFLICT(client_id) DO UPDATE SET token=excluded.token, created_at=excluded.created_at, "
               "last_seen=NULL", (client_id, token, int(time.time())))
    return token


def revoke(client_id: int):
    db.execute("DELETE FROM user_links WHERE client_id=?", (client_id,))


def blocked(ip: str) -> bool:
    q = _misses[ip]
    now = time.time()
    while q and now - q[0] > MISS_WINDOW:
        q.popleft()
    return len(q) >= MISS_LIMIT


def resolve(token: str, ip: str) -> int | None:
    """Токен → id клиента панели. Неверные токены считаются по IP (перебор)."""
    row = db.one("SELECT client_id FROM user_links WHERE token=?", (token,)) if TOKEN_RE.fullmatch(token) else None
    if not row:
        _misses[ip].append(time.time())
        return None
    db.execute("UPDATE user_links SET last_seen=? WHERE client_id=?", (int(time.time()), row["client_id"]))
    return row["client_id"]


# ── разметка шаблона ───────────────────────────────────────────
_INLINE = [
    (re.compile(r"`([^`]+)`"), r"<code>\1</code>"),
    (re.compile(r"\*\*(.+?)\*\*"), r"<b>\1</b>"),
    (re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)"), r'<a href="\2" rel="noopener noreferrer" target="_blank">\1</a>'),
]
_ITEM = re.compile(r"(\s*)(?:[-*]|(\d+)\.)\s+(.*)")


def _inline(text: str) -> str:
    out = html.escape(text, quote=False)
    for rx, rep in _INLINE:
        out = rx.sub(rep, out)
    return out


def render_markup(text: str) -> str:
    """Шаблон → HTML. Списки — до двух уровней (вложенность — отступом)."""
    out: list[str] = []
    stack: list[tuple[str, int]] = []   # (тег списка, отступ)
    para: list[str] = []

    def flush_para():
        if para:
            out.append("<p>" + "<br>".join(_inline(p) for p in para) + "</p>")
            para.clear()

    def close_lists(indent=-1):
        while stack and stack[-1][1] > indent:
            out.append(f"</li></{stack.pop()[0]}>")

    for line in text.splitlines():
        m = _ITEM.fullmatch(line)
        if m and line.strip():
            flush_para()
            indent = min(len(m.group(1).expandtabs(4)), 8)
            tag = "ol" if m.group(2) else "ul"
            if stack and indent > stack[-1][1] and len(stack) < 2:
                out.append(f"<{tag}>")           # вложенный список внутри открытого <li>
                stack.append((tag, indent))
            else:
                close_lists(indent)
                if stack and stack[-1][0] == tag:
                    out.append("</li>")
                else:
                    if stack:                    # другой тип списка на том же уровне
                        out.append(f"</li></{stack.pop()[0]}>")
                    out.append(f"<{tag}>")
                    stack.append((tag, indent))
            out.append("<li>" + _inline(m.group(3)))
            continue
        close_lists()
        s = line.strip()
        if not s:
            flush_para()
        elif s.startswith("## "):
            flush_para()
            out.append(f"<h3>{_inline(s[3:])}</h3>")
        elif s.startswith("# "):
            flush_para()
            out.append(f"<h2>{_inline(s[2:])}</h2>")
        else:
            para.append(s)
    flush_para()
    close_lists()
    return "\n".join(out)


def fill(markup_html: str, values: dict) -> str:
    for k in PLACEHOLDERS:
        markup_html = markup_html.replace("{" + k + "}", html.escape(str(values.get(k, "—"))))
    return markup_html


# ── данные клиента ─────────────────────────────────────────────
def _gb(b: int) -> str:
    return f"{b / 1024**3:.2f} ГБ" if b >= 1024**3 / 100 else f"{b / 1024**2:.1f} МБ"


def _expiry(exp: str | None, tz: str) -> tuple[str, bool]:
    if not exp:
        return "без ограничения", False
    try:
        when = datetime.fromisoformat(exp.replace("Z", "+00:00"))
    except ValueError:
        return exp, False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(zoneinfo.ZoneInfo(tz)).strftime("%d.%m.%Y"), when < datetime.now(timezone.utc)


async def page_data(client_id: int) -> dict:
    """Всё, что показывает страница: состояние клиента в панели и его профили по нодам."""
    tz = db.get_setting("timezone", "Europe/Moscow")
    c = clients.get(client_id) or {}
    month = quotas.month(tz)
    used = quotas.used(client_id, month)
    q = db.one("SELECT limit_bytes, blocked FROM quotas WHERE client_id=?", (client_id,))
    expires, expired = _expiry(c.get("expires_at"), tz)
    servers = [{"node_id": p["node_id"], "name": p["node_name"]} for p in clients.profiles(client_id)] if c else []
    return {"id": client_id, "name": c.get("name") or "—", "ip": c.get("ipv4") or "—", "ok": bool(servers),
            "enabled": bool(c.get("enabled")), "expired": expired, "expires": expires, "servers": servers,
            "portal": db.get_setting("portal_name", "Private World"),
            "traffic": _gb(used), "used": used, "limit": q["limit_bytes"] if q else None,
            "quota": _gb(q["limit_bytes"]) if q else "без ограничения",
            "quota_blocked": bool(q and q["blocked"] == month)}


def can_download(d: dict) -> bool:
    return d["ok"] and d["enabled"] and not d["expired"]


async def qr_svg(client_id: int, node_id: int | None = None) -> str | None:
    text, _, _ = await routing.client_config(client_id, node_id)
    try:
        qr = segno.make(text, error="l")
    except segno.DataOverflowError:
        return None
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=5, border=2, light="#ffffff", xmldecl=False)
    return buf.getvalue().decode()


# ── HTML страницы ──────────────────────────────────────────────
CSP = ("default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; "
       "form-action 'none'; frame-ancestors 'none'")

_CSS = """
:root{--bg:#f4f6fa;--card:#fff;--text:#1c2030;--muted:#6b7490;--line:#e2e6ee;--accent:#2d5fd4;--ok:#16a34a;--warn:#d97706;--bad:#dc2626}
@media(prefers-color-scheme:dark){:root{--bg:#0b1424;--card:#121f36;--text:#d6e4f5;--muted:#7d93b2;--line:#1f3354;--accent:#4aa8f0;--ok:#4ade80;--warn:#fbbf24;--bad:#f87171}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:640px;margin:0 auto;padding:24px 16px 40px;display:flex;flex-direction:column;gap:14px}
header{font-weight:700;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 20px}
.row{display:flex;justify-content:space-between;gap:12px;padding:6px 0;border-bottom:1px solid var(--line)}.row:last-child{border:0}
.row span:first-child{color:var(--muted)}.pill{font-weight:700}.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}
.bar{height:6px;border-radius:3px;background:var(--line);overflow:hidden;margin-top:8px}.bar i{display:block;height:100%;background:var(--accent)}
h2{font-size:21px;margin:0 0 6px}h3{font-size:16px;margin:16px 0 6px}p{margin:8px 0}ul,ol{margin:6px 0;padding-left:22px}li{margin:3px 0}
a{color:var(--accent)}code{font:13px ui-monospace,Menlo,Consolas,monospace;background:var(--bg);padding:1px 5px;border-radius:4px}
.qr{display:flex;flex-direction:column;align-items:center;gap:14px}.qr svg{width:min(280px,100%);height:auto;background:#fff;padding:10px;border-radius:12px}
.btn{display:inline-block;padding:11px 20px;border-radius:10px;background:var(--accent);color:#fff;text-decoration:none;font-weight:600}
.note{font-size:13px;color:var(--muted);text-align:center}
"""


def _server_card(srv: dict, show_qr: bool, href: str, many: bool) -> str:
    """Блок одной ноды: заголовок (если нод несколько), QR и кнопка скачивания."""
    e = html.escape
    qr = srv.get("qr")
    if not show_qr:
        qr_part = ""
    elif qr == "error":
        qr_part = '<div class="note">Сервер временно недоступен — попробуйте позже.</div>'
    elif qr:
        qr_part = qr
    else:
        qr_part = '<div class="note">Конфигурация слишком большая для QR-кода — скачайте файл.</div>'
    title = f'<h3 style="margin:0">🌍 {e(srv["name"])}</h3>' if many else ""
    return (f'<div class="card qr">{title}{qr_part}<a class="btn" href="{e(href)}" download>⬇ Скачать конфигурацию</a>'
            f'<div class="note">Файл .conf импортируется в приложение</div></div>')


def page_html(d: dict, body_html: str, show_qr: bool, token: str = "", preview: bool = False) -> str:
    e = html.escape
    if not d["ok"]:
        status = '<span class="pill warn">профили ещё создаются</span>'
    elif d["expired"]:
        status = '<span class="pill bad">срок истёк</span>'
    elif d["quota_blocked"]:
        status = '<span class="pill bad">квота исчерпана</span>'
    elif not d["enabled"]:
        status = '<span class="pill bad">отключён</span>'
    else:
        status = '<span class="pill ok">активен</span>'
    bar = ""
    if d["limit"]:
        pct = min(100, int(d["used"] * 100 / d["limit"]))
        bar = f'<div class="bar"><i style="width:{pct}%"></i></div>'
    info = (f'<div class="card"><div class="row"><span>Статус</span>{status}</div>'
            f'<div class="row"><span>Срок доступа</span><span>{e(d["expires"])}</span></div>'
            f'<div class="row"><span>Трафик за месяц</span><span>{e(d["traffic"])}'
            f'{" из " + e(d["quota"]) if d["limit"] else ""}</span></div>{bar}</div>')
    if can_download(d) or preview:
        servers = d["servers"]
        many = len(servers) > 1
        access = "".join(_server_card(s, show_qr, "#" if preview else f"{token}/config?node={s['node_id']}", many)
                         for s in servers)      # ссылка относительно /u/<токен>
        if many:
            access = ('<div class="card note">Серверов несколько — подключите любой или добавьте все '
                      'в приложение и переключайтесь между ними.</div>' + access)
    else:
        access = ('<div class="card note">Доступ сейчас не активен — конфигурация недоступна. '
                  'Обратитесь к администратору.</div>')
    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow"><title>{e(d["portal"])} — {e(d["name"])}</title>'
            f'<style>{_CSS}</style></head><body><main><header>{e(d["portal"])}</header>{info}'
            f'<div class="card">{body_html}</div>{access}</main></body></html>')


async def render(client_id: int, token: str = "", template: str | None = None, preview: bool = False) -> str:
    s = settings()
    d = await page_data(client_id)
    body = fill(render_markup(template if template is not None else s["template"]), d)
    if s["show_qr"] and can_download(d):
        for srv in d["servers"]:
            try:
                srv["qr"] = await qr_svg(client_id, srv["node_id"])
            except (nodes.NodeError, ValueError):
                srv["qr"] = "error"
    return page_html(d, body, s["show_qr"], token, preview)


SAMPLE = {"id": 0, "name": "Иван телефон", "ip": "10.8.0.7", "ok": True, "enabled": True, "expired": False,
          "expires": "31.12.2026", "traffic": "3.42 ГБ", "used": 3.42 * 1024**3, "limit": 50 * 1024**3,
          "quota": "50.00 ГБ", "quota_blocked": False,
          "servers": [{"node_id": 1, "name": "Финляндия"}, {"node_id": 2, "name": "Швеция"}]}


def render_sample(template: str) -> str:
    d = {**SAMPLE, "portal": db.get_setting("portal_name", "Private World"),
         "servers": [dict(s) for s in SAMPLE["servers"]]}
    return page_html(d, fill(render_markup(template), d), False, preview=True)
