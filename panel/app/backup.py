"""Бэкапы: зашифрованный архив (AES-256 ZIP) с данными панели и всех нод, расписание, Telegram.

Состав архива:
    backup-info.json            версия, время, сервер
    panel/panel.db              панель: клиенты, метаданные, трафик, настройки, журнал
    nodes/<id>/wg-easy.db       нода: ключи сервера и клиентов, параметры AmneziaWG
    nodes/<id>/limits.json      лимиты скорости
    nodes/<id>/wg-easy-admin.json  учётка агента к wg-easy (нужна при восстановлении)
    nodes/<id>/uids.json        связь клиентов wg-easy со скрытыми ID панели
Недоступная нода в архив не попадает (backup-info.json: skipped).
Открывается 7-Zip или `tunnelwright restore`.
"""
import io
import json
import logging
import sqlite3
import tempfile
import time
import zipfile
import zoneinfo
from datetime import datetime
from pathlib import Path

import pyzipper

from . import config, db, nodes, telegram

log = logging.getLogger("panel.backup")

KEEP = 5
MIN_PASSWORD = 8
SCHEDULES = {"off": None, "daily": 86400, "weekly": 7 * 86400}
# Имя архива; архивы vpn-panel-backup-… (установка в /opt/vpn-panel) тоже видны и восстанавливаются
PREFIX = "tunnelwright-backup-"
PREFIXES = (PREFIX, "vpn-panel-backup-")


def _dir() -> Path:
    """Каталог архивов; из config при каждом вызове (тесты подменяют DATA_DIR)."""
    return config.DATA_DIR / "backups"


def _archives() -> list[Path]:
    """Архивы бэкапов, новые первыми (по времени: у старых и новых разный префикс имени)."""
    if not _dir().exists():
        return []
    return sorted((p for p in _dir().glob("*.zip") if p.name.startswith(PREFIXES)),
                  key=lambda p: p.stat().st_mtime, reverse=True)


def settings() -> dict:
    s = db.get_setting("backup", {}) or {}
    return {"schedule": s.get("schedule", "off"), "hour": int(s.get("hour", 4)),
            "telegram": bool(s.get("telegram", True)), "password": s.get("password", ""),
            "last_ts": s.get("last_ts"), "last_ok": s.get("last_ok"), "last_error": s.get("last_error")}


def public_settings() -> dict:
    s = settings()
    s["password_set"] = len(s.pop("password")) >= MIN_PASSWORD
    return s


def save_settings(schedule=None, hour=None, telegram_send=None, password=None):
    s = settings()
    if schedule is not None:
        if schedule not in SCHEDULES:
            raise ValueError("неизвестное расписание")
        s["schedule"] = schedule
    if hour is not None:
        if not 0 <= int(hour) <= 23:
            raise ValueError("час должен быть от 0 до 23")
        s["hour"] = int(hour)
    if telegram_send is not None:
        s["telegram"] = bool(telegram_send)
    if password is not None:
        if len(password) < MIN_PASSWORD:
            raise ValueError(f"пароль бэкапа — не короче {MIN_PASSWORD} символов")
        s["password"] = password
    db.set_setting("backup", s)


def _record(ok: bool, error: str | None = None):
    s = settings()
    s.update(last_ts=int(time.time()), last_ok=ok, last_error=error)
    db.set_setting("backup", s)


def _panel_db_copy(path: Path):
    out = sqlite3.connect(path)
    with db.tx() as c, out:
        c.backup(out)
    out.close()


