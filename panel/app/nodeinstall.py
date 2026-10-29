"""Установка, обновление и удаление удалённых нод по SSH.

Пароль или ключ SSH используются только в задаче установки и нигде не сохраняются.
Запоминается отпечаток ключа SSH-хоста — при обновлении ноды он сверяется.
"""
import asyncio
import io
import ipaddress
import logging
import re
import secrets
import shlex
import tarfile
import time
import uuid
from pathlib import Path

import asyncssh

from . import audit, backup, config, db, nodes

log = logging.getLogger("panel.nodeinstall")

SCRIPT = Path(__file__).parent / "remote" / "install-node.sh"
REMOVE_SCRIPT = Path(__file__).parent / "remote" / "remove-node.sh"
HOST_RE = re.compile(r"(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)*")
REMOTE = {"script": "/root/.tunnelwright-node-install.sh", "bundle": "/root/.tunnelwright-node-bundle.tgz",
          "token": "/root/.tunnelwright-node-token"}
RESTORE_DIR = "/root/.tunnelwright-node-restore"
HEALTH_WAIT_SEC = 150
MAX_JOBS = 20
MAX_LOG_LINES = 400

jobs: dict[str, dict] = {}


class InstallError(Exception):
    pass


# ── проверка параметров ────────────────────────────────────────
def _host(h: str) -> str:
    h = (h or "").strip().strip("[]")
    try:
        return str(ipaddress.ip_address(h))
    except ValueError:
        pass
    if not HOST_RE.fullmatch(h):
        raise InstallError("неверный адрес сервера")
    return h.lower()


def _port(v, name) -> int:
    try:
        p = int(v)
    except (TypeError, ValueError):
        raise InstallError(f"{name}: неверный порт")
    if not 1 <= p <= 65535:
        raise InstallError(f"{name}: порт 1–65535")
    return p


def _dns(v) -> str:
    out = []
    for d in str(v or "1.1.1.1").replace(" ", "").split(","):
        if d:
            try:
                out.append(str(ipaddress.IPv4Address(d)))
            except ValueError:
                raise InstallError(f"DNS: неверный адрес {d[:40]}")
    return ",".join(out) or "1.1.1.1"


def params(body: dict, row: dict | None = None) -> dict:
    """Параметры установки; для обновления недостающие берутся из записи ноды."""
    row = row or {}
    p = {
        "name": str(body.get("name") or row.get("name") or "").strip()[:64],
        "host": _host(body.get("host") or row.get("host") or ""),
        "ssh_port": _port(body.get("ssh_port") or row.get("ssh_port") or 22, "SSH"),
        "wg_port": _port(body.get("wg_port") or row.get("wg_port") or 51820, "VPN"),
        "agent_port": _port(body.get("agent_port") or row.get("agent_port") or 8711, "агент"),
        "wg_dns": _dns(body.get("wg_dns") or row.get("wg_dns")),
        # только для обновления: сервер переустановлен — новый ключ SSH-хоста и данные ноды из бэкапа
        "new_host_key": bool(row and body.get("new_host_key")),
        "restore": bool(row and body.get("restore")),
    }
    if not p["name"]:
        p["name"] = p["host"]
    if p["wg_port"] == p["agent_port"]:
        raise InstallError("порт VPN и порт агента совпадают")
    return p


def credentials(body: dict) -> dict:
    password = body.get("password") or None
    key_text = (body.get("private_key") or "").strip()
    if not password and not key_text:
        raise InstallError("укажите пароль root или приватный ключ SSH")
    key = None
    if key_text:
        try:
            key = asyncssh.import_private_key(key_text, body.get("passphrase") or None)
        except (asyncssh.KeyImportError, ValueError) as e:
            raise InstallError(f"приватный ключ не прочитан: {e}")
    return {"password": password, "key": key}


