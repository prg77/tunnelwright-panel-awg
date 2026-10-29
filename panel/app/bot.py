"""Telegram-бот администратора (long polling).

Команды принимаются только из чата, указанного в настройках Telegram (chat_id администратора).
Бот работает поверх тех же функций, что и панель: пользователи и их конфиги, бэкап, журнал.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from . import audit, backup, clients, config, db, hostmetrics, nodes, notify, quotas, telegram, traffic, userpage, users

log = logging.getLogger("panel.bot")

COMMANDS = [
    ("status", "Состояние сервера"),
    ("clients", "Список пользователей"),
    ("client", "Карточка пользователя: /client имя или /client #ID"),
    ("conf", "Конфиги и QR всех устройств: /conf имя"),
    ("link", "Ссылка на страницу пользователя: /link имя"),
    ("add", "Новый пользователь: /add имя [дней]"),
    ("device", "Новое устройство: /device имя [название]"),
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
    """Пользователи с трафиком и handshake всех конфигов по всем доступным нодам."""
    rows, _ = await clients.reconcile_all()
    by_cfg = clients.summary(rows)
    cfgs: dict[int, list[dict]] = {}
    for c in clients.all_clients():
        cfgs.setdefault(c["user_id"], []).append(c)
    out = []
    for u in users.all_users():
        mine = cfgs.get(u["id"], [])
        hs = [by_cfg.get(c["id"], {}).get("latestHandshakeAt") for c in mine if c["enabled"]]
        hs = [h for h in hs if h]
        out.append({"panel_id": u["id"], "uid": u["uid"], "name": u["name"] or "", "enabled": bool(u["enabled"]),
                    "expiresAt": u["expires_at"], "ips": [c["ipv4"] for c in mine],
                    "devices": [(c["name"] or "", c["ipv4"], bool(c["enabled"])) for c in mine],
                    "latestHandshakeAt": max(hs, key=clients.parse_ts) if hs else None,
                    "transferRx": sum(by_cfg.get(c["id"], {}).get("transferRx", 0) for c in mine),
                    "transferTx": sum(by_cfg.get(c["id"], {}).get("transferTx", 0) for c in mine)})
    return out


def _ips(c) -> str:
    return ", ".join(c["ips"]) or "нет конфигов"


def _find(items, query: str):
    """Пользователь по ID (#a1b2…, достаточно начала) или по имени. Одинаковые имена — выбор по ID."""
    q = query.strip().lower()
    if q.startswith("#"):
        found = [c for c in items if len(q) > 3 and (c.get("uid") or "").startswith(q[1:])]
    else:
        found = [c for c in items if c["name"].lower() == q] or \
                [c for c in items if c["name"].lower().startswith(q)]
    if len(found) == 1:
        return found[0], None
    if not found:
        return None, f"Пользователь «{telegram.escape(query)}» не найден"
    return None, ("Найдено несколько — укажите ID:\n" + "\n".join(
        f"<code>#{c.get('uid')}</code> {telegram.escape(c['name'])} · {_ips(c)}" for c in found[:15]))


def _split_user(items, arg: str):
    """«имя пользователя [название устройства]»: самое длинное начало, совпадающее с пользователем."""
    words = arg.split()
    for k in range(len(words), 0, -1):
        head = " ".join(words[:k])
        found = [c for c in items if c["name"].lower() == head.lower()] if not head.startswith("#") else \
            [c for c in items if len(head) > 3 and (c.get("uid") or "").startswith(head[1:].lower())]
        if len(found) == 1:
            return found[0], " ".join(words[k:]), None
    c, err = _find(items, words[0]) if words else (None, "Укажите имя")
    return c, " ".join(words[1:]), err


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
                await reply("Пользователей пока нет")
                return
            lines = [f"{'🟢' if _online(c) else ('⚪' if c['enabled'] else '⛔')} "
                     f"<code>{telegram.escape(c['name'])}</code> · {_ips(c)} · #{c['uid']}" for c in items[:80]]
            await reply("👥 <b>Пользователи</b>\n\n" + "\n".join(lines) + ("\n…" if len(items) > 80 else ""))
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
                devices = "".join(f"\n📱 {telegram.escape(name or 'устройство ' + str(i))} · <code>{ip}</code>"
                                  + ("" if on else " · ⛔") for i, (name, ip, on) in enumerate(c["devices"], 1))
                await reply(f"👤 <b>{telegram.escape(c['name'])}</b> · <code>#{c['uid']}</code>"
                            f"{devices or chr(10) + 'нет конфигов'}\n"
                            f"{'🟢 онлайн' if _online(c) else ('⚪ включён' if c['enabled'] else '⛔ отключён')}\n"
                            f"📊 всего {_gb(c['transferRx'] + c['transferTx'])}"
                            + (f"\n📦 квота {_gb(q['used_bytes'])} из {_gb(q['limit_bytes'])}" if q else "")
                            + (f"\n⏳ до {exp[:10]}" if exp else ""))
            elif cmd == "conf":
                await notify.user_configs(c["panel_id"], chat)
                audit.log(None, "telegram", "client_config_sent", str(c["panel_id"]), name=c["name"])
            elif cmd == "link":
                if not userpage.settings()["enabled"]:
                    await reply("Страница пользователя выключена в настройках панели")
                    return
                token = userpage.issue(c["panel_id"])
                audit.log(None, "telegram", "user_link_sent", str(c["panel_id"]), name=c["name"])
                user_url = userpage.settings()["user_url"]   # отдельный адрес ссылок, если задан
                own_cert = user_url or os.environ.get("PANEL_PUBLIC_URL")   # адрес задан — свой сертификат
                await reply(f"🔗 <b>{telegram.escape(c['name'])}</b>\n"
                            f"{telegram.escape(user_url or config.PUBLIC_URL)}/u/{token}"
                            + ("" if own_cert else
                               "\n\nСертификат панели самоподписанный — браузер попросит подтвердить переход."))
            else:
                users.update(c["panel_id"], enabled=cmd == "enable")
                await clients.sync_all()
                audit.log(None, "telegram", f"user_{cmd}d", str(c["panel_id"]), name=c["name"])
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
            user_id = users.create(name, exp)
            pid = clients.create(user_id)
            down = await clients.sync_all()
            c = clients.get(pid)
            audit.log(None, "telegram", "user_created", str(user_id), name=name, ip=c["ipv4"], days=days)
            await reply(f"➕ Создан <code>{telegram.escape(name)}</code> · {c['ipv4']}"
                        + (f" · на {days} дн." if days else "")
                        + (f"\n⚠️ Недоступны ноды: {telegram.escape(', '.join(down))} — профили создадутся позже"
                           if down else ""))
            await notify.client_config(pid, chat)
        elif cmd == "device":
            if not arg:
                await reply("Укажите имя: /device имя [название устройства]")
                return
            c, device, err = _split_user(await _clients(), arg)
            if err:
                await reply(err)
                return
            pid = clients.create(c["panel_id"], device or None)
            down = await clients.sync_all()
            cfg = clients.get(pid)
            audit.log(None, "telegram", "client_created", clients.label(cfg), ip=cfg["ipv4"], user=str(c["panel_id"]))
            await reply(f"📱 Новое устройство <code>{telegram.escape(clients.label(cfg))}</code> · {cfg['ipv4']}"
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
