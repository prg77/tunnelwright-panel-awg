"""Группы клиентов, справочник списков, GeoIP и маршрутизация клиентов."""
import re
import sqlite3

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import audit, db, geoip, lists, nodes, routing
from ..security import Admin

router = APIRouter(prefix="/api", tags=["catalog"])

COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")


# ── группы ─────────────────────────────────────────────────────
class GroupBody(BaseModel):
    name: str | None = Field(default=None, max_length=32)
    color: str | None = None
    sort: int | None = None


def _groups():
    return db.query("SELECT g.id, g.name, g.color, g.sort, COUNT(c.id) AS clients FROM groups g "
                    "LEFT JOIN clients c ON c.group_id = g.id GROUP BY g.id ORDER BY g.sort, g.name")


def _group_fields(body: GroupBody) -> dict:
    out = {}
    if body.name is not None:
        name = body.name.strip()
        if not name or name == "Без группы":
            raise HTTPException(400, "недопустимое имя группы")
        out["name"] = name
    if body.color is not None:
        if not COLOR_RE.fullmatch(body.color):
            raise HTTPException(400, "цвет — в формате #rrggbb")
        out["color"] = body.color.lower()
    if body.sort is not None:
        out["sort"] = body.sort
    return out


@router.get("/groups")
def list_groups(_admin=Admin):
    return _groups()


@router.post("/groups")
def create_group(body: GroupBody, request: Request, admin=Admin):
    f = _group_fields(body)
    if "name" not in f:
        raise HTTPException(400, "имя группы не задано")
    f.setdefault("sort", (db.one("SELECT COALESCE(MAX(sort), 0) + 1 AS s FROM groups") or {})["s"])
    try:
        gid = db.execute("INSERT INTO groups(name, color, sort) VALUES(?,?,?)",
                         (f["name"], f.get("color", "#94a3b8"), f["sort"]))
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"группа «{f['name']}» уже есть")
    audit.log(request, admin, "group_created", f["name"])
    return next(g for g in _groups() if g["id"] == gid)


@router.put("/groups/{gid}")
def update_group(gid: int, body: GroupBody, request: Request, admin=Admin):
    cur = db.one("SELECT * FROM groups WHERE id=?", (gid,))
    if not cur:
        raise HTTPException(404, "группа не найдена")
    f = _group_fields(body)
    if f:
        try:
            db.execute(f"UPDATE groups SET {', '.join(k + '=?' for k in f)} WHERE id=?", (*f.values(), gid))
        except sqlite3.IntegrityError:
            raise HTTPException(409, f"группа «{f.get('name')}» уже есть")
        audit.log(request, admin, "group_updated", cur["name"], **f)
    return next(g for g in _groups() if g["id"] == gid)


@router.put("/groups-order")
def reorder_groups(ids: list[int], request: Request, admin=Admin):
    for i, gid in enumerate(ids, 1):
        db.execute("UPDATE groups SET sort=? WHERE id=?", (i, gid))
    audit.log(request, admin, "groups_reordered")
    return _groups()


@router.delete("/groups/{gid}")
def delete_group(gid: int, request: Request, admin=Admin):
    cur = db.one("SELECT * FROM groups WHERE id=?", (gid,))
    if not cur:
        raise HTTPException(404, "группа не найдена")
    db.execute("DELETE FROM groups WHERE id=?", (gid,))   # клиенты остаются без группы
    audit.log(request, admin, "group_deleted", cur["name"])
    return {"ok": True}


# ── списки ─────────────────────────────────────────────────────
class ListBody(BaseModel):
    kind: str | None = None
    name: str | None = None
    countries: list[str] | None = None
    cidrs: list[str] | None = None
    apps: list[str] | None = None


def _data(body: ListBody):
    if body.countries is None and body.cidrs is None and body.apps is None:
        return None
    return {"countries": body.countries or [], "cidrs": body.cidrs or [], "apps": body.apps or []}


def _list_or_404(lid):
    lst = lists.get(lid)
    if not lst:
        raise HTTPException(404, "список не найден")
    return lst


