"""Tunnelwright Panel AWG: panel-api."""
import asyncio
import contextlib
import logging
import os

from fastapi import FastAPI

from . import audit, backup, config, db, security, tasks
from .routers import auth, backups, catalog, clients, nodes, quotas, system, userpage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("panel")


@contextlib.asynccontextmanager
async def lifespan(_app):
    restored = backup.apply_staged_restore()   # до подключения к БД: подменяет panel.db
    db.connect()
    if restored:
        log.info("панель восстановлена из бэкапа %s", restored)
        audit.log(None, "system", "backup_restore", restored)
    first = security.ensure_first_admin()
    if isinstance(first, str):
        log.warning("\n%s\n  Создан администратор. Логин: %s  Пароль: %s\n"
                    "  Смените пароль в «Настройки → Безопасность» — эта строка остаётся в логе контейнера.\n%s",
                    "=" * 72, config.ADMIN_USERNAME, first, "=" * 72)
    elif first:
        log.info("создан администратор %s", config.ADMIN_USERNAME)
    if security.apply_initial_settings():
        log.info("применены начальные настройки установщика")
    task = None
    if os.environ.get("PANEL_DISABLE_TASKS") != "1":
        task = asyncio.create_task(tasks.run())
    yield
    if task:
        task.cancel()


app = FastAPI(title="Tunnelwright Panel AWG", version=config.APP_VERSION, lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(auth.router)
app.include_router(system.router)
app.include_router(backups.router)
app.include_router(quotas.router)
app.include_router(catalog.router)
app.include_router(userpage.router)
app.include_router(nodes.router)
app.include_router(clients.router)


@app.get("/api/health")
def health():
    return {"ok": True, "version": config.APP_VERSION}