async def create() -> Path:
    """Собрать зашифрованный архив и сохранить в каталог бэкапов. Возвращает путь."""
    s = settings()
    if len(s["password"]) < MIN_PASSWORD:
        raise ValueError("не задан пароль бэкапа")
    _dir().mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(zoneinfo.ZoneInfo(db.get_setting("timezone", "Europe/Moscow"))).strftime("%Y%m%d-%H%M")
    path = _dir() / f"{PREFIX}{stamp}.zip"
    info = {"version": config.APP_VERSION, "created": int(time.time()), "host": config.WG_HOST, "nodes": []}

    with tempfile.TemporaryDirectory() as tmp:
        panel_copy = Path(tmp) / "panel.db"
        _panel_db_copy(panel_copy)
        with pyzipper.AESZipFile(path.with_suffix(".tmp"), "w", compression=pyzipper.ZIP_DEFLATED,
                                 encryption=pyzipper.WZ_AES) as z:
            z.setpassword(s["password"].encode())
            z.write(panel_copy, "panel/panel.db")
            for node in nodes.all_nodes():
                try:
                    raw = (await node.req("GET", "/backup")).content
                except nodes.NodeError as e:   # недоступная нода не мешает бэкапу остальных
                    log.warning("бэкап: нода %s недоступна: %s", node.name, e)
                    info.setdefault("skipped", []).append(node.name)
                    continue
                with zipfile.ZipFile(io.BytesIO(raw)) as nz:
                    for name in nz.namelist():
                        z.writestr(f"nodes/{node.id}/{name}", nz.read(name))
                info["nodes"].append({"id": node.id, "name": node.name, "local": node.is_local,
                                      "host": node.row.get("host")})
            z.writestr("backup-info.json", json.dumps(info, ensure_ascii=False, indent=2))
    path.with_suffix(".tmp").rename(path)
    path.chmod(0o600)
    for old in _archives()[KEEP:]:
        old.unlink()
    return path


async def run(send_telegram: bool | None = None) -> dict:
    """Создать бэкап и (по настройке) отправить администратору в Telegram."""
    s = settings()
    try:
        path = await create()
    except Exception as e:  # noqa: BLE001 — ошибку показываем в интерфейсе и в Telegram
        log.exception("бэкап не создан")
        _record(False, str(e))
        await telegram.send(f"❌ <b>Бэкап не создан</b>\n\n{telegram.escape(e)}")
        return {"ok": False, "error": str(e)}
    sent = False
    want = s["telegram"] if send_telegram is None else send_telegram
    if want and telegram.active():
        size_kb = path.stat().st_size // 1024
        sent = await telegram.send_document(
            path.name, path.read_bytes(),
            f"🗄 <b>Бэкап Tunnelwright Panel AWG</b>\n🖥 <code>{telegram.escape(config.WG_HOST)}</code> · {size_kb} КБ\n"
            f"Архив зашифрован паролем бэкапа (AES-256, открывается 7-Zip или <code>tunnelwright restore</code>).")
    _record(True)
    return {"ok": True, "file": path.name, "size": path.stat().st_size, "telegram": sent,
            "skipped": _info(path).get("skipped", [])}


def _info(path: Path) -> dict:
    with pyzipper.AESZipFile(path) as z:
        z.setpassword(settings()["password"].encode())
        return json.loads(z.read("backup-info.json"))


def due(now: float | None = None) -> bool:
    s = settings()
    period = SCHEDULES.get(s["schedule"])
    if not period or len(s["password"]) < MIN_PASSWORD:
        return False
    now = now or time.time()
    local = datetime.fromtimestamp(now, zoneinfo.ZoneInfo(db.get_setting("timezone", "Europe/Moscow")))
    if local.hour < s["hour"]:
        return False
    return not s["last_ts"] or now - s["last_ts"] >= period - 3600   # запас на дрейф проверки


def list_backups() -> list[dict]:
    return [{"name": p.name, "size": p.stat().st_size, "ts": int(p.stat().st_mtime)} for p in _archives()]


def path_of(name: str) -> Path | None:
    p = _dir() / Path(name).name
    return p if p.exists() and p.name.startswith(PREFIXES) else None


NODE_FILES = ("wg-easy.db", "wg-easy-admin.json", "limits.json", "uids.json")


def node_data(node_id: int) -> tuple[str, dict[str, bytes]] | None:
    """Данные ноды из самого свежего бэкапа, где она есть: (имя архива, {файл: содержимое}).
    Нужны, чтобы переустановленный сервер ноды получил прежние ключи — клиентам не придётся менять конфиги."""
    pw = settings()["password"]
    if len(pw) < MIN_PASSWORD:
        return None
    for b in list_backups():
        try:
            with pyzipper.AESZipFile(_dir() / b["name"]) as z:
                z.setpassword(pw.encode())
                names = set(z.namelist())
                if f"nodes/{node_id}/wg-easy.db" not in names:
                    continue
                return b["name"], {f: z.read(f"nodes/{node_id}/{f}") for f in NODE_FILES
                                   if f"nodes/{node_id}/{f}" in names}
        except (RuntimeError, zipfile.BadZipFile, pyzipper.BadZipFile, KeyError) as e:   # другой пароль или повреждён
            log.warning("бэкап %s пропущен: %s", b["name"], e)
    return None


