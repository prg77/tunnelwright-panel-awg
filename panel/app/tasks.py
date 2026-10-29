"""Фоновые задачи panel-api: трафик, сроки пользователей, состояние нод, импорт amnezia-wg."""
import asyncio
import logging
import time
from datetime import datetime, timezone

from . import audit, backup, bot, clients, config, db, geoip, legacy, lists, nodes, nodeupdate, quotas, telegram, traffic, users

log = logging.getLogger("panel.tasks")

TRAFFIC_SEC = 60
EXPIRY_SEC = 300
QUOTA_SEC = 300
HEALTH_SEC = 120
BACKUP_CHECK_SEC = 600
GEOIP_SEC = 6 * 3600

_node_ok: dict[int, bool] = {}


async def _expiry():
    """Срок истёк — пользователь отключается в панели и на всех нодах (wg-easy и сам отключает профили)."""
    now = datetime.now(timezone.utc)
    expired = []
    for u in users.all_users():
        when = clients.parse_ts(u["expires_at"])
        if u["enabled"] and when and when < now:
            users.update(u["id"], enabled=False)
            expired.append(u)
    if not expired:
        return
    await clients.sync_all()
    for u in expired:
        audit.log(None, "system", "user_expired", str(u["id"]), name=u["name"])
        await telegram.send(f"⏳ <b>Срок доступа истёк</b>\n\n👤 <code>{telegram.escape(u['name'] or '')}</code>"
                            "\nПользователь отключён.", event="on_toggle")


async def _health():
    for node in nodes.all_nodes():
        h = await node.health()
        await nodeupdate.check(node, h)
        ok = bool(h.get("ok"))
        prev = _node_ok.get(node.id)
        _node_ok[node.id] = ok
        if prev is None or prev == ok:
            continue
        name = telegram.escape(node.name)
        if ok:
            await telegram.send(f"✅ <b>VPN-нода восстановлена</b>\n\n🖥 {name}", event="on_health_ok")
        else:
            await telegram.send(f"🚨 <b>VPN-нода недоступна</b>\n\n🖥 {name}\n⚠️ "
                                f"{telegram.escape(h.get('error') or 'нет ответа')}", event="on_health_fail")
        audit.log(None, "system", "node_up" if ok else "node_down", node.name)


async def run():
    dropped = nodes.drop_local_if_disabled()
    if dropped:
        log.warning("VPN на сервере панели отключён установщиком — нода «%s» убрана из панели", dropped)
        audit.log(None, "system", "node_removed", dropped, reason="local VPN disabled")
    nodes.ensure_local_node()
    if telegram.active("on_start"):
        await telegram.send(f"🚀 <b>Панель запущена</b>\n\n🖥 <code>{telegram.escape(config.WG_HOST)}</code>"
                            f"\n📊 v{config.APP_VERSION}", event="on_start")
    asyncio.create_task(bot.run())   # Telegram-бот — своя петля long polling
    last = {"traffic": 0.0, "expiry": 0.0, "quota": 0.0, "health": 0.0, "backup": 0.0, "geoip": 0.0}
    while True:
        now = time.time()
        tz = db.get_setting("timezone", "Europe/Moscow")
        try:
            if legacy.pending() and nodes.local_node_id() and (await nodes.local().health()).get("ok"):
                await legacy.run()
            if now - last["traffic"] >= TRAFFIC_SEC:
                last["traffic"] = now
                await traffic.collect(tz)
            if now - last["quota"] >= QUOTA_SEC:
                last["quota"] = now
                await quotas.check(tz)
            if now - last["expiry"] >= EXPIRY_SEC:
                last["expiry"] = now
                await _expiry()
            if now - last["health"] >= HEALTH_SEC:
                last["health"] = now
                await _health()
            if now - last["backup"] >= BACKUP_CHECK_SEC:
                last["backup"] = now
                if backup.due():
                    await backup.run()
            if now - last["geoip"] >= GEOIP_SEC:
                last["geoip"] = now
                await geoip.refresh_stale(lists.used_countries())
        except Exception:
            log.exception("фоновая задача упала")
        await asyncio.sleep(10)
