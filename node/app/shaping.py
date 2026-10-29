"""Лимиты скорости через tc (HTB на egress, police на ingress) на интерфейсе wg-easy.

Агент работает в сетевом namespace wg-easy, поэтому tc вызывается напрямую.
Порт логики прежнего amnezia-ratelimit-apply.py: класс на каждый IP клиента.
"""
import ipaddress
import json
import logging
import subprocess

from . import config

log = logging.getLogger("node.shaping")


def load_limits() -> dict:
    try:
        data = json.loads(config.LIMITS_FILE.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_limits(limits: dict):
    config.LIMITS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = config.LIMITS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(limits, indent=2))
    tmp.replace(config.LIMITS_FILE)


def validate(limits: dict) -> dict:
    """Только IPv4-ключи и положительные числа — остальное отбрасывается."""
    clean = {}
    for ip, cfg in limits.items():
        try:
            ipaddress.IPv4Address(ip)
            down, up = float(cfg["down"]), float(cfg["up"])
        except (ValueError, KeyError, TypeError):
            continue
        if down > 0 and up > 0:
            clean[ip] = {"down": down, "up": up}
    return clean


def _tc(*args, check=True):
    r = subprocess.run(["tc", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"tc {' '.join(args)}: {r.stderr.strip()}")
    return r


def _rate(mbit: float) -> str:
    return f"{max(1, int(mbit * 1000))}kbit"


def apply(limits: dict) -> dict:
    """Пересоздаёт правила. Возвращает {applied, errors}."""
    dev = config.WG_INTERFACE
    if subprocess.run(["ip", "link", "show", dev], capture_output=True).returncode != 0:
        return {"applied": 0, "errors": [f"интерфейс {dev} не найден"]}
    _tc("qdisc", "del", "dev", dev, "root", check=False)
    _tc("qdisc", "del", "dev", dev, "ingress", check=False)
    if not limits:
        return {"applied": 0, "errors": []}

    _tc("qdisc", "add", "dev", dev, "root", "handle", "1:", "htb", "default", "ffff", "r2q", "100")
    _tc("class", "add", "dev", dev, "parent", "1:", "classid", "1:ffff", "htb", "rate", "10gbit")
    _tc("qdisc", "add", "dev", dev, "handle", "ffff:", "ingress")

    applied, errors = 0, []
    for idx, (ip, cfg) in enumerate(sorted(limits.items()), start=1):
        cid = f"1:{idx:x}"
        try:
            down, up = _rate(cfg["down"]), _rate(cfg["up"])
            # egress: сервер → клиент (download клиента)
            _tc("class", "add", "dev", dev, "parent", "1:", "classid", cid,
                "htb", "rate", down, "ceil", down, "burst", "64k")
            _tc("filter", "add", "dev", dev, "parent", "1:", "protocol", "ip",
                "u32", "match", "ip", "dst", f"{ip}/32", "flowid", cid)
            # ingress: клиент → сервер (upload клиента)
            _tc("filter", "add", "dev", dev, "parent", "ffff:", "protocol", "ip",
                "u32", "match", "ip", "src", f"{ip}/32",
                "police", "rate", up, "burst", "128k", "drop", "flowid", ":1")
            applied += 1
        except RuntimeError as e:
            errors.append(f"{ip}: {e}")
    if errors:
        log.warning("лимиты применены с ошибками: %s", errors)
    return {"applied": applied, "errors": errors}