def extract(archive: Path, password: str, out_dir: Path):
    """Для восстановления: проверить пароль и распаковать (используется в cli restore)."""
    with pyzipper.AESZipFile(archive) as z:
        z.setpassword(password.encode())
        info = json.loads(z.read("backup-info.json"))
        z.extractall(out_dir)
    return info


# ── восстановление из интерфейса (стек Portainer: нет хоста с `tunnelwright restore`) ──
# Архив проверяется и раскладывается в DATA_DIR/restore, panel-api перезапускается, а подмена
# panel.db происходит при старте, до подключения к БД (apply_staged_restore).
# Только для панели без VPN на её сервере: ключи локальной ноды восстанавливает `tunnelwright restore`.

def _staged() -> Path:
    return config.DATA_DIR / "restore"


def stage_restore(data: bytes, password: str, filename: str = "") -> dict:
    """Проверить архив и подготовить восстановление. Ошибки — ValueError с текстом для пользователя."""
    if config.LOCAL_NODE_URL:
        raise ValueError("на сервере панели есть VPN — восстановление только командой tunnelwright restore")
    try:
        with pyzipper.AESZipFile(io.BytesIO(data)) as z:
            z.setpassword(password.encode())
            info = json.loads(z.read("backup-info.json"))
            panel_db = z.read("panel/panel.db")
    except RuntimeError:
        raise ValueError("неверный пароль бэкапа")
    except (zipfile.BadZipFile, pyzipper.BadZipFile, KeyError, ValueError) as e:
        raise ValueError(f"архив повреждён или не является бэкапом Tunnelwright Panel AWG ({e})")
    st = _staged()
    st.mkdir(parents=True, exist_ok=True)
    (st / "panel.db.tmp").write_bytes(panel_db)
    try:
        con = sqlite3.connect(st / "panel.db.tmp")
        ok = {"admins", "clients", "nodes"} <= {r[0] for r in con.execute("SELECT name FROM sqlite_master")}
        con.close()
    except sqlite3.DatabaseError:
        ok = False
    if not ok:
        (st / "panel.db.tmp").unlink()
        raise ValueError("в архиве нет базы панели")
    (st / "panel.db.tmp").replace(st / "panel.db")
    # Архив — в каталог бэкапов: из него же потом восстанавливаются данные переустановленных нод
    name = Path(filename).name
    if not (name.startswith(PREFIXES) and name.endswith(".zip")):
        name = f"{PREFIX}restored-{int(time.time())}.zip"
    _dir().mkdir(parents=True, exist_ok=True)
    (_dir() / name).write_bytes(data)
    (_dir() / name).chmod(0o600)
    info["file"] = name
    (st / "info.json").write_text(json.dumps(info, ensure_ascii=False))
    return info


def apply_staged_restore() -> str | None:
    """При старте: подготовленная panel.db заменяет текущую (прежняя — panel.db.before-restore)."""
    st = _staged()
    if not (st / "panel.db").exists():
        return None
    try:
        name = json.loads((st / "info.json").read_text()).get("file", "")
    except (OSError, ValueError):
        name = ""
    if config.DB_FILE.exists():
        config.DB_FILE.replace(config.DB_FILE.with_name("panel.db.before-restore"))
    for suffix in ("-wal", "-shm"):
        config.DB_FILE.with_name(config.DB_FILE.name + suffix).unlink(missing_ok=True)
    (st / "panel.db").replace(config.DB_FILE)
    config.DB_FILE.chmod(0o600)
    (st / "info.json").unlink(missing_ok=True)
    return name or "без имени"


def restart_soon(delay: float = 1.5):
    """Перезапуск panel-api: процесс завершается, Docker поднимает контейнер (restart: unless-stopped)."""
    import asyncio
    import os
    import signal
    asyncio.get_running_loop().call_later(delay, os.kill, os.getpid(), signal.SIGTERM)
