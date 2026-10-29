"""Страница пользователя: личная ссылка /u/<токен> с конфигами всех его устройств, QR и инструкцией.

Оформление — как у панели (те же цвета, шрифты и панели; светлая тема — по настройке устройства).
Текст инструкции — шаблон из настроек панели: упрощённая разметка (заголовки #, списки,
**жирный**, `код`, [ссылки](https://…)) и подстановки {name}, {ip}, {devices}, {portal}, {expires},
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
from urllib.parse import urlsplit

import segno

from . import clients, config, db, nodes, quotas, routing, users

SETTING = "user_page"
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{20,64}")
MAX_TEMPLATE = 20000
MISS_LIMIT, MISS_WINDOW = 30, 900   # неверных токенов с одного IP за 15 минут

DEFAULT_TEMPLATE = """## Как подключиться
1. Установите приложение:
  - Android — [AmneziaWG в Google Play](https://play.google.com/store/apps/details?id=org.amnezia.awg)
  - iPhone, iPad, Mac — [AmneziaWG в App Store](https://apps.apple.com/app/amneziawg/id6478942365)
  - Windows — [WireSock Secure Connect](https://www.wiresock.net/) или [AmneziaWG](https://github.com/amnezia-vpn/amneziawg-windows-client/releases/latest)
2. Ниже откройте своё устройство, отсканируйте QR-код в приложении или скачайте файл конфигурации и импортируйте его.
3. Включите подключение.

У каждого устройства своя конфигурация — не используйте одну и ту же на нескольких.
**Не пересылайте эту ссылку** — по ней можно получить ваши ключи доступа.
"""

PLACEHOLDERS = {
    "name": "имя пользователя", "ip": "адреса устройств в VPN", "devices": "число устройств",
    "portal": "название панели", "expires": "срок доступа", "traffic": "трафик за месяц (все устройства)",
    "quota": "квота за месяц",
}

_misses: dict[str, deque] = defaultdict(deque)


# ── настройки ──────────────────────────────────────────────────
def settings() -> dict:
    s = db.get_setting(SETTING, {}) or {}
    return {"enabled": s.get("enabled", True), "template": s.get("template") or DEFAULT_TEMPLATE,
            "show_qr": s.get("show_qr", True), "custom": bool(s.get("template")),
            # адрес ссылок: свой домен для страниц пользователей; пусто — адрес панели
            "user_url": s["user_url"] if "user_url" in s else config.USER_URL}


def normalize_url(url: str) -> str:
    """https://example.com — схема и хост (порт можно), без пути. Пусто — сброс."""
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    p = urlsplit(url)
    if p.scheme not in ("https", "http") or not p.hostname or p.path or p.query or p.fragment or p.username:
        raise ValueError("адрес ссылок — вида https://example.com, без пути")
    return f"{p.scheme}://{p.netloc.lower()}"


def user_host() -> str | None:
    """Хост отдельного адреса страниц пользователей: на нём открываются только /u/."""
    url = settings()["user_url"]
    return urlsplit(url).hostname if url else None


def save_settings(enabled=None, template=None, show_qr=None, user_url=None) -> dict:
    s = db.get_setting(SETTING, {}) or {}
    if enabled is not None:
        s["enabled"] = bool(enabled)
    if show_qr is not None:
        s["show_qr"] = bool(show_qr)
    if user_url is not None:
        s["user_url"] = normalize_url(user_url)
    if template is not None:
        template = template.replace("\r\n", "\n").strip()
        if len(template) > MAX_TEMPLATE:
            raise ValueError(f"шаблон — не больше {MAX_TEMPLATE} символов")
        s["template"] = "" if template == DEFAULT_TEMPLATE.strip() else template
    db.set_setting(SETTING, s)
    return settings()


# ── ссылки ─────────────────────────────────────────────────────
def link(user_id: int) -> str | None:
    r = db.one("SELECT token FROM user_links WHERE user_id=?", (user_id,))
    return r["token"] if r else None


def all_links() -> dict[str, dict]:
    return {str(r["user_id"]): {"token": r["token"], "last_seen": r["last_seen"]}
            for r in db.query("SELECT * FROM user_links")}


def issue(user_id: int, regenerate: bool = False) -> str:
    """Токен пользователя; regenerate — новый токен, старая ссылка перестаёт работать."""
    cur = link(user_id)
    if cur and not regenerate:
        return cur
    token = secrets.token_urlsafe(24)
    db.execute("INSERT INTO user_links(user_id, token, created_at) VALUES(?,?,?) "
               "ON CONFLICT(user_id) DO UPDATE SET token=excluded.token, created_at=excluded.created_at, "
               "last_seen=NULL", (user_id, token, int(time.time())))
    return token


def revoke(user_id: int):
    db.execute("DELETE FROM user_links WHERE user_id=?", (user_id,))


def blocked(ip: str) -> bool:
    q = _misses[ip]
    now = time.time()
    while q and now - q[0] > MISS_WINDOW:
        q.popleft()
    return len(q) >= MISS_LIMIT


def resolve(token: str, ip: str) -> int | None:
    """Токен → id пользователя. Неверные токены считаются по IP (перебор)."""
    row = db.one("SELECT user_id FROM user_links WHERE token=?", (token,)) if TOKEN_RE.fullmatch(token) else None
    if not row:
        _misses[ip].append(time.time())
        return None
    db.execute("UPDATE user_links SET last_seen=? WHERE user_id=?", (int(time.time()), row["user_id"]))
    return row["user_id"]


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
        v = values.get(k, "—")
        if isinstance(v, list):          # {devices} — число устройств
            v = len(v)
        markup_html = markup_html.replace("{" + k + "}", html.escape(str(v)))
    return markup_html


# ── данные пользователя ────────────────────────────────────────
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


def _device_used(cid: int, month_key: str) -> int:
    row = db.one("SELECT COALESCE(SUM(rx + tx), 0) AS b FROM traffic_daily WHERE client_id=? AND day LIKE ?",
                 (cid, month_key + "-%"))
    return int(row["b"])


async def page_data(user_id: int) -> dict:
    """Всё, что показывает страница: состояние пользователя и его конфиги с профилями по нодам."""
    tz = db.get_setting("timezone", "Europe/Moscow")
    u = users.get(user_id) or {}
    month = quotas.month(tz)
    used = quotas.used(user_id, month)
    q = db.one("SELECT limit_bytes, blocked FROM quotas WHERE user_id=?", (user_id,))
    expires, expired = _expiry(u.get("expires_at"), tz)
    devices = [{"id": c["id"], "name": c["name"] or "", "ip": c["ipv4"], "enabled": bool(c["enabled"]),
                "traffic": _gb(_device_used(c["id"], month)),
                "servers": [{"node_id": p["node_id"], "name": p["node_name"]} for p in clients.profiles(c["id"])]}
               for c in (clients.of_user(user_id) if u else [])]
    return {"id": user_id, "name": u.get("name") or "—",
            "ip": ", ".join(d["ip"] for d in devices if d["ip"]) or "—",
            "ok": any(d["servers"] for d in devices),
            "enabled": bool(u.get("enabled")), "expired": expired, "expires": expires, "devices": devices,
            "portal": db.get_setting("portal_name", "Private World"),
            "traffic": _gb(used), "used": used, "limit": q["limit_bytes"] if q else None,
            "quota": _gb(q["limit_bytes"]) if q else "без ограничения",
            "quota_blocked": bool(q and q["blocked"] == month)}


def can_download(d: dict, device: dict | None = None) -> bool:
    """Пользователь активен (и устройство включено, если задано)."""
    return d["ok"] and d["enabled"] and not d["expired"] and (device is None or device["enabled"])


def device(d: dict, cid: int | None) -> dict | None:
    """Устройство пользователя по id конфига; без id — первое."""
    return next((x for x in d["devices"] if cid is None or x["id"] == cid), None)


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

# Те же токены, что у панели (web/src/theme/tokens.css): тёмная тема Grafana, светлая — по настройке устройства.
# Скриптов и внешних шрифтов нет (CSP): устройства раскрываются через <details>.
_CSS = """
:root{color-scheme:dark;--bg:#111217;--surface:#181b1f;--surface2:#22252b;--border:rgba(204,204,220,.12);
--border-medium:rgba(204,204,220,.2);--text:#ccccdc;--muted:rgba(204,204,220,.65);--primary:#3d71d9;--primary-hover:#5a87e1;
--cyan:#6e9fff;--success:#6ccf8e;--warning:#fbad37;--error:#ff5286;--bar:rgba(204,204,220,.12);--logo-frame:#EFE6D2;
--sans:'Inter',-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;--mono:'Roboto Mono',ui-monospace,Menlo,Consolas,monospace}
@media(prefers-color-scheme:light){:root{color-scheme:light;--bg:#f4f5f5;--surface:#fff;--surface2:#f4f5f5;--border:rgba(36,41,46,.12);
--border-medium:rgba(36,41,46,.3);--text:#24292e;--muted:rgba(36,41,46,.75);--primary:#3871dc;--primary-hover:#2e62c4;--cyan:#1f62e0;
--success:#0a764e;--warning:#bd4b00;--error:#cf0e5b;--bar:rgba(36,41,46,.12);--logo-frame:#1E2A24}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 var(--sans)}
.top{height:48px;display:flex;align-items:center;gap:10px;padding:0 16px;background:var(--surface);border-bottom:1px solid var(--border)}
.top b{font-weight:500}.top span{margin-left:auto;color:var(--muted);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
main{max-width:760px;margin:0 auto;padding:16px 16px 32px;display:flex;flex-direction:column;gap:16px}
h1{font-size:24px;font-weight:400;line-height:1.3;margin:0}.sub{color:var(--muted);margin-top:2px}
.panel{background:var(--surface);border:1px solid var(--border);border-radius:4px;overflow:hidden}
.ph{padding:8px 16px;min-height:40px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;font-weight:500}
.pb{padding:12px 16px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;background:var(--border)}
.stat{background:var(--surface);padding:12px 16px}.stat small{display:block;color:var(--muted);font-size:12px}
.stat div{font-size:18px;margin-top:2px}.mono{font-family:var(--mono)}
.dot{display:inline-flex;align-items:center;gap:6px}.dot:before{content:"";width:8px;height:8px;border-radius:50%;background:currentColor}
.ok{color:var(--success)}.warn{color:var(--warning)}.bad{color:var(--error)}.off{color:var(--muted)}
.bar{height:6px;background:var(--bar);border-radius:2px;overflow:hidden;margin-top:8px}.bar i{display:block;height:100%;background:var(--primary)}
.tpl h2{font-size:18px;font-weight:500;margin:4px 0 8px}.tpl h3{font-size:14px;font-weight:500;margin:16px 0 6px}
.tpl p{margin:8px 0}.tpl ul,.tpl ol{margin:6px 0;padding-left:22px}.tpl li{margin:3px 0}
a{color:var(--cyan)}code{font:12px var(--mono);background:var(--surface2);border:1px solid var(--border);padding:0 4px;border-radius:2px}
.sec{font-size:12px;font-weight:500;color:var(--muted);margin:4px 0 -8px}
details.panel>summary{list-style:none;cursor:pointer;padding:10px 16px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
details.panel>summary::-webkit-details-marker{display:none}
details.panel>summary:before{content:"";width:6px;height:6px;border-right:1.5px solid var(--muted);border-bottom:1.5px solid var(--muted);transform:rotate(-45deg);margin-right:2px;transition:transform .15s}
details[open].panel>summary:before{transform:rotate(45deg)}
details[open].panel>summary{border-bottom:1px solid var(--border)}
summary .name{font-weight:500}summary .meta{margin-left:auto;display:flex;gap:12px;align-items:center;font-size:12px;color:var(--muted)}
.tag{font-size:12px;line-height:18px;padding:0 6px;border-radius:2px;border:1px solid currentColor;opacity:.9}
.nodes{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;padding:12px 16px}
.node{border:1px solid var(--border);border-radius:4px;padding:12px;display:flex;flex-direction:column;align-items:center;gap:10px;background:var(--surface2)}
.node h4{margin:0;font-size:14px;font-weight:500;align-self:stretch}
.node svg{width:100%;max-width:220px;height:auto;background:#fff;padding:8px;border-radius:4px}
.btn{display:flex;align-items:center;justify-content:center;height:32px;padding:0 16px;border-radius:2px;background:var(--primary);
color:#fff;text-decoration:none;font-weight:500;align-self:stretch}.btn:hover{background:var(--primary-hover)}
.note{font-size:12px;color:var(--muted);text-align:center}.empty{padding:16px;color:var(--muted)}
@media(max-width:480px){main{padding:12px 8px 24px}.nodes{grid-template-columns:1fr}}
"""

# Логотип Tunnelwright (упрощённая иконка, как в шапке панели)
_LOGO = ('<svg width="24" height="24" viewBox="0 0 100 100" aria-hidden="true"><defs><clipPath id="lc">'
         '<polygon points="50,16 85,87 15,87"/></clipPath></defs><g clip-path="url(#lc)">'
         '<polygon points="10,90 32,58 52,20 70,50 90,90" fill="#1E3B30"/>'
         '<polygon points="52,20 44,46 38,90 54,90 50,62 58,42" fill="#4E8C6A"/>'
         '<polygon points="70,50 62,66 70,90 90,90" fill="#2E6450"/>'
         '<path d="M39 90V75a11 11 0 0 1 22 0V90Z" fill="#F2C14E"/></g>'
         '<polygon points="50,5 94,93 6,93" fill="none" stroke="var(--logo-frame)" stroke-width="6"/></svg>')


def _device_name(dev: dict, i: int) -> str:
    return dev["name"] or f"Устройство {i}"


def _node_card(srv: dict, show_qr: bool, href: str, title: str) -> str:
    """Профиль устройства на одной ноде: название ноды, QR и кнопка скачивания."""
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
    head = f"<h4>🌍 {e(title)}</h4>" if title else ""
    return f'<div class="node">{head}{qr_part}<a class="btn" href="{e(href)}" download>Скачать конфигурацию</a></div>'


def _status(d: dict) -> str:
    if not d["ok"]:
        return '<span class="dot warn">Профили создаются</span>'
    if d["expired"]:
        return '<span class="dot bad">Срок истёк</span>'
    if d["quota_blocked"]:
        return '<span class="dot bad">Квота исчерпана</span>'
    if not d["enabled"]:
        return '<span class="dot bad">Отключён</span>'
    return '<span class="dot ok">Активен</span>'


def page_html(d: dict, body_html: str, show_qr: bool, token: str = "", preview: bool = False) -> str:
    e = html.escape
    bar = ""
    if d["limit"]:
        pct = min(100, int(d["used"] * 100 / d["limit"]))
        bar = f'<div class="bar"><i style="width:{pct}%"></i></div>'
    traffic = e(d["traffic"]) + (f' <small style="display:inline">из {e(d["quota"])}</small>' if d["limit"] else "")
    stats = (f'<div class="panel"><div class="stats">'
             f'<div class="stat"><small>Статус</small><div>{_status(d)}</div></div>'
             f'<div class="stat"><small>Срок доступа</small><div>{e(d["expires"])}</div></div>'
             f'<div class="stat"><small>Трафик за месяц</small><div>{traffic}</div>{bar}</div>'
             f'<div class="stat"><small>Устройств</small><div>{len(d["devices"])}</div></div>'
             f'</div></div>')

    allowed = can_download(d) or preview
    devices = d["devices"]
    blocks = []
    for i, dev in enumerate(devices, 1):
        on = dev["enabled"] and allowed
        state = ('<span class="dot ok">включено</span>' if on else
                 '<span class="dot off">отключено</span>' if not dev["enabled"] else '<span class="dot off">недоступно</span>')
        meta = (f'<span class="meta"><span class="mono">{e(dev["ip"] or "—")}</span>'
                f'<span>{e(dev.get("traffic", "—"))} за месяц</span>{state}</span>')
        if not on:
            inner = ('<div class="empty">Устройство отключено администратором.</div>' if not dev["enabled"] else
                     '<div class="empty">Доступ сейчас не активен — конфигурация недоступна. Обратитесь к администратору.</div>')
        elif not dev["servers"]:
            inner = '<div class="empty">Профили устройства ещё создаются на серверах — откройте страницу через минуту.</div>'
        else:
            many = len(dev["servers"]) > 1
            inner = '<div class="nodes">' + "".join(
                _node_card(s, show_qr, "#" if preview else f"{token}/config?c={dev['id']}&node={s['node_id']}",
                           s["name"] if many else "")       # ссылка относительно /u/<токен>
                for s in dev["servers"]) + "</div>"
            if many:
                inner = ('<div class="pb note" style="text-align:left;padding-bottom:0">Серверов несколько — подключите '
                         'любой или добавьте все в приложение и переключайтесь между ними.</div>') + inner
        is_open = " open" if i == 1 or len(devices) <= 2 else ""
        blocks.append(f'<details class="panel"{is_open}><summary><span class="name">📱 {e(_device_name(dev, i))}</span>'
                      f"{meta}</summary>{inner}</details>")
    if not blocks:
        blocks.append('<div class="panel empty">Устройств пока нет — обратитесь к администратору.</div>')
    access = ('<div class="sec">Устройства — у каждого своя конфигурация</div>' if len(devices) > 1 else
              '<div class="sec">Конфигурация</div>') + "".join(blocks)

    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow"><title>{e(d["portal"])} — {e(d["name"])}</title>'
            f'<style>{_CSS}</style></head><body>'
            f'<div class="top">{_LOGO}<b>{e(d["portal"])}</b><span>{e(d["name"])}</span></div>'
            f'<main><div><h1>{e(d["name"])}</h1><div class="sub">Личная страница доступа к VPN</div></div>'
            f'{stats}<div class="panel"><div class="pb tpl">{body_html}</div></div>{access}</main></body></html>')


async def render(user_id: int, token: str = "", template: str | None = None, preview: bool = False) -> str:
    s = settings()
    d = await page_data(user_id)
    body = fill(render_markup(template if template is not None else s["template"]), d)
    if s["show_qr"] and can_download(d):
        for dev in d["devices"]:
            if not dev["enabled"]:
                continue
            for srv in dev["servers"]:
                try:
                    srv["qr"] = await qr_svg(dev["id"], srv["node_id"])
                except (nodes.NodeError, ValueError):
                    srv["qr"] = "error"
    return page_html(d, body, s["show_qr"], token, preview)


SAMPLE = {"id": 0, "name": "Иван", "ip": "10.8.0.7, 10.8.0.8", "ok": True, "enabled": True, "expired": False,
          "expires": "31.12.2026", "traffic": "3.42 ГБ", "used": 3.42 * 1024**3, "limit": 50 * 1024**3,
          "quota": "50.00 ГБ", "quota_blocked": False,
          "devices": [{"id": 1, "name": "Телефон", "ip": "10.8.0.7", "enabled": True, "traffic": "2.90 ГБ",
                       "servers": [{"node_id": 1, "name": "Финляндия"}, {"node_id": 2, "name": "Швеция"}]},
                      {"id": 2, "name": "Ноутбук", "ip": "10.8.0.8", "enabled": True, "traffic": "530.0 МБ",
                       "servers": [{"node_id": 1, "name": "Финляндия"}, {"node_id": 2, "name": "Швеция"}]}]}


def render_sample(template: str) -> str:
    d = {**SAMPLE, "portal": db.get_setting("portal_name", "Private World"),
         "devices": [{**x, "servers": [dict(s) for s in x["servers"]]} for x in SAMPLE["devices"]]}
    return page_html(d, fill(render_markup(template), d), False, preview=True)
