"""Журнал действий администраторов."""
import json
import time

from fastapi import Request

from . import db
from .security import client_ip


def log(request: Request | None, admin: dict | str | None, action: str,
        target: str | None = None, **details):
    name = admin["username"] if isinstance(admin, dict) else admin
    db.execute("INSERT INTO audit_log(ts, admin, action, target, details, ip) VALUES(?,?,?,?,?,?)",
               (int(time.time()), name, action, target,
                json.dumps(details, ensure_ascii=False) if details else None,
                client_ip(request) if request else None))


def recent(limit=200, before_id=None):
    if before_id:
        rows = db.query("SELECT * FROM audit_log WHERE id<? ORDER BY id DESC LIMIT ?", (before_id, limit))
    else:
        rows = db.query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
    for r in rows:
        r["details"] = json.loads(r["details"]) if r["details"] else None
    return rows
