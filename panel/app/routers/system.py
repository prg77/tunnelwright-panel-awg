"""Настройки панели, нагрузка и трафик, уведомления Telegram, журнал действий."""
import asyncio
import zoneinfo

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import audit, clients, config, db, hostmetrics, nodes, telegram, traffic
from ..security import Admin

router = APIRouter(prefix="/api", tags=["system"])

DEFAULT_TZ = "Europe/Moscow"


def timezone() -> str:
    return db.get_setting("timezone", DEFAULT_TZ)


@router.get("/settings")
def get_settings(_admin=Admin):
    return {"portal_name": db.get_setting("portal_name", "Private World"),
            "timezone": timezone(), "version": config.APP_VERSION,
            "wg_host": config.WG_HOST, "web_port": config.WEB_PORT,
            "wg_port": config.WG_PORT if nodes.local_node_id() else None,   # VPN на сервере панели
            "subnet": str(clients.SUBNET)}


class SettingsBody(BaseModel):
    portal_name: str | None = Field(default=None, min_length=1, max_length=32)
    timezone: str | None = Field(default=None, max_length=64)


@router.put("/settings")
def put_settings(body: SettingsBody, request: Request, admin=Admin):
    changes = body.model_dump(exclude_unset=True)
    if "timezone" in changes and changes["timezone"] not in zoneinfo.available_timezones():
        raise HTTPException(400, "Неизвестный часовой пояс")
    for k, v in changes.items():
        db.set_setting(k, v.strip() if isinstance(v, str) else v)
    audit.log(request, admin, "settings_changed", **changes)
    return get_settings()


@router.get("/timezones")
def timezones(_admin=Admin):
    return sorted(z for z in zoneinfo.available_timezones() if "/" in z and not z.startswith("Etc/"))


class BotBody(BaseModel):
    enabled: bool


@router.get("/telegram/bot")
def get_bot(_admin=Admin):
    s = telegram.settings()
    return {"enabled": s["bot"], "configured": bool(s["token"] and s["chat_id"])}


@router.put("/telegram/bot")
def put_bot(body: BotBody, request: Request, admin=Admin):
    telegram.set_bot(body.enabled)
    audit.log(request, admin, "telegram_bot", enabled=body.enabled)
    return get_bot()


@router.get("/audit")
def audit_log(limit: int = 200, before_id: int | None = None, _admin=Admin):
    return audit.recent(min(max(limit, 1), 500), before_id)


# ── нагрузка и трафик (дашборд) ──────────────────────────────────
@router.get("/stats")
async def stats(_admin=Admin):
    """Нагрузка сервера панели и число работающих нод."""
    m = await asyncio.to_thread(hostmetrics.snapshot)
    health = await asyncio.gather(*(n.health() for n in nodes.all_nodes()))
    m["nodes_up"], m["nodes_total"] = sum(bool(h.get("ok")) for h in health), len(health)
    return m


@router.get("/traffic/history")
def traffic_history(_admin=Admin):
    """Точки графика: [{ts: мс, tx, rx}] — суммарные счётчики всех клиентов."""
    return traffic.points()


@router.get("/traffic/usage")
def traffic_usage(_admin=Admin):
    """Суточный трафик клиентов: {id: {name, daily: {день: {tx, rx}}}}."""
    return traffic.usage()


@router.delete("/traffic")
def traffic_reset(request: Request, admin=Admin):
    traffic.reset()
    audit.log(request, admin, "traffic_reset")
    return Response(status_code=204)


# ── Telegram: уведомления ────────────────────────────────────────
def _tg_public() -> dict:
    """Токен бота в браузер не отдаётся — только признак и последние символы."""
    s = telegram.settings()
    return {"enabled": s["enabled"], "chat_id": s["chat_id"], "events": s["events"],
            "token_set": bool(s["token"]), "token_hint": s["token"][-4:] if s["token"] else "",
            "active": telegram.active(s=s)}


class TelegramBody(BaseModel):
    enabled: bool | None = None
    token: str | None = Field(default=None, max_length=100)     # пусто/не передан — оставить прежний
    chat_id: str | None = Field(default=None, max_length=64)
    events: dict[str, bool] | None = None


@router.get("/telegram")
def get_telegram(_admin=Admin):
    return _tg_public()


@router.put("/telegram")
def put_telegram(body: TelegramBody, request: Request, admin=Admin):
    s = telegram.settings()
    events = {k: v for k, v in (body.events or {}).items() if k in telegram.DEFAULT_EVENTS}
    telegram.save(s["enabled"] if body.enabled is None else body.enabled,
                  body.token.strip() if body.token and body.token.strip() else s["token"],
                  s["chat_id"] if body.chat_id is None else body.chat_id, events)
    audit.log(request, admin, "telegram_settings", enabled=telegram.settings()["enabled"])
    return _tg_public()


@router.post("/telegram/test")
async def test_telegram(_admin=Admin):
    s = telegram.settings()
    if not (s["token"] and s["chat_id"]):
        raise HTTPException(409, "укажите токен бота и Chat ID")
    on = [k for k, v in s["events"].items() if v]
    ok = await telegram.send(f"✅ <b>Тест уведомлений</b>\n\n🖥 <code>{telegram.escape(config.WG_HOST)}</code>\n"
                             f"Событий включено: {len(on)} из {len(s['events'])}",
                             token=s["token"], chat_id=s["chat_id"])
    if not ok:
        raise HTTPException(502, "Telegram не принял сообщение — проверьте токен и Chat ID")
    return {"ok": True}
