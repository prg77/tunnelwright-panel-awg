"""Автообновление агента: запрос от панели → файлы в UPDATE_DIR → systemd-юнит на хосте.

Агент только записывает запрос (версию и, если передан, архив исходников для сборки, когда
образ GHCR недоступен). Скачивание образа и перезапуск агента делает update.sh на хосте —
агенту не нужен доступ к Docker.
"""
import json
import os
import re

from . import config

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
MAX_BUNDLE = 20 * 1024 * 1024


class UpdateError(ValueError):
    pass


def available() -> bool:
    return config.UPDATE_DIR.is_dir()


def status() -> dict | None:
    """Итог последнего обновления: {version, ok, message, ts} — пишет update.sh."""
    try:
        return json.loads((config.UPDATE_DIR / "status").read_text())
    except (OSError, ValueError):
        return None


def _write(name: str, data: bytes):
    tmp = config.UPDATE_DIR / f".{name}.tmp"
    tmp.write_bytes(data)
    os.replace(tmp, config.UPDATE_DIR / name)


def request(version: str, bundle: bytes):
    if not SEMVER.match(version or ""):
        raise UpdateError("неверная версия")
    if not available():
        raise UpdateError("на ноде нет автообновления — обновите её один раз по SSH")
    if len(bundle) > MAX_BUNDLE:
        raise UpdateError("архив исходников слишком большой")
    if bundle:
        _write("bundle.tgz", bundle)
    _write("request", version.encode())     # последним: появление файла запускает обновление
