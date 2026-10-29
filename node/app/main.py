"""Tunnelwright Panel AWG node-agent: API ноды для panel-api.

Все запросы, кроме /health, требуют заголовок «Authorization: Bearer <токен ноды>».
"""
import asyncio
import contextlib
import logging
import os
import secrets
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from . import backup, config, firewall, metrics, shaping, uids, updater
from .wgeasy import WgEasy, WgEasyError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("node")
logging.getLogger("httpx").setLevel(logging.WARNING)

wg = WgEasy()
state = {"bootstrapped": False, "last_ok": 0.0, "error": None}

REAPPLY_LIMITS_SEC = 300   # tc-правила теряются при перезапуске интерфейса; заодно — блокировка торрентов
WATCHDOG_SEC = 90          # дольше без wg-easy — выходим: Docker перезапустит агент в новом netns


def _token() -> str:
    try:
        return config.TOKEN_FILE.read_text().strip()
    except OSError:
        return ""


def require_token(authorization: str = Header(default="")):
    token = _token()
    given = authorization.removeprefix("Bearer ").strip()
    if not token or not secrets.compare_digest(given, token):
        raise HTTPException(401, "unauthorized")


async def _background():
    """Настройка wg-easy, применение лимитов, watchdog сетевого namespace."""
    last_apply = 0.0
    while True:
        try:
            if not state["bootstrapped"]:
                await wg.bootstrap()
                state["bootstrapped"] = True
                state["error"] = None
            if await wg.ready():
                state["last_ok"] = time.time()
                if time.time() - last_apply > REAPPLY_LIMITS_SEC:
                    res = await asyncio.to_thread(shaping.apply, shaping.load_limits())
                    log.info("лимиты: применено %s, ошибок %s", res["applied"], len(res["errors"]))
                    await asyncio.to_thread(firewall.apply)
                    last_apply = time.time()
        except (WgEasyError, OSError) as e:
            state["error"] = str(e)
            log.warning("%s", e)
        except Exception as e:  # сеть до wg-easy ещё не поднялась
            state["error"] = f"{type(e).__name__}: {e}"
        if state["bootstrapped"] and state["last_ok"] and time.time() - state["last_ok"] > WATCHDOG_SEC:
            log.error("wg-easy недоступен %s с — перезапуск агента", WATCHDOG_SEC)
            os._exit(1)
        await asyncio.sleep(5)


@contextlib.asynccontextmanager
async def lifespan(_app):
    task = asyncio.create_task(_background())
    yield
    task.cancel()
    await wg.close()


app = FastAPI(title="Tunnelwright Panel AWG node-agent", version=config.APP_VERSION, lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)
auth = [Depends(require_token)]


@app.middleware("http")
async def allow_panel_only(request: Request, call_next):
    """Удалённая нода отвечает только панели: опубликованный порт Docker обходит ufw."""
    ip = request.client.host if request.client else ""
    if config.ALLOWED_IPS and ip not in config.ALLOWED_IPS and ip != "127.0.0.1":
        return JSONResponse({"detail": "forbidden"}, status_code=403)
    return await call_next(request)


def _client(c: dict) -> dict:
    """Клиент wg-easy → формат панели (без ключей)."""
    return {
        "id": c["id"], "name": c["name"], "ipv4": c.get("ipv4Address"),
        "enabled": bool(c.get("enabled")), "expiresAt": c.get("expiresAt"),
        "publicKey": c.get("publicKey"), "createdAt": c.get("createdAt"),
        "latestHandshakeAt": c.get("latestHandshakeAt"),
        "transferRx": c.get("transferRx") or 0, "transferTx": c.get("transferTx") or 0,
        "endpoint": c.get("endpoint"), "allowedIps": c.get("allowedIps"), "dns": c.get("dns"),
    }


async def _call(coro):
    try:
        return await coro
    except WgEasyError as e:
        raise HTTPException(502, str(e))


@app.get("/health")
async def health():
    ok = state["bootstrapped"] and time.time() - state["last_ok"] < 30
    return {"ok": ok, "bootstrapped": state["bootstrapped"], "error": state["error"],
            "version": config.APP_VERSION,
            "auto_update": updater.available(), "update_status": updater.status()}


@app.get("/info", dependencies=auth)
async def info():
    iface = await _call(wg.interface())
    return {"version": config.APP_VERSION, "host": config.WG_HOST, "port": config.WG_PORT,
            "interface": {k: iface.get(k) for k in ("name", "port", "ipv4Cidr", "mtu", "publicKey")}}


