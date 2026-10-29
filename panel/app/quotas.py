"""Квоты трафика пользователей: объём (rx+tx) всех конфигов за календарный месяц в часовом поясе панели.

80 % — предупреждение, 100 % — пользователь отключается. В новом месяце пользователь, отключённый
именно квотой, включается обратно; вручную выключенных пользователей квота не трогает.
"""
import time
import zoneinfo
from datetime import datetime

from . import audit, clients, db, telegram, users

WARN_RATIO = 0.8


def month(tz: str, ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts or time.time(), zoneinfo.ZoneInfo(tz)).strftime("%Y-%m")


def used(user_id: int, month_key: str) -> int:
    """Трафик всех конфигов пользователя за месяц (и удаляемых — пока их статистика в панели)."""
    row = db.one("SELECT COALESCE(SUM(t.rx + t.tx), 0) AS b FROM traffic_daily t JOIN clients c ON c.id=t.client_id "
                 "WHERE c.user_id=? AND t.day LIKE ?", (user_id, month_key + "-%"))
    return int(row["b"])


def get_all(tz: str) -> dict:
    m = month(tz)
    return {str(q["user_id"]): {"limit_bytes": q["limit_bytes"], "used_bytes": used(q["user_id"], m),
                                "blocked": q["blocked"] == m}
            for q in db.query("SELECT * FROM quotas")}


def set_quota(user_id: int, limit_bytes: int | None):
    if not limit_bytes:
        db.execute("DELETE FROM quotas WHERE user_id=?", (user_id,))
        return
    db.execute("INSERT INTO quotas(user_id, limit_bytes) VALUES(?, ?) "
               "ON CONFLICT(user_id) DO UPDATE SET limit_bytes=excluded.limit_bytes, warned=NULL",
               (user_id, int(limit_bytes)))


def _gb(b: int) -> str:
    return f"{b / 1024**3:.2f} ГБ"


async def check(tz: str):
    m = month(tz)
    changed = False
    for q in db.query("SELECT q.*, u.name FROM quotas q JOIN users u ON u.id=q.user_id"):
        uid, limit = q["user_id"], q["limit_bytes"]
        name = telegram.escape(q["name"] or uid)

        # Новый месяц: вернуть доступ пользователю, отключённому квотой
        if q["blocked"] and q["blocked"] != m:
            users.update(uid, enabled=True)
            db.execute("UPDATE quotas SET blocked=NULL, warned=NULL WHERE user_id=?", (uid,))
            changed = True
            audit.log(None, "system", "quota_reset", str(uid), name=q["name"])
            await telegram.send(f"🔄 <b>Квота обновлена</b>\n\n👤 <code>{name}</code> снова подключён.",
                                event="on_toggle")
            continue

        u = used(uid, m)
        if u >= limit and q["blocked"] != m:
            users.update(uid, enabled=False)
            db.execute("UPDATE quotas SET blocked=? WHERE user_id=?", (m, uid))
            changed = True
            audit.log(None, "system", "quota_exceeded", str(uid), name=q["name"], used=u, limit=limit)
            await telegram.send(f"⛔ <b>Квота трафика исчерпана</b>\n\n👤 <code>{name}</code>\n"
                                f"📊 {_gb(u)} из {_gb(limit)} за месяц (все устройства и ноды)\n"
                                "Пользователь отключён до начала следующего месяца.", event="on_toggle")
        elif u >= limit * WARN_RATIO and q["warned"] != m and q["blocked"] != m:
            db.execute("UPDATE quotas SET warned=? WHERE user_id=?", (m, uid))
            await telegram.send(f"⚠️ <b>Квота трафика: {int(u * 100 / limit)} %</b>\n\n👤 <code>{name}</code>\n"
                                f"📊 {_gb(u)} из {_gb(limit)} за месяц", event="on_toggle")
    if changed:
        await clients.sync_all()   # недоступные ноды получат состояние при следующей синхронизации
