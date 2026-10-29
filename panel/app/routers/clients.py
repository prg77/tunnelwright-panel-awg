"""API конфигов: список с трафиком по нодам, новый пользователь с первым конфигом, изменение,
удаление, лимит скорости, конфиг и QR по нодам, отправка конфига в Telegram.

Конфиг — устройство пользователя; на каждой ноде у него профиль с тем же IP. Имя, срок, группа
и общее включение — у пользователя (routers/users.py). Изменения применяются на нодах сразу
(недоступные ноды догонит фоновая синхронизация). Уведомления в Telegram отправляет сервер
по настройкам событий.
"""
import io

import segno
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field

from .. import audit, clients, limits, nodes, notify, routing, telegram, users
from ..security import Admin

router = APIRouter(prefix="/api/clients", tags=["clients"])


def out(c: dict, s: dict | None = None, lims: dict | None = None) -> dict:
    s = s or {}
    lim = (lims if lims is not None else limits.get()).get(c["ipv4"])
    return {"id": c["id"], "uid": c.get("uid"), "userId": c["user_id"], "user": c.get("user_name") or "",
            "name": c["name"] or "", "label": clients.label(c), "ip": c["ipv4"],
            "enabled": bool(c["enabled"]), "active": clients.active(c), "createdAt": c.get("created_at"),
            "limit": lim, "handshakeAt": s.get("latestHandshakeAt"),
            "rx": s.get("transferRx", 0), "tx": s.get("transferTx", 0),
            "nodes": [{"id": n["nodeId"], "name": n["nodeName"], "handshakeAt": n["latestHandshakeAt"]}
                      for n in s.get("nodes", [])]}


def _get(cid: int) -> dict:
    c = clients.get(cid)
    if not c:
        raise HTTPException(404, "конфиг не найден")
    return c


async def apply(request, admin) -> None:
    down = await clients.sync_all()
    if down:
        audit.log(request, admin, "nodes_pending", None, nodes=down)


async def one(cid: int) -> dict:
    rows, _ = await clients.reconcile_all()
    return out(clients.get(cid), clients.summary(rows).get(cid))


class Limit(BaseModel):
    down: float = Field(gt=0, le=10000)
    up: float = Field(gt=0, le=10000)


class ClientCreate(BaseModel):
    """Новый пользователь и его первый конфиг."""
    name: str = Field(min_length=1, max_length=64)
    device: str | None = Field(default=None, max_length=64)
    ip: str | None = Field(default=None, max_length=18)
    expiresAt: str | None = Field(default=None, max_length=40)
    group: str | None = Field(default=None, max_length=32)
    note: str | None = Field(default=None, max_length=500)
    limit: Limit | None = None


class ClientPatch(BaseModel):
    name: str | None = Field(default=None, max_length=64)    # название устройства; пусто — без названия
    ip: str | None = Field(default=None, max_length=18)
    enabled: bool | None = None


@router.get("")
async def list_clients(_admin=Admin):
    rows, _ = await clients.reconcile_all()
    by_client, lims = clients.summary(rows), limits.get()
    return [out(c, by_client.get(c["id"]), lims) for c in clients.all_clients()]


async def add_config(request, admin, user_id: int, device: str | None, ip: str | None, limit: Limit | None) -> dict:
    """Конфиг создаётся сразу на всех нодах с одним IP."""
    try:
        cid = clients.create(user_id, device, ip or None)
    except clients.ClientError as e:
        raise HTTPException(400, str(e))
    c = clients.get(cid)
    if limit:
        limits.set_for(c["ipv4"], limit.model_dump())
    await apply(request, admin)
    audit.log(request, admin, "client_created", clients.label(c), ip=c["ipv4"], user=str(user_id),
              nodes=[p["node_name"] for p in clients.profiles(cid)])
    notify.client_added(cid)
    return await one(cid)


@router.post("")
async def create_client(body: ClientCreate, request: Request, admin=Admin):
    """Новый пользователь с первым конфигом. Ещё одно устройство — POST /api/users/{id}/configs."""
    if body.ip:
        try:
            clients.check_ip(body.ip)
        except clients.ClientError as e:
            raise HTTPException(400, str(e))
    try:
        user_id = users.create(body.name, body.expiresAt or None)
    except users.UserError as e:
        raise HTTPException(400, str(e))
    if body.group or body.note:
        users.set_meta(user_id, {"group": body.group, "note": body.note})
    audit.log(request, admin, "user_created", body.name.strip(), id=str(user_id))
    try:
        return await add_config(request, admin, user_id, body.device, body.ip, body.limit)
    except HTTPException:
        users.delete(user_id)     # конфиг не создан — пользователь без конфигов не нужен
        raise


