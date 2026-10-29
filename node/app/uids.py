"""Скрытые ID клиентов панели для профилей wg-easy на этой ноде: {id в wg-easy: uid}.

wg-easy не хранит произвольных полей, поэтому связь хранит агент. По ней панель находит
профиль своего клиента даже при одинаковых именах, после восстановления бэкапа или
повторного добавления ноды. В конфиг пользователя uid не попадает.
"""
import json
import re
import threading

from . import config

UID_RE = re.compile(r"[a-f0-9]{8,32}")
_lock = threading.Lock()


def _file():
    return config.DATA_DIR / "uids.json"


def load() -> dict[int, str]:
    try:
        return {int(k): v for k, v in json.loads(_file().read_text()).items()}
    except (OSError, ValueError):
        return {}


def _save(data: dict[int, str]):
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _file().with_suffix(".tmp")
    tmp.write_text(json.dumps({str(k): v for k, v in sorted(data.items())}))
    tmp.replace(_file())


def set_uid(cid: int, uid: str | None):
    with _lock:
        data = load()
        if uid:
            if not UID_RE.fullmatch(uid):
                raise ValueError("неверный uid")
            data[cid] = uid
        else:
            data.pop(cid, None)
        _save(data)


def prune(existing: set[int]):
    """Убрать связи клиентов, которых в wg-easy больше нет."""
    with _lock:
        data = load()
        keep = {k: v for k, v in data.items() if k in existing}
        if keep != data:
            _save(keep)
