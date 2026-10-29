"""Лимиты скорости {IP: {down, up}} в Мбит/с — хранятся в панели, одинаковые на всех нодах.

IP клиента один на всех нодах, поэтому каждая нода получает весь набор лимитов. Синхронизация
ноды досылает лимиты, если на ноде они другие (новая нода, нода была недоступна).
"""
import logging

from . import db, nodes

log = logging.getLogger("panel.limits")

SETTING = "limits"


def get() -> dict:
    return db.get_setting(SETTING, {}) or {}


def initialized() -> bool:
    return db.get_setting(SETTING) is not None


def save(value: dict):
    db.set_setting(SETTING, value)


def set_for(ip: str, lim: dict | None):
    """Лимит одного IP: {down, up} в Мбит/с или None — снять."""
    cur = get()
    if lim:
        cur[ip] = {"down": float(lim["down"]), "up": float(lim["up"])}
    else:
        cur.pop(ip, None)
    save(cur)


async def push_all() -> list[str]:
    """Выровнять лимиты на всех нодах сейчас. Ошибки — в ответ; недоступные ноды догонит синхронизация."""
    errors = []
    for node in nodes.all_nodes():
        try:
            res = await push(node)
        except nodes.NodeError as e:
            errors.append(str(e))
            continue
        if res:
            errors += res["errors"]
    return errors


async def push(node: nodes.Node) -> dict | None:
    """Выровнять лимиты на ноде. Если в панели лимитов ещё нет — взять их с ноды."""
    current = await node.json("GET", "/limits")
    if not initialized():
        save(current)
        log.info("лимиты взяты с ноды %s: %s", node.name, len(current))
        return None
    wanted = get()
    if current == wanted:
        return None
    return await node.json("PUT", "/limits", json=wanted)