@router.patch("/{cid}")
async def patch_client(cid: int, body: ClientPatch, request: Request, admin=Admin):
    c = _get(cid)
    ch = body.model_dump(exclude_unset=True)
    fields = {}
    if "name" in ch and (ch["name"] or "").strip() != (c["name"] or ""):
        fields["name"] = ch["name"]
    if ch.get("ip") and ch["ip"] != c["ipv4"]:
        fields["ipv4"] = ch["ip"]
    if "enabled" in ch and ch["enabled"] != bool(c["enabled"]):
        fields["enabled"] = ch["enabled"]
    try:
        clients.update(cid, **fields)
    except clients.ClientError as e:
        raise HTTPException(400, str(e))
    if fields:
        await apply(request, admin)
    if "ipv4" in fields:
        await limits.push_all()   # лимит переехал на новый IP
        audit.log(request, admin, "client_address", str(cid), ip=clients.get(cid)["ipv4"])
    if "enabled" in fields:
        audit.log(request, admin, "client_enabled" if fields["enabled"] else "client_disabled", str(cid),
                  name=clients.label(c))
        notify.client_toggled(clients.get(cid), fields["enabled"])
    if "name" in fields:
        audit.log(request, admin, "client_renamed", str(cid), name=clients.label(clients.get(cid)),
                  was=clients.label(c))
    return await one(cid)


@router.delete("/{cid}")
async def delete_client(cid: int, request: Request, admin=Admin):
    c = _get(cid)
    clients.mark_deleted(cid)
    await apply(request, admin)
    await limits.push_all()
    audit.log(request, admin, "client_deleted", str(cid), name=clients.label(c))
    notify.client_deleted(c)
    return Response(status_code=204)


@router.put("/{cid}/limit")
async def set_limit(cid: int, body: Limit, request: Request, admin=Admin):
    c = _get(cid)
    limits.set_for(c["ipv4"], body.model_dump())
    errors = await limits.push_all()
    audit.log(request, admin, "limits_changed", str(cid), ip=c["ipv4"], set=body.model_dump())
    notify.limit_set(c, body.model_dump())
    return {"limit": limits.get().get(c["ipv4"]), "errors": errors}


@router.delete("/{cid}/limit")
async def del_limit(cid: int, request: Request, admin=Admin):
    c = _get(cid)
    if c["ipv4"] in limits.get():
        limits.set_for(c["ipv4"], None)
        await limits.push_all()
        audit.log(request, admin, "limits_changed", str(cid), ip=c["ipv4"], removed=True)
        notify.limit_set(c, None)
    return {"limit": None}


async def _config(cid: int, node: int | None):
    """Конфиг профиля на ноде с маршрутизацией (списки сетей и приложений, свои параметры)."""
    _get(cid)
    try:
        return await routing.client_config(cid, node)
    except nodes.NodeError as e:
        raise HTTPException(502, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/{cid}/config")
async def client_config(cid: int, node: int | None = None, _admin=Admin):
    text, name, _ = await _config(cid, node)
    return PlainTextResponse(text, headers={"Content-Disposition": routing.attachment(name, f"client-{cid}")})


@router.get("/{cid}/qr.svg")
async def client_qr(cid: int, node: int | None = None, _admin=Admin):
    text, _, _ = await _config(cid, node)
    try:
        qr = segno.make(text, error="l")
    except segno.DataOverflowError:
        raise HTTPException(413, "конфиг слишком большой для QR-кода — используйте файл")
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=4, border=2, light="#ffffff", xmldecl=False)
    return Response(buf.getvalue(), media_type="image/svg+xml")


@router.post("/{cid}/telegram")
async def send_to_telegram(cid: int, request: Request, node: int | None = None, admin=Admin):
    """Конфиг и QR — администратору в Telegram (по ноде или по всем нодам)."""
    c = _get(cid)
    if not telegram.active():
        raise HTTPException(409, "Telegram не настроен: укажите токен бота и Chat ID в настройках")
    await _config(cid, node)   # ошибки конфига — сразу в ответ, а не молча в фоне
    ok = await notify.client_config(cid, node_id=node)
    audit.log(request, admin, "client_config_sent", str(cid), name=clients.label(c), node=node)
    return {"ok": ok}
