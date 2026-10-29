"""Квоты трафика клиентов."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import audit, db, quotas
from ..security import Admin

router = APIRouter(prefix="/api", tags=["quotas"])


@router.get("/quotas")
def list_quotas(_admin=Admin):
    """{clientId: {limit_bytes, used_bytes, blocked}} — расход за текущий месяц."""
    return quotas.get_all(db.get_setting("timezone", "Europe/Moscow"))


class QuotaBody(BaseModel):
    limit_gb: float | None = Field(default=None, ge=0, le=100000)


@router.put("/clients/{cid}/quota")
def set_quota(cid: int, body: QuotaBody, request: Request, admin=Admin):
    if not db.one("SELECT id FROM clients WHERE id=?", (cid,)):
        raise HTTPException(404, "клиент не найден")
    limit = int(body.limit_gb * 1024**3) if body.limit_gb else None
    quotas.set_quota(cid, limit)
    audit.log(request, admin, "quota_set" if limit else "quota_removed", str(cid), limit_gb=body.limit_gb)
    return {"ok": True}
