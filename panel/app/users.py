"""Пользователи панели — люди, которым выдан доступ к VPN.

У пользователя имя, группа, заметка, срок доступа, квота трафика и личная ссылка; включение
пользователя включает и отключает все его конфиги сразу. Конфиги (устройства) — в clients.py:
у каждого свой IP, ключи и профили на нодах.
"""
import json
import secrets

from . import db

NO_GROUP = "Без группы"

_SELECT = "SELECT u.*, g.name AS group_name FROM users u LEFT JOIN groups g ON g.id = u.group_id"


class UserError(ValueError):
    pass


def meta(row) -> dict:
    """Метаданные: заметка и прочее из JSON, группа и срок — из своих колонок."""
    try:
        m = json.loads(row["meta"] or "{}")
    except ValueError:
        m = {}
    if row.get("group_name"):
        m["group"] = row["group_name"]
    if row.get("expires_at"):
        m["expiresAt"] = row["expires_at"]
    return m


def get(user_id: int) -> dict | None:
    return db.one(f"{_SELECT} WHERE u.id=?", (user_id,))


def all_users() -> list[dict]:
    return db.query(f"{_SELECT} ORDER BY u.id")


def by_uid(uid: str | None) -> dict | None:
    return db.one("SELECT * FROM users WHERE uid=?", (uid,)) if uid else None


def configs(user_id: int) -> list[dict]:
    """Конфиги пользователя (без удаляемых) в порядке создания."""
    return db.query("SELECT * FROM clients WHERE user_id=? AND deleted=0 ORDER BY id", (user_id,))


def group_id(name) -> int | None:
    """Группа по имени; неизвестное имя создаёт группу (импорт amnezia-wg)."""
    name = str(name or "").strip()[:32]
    if not name or name == NO_GROUP:
        return None
    row = db.one("SELECT id FROM groups WHERE name=?", (name,))
    if row:
        return row["id"]
    return db.execute("INSERT INTO groups(name, sort) VALUES(?, 100)", (name,))


def new_uid() -> str:
    """Скрытый ID пользователя: 8 hex-символов. Имена могут повторяться — ID нет."""
    while True:
        uid = secrets.token_hex(4)
        if not db.one("SELECT 1 FROM users WHERE uid=?", (uid,)):
            return uid


def create(name: str, expires_at: str | None = None, enabled: bool = True, uid: str | None = None) -> int:
    name = str(name or "").strip()[:64]
    if not name:
        raise UserError("имя не задано")
    if not uid or by_uid(uid):
        uid = new_uid()
    return db.execute("INSERT INTO users(uid, name, enabled, expires_at) VALUES(?,?,?,?)",
                      (uid, name, int(bool(enabled)), expires_at))


def update(user_id: int, **fields):
    """name / enabled / expires_at; на ноды уходит через clients.sync_all."""
    allowed = {k: v for k, v in fields.items() if k in ("name", "enabled", "expires_at")}
    if "name" in allowed:
        allowed["name"] = str(allowed["name"] or "").strip()[:64]
        if not allowed["name"]:
            raise UserError("имя не задано")
    if "enabled" in allowed:
        allowed["enabled"] = int(bool(allowed["enabled"]))
    if allowed:
        db.execute(f"UPDATE users SET {', '.join(k + '=?' for k in allowed)} WHERE id=?", (*allowed.values(), user_id))


def set_meta(user_id: int, m: dict):
    """Группа и срок хранятся отдельными колонками, остальное — JSON."""
    m = dict(m)
    gid = group_id(m.pop("group", None))
    m.pop("expiresAt", None)
    db.execute("UPDATE users SET meta=?, group_id=? WHERE id=?", (json.dumps(m, ensure_ascii=False), gid, user_id))


def delete(user_id: int):
    """Пользователь удаляется сразу, его конфиги — помечаются: профили на нодах дочистит синхронизация."""
    db.execute("UPDATE clients SET deleted=1 WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM users WHERE id=?", (user_id,))


def merge(into: int, others: list[int]):
    """Перенести конфиги других пользователей в этого; сами пользователи (их ссылки, квоты) удаляются.
    Перенесённые конфиги без названия получают имя своего прежнего пользователя — чтобы устройства различались."""
    others = [o for o in dict.fromkeys(others) if o != into]
    for uid_ in others:
        db.execute("UPDATE clients SET name=(SELECT name FROM users WHERE id=?) "
                   "WHERE user_id=? AND (name IS NULL OR name='')", (uid_, uid_))
    for uid_ in others:
        db.execute("UPDATE clients SET user_id=? WHERE user_id=?", (into, uid_))
        db.execute("DELETE FROM users WHERE id=?", (uid_,))