@app.get("/metrics", dependencies=auth)
async def node_metrics():
    m = await asyncio.to_thread(metrics.snapshot)
    m["wg_up"] = bool(state["bootstrapped"] and time.time() - state["last_ok"] < 30)
    m["torrent_block"] = {**firewall.state, "blocked": await asyncio.to_thread(firewall.blocked)}
    return m


# ── клиенты ─────────────────────────────────────────────────────
UID_FIELD = Field(default=None, pattern=r"^[a-f0-9]{8,32}$")   # скрытый ID клиента панели


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    expiresAt: str | None = None
    ipv4: str | None = None
    uid: str | None = UID_FIELD


class ClientPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    expiresAt: str | None = None
    ipv4: str | None = None
    allowedIps: list[str] | None = None
    dns: list[str] | None = None
    uid: str | None = UID_FIELD


def _with_uid(c: dict, ids: dict[int, str] | None = None) -> dict:
    out = _client(c)
    out["uid"] = (ids if ids is not None else uids.load()).get(c["id"])
    return out


@app.get("/clients", dependencies=auth)
async def list_clients():
    items = await _call(wg.list_clients())
    uids.prune({c["id"] for c in items})
    ids = uids.load()
    return [_with_uid(c, ids) for c in items]


@app.post("/clients", dependencies=auth)
async def create_client(body: ClientCreate):
    cid = await _call(wg.create_client(body.name, body.expiresAt))
    if body.ipv4:
        await _call(wg.update_client(cid, {"ipv4Address": body.ipv4}))
    if body.uid:
        uids.set_uid(cid, body.uid)
    return _with_uid(await _call(wg.get_client(cid)))


@app.get("/clients/{cid}", dependencies=auth)
async def get_client(cid: int):
    return _with_uid(await _call(wg.get_client(cid)))


@app.patch("/clients/{cid}", dependencies=auth)
async def patch_client(cid: int, body: ClientPatch):
    data = body.model_dump(exclude_unset=True)
    uid = data.pop("uid", None)
    patch = {"ipv4Address" if k == "ipv4" else k: v for k, v in data.items()}
    if patch:
        await _call(wg.update_client(cid, patch))
    c = await _call(wg.get_client(cid))
    if uid:
        uids.set_uid(cid, uid)
    return _with_uid(c)


@app.delete("/clients/{cid}", dependencies=auth)
async def delete_client(cid: int):
    await _call(wg.delete_client(cid))
    uids.set_uid(cid, None)
    return {"ok": True}


@app.post("/clients/{cid}/enable", dependencies=auth)
async def enable_client(cid: int):
    await _call(wg.set_enabled(cid, True))
    return {"ok": True}


@app.post("/clients/{cid}/disable", dependencies=auth)
async def disable_client(cid: int):
    await _call(wg.set_enabled(cid, False))
    return {"ok": True}


@app.get("/clients/{cid}/config", dependencies=auth, response_class=PlainTextResponse)
async def client_config(cid: int):
    return await _call(wg.configuration(cid))


@app.get("/clients/{cid}/qr", dependencies=auth)
async def client_qr(cid: int):
    return Response(await _call(wg.qrcode(cid)), media_type="image/svg+xml")


# ── лимиты скорости ─────────────────────────────────────────────
@app.get("/limits", dependencies=auth)
async def get_limits():
    return shaping.load_limits()


@app.put("/limits", dependencies=auth)
async def put_limits(limits: dict):
    clean = shaping.validate(limits)
    shaping.save_limits(clean)
    res = await asyncio.to_thread(shaping.apply, clean)
    return {"limits": clean, **res}


# ── бэкап ───────────────────────────────────────────────────────
@app.post("/update", dependencies=auth, status_code=202)
async def request_update(request: Request, version: str):
    """Обновить агент до version: файлы запроса подхватит systemd-юнит хоста, агент перезапустится."""
    try:
        updater.request(version, await request.body())
    except updater.UpdateError as e:
        raise HTTPException(409, str(e))
    log.info("запрошено обновление агента до %s", version)
    return {"accepted": version}


@app.get("/backup", dependencies=auth)
async def node_backup():
    data = await asyncio.to_thread(backup.snapshot)
    return Response(data, media_type="application/zip")
