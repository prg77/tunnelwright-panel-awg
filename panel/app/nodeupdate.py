"""Автообновление агентов удалённых нод до версии панели.

При проверке нод (раз в 2 минуты и сразу после старта панели) нода, чей агент отстаёт от панели,
получает запрос обновления: версию и архив исходников агента (на случай, если образ из GHCR
недоступен и его надо собрать). Сам агент записывает запрос, а обновляет его systemd-юнит на
хосте ноды — по SSH ничего не нужно. Если юнита на ноде нет (автообновление не настроено),
ноду нужно один раз обновить по SSH, дальше — автоматически.
"""
import logging
import re
import time

from . import audit, config, nodeinstall, nodes

log = logging.getLogger("panel.nodeupdate")

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
RETRY_SEC = 30 * 60        # повтор, если нода так и не обновилась (сборка упала, нода перезагружалась)

_requested: dict[int, tuple[str, float]] = {}   # node_id → (версия, когда запрошена)


def target() -> str | None:
    """Версия, до которой обновлять агентов; None — сборка панели без номера версии (dev)."""
    return config.APP_VERSION if SEMVER.match(config.APP_VERSION) else None


def state(node: nodes.Node, h: dict) -> dict:
    """Для карточки ноды: можно ли обновлять автоматически и чем кончилась последняя попытка."""
    want = target()
    return {"auto": bool(h.get("auto_update")), "target": want,
            "current": bool(want and h.get("version") == want),
            "pending": node.id in _requested, "last": h.get("update_status")}


async def check(node: nodes.Node, h: dict):
    want = target()
    if node.is_local or not want or not h.get("ok"):
        return
    if h.get("version") == want:
        if _requested.pop(node.id, None):
            audit.log(None, "system", "node_updated", node.name, version=want, auto=True)
        return
    if not h.get("auto_update"):
        return
    last = _requested.get(node.id)
    if last and last[0] == want and time.time() - last[1] < RETRY_SEC:
        return
    _requested[node.id] = (want, time.time())
    try:
        await node.req("POST", f"/update?version={want}", content=nodeinstall.bundle())
    except nodes.NodeError as e:
        log.warning("автообновление ноды %s не запрошено: %s", node.name, e)
        audit.log(None, "system", "node_update_failed", node.name, version=want, error=str(e))
        return
    log.info("нода %s: запрошено обновление агента %s → %s", node.name, h.get("version"), want)
    audit.log(None, "system", "node_update_started", node.name, version=want, was=h.get("version"), auto=True)
