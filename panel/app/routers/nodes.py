"""Ноды: список с состоянием, установка и обновление по SSH, переименование, удаление."""
import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import audit, backup, config, db, nodeinstall, nodes, nodeupdate
from ..security import Admin

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


async def _state(node: nodes.Node) -> dict:
    h = await node.health()
    m = None
    if h.get("ok"):
        try:
            m = await node.json("GET", "/metrics")
        except nodes.NodeError:
            m = None
    r = node.row
    return {"id": node.id, "name": node.name, "is_local": node.is_local,
            "host": config.WG_HOST if node.is_local else r.get("host"),
            "wg_port": config.WG_PORT if node.is_local else r.get("wg_port"),
            "agent_port": r.get("agent_port"), "ssh_port": r.get("ssh_port"), "wg_dns": r.get("wg_dns"),
            "installed_at": r.get("installed_at"),
            "cert_sha256": nodes.cert_fingerprint(r["tls_cert"]) if r.get("tls_cert") else None,
            "ssh_host_key": r.get("ssh_host_key"),
            "ok": bool(h.get("ok")), "error": h.get("error"), "version": h.get("version"),
            "update": nodeupdate.state(node, h),
            "clients": db.one("SELECT COUNT(*) n FROM profiles WHERE node_id=?", (node.id,))["n"],
            "metrics": m}


@router.get("")
async def list_nodes(_admin=Admin):
    return await asyncio.gather(*(_state(n) for n in nodes.all_nodes()))


class InstallBody(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    host: str | None = Field(default=None, max_length=253)
    ssh_port: int | None = None
    wg_port: int | None = None
    agent_port: int | None = None
    wg_dns: str | None = Field(default=None, max_length=100)
    password: str | None = Field(default=None, max_length=512)
    private_key: str | None = Field(default=None, max_length=20000)
    passphrase: str | None = Field(default=None, max_length=512)
    new_host_key: bool = False   # обновление: сервер переустановлен, принять новый ключ SSH-хоста
    restore: bool = False        # обновление: вернуть данные ноды (ключи) из бэкапа панели


def _remote_row(nid: int) -> dict:
    row = db.one("SELECT * FROM nodes WHERE id=?", (nid,))
    if not row:
        raise HTTPException(404, "нода не найдена")
    if row["is_local"]:
        raise HTTPException(400, "локальная нода обновляется вместе с панелью: tunnelwright update")
    return row


@router.post("/install")
async def install(body: InstallBody, request: Request, admin=Admin):
    try:
        job = nodeinstall.start(nodeinstall.params(body.model_dump()), nodeinstall.credentials(body.model_dump()), admin)
    except nodeinstall.InstallError as e:
        raise HTTPException(400, str(e))
    audit.log(request, admin, "node_install_started", job["name"], host=job["host"])
    return nodeinstall.public(job)


@router.post("/{nid}/update")
async def update(nid: int, body: InstallBody, request: Request, admin=Admin):
    """Переустановка поверх: новая версия агента, те же токен, сертификат и данные."""
    row = _remote_row(nid)
    data = {**body.model_dump(), "host": row["host"]}   # адрес ноды при обновлении не меняется
    try:
        job = nodeinstall.start(nodeinstall.params(data, row), nodeinstall.credentials(data), admin, node_id=nid)
    except nodeinstall.InstallError as e:
        raise HTTPException(400, str(e))
    audit.log(request, admin, "node_update_started", row["name"], host=row["host"])
    return nodeinstall.public(job)


@router.get("/{nid}/backup")
def node_backup(nid: int, _admin=Admin):
    """Есть ли данные ноды в бэкапах панели — для восстановления переустановленного сервера."""
    _remote_row(nid)
    found = backup.node_data(nid)
    return {"archive": found[0] if found else None}


@router.post("/{nid}/remove")
async def remove_from_server(nid: int, body: InstallBody, request: Request, admin=Admin):
    """Удалить VPN с сервера ноды по SSH, затем убрать ноду из панели."""
    row = _remote_row(nid)
    try:
        job = nodeinstall.start_remove(row, nodeinstall.credentials(body.model_dump()), admin)
    except nodeinstall.InstallError as e:
        raise HTTPException(400, str(e))
    audit.log(request, admin, "node_remove_started", row["name"], host=row["host"])
    return nodeinstall.public(job)


@router.get("/jobs")
def list_jobs(_admin=Admin):
    return [nodeinstall.public(j) for j in sorted(nodeinstall.jobs.values(), key=lambda j: -j["started"])]


@router.get("/jobs/{job_id}")
def get_job(job_id: str, _admin=Admin):
    job = nodeinstall.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "задача не найдена")
    return nodeinstall.public(job)


class RenameBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)


@router.put("/{nid}")
def rename(nid: int, body: RenameBody, request: Request, admin=Admin):
    row = db.one("SELECT * FROM nodes WHERE id=?", (nid,))
    if not row:
        raise HTTPException(404, "нода не найдена")
    db.execute("UPDATE nodes SET name=? WHERE id=?", (body.name.strip(), nid))
    audit.log(request, admin, "node_renamed", row["name"], name=body.name.strip())
    return {"ok": True}


@router.delete("/{nid}")
def delete(nid: int, request: Request, admin=Admin):
    """Убрать ноду из панели: профили клиентов на ней забываются (клиенты остаются на других нодах).
    На самом сервере ничего не удаляется — для этого POST /{nid}/remove."""
    row = _remote_row(nid)
    n = db.one("SELECT COUNT(*) n FROM profiles WHERE node_id=?", (nid,))["n"]
    db.execute("DELETE FROM nodes WHERE id=?", (nid,))
    audit.log(request, admin, "node_removed", row["name"], host=row["host"], clients=n)
    return {"ok": True}
