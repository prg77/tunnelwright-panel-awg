"""API пользователей: список, изменение (имя, срок, группа, заметка, включение), удаление,
новый конфиг, объединение пользователей, отправка всех конфигов в Telegram.

Включение и срок пользователя действуют на все его конфиги; на ноды изменения уходят сразу.
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import audit, clients, limits, notify, telegram, users
from ..security import Admin
from .clients import Limit, add_config, apply

router = APIRouter(prefix="/api/users", tags=["users"])


def out(u: dict, configs: list[int] | None = None) -> dict:
    m = users.meta(u)
    if configs is None:
        configs = [c["id"] for c in users.configs(u["id"])]
    return {"id": u["id"], "uid": u["uid"], "name": u["name"], "enabled": bool(u["enabled"]),
            "group": u.get("group_name"), "note": m.get("note") or "", "expiresAt": u.get("expires_at"),
            "createdAt": u.get("created_at"), "configs": configs}


def _get(user_id: int) -> dict:
    u = users.get(user_id)
    if not u:
        raise HTTPException(404, "пользователь не найден")
    return u


class UserPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    enabled: bool | None = None
    expiresAt: str | None = Field(default=None, max_length=40)
    group: str | None = Field(default=None, max_length=32)
    note: str | None = Field(default=None, max_length=500)


class ConfigCreate(BaseModel):
    name: str | None = Field(default=None, max_length=64)    # название устройства
    ip: str | None = Field(default=None, max_length=18)
    limit: Limit | None = None


class MergeBody(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=100)


@router.get("")
def list_users(_admin=Admin):
    by_user: dict[int, list[int]] = {}
    for c in clients.all_clients():
        by_user.setdefault(c["user_id"], []).append(c["id"])
    return [out(u, by_user.get(u["id"], [])) for u in users.all_users()]


@router.get("/{user_id}")
def get_user(user_id: int, _admin=Admin):
    return out(_get(user_id))


@router.patch("/{user_id}")
async def patch_user(user_id: int, body: UserPatch, request: Request, admin=Admin):
    u = _get(user_id)
    ch = body.model_dump(exclude_unset=True)
    fields = {}
    if "name" in ch and ch["name"].strip() != u["name"]:
        fields["name"] = ch["name"]
    if "enabled" in ch and ch["enabled"] != bool(u["enabled"]):
        fields["enabled"] = ch["enabled"]
    if "expiresAt" in ch and (ch["expiresAt"] or None) != u["expires_at"]:
        fields["expires_at"] = ch["expiresAt"] or None
    try:
        users.update(user_id, **fields)
    except users.UserError as e:
        raise HTTPException(400, str(e))
    if "group" in ch or "note" in ch:
        m = users.meta(u)
        m["group"] = ch["group"] if "group" in ch else u.get("group_name")
        if "note" in ch:
            m["note"] = ch["note"] or ""
        users.set_meta(user_id, m)
    if fields:
        await apply(request, admin)
    if "enabled" in fields:
        audit.log(request, admin, "user_enabled" if fields["enabled"] else "user_disabled", str(user_id), name=u["name"])
        notify.user_toggled(users.get(user_id), fields["enabled"])
    if "expires_at" in fields:
        audit.log(request, admin, "user_expiry", str(user_id), expiresAt=fields["expires_at"])
    if "name" in fields:
        audit.log(request, admin, "user_renamed", str(user_id), name=fields["name"].strip(), was=u["name"])
    return out(users.get(user_id))


@router.delete("/{user_id}")
async def delete_user(user_id: int, request: Request, admin=Admin):
    u = _get(user_id)
    ips = [c["ipv4"] for c in clients.of_user(user_id)]
    clients.delete_user(user_id)
    await apply(request, admin)
    await limits.push_all()
    audit.log(request, admin, "user_deleted", str(user_id), name=u["name"], ips=ips)
    notify.user_deleted(u, ips)
    return Response(status_code=204)


@router.post("/{user_id}/configs")
async def create_config(user_id: int, body: ConfigCreate, request: Request, admin=Admin):
    """Ещё одно устройство пользователя: свой IP и ключи на каждой ноде."""
    _get(user_id)
    return await add_config(request, admin, user_id, body.name, body.ip, body.limit)


@router.post("/{user_id}/merge")
async def merge_users(user_id: int, body: MergeBody, request: Request, admin=Admin):
    """Конфиги выбранных пользователей переходят к этому; выбранные пользователи удаляются
    (их личные ссылки и квоты — тоже). Срок, группа и заметка остаются от этого пользователя."""
    u = _get(user_id)
    others = [i for i in dict.fromkeys(body.ids) if i != user_id]
    names = []
    for i in others:
        names.append(_get(i)["name"])
    users.merge(user_id, others)
    await apply(request, admin)
    audit.log(request, admin, "users_merged", str(user_id), name=u["name"], merged=names)
    return out(users.get(user_id))


@router.post("/{user_id}/telegram")
async def send_to_telegram(user_id: int, request: Request, admin=Admin):
    """Все конфиги пользователя (по всем нодам) — администратору в Telegram."""
    u = _get(user_id)
    if not telegram.active():
        raise HTTPException(409, "Telegram не настроен: укажите токен бота и Chat ID в настройках")
    ok = await notify.user_configs(user_id)
    audit.log(request, admin, "client_config_sent", str(user_id), name=u["name"])
    return {"ok": ok}
