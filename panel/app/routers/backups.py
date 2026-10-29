"""Бэкапы: настройки, ручной запуск, список и скачивание архивов."""
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import audit, backup, config
from ..security import Admin

router = APIRouter(prefix="/api/backups", tags=["backups"])


@router.get("")
def get_backups(_admin=Admin):
    # restore: восстановление из интерфейса — только у панели без VPN на её сервере
    return {"settings": backup.public_settings(), "files": backup.list_backups(), "restore": not config.LOCAL_NODE_URL}


class BackupSettings(BaseModel):
    schedule: str | None = None
    hour: int | None = Field(default=None, ge=0, le=23)
    telegram: bool | None = None
    password: str | None = Field(default=None, max_length=256)


@router.put("/settings")
def put_settings(body: BackupSettings, request: Request, admin=Admin):
    try:
        backup.save_settings(body.schedule, body.hour, body.telegram, body.password or None)
    except ValueError as e:
        raise HTTPException(400, str(e))
    audit.log(request, admin, "backup_settings", schedule=body.schedule, hour=body.hour,
              telegram=body.telegram, password_changed=bool(body.password))
    return backup.public_settings()


@router.post("/run")
async def run_backup(request: Request, admin=Admin):
    res = await backup.run()
    audit.log(request, admin, "backup_run", res.get("file"), ok=res["ok"], telegram=res.get("telegram"))
    if not res["ok"]:
        raise HTTPException(400, res["error"])
    return res


@router.get("/file/{name}")
def download(name: str, request: Request, admin=Admin):
    path = backup.path_of(name)
    if not path:
        raise HTTPException(404, "архив не найден")
    audit.log(request, admin, "backup_download", path.name)
    return FileResponse(path, media_type="application/zip", filename=path.name)


@router.post("/restore")
async def restore(request: Request, admin=Admin):
    """Восстановление из архива: тело — сам .zip, пароль — в заголовке X-Backup-Password
    (encodeURIComponent: пароль может быть не в latin-1). После ответа panel-api перезапускается."""
    data = await request.body()
    if not data:
        raise HTTPException(400, "пустой архив")
    password = unquote(request.headers.get("x-backup-password", ""))
    try:
        info = backup.stage_restore(data, password, request.query_params.get("name", ""))
    except ValueError as e:
        audit.log(request, admin, "backup_restore_failed", request.query_params.get("name"), error=str(e))
        raise HTTPException(400, str(e))
    backup.restart_soon()
    return {"ok": True, "version": info.get("version"), "created": info.get("created"),
            "host": info.get("host"), "nodes": [n["name"] for n in info.get("nodes", []) if not n.get("local")],
            "local_dropped": any(n.get("local") for n in info.get("nodes", []))}