# ── задача установки ───────────────────────────────────────────
def bundle() -> bytes:
    """Исходники node-agent для сборки на ноде (если образ из GHCR недоступен)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(config.NODE_BUNDLE_DIR, arcname=".",
                filter=lambda ti: None if "__pycache__" in ti.name or ti.name.endswith(".pyc") else ti)
    return buf.getvalue()


def _url_host(host: str) -> str:
    return f"[{host}]" if ":" in host else host


def public(job: dict) -> dict:
    return {k: job[k] for k in ("id", "node_id", "name", "host", "action", "status", "log", "error",
                                "started", "finished")}


def running_for(host: str) -> dict | None:
    return next((j for j in jobs.values() if j["host"] == host and j["status"] == "running"), None)


def start(p: dict, creds: dict, admin: dict, node_id: int | None = None) -> dict:
    if running_for(p["host"]):
        raise InstallError("на этом сервере уже идёт установка")
    if node_id is None and db.one("SELECT id FROM nodes WHERE host=? AND wg_port=?", (p["host"], p["wg_port"])):
        raise InstallError("такая нода уже добавлена — используйте обновление")
    job = {"id": uuid.uuid4().hex[:12], "node_id": node_id, "name": p["name"], "host": p["host"],
           "action": "update" if node_id else "install", "status": "running", "log": [], "error": None,
           "started": int(time.time()), "finished": None}
    for old in sorted(jobs.values(), key=lambda j: j["started"])[:-MAX_JOBS + 1]:
        if old["status"] != "running":
            jobs.pop(old["id"], None)
    jobs[job["id"]] = job
    asyncio.create_task(_run(job, p, creds, admin))
    return job


def start_remove(row: dict, creds: dict, admin: dict) -> dict:
    """Удалить VPN с сервера ноды; запись ноды убирается из панели только после успеха."""
    if running_for(row["host"]):
        raise InstallError("на этом сервере уже идёт установка или удаление")
    job = {"id": uuid.uuid4().hex[:12], "node_id": row["id"], "name": row["name"], "host": row["host"],
           "action": "remove", "status": "running", "log": [], "error": None,
           "started": int(time.time()), "finished": None}
    jobs[job["id"]] = job
    asyncio.create_task(_run_remove(job, row, creds, admin))
    return job


def _say(job, line: str):
    job["log"].append(line.rstrip()[:300])
    del job["log"][:-MAX_LOG_LINES]


async def _connect(job: dict, host: str, port: int, creds: dict, row: dict | None):
    """SSH root@host; у известной ноды ключ хоста сверяется с сохранённым."""
    _say(job, f"Подключение к {host}:{port} по SSH…")
    conn = await asyncio.wait_for(asyncssh.connect(
        host, port=port, username="root", password=creds["password"],
        client_keys=[creds["key"]] if creds["key"] else None, known_hosts=None,
        agent_path=None, connect_timeout=20), 40)
    fp = conn.get_server_host_key().get_fingerprint("sha256")
    if row and row.get("ssh_host_key") and row["ssh_host_key"] != fp:
        conn.close()
        raise InstallError(f"ключ SSH-хоста изменился ({fp}, ожидался {row['ssh_host_key']}) — "
                           "если сервер переустановлен, удалите ноду из панели без удаления с сервера")
    _say(job, f"Подключено. Ключ хоста: {fp}")
    return conn, fp


async def _run_remove(job: dict, row: dict, creds: dict, admin: dict):
    try:
        conn, _ = await _connect(job, row["host"], row["ssh_port"] or 22, creds, row)
        async with conn:
            async with conn.start_sftp_client() as sftp:
                async with sftp.open(REMOTE["script"], "wb", asyncssh.SFTPAttrs(permissions=0o600)) as f:
                    await f.write(REMOVE_SCRIPT.read_bytes())
            cmd = (f"WG_PORT={shlex.quote(str(row['wg_port'] or ''))} bash {REMOTE['script']}; "
                   f"rc=$?; rm -f {REMOTE['script']}; exit $rc")
            proc = await conn.create_process(cmd, stderr=asyncssh.STDOUT)
            async for line in proc.stdout:
                _say(job, line.rstrip("\n"))
            await proc.wait()
            if proc.exit_status != 0:
                raise InstallError(f"скрипт удаления завершился с кодом {proc.exit_status}")
        n = db.one("SELECT COUNT(*) n FROM profiles WHERE node_id=?", (row["id"],))["n"]
        db.execute("DELETE FROM nodes WHERE id=?", (row["id"],))
        _say(job, f"✓ Нода «{row['name']}» удалена с сервера и из панели")
        job["status"] = "ok"
        audit.log(None, admin, "node_removed", row["name"], host=row["host"], clients=n, purged=True)
    except asyncssh.PermissionDenied:
        _fail(job, "SSH: доступ запрещён — проверьте пароль или ключ")
    except (InstallError, asyncssh.Error, OSError, asyncio.TimeoutError) as e:
        _fail(job, str(e) or type(e).__name__)
    except Exception as e:  # чтобы задача не зависла в состоянии «идёт»
        log.exception("удаление ноды")
        _fail(job, f"{type(e).__name__}: {e}")
    finally:
        job["finished"] = int(time.time())


async def _run(job: dict, p: dict, creds: dict, admin: dict):
    row = db.one("SELECT * FROM nodes WHERE id=?", (job["node_id"],)) if job["node_id"] else None
    try:
        token = (row or {}).get("token") or secrets.token_urlsafe(32)
        restore = None
        if p["restore"]:
            restore = backup.node_data(row["id"])
            if not restore:
                raise InstallError("в бэкапах панели нет данных этой ноды (или не задан пароль бэкапа)")
            _say(job, f"Данные ноды берутся из бэкапа {restore[0]}")
        if p["new_host_key"]:
            _say(job, "Сервер переустановлен: новый ключ SSH-хоста будет принят")
        conn, fp = await _connect(job, p["host"], p["ssh_port"], creds, None if p["new_host_key"] else row)
        async with conn:
            async with conn.start_sftp_client() as sftp:
                for name, data in (("script", SCRIPT.read_bytes()), ("bundle", bundle()),
                                   ("token", token.encode() + b"\n")):
                    async with sftp.open(REMOTE[name], "wb", asyncssh.SFTPAttrs(permissions=0o600)) as f:
                        await f.write(data)
                if restore:
                    await sftp.makedirs(RESTORE_DIR, asyncssh.SFTPAttrs(permissions=0o700), exist_ok=True)
                    for fname, data in restore[1].items():
                        async with sftp.open(f"{RESTORE_DIR}/{fname}", "wb", asyncssh.SFTPAttrs(permissions=0o600)) as f:
                            await f.write(data)
            env = {"WG_HOST": p["host"], "WG_PORT": str(p["wg_port"]), "AGENT_PORT": str(p["agent_port"]),
                   "WG_DNS": p["wg_dns"], "APP_VERSION": config.APP_VERSION, "NODE_IMAGE": config.NODE_IMAGE,
                   "WG_EASY_IMAGE": config.WG_EASY_IMAGE, "BUNDLE": REMOTE["bundle"],
                   "NODE_TOKEN_FILE": REMOTE["token"], "RESTORE_DIR": RESTORE_DIR if restore else "",
                   "PANEL_IP": "" if config.NODE_IP_LOCK else "any"}
            cmd = (" ".join(f"{k}={shlex.quote(v)}" for k, v in env.items()) + f" bash {REMOTE['script']}; "
                   f"rc=$?; rm -f {' '.join(REMOTE.values())}; rm -rf {RESTORE_DIR}; exit $rc")
            cert_lines, in_cert = [], False
            proc = await conn.create_process(cmd, stderr=asyncssh.STDOUT)
            async for line in proc.stdout:
                s = line.rstrip("\n")
                if s == "=====CERT=====":
                    in_cert = True
                elif s == "=====END=====":
                    in_cert = False
                elif in_cert:
                    cert_lines.append(s)
                else:
                    _say(job, s)
            await proc.wait()
            if proc.exit_status != 0:
                raise InstallError(f"скрипт установки завершился с кодом {proc.exit_status}")
        cert = "\n".join(cert_lines).strip() + "\n"
        try:
            fingerprint = nodes.cert_fingerprint(cert)
        except ValueError:
            raise InstallError("сертификат агента не получен")
        fields = {"name": p["name"], "url": f"https://{_url_host(p['host'])}:{p['agent_port']}", "token": token,
                  "host": p["host"], "ssh_port": p["ssh_port"], "wg_port": p["wg_port"],
                  "agent_port": p["agent_port"], "wg_dns": p["wg_dns"], "tls_cert": cert,
                  "ssh_host_key": fp, "installed_at": int(time.time())}
        if row:
            db.execute(f"UPDATE nodes SET {', '.join(k + '=?' for k in fields)} WHERE id=?", (*fields.values(), row["id"]))
            node_id = row["id"]
        else:
            node_id = db.execute(f"INSERT INTO nodes({', '.join(fields)}, is_local) VALUES({', '.join('?' * len(fields))}, 0)",
                                 tuple(fields.values()))
        job["node_id"] = node_id
        _say(job, f"Сертификат агента: SHA-256 {fingerprint[:23]}…")
        _say(job, "Ожидание готовности ноды…")
        node = nodes.get(node_id)
        deadline = time.time() + HEALTH_WAIT_SEC
        while True:
            h = await node.health()
            if h.get("ok"):
                break
            if time.time() > deadline:
                raise InstallError(f"нода установлена, но не отвечает панели: {h.get('error') or 'wg-easy не готов'}")
            await asyncio.sleep(5)
        _say(job, f"✓ Нода «{p['name']}» готова (версия агента {h.get('version')})")
        job["status"] = "ok"
        audit.log(None, admin, "node_installed" if job["action"] == "install" else "node_updated",
                  p["name"], host=p["host"], wg_port=p["wg_port"])
    except asyncssh.PermissionDenied:
        _fail(job, "SSH: доступ запрещён — проверьте пароль или ключ")
    except (InstallError, asyncssh.Error, OSError, asyncio.TimeoutError) as e:
        _fail(job, str(e) or type(e).__name__)
    except Exception as e:  # чтобы задача не зависла в состоянии «идёт»
        log.exception("установка ноды")
        _fail(job, f"{type(e).__name__}: {e}")
    finally:
        job["finished"] = int(time.time())


def _fail(job, msg):
    job["status"], job["error"] = "error", msg
    _say(job, f"✗ {msg}")
