"""Подсети стран (IPv4) из агрегированных зон ipdeny.com с кэшем на диске."""
import asyncio
import ipaddress
import logging
import re
import time

import httpx

from . import config

log = logging.getLogger("panel.geoip")

URL = "https://www.ipdeny.com/ipblocks/data/aggregated/{cc}-aggregated.zone"
MAX_AGE = 7 * 86400
CC_RE = re.compile(r"[a-z]{2}")

_lock = asyncio.Lock()


def _dir():
    d = config.DATA_DIR / "geoip"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _file(cc: str):
    return _dir() / f"{cc}.zone"


def valid(cc: str) -> bool:
    return bool(CC_RE.fullmatch(cc))


def _parse(text: str) -> list[ipaddress.IPv4Network]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            net = ipaddress.ip_network(line, strict=False)
        except ValueError:
            continue
        if net.version == 4:
            out.append(net)
    return out


async def _download(cc: str) -> str:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        r = await c.get(URL.format(cc=cc))
    if r.status_code == 404:
        raise ValueError(f"страна {cc.upper()} не найдена в базе GeoIP")
    r.raise_for_status()
    if not _parse(r.text):
        raise ValueError(f"пустой ответ GeoIP для {cc.upper()}")
    return r.text


async def networks(cc: str, refresh: bool = False) -> list[ipaddress.IPv4Network]:
    """Подсети страны. Кэш обновляется раз в неделю; без сети используется старый кэш."""
    cc = cc.lower()
    if not valid(cc):
        raise ValueError(f"неверный код страны: {cc}")
    f = _file(cc)
    fresh = f.exists() and time.time() - f.stat().st_mtime < MAX_AGE
    if not fresh or refresh:
        async with _lock:
            try:
                text = await _download(cc)
                tmp = f.with_suffix(".tmp")
                tmp.write_text(text)
                tmp.replace(f)
            except ValueError:
                raise
            except Exception as e:  # сеть, TLS, 5xx
                if not f.exists():
                    raise ValueError(f"GeoIP {cc.upper()} недоступен: {e}") from e
                log.warning("GeoIP %s: обновить не удалось (%s), используется кэш", cc, e)
    return _parse(f.read_text())


def status() -> dict:
    """{cc: {count, updated}} по кэшу."""
    out = {}
    for f in sorted(_dir().glob("*.zone")):
        out[f.stem] = {"count": len(_parse(f.read_text())), "updated": int(f.stat().st_mtime)}
    return out


async def refresh_stale(codes) -> int:
    """Обновить устаревшие зоны используемых стран (фоновая задача)."""
    n = 0
    for cc in sorted(set(codes)):
        f = _file(cc)
        if f.exists() and time.time() - f.stat().st_mtime < MAX_AGE:
            continue
        try:
            await networks(cc)
            n += 1
        except ValueError as e:
            log.warning("%s", e)
    return n
