"""Учёт трафика на сервере: суточные суммы по клиентам и точки общего графика."""
import time
import zoneinfo
from datetime import datetime

from . import clients, db

POINTS_KEEP_SEC = 31 * 86400


def _day(ts: float, tz: str) -> str:
    return datetime.fromtimestamp(ts, zoneinfo.ZoneInfo(tz)).strftime("%Y-%m-%d")


def day_key(tz: str) -> str:
    """Сегодняшняя дата в часовом поясе панели."""
    return _day(time.time(), tz)


def _delta(cur: int, last: int | None) -> int:
    if last is None:
        return 0          # первый замер — точка отсчёта
    return cur - last if cur >= last else cur   # счётчик сбросился (рестарт интерфейса)


async def collect(tz: str):
    now = time.time()
    day = _day(now, tz)
    sum_rx = sum_tx = 0
    rows, _ = await clients.reconcile_all()
    for p in rows:
        pid, cid, rx, tx = p["profile_id"], p["client_id"], p["transferRx"], p["transferTx"]
        last = db.one("SELECT rx, tx FROM traffic_last WHERE profile_id=?", (pid,))
        drx = _delta(rx, last["rx"] if last else None)
        dtx = _delta(tx, last["tx"] if last else None)
        db.execute("INSERT INTO traffic_last(profile_id, rx, tx, ts) VALUES(?,?,?,?) "
                   "ON CONFLICT(profile_id) DO UPDATE SET rx=excluded.rx, tx=excluded.tx, ts=excluded.ts",
                   (pid, rx, tx, int(now)))
        if drx or dtx:
            db.execute("INSERT INTO traffic_daily(client_id, day, rx, tx) VALUES(?,?,?,?) "
                       "ON CONFLICT(client_id, day) DO UPDATE SET rx=rx+excluded.rx, tx=tx+excluded.tx",
                       (cid, day, drx, dtx))
        sum_rx += drx
        sum_tx += dtx
    # Общий график: монотонные счётчики (предыдущая точка + приращение)
    prev = db.one("SELECT rx, tx FROM traffic_points ORDER BY ts DESC LIMIT 1") or {"rx": 0, "tx": 0}
    minute = int(now) // 60 * 60
    db.execute("INSERT INTO traffic_points(ts, rx, tx) VALUES(?,?,?) "
               "ON CONFLICT(ts) DO UPDATE SET rx=excluded.rx, tx=excluded.tx",
               (minute, prev["rx"] + sum_rx, prev["tx"] + sum_tx))
    db.execute("DELETE FROM traffic_points WHERE ts < ?", (int(now) - POINTS_KEEP_SEC,))


def usage() -> dict:
    """Суточный трафик клиентов: {id: {name, prev, daily: {день: {tx, rx}}}}."""
    out = {}
    for r in db.query("SELECT t.client_id, t.day, t.rx, t.tx, c.name FROM traffic_daily t "
                      "LEFT JOIN clients c ON c.id=t.client_id ORDER BY t.day"):
        rec = out.setdefault(str(r["client_id"]), {"name": r["name"] or "", "prev": None, "daily": {}})
        rec["daily"][r["day"]] = {"tx": r["tx"], "rx": r["rx"]}
    return out


def points() -> list[dict]:
    """Точки графика: [{ts: мс, tx, rx}]."""
    return [{"ts": r["ts"] * 1000, "tx": r["tx"], "rx": r["rx"]}
            for r in db.query("SELECT ts, rx, tx FROM traffic_points ORDER BY ts")]


def reset():
    db.execute("DELETE FROM traffic_daily")
    db.execute("DELETE FROM traffic_points")
