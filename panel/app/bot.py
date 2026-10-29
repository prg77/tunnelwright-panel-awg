"""Telegram-бот администратора (long polling).

Команды принимаются только из чата, указанного в настройках Telegram (chat_id администратора).
Бот работает поверх тех же функций, что и панель: клиенты на локальной ноде, бэкап, журнал.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from . import audit, backup, clients, config, db, hostmetrics, nodes, notify, quotas, telegram, traffic, userpage

log = logging.getLogger("panel.bot")

COMMANDS = [
    ("status", "Состояние сервера"),
    ("clients", "Список клиентов"),
    ("client", "Карточка клиента: /client имя или /client #ID"),
    ("conf", "Конфиг и QR: /conf имя"),
    ("link", "Ссылка на страницу пользователя: /link имя"),
    ("add", "Новый клиент: /add имя [дней]"),
    ("enable", "Включить: /enable имя"),
    ("disable", "Отключить: /disable имя"),
    ("backup", "Сделать бэкап сейчас"),
    ("help", "Справка"),
]
HELP = "🤖 <b>Команды</b>\n\n" + "\n".join(f"/{c} — {d}" for c, d in COMMANDS)


def _gb(b) -> str:
    b = b or 0
    return f"{b / 1024**3:.2f} ГБ" if b >= 1024**3 else f"{b / 1024**2:.1f} МБ"


def _online(c) -> bool:
    ts = c.get("latestHandshakeAt")
    if not (ts and c["enabled"]):
        return False
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return False
    return datetime.now(timezone.utc) - t < timedelta(minutes=3)


async def _clients() -> list[dict]:
    """Клиенты панели с трафиком и handshake по всем доступным нодам."""
    rows, _ = await clients.reconcile_all()
    by_client = clients.summary(rows)
    out = []
    for c in clients.all_clients():
        s = by_client.get(c["id"], {})
        out.append({"panel_id": c["id"], "uid": c["uid"], "name": c["name"] or "", "ipv4": c["ipv4"], "enabled": bool(c["enabled"]),
                    "expiresAt": c["expires_at"], "latestHandshakeAt": s.get("latestHandshakeAt"),
                    "transferRx": s.get("transferRx", 0), "transferTx": s.get("transferTx", 0)})
    return out


def _find(items, query: str):
    """Клиент по ID (#a1b2…, достаточно начала) или по имени. Одинаковые имена — выбор по ID."""
    q = query.strip().lower()
    if q.startswith("#"):
        found = [c for c in items if len(q) > 3 and (c.get("uid") or "").startswith(q[1:])]
    else:
        found = [c for c in items if c["name"].lower() == q] or \
                [c for c in items if c["name"].lower().startswith(q)]
    if len(found) == 1:
        return found[0], None
    if not found:
        return None, f"Клиент «{telegram.escape(query)}» не найден"
    return None, ("Найдено несколько — укажите ID:\n" + "\n".join(
        f"<code>#{c.get('uid')}</code> {telegram.escape(c['name'])} · {c['ipv4']}" for c in found[:15]))



async def handle(text: str, chat: str):
    cmd, _, arg = text.partition(" ")
    cmd = cmd.split("@")[0].lstrip("/").lower()
    arg = arg.strip()
    reply = lambda t: telegram.send(t, token=telegram.settings()["token"], chat_id=chat)  # noqa: E731

    try:
        if cmd in ("start", "help"):
            await reply(HELP)
        elif cmd == "status":
            all_n = nodes.all_nodes()
            health = await asyncio.gather(*(n.health() for n in all_n))
            items = await _clients()
            m = await asyncio.to_thread(hostmetrics.snapshot)
            today = db.one("SELECT COALESCE(SUM(rx+tx),0) b FROM traffic_daily WHERE day=?",
                           (traffic.day_key(db.get_setting("timezone", "Europe/Moscow")),))["b"]
            node_lines = "\n".join(f"{'✅' if h.get('ok') else '🚨'} {telegram.escape(n.name)}"
                                   for n, h in zip(all_n, health)) or "нод нет — добавьте в панели"
            await reply(f"🖥 <b>{telegram.escape(db.get_setting('portal_name', 'Tunnelwright Panel AWG'))}</b> · "
                        f"<code>{telegram.escape(config.WG_HOST)}</code>\n"
                        f"{node_lines}\n"
                        f"👥 Онлайн {sum(_online(c) for c in items)} из {len(items)} "
                        f"(включено {sum(c['enabled'] for c in items)})\n"
                        f"📊 Сегодня {_gb(today)}\n"
                        f"⚙️ Панель: CPU {m['cpu']}% · RAM {m['ram_pct']}% · диск {m['disk_pct']}%")
        elif cmd == "clients":
            items = sorted(await _clients(), key=lambda c: c["name"].lower())
            if not items:
                await reply("Клиентов пока нет")
                return
            lines = [f"{'🟢' if _online(c) else ('⚪' if c['enabled'] else '⛔')} "
                     f"<code>{telegram.escape(c['name'])}</code> · {c['ipv4']} · #{c['uid']}" for c in items[:80]]
            await reply("👥 <b>Клиенты</b>\n\n" + "\n".join(lines) + ("\n…" if len(items) > 80 else ""))
        elif cmd in ("client", "conf", "link", "enable", "disable"):
            if not arg:
                await reply(f"Укажите имя: /{cmd} имя")
                return
            c, err = _find(await _clients(), arg)
            if err:
                await reply(err)
                return
            if cmd == "client":
                q = quotas.get_all(db.get_setting("timezone", "Europe/Moscow")).get(str(c["panel_id"]))
                exp = c.get("expiresAt")
                await reply(f"👤 <b>{telegram.escape(c['name'])}</b> · <code>#{c['uid']}</code>\n"
                            f"🌐 <code>{c['ipv4']}</code>\n"
                            f"{'🟢 онлайн' if _online(c) else ('⚪ включён' if c['enabled'] else '⛔ отключён')}\n"
                            f"📊 всего {_gb(c['transferRx'] + c['transferTx'])}"
                            + (f"\n📦 квота {_gb(q['used_bytes'])} из {_gb(q['limit_bytes'])}" if q else "")
                            + (f"\n⏳ до {exp[:10]}" if exp else ""))
            elif cmd == "conf":
                await notify.client_config(c["panel_id"], chat)
                audit.log(None, "telegram", "client_config_sent", str(c["panel_id"]), name=c["name"])
            elif cmd == "link":
                if not userpage.settings()["enabled"]:
                    await reply("Страница пользователя выключена в настройках панели")
                    return
                token = userpage.issue(c["panel_id"])
                audit.log(None, "telegram", "user_link_sent", str(c["panel_id"]), name=c["name"])
                own_cert = os.environ.get("PANEL_PUBLIC_URL")   # задан — панель за прокси со своим сертификатом
                await reply(f"🔗 <b>{telegram.escape(c['name'])}</b>\n"
                            f"{telegram.escape(config.PUBLIC_URL)}/u/{token}"
                            + ("" if own_cert else
                               "\n\nСертификат панели самоподписанный — браузер попросит подтвердить переход."))
            else:
                clients.update(c["panel_id"], enabled=cmd == "enable")
                await clients.sync_all()
                audit.log(None, "telegram", f"client_{cmd}d", str(c["panel_id"]), name=c["name"])
                await reply(f"{'▶️ Включён' if cmd == 'enable' else '⏸ Отключён'}: "
                            f"<code>{telegram.escape(c['name'])}</code>")
        elif cmd == "add":
            parts = arg.split()
            if not parts:
                await reply("Укажите имя: /add имя [дней]")
                return
            days = int(parts[-1]) if len(parts) > 1 and parts[-1].isdigit() else None
            name = " ".join(parts[:-1] if days else parts)[:64]
            exp = ((datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                   if days else None)
            pid = clients.create(name, None, exp)
            down = await clients.sync_all()
            c = clients.get(pid)
            audit.log(None, "telegram", "client_created", str(pid), name=name, ip=c["ipv4"], days=days)
            await reply(f"➕ Создан <code>{telegram.escape(name)}</code> · {c['ipv4']}"
                        + (f" · на {days} дн." if days else "")
                        + (f"\n⚠️ Недоступны ноды: {telegram.escape(', '.join(down))} — профили создадутся позже"
                           if down else ""))
            await notify.client_config(pid, chat)
        elif cmd == "backup":
            await reply("🗄 Создаю бэкап…")
            res = await backup.run(send_telegram=True)
            audit.log(None, "telegram", "backup_run", res.get("file"), ok=res["ok"])
            if not res["ok"]:
                await reply(f"❌ {telegram.escape(res['error'])}")
        else:
            await reply("Неизвестная команда. /help — список команд")
    except (nodes.NodeError, ValueError) as e:  # ValueError: маршрутизация, GeoIP
        await reply(f"🚨 {telegram.escape(e)}")


async def run():
    offset = db.get_setting("tg_bot_offset", 0)
    commands_for = None
    while True:
        s = telegram.settings()
        if not (s["bot"] and s["token"] and s["chat_id"]):
            commands_for = None
            await asyncio.sleep(15)
            continue
        if commands_for != s["token"]:
            await telegram.api("setMyCommands", commands=[{"command": c, "description": d} for c, d in COMMANDS])
            commands_for = s["token"]
        updates = await telegram.api("getUpdates", http_timeout=40, timeout=25, offset=offset,
                                     allowed_updates=["message"])
        if updates is None:
            await asyncio.sleep(10)
            continue
        for u in updates:
            offset = u["update_id"] + 1
            db.set_setting("tg_bot_offset", offset)
            msg = u.get("message") or {}
            text = (msg.get("text") or "").strip()
            chat = str((msg.get("chat") or {}).get("id", ""))
            if not text.startswith("/"):
                continue
            if chat != str(s["chat_id"]).strip():
                log.warning("бот: команда из чужого чата %s отклонена", chat)
                continue
            try:
                await handle(text, chat)
            except Exception:
                log.exception("бот: ошибка команды %s", text[:40])