@router.get("/lists")
def get_lists(kind: str | None = None, _admin=Admin):
    return lists.all_lists(kind)


@router.post("/lists")
async def create_list(body: ListBody, request: Request, admin=Admin):
    try:
        lst = lists.create(body.kind or "", body.name, _data(body) or {})
        await _prefetch(lst)
    except ValueError as e:
        raise HTTPException(400, str(e))
    audit.log(request, admin, "list_created", lst["name"], kind=lst["kind"])
    return lst


@router.put("/lists/{lid}")
async def update_list(lid: int, body: ListBody, request: Request, admin=Admin):
    _list_or_404(lid)
    try:
        lst = lists.update(lid, body.name, _data(body))
        await _prefetch(lst)
    except ValueError as e:
        raise HTTPException(400, str(e))
    audit.log(request, admin, "list_updated", lst["name"], kind=lst["kind"])
    return lst


@router.post("/lists/{lid}/duplicate")
def duplicate_list(lid: int, request: Request, admin=Admin):
    _list_or_404(lid)
    lst = lists.duplicate(lid)
    audit.log(request, admin, "list_created", lst["name"], kind=lst["kind"], copy_of=lid)
    return lst


@router.delete("/lists/{lid}")
def delete_list(lid: int, request: Request, admin=Admin):
    lst = _list_or_404(lid)
    lists.delete(lid)
    audit.log(request, admin, "list_deleted", lst["name"], kind=lst["kind"])
    return {"ok": True}


async def _prefetch(lst):
    """Скачать зоны стран сразу — ошибка в коде страны видна при сохранении, а не при выдаче конфига."""
    for cc in lst.get("countries", []):
        await geoip.networks(cc)


# ── GeoIP ──────────────────────────────────────────────────────
@router.get("/geoip")
def geoip_status(_admin=Admin):
    return {"source": "ipdeny.com", "countries": geoip.status()}


@router.post("/geoip/refresh")
async def geoip_refresh(request: Request, admin=Admin):
    errors = {}
    for cc in sorted(lists.used_countries()):
        try:
            await geoip.networks(cc, refresh=True)
        except ValueError as e:
            errors[cc] = str(e)
    audit.log(request, admin, "geoip_refresh", errors=list(errors))
    return {"countries": geoip.status(), "errors": errors}


# ── маршрутизация клиента ──────────────────────────────────────
class RoutingBody(BaseModel):
    net_mode: str | None = None
    net_lists: list[int] | None = None
    app_mode: str | None = None
    app_lists: list[int] | None = None
    extra: str | None = None


def _client_or_404(cid):
    if not db.one("SELECT id FROM clients WHERE id=?", (cid,)):
        raise HTTPException(404, "клиент не найден")


@router.get("/routing")
def routing_overview(_admin=Admin):
    """{clientId: {net_mode, app_mode, custom}} — для значков в списке клиентов."""
    return {str(k): v for k, v in routing.all_routing().items()}


@router.get("/clients/{cid}/routing")
def get_routing(cid: int, _admin=Admin):
    _client_or_404(cid)
    return routing.get(cid)


@router.put("/clients/{cid}/routing")
def put_routing(cid: int, body: RoutingBody, request: Request, admin=Admin):
    _client_or_404(cid)
    try:
        r = routing.save(cid, body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))
    audit.log(request, admin, "client_routing", str(cid), net=r["net_mode"], apps=r["app_mode"],
              custom=bool(r["extra"]))
    return r


@router.get("/clients/{cid}/routing/preview")
async def preview_routing(cid: int, _admin=Admin):
    """Итоговый конфиг без приватного ключа и сводка (число подсетей, размер)."""
    _client_or_404(cid)
    try:
        text, _, info = await routing.client_config(cid)
    except nodes.NodeError as e:
        raise HTTPException(502, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))
    text = re.sub(r"(?im)^(\s*(PrivateKey|PresharedKey)\s*=\s*).*$", r"\1•••", text)
    return {"config": text, **info, "qr": info["size"] <= 2900}
