"""Квоты трафика: объём (rx+tx) за календарный месяц в часовом поясе панели.

80 % — предупреждение, 100 % — клиент отключается. В новом месяце клиент, отключённый
именно квотой, включается обратно; вручную выключенных клиентов квота не трогает.
"""
import time
import zoneinfo
from datetime import datetime

from . import audit, clients, db, telegram

WARN_RATIO = 0.8


def month(tz: str, ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts or time.time(), zoneinfo.ZoneInfo(tz)).strftime("%Y-%m")


def used(client_id: int, month_key: str) -> int:
    row = db.one("SELECT COALESCE(SUM(rx + tx), 0) AS b FROM traffic_daily WHERE client_id=? AND day LIKE ?",
                 (client_id, month_key + "-%"))
    return int(row["b"])


def get_all(tz: str) -> dict:
    m = month(tz)
    return {str(q["client_id"]): {"limit_bytes": q["limit_bytes"], "used_bytes": used(q["client_id"], m),
                                  "blocked": q["blocked"] == m}
            for q in db.query("SELECT * FROM quotas")}


def set_quota(client_id: int, limit_bytes: int | None):
    if not limit_bytes:
        db.execute("DELETE FROM quotas WHERE client_id=?", (client_id,))
        return
    db.execute("INSERT INTO quotas(client_id, limit_bytes) VALUES(?, ?) "
               "ON CONFLICT(client_id) DO UPDATE SET limit_bytes=excluded.limit_bytes, warned=NULL",
               (client_id, int(limit_bytes)))


def _gb(b: int) -> str:
    return f"{b / 1024**3:.2f} ГБ"


async def check(tz: str):
    m = month(tz)
    changed = False
    for q in db.query("SELECT q.*, c.name FROM quotas q JOIN clients c ON c.id=q.client_id WHERE c.deleted=0"):
        cid, limit = q["client_id"], q["limit_bytes"]
        name = telegram.escape(q["name"] or cid)

        # Новый месяц: вернуть доступ клиенту, отключённому квотой
        if q["blocked"] and q["blocked"] != m:
            clients.update(cid, enabled=True)
            db.execute("UPDATE quotas SET blocked=NULL, warned=NULL WHERE client_id=?", (cid,))
            changed = True
            audit.log(None, "system", "quota_reset", str(cid), name=q["name"])
            await telegram.send(f"🔄 <b>Квота обновлена</b>\n\n👤 <code>{name}</code> снова подключён.",
                                event="on_toggle")
            continue

        u = used(cid, m)
        if u >= limit and q["blocked"] != m:
            clients.update(cid, enabled=False)
            db.execute("UPDATE quotas SET blocked=? WHERE client_id=?", (m, cid))
            changed = True
            audit.log(None, "system", "quota_exceeded", str(cid), name=q["name"], used=u, limit=limit)
            await telegram.send(f"⛔ <b>Квота трафика исчерпана</b>\n\n👤 <code>{name}</code>\n"
                                f"📊 {_gb(u)} из {_gb(limit)} за месяц (все ноды)\n"
                                "Клиент отключён до начала следующего месяца.", event="on_toggle")
        elif u >= limit * WARN_RATIO and q["warned"] != m and q["blocked"] != m:
            db.execute("UPDATE quotas SET warned=? WHERE client_id=?", (m, cid))
            await telegram.send(f"⚠️ <b>Квота трафика: {int(u * 100 / limit)} %</b>\n\n👤 <code>{name}</code>\n"
                                f"📊 {_gb(u)} из {_gb(limit)} за месяц", event="on_toggle")
    if changed:
        await clients.sync_all()   # недоступные ноды получат состояние при следующей синхронизации
