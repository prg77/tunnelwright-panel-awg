"""Однократный импорт данных установки amnezia-wg (каталог dashboard и wg0.json).

Старый форк wg-easy давал клиентам UUID, новые клиенты — целые id. Сопоставление идёт
по публичному ключу: он переживает перенос wg-easy без изменений.
"""
import json
import logging

from . import clients, config, db, nodes, telegram, users
from . import limits as lim

log = logging.getLogger("panel.legacy")


def _read(name, default):
    try:
        return json.loads((config.LEGACY_DIR / name).read_text())
    except (OSError, ValueError):
        return default


def pending() -> bool:
    return not db.get_setting("legacy_imported", False) and (config.LEGACY_DIR / "wg0.json").exists()


async def run():
    node = nodes.local()
    await clients.reconcile(node)
    by_key = {p["public_key"]: p["client_id"]
              for p in db.query("SELECT public_key, client_id FROM profiles WHERE node_id=?", (node.id,))}
    old = _read("wg0.json", {}).get("clients", {})
    uuid_to_pid = {}
    for uuid, oc in old.items():
        pid = by_key.get(oc.get("publicKey"))
        if pid:
            uuid_to_pid[uuid] = pid

    meta = _read("meta.json", {})
    n_meta = 0
    for uuid, m in meta.items():
        pid = uuid_to_pid.get(uuid)
        cfg = clients.get(pid) if pid else None
        if cfg and isinstance(m, dict):
            users.set_meta(cfg["user_id"], m)
            if m.get("expiresAt"):
                users.update(cfg["user_id"], expires_at=m["expiresAt"])
            n_meta += 1

    usage =_read("client-usage.json", {})
    n_days = 0
    for uuid, rec in usage.items():
        pid = uuid_to_pid.get(uuid)
        if not pid:
            continue
        for day, v in (rec.get("daily") or {}).items():
            db.execute("INSERT INTO traffic_daily(client_id, day, rx, tx) VALUES(?,?,?,?) "
                       "ON CONFLICT(client_id, day) DO UPDATE SET rx=max(rx, excluded.rx), tx=max(tx, excluded.tx)",
                       (pid, day, int(v.get("rx", 0)), int(v.get("tx", 0))))
            n_days += 1

    points = {}
    for p in _read("traffic-history.json", []):
        try:
            points[int(p["ts"]) // 1000 // 60 * 60] = (int(p["rx"]), int(p["tx"]))
        except (KeyError, TypeError, ValueError):
            continue
    for ts, (rx, tx) in points.items():
        db.execute("INSERT OR IGNORE INTO traffic_points(ts, rx, tx) VALUES(?,?,?)", (ts, rx, tx))

    cfg = _read("config.json", {})
    if cfg.get("portal_name"):
        db.set_setting("portal_name", str(cfg["portal_name"])[:32])
    if cfg.get("tg_token") or cfg.get("tg_chat_id"):
        telegram.save(bool(cfg.get("tg_enabled")), str(cfg.get("tg_token", "")),
                      str(cfg.get("tg_chat_id", "")), cfg.get("tg_events"))

    limits = _read("limits.json", {})
    if limits:
        lim.save(limits)
        await lim.push(node)
    await clients.reconcile(node)   # срок и прочее — на ноду

    db.set_setting("legacy_imported", True)
    log.info("импорт amnezia-wg: клиентов %s/%s, метаданных %s, дней трафика %s, точек графика %s, лимитов %s",
             len(uuid_to_pid), len(old), n_meta, n_days, len(points), len(limits))
