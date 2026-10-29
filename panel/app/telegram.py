"""Telegram: настройки, отправка сообщений, документов и фото через Bot API."""
import base64
import logging

import httpx

from . import db

log = logging.getLogger("panel.telegram")

DEFAULT_EVENTS = {"on_start": True, "on_client_add": True, "on_client_del": False,
                  "on_limit_set": False, "on_limit_del": False, "on_toggle": False,
                  "on_health_fail": True, "on_health_ok": False}


def settings() -> dict:
    s = db.get_setting("telegram", {}) or {}
    events = {**DEFAULT_EVENTS, **(s.get("events") or {})}
    return {"enabled": bool(s.get("enabled")), "token": s.get("token", ""),
            "chat_id": s.get("chat_id", ""), "events": events, "bot": bool(s.get("bot"))}


def save(enabled: bool, token: str, chat_id: str, events: dict | None, bot: bool | None = None):
    cur = settings()
    db.set_setting("telegram", {"enabled": enabled, "token": token.strip(), "chat_id": chat_id.strip(),
                                "events": {**cur["events"], **(events or {})},
                                "bot": cur["bot"] if bot is None else bool(bot)})


def set_bot(enabled: bool):
    s = db.get_setting("telegram", {}) or {}
    s["bot"] = bool(enabled)
    db.set_setting("telegram", s)


def active(event: str | None = None, s: dict | None = None) -> bool:
    s = s or settings()
    if not (s["enabled"] and s["token"] and s["chat_id"]):
        return False
    return event is None or s["events"].get(event, True)


async def _call(token, method, *, data=None, files=None) -> bool:
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(f"https://api.telegram.org/bot{token}/{method}", data=data, files=files)
        if r.status_code != 200:
            log.warning("telegram %s: %s %s", method, r.status_code, r.text[:200])
        return r.status_code == 200
    except httpx.HTTPError as e:
        log.warning("telegram %s: %s", method, e)
        return False


async def send(text: str, *, token=None, chat_id=None, event=None) -> bool:
    s = settings()
    if token is None and not active(event, s):
        return False
    return await _call(token or s["token"], "sendMessage",
                       data={"chat_id": chat_id or s["chat_id"], "text": text, "parse_mode": "HTML"})


async def send_document(filename: str, content: bytes, caption: str = "", *, token=None, chat_id=None) -> bool:
    s = settings()
    return await _call(token or s["token"], "sendDocument",
                       data={"chat_id": chat_id or s["chat_id"], "caption": caption, "parse_mode": "HTML"},
                       files={"document": (filename, content, "application/octet-stream")})


async def send_photo_b64(photo_b64: str, caption: str = "", *, token=None, chat_id=None) -> bool:
    s = settings()
    if "," in photo_b64:
        photo_b64 = photo_b64.split(",", 1)[1]
    return await _call(token or s["token"], "sendPhoto",
                       data={"chat_id": chat_id or s["chat_id"], "caption": caption, "parse_mode": "HTML"},
                       files={"photo": ("qr.png", base64.b64decode(photo_b64), "image/png")})


async def send_photo(png: bytes, caption: str = "", *, chat_id=None) -> bool:
    s = settings()
    return await _call(s["token"], "sendPhoto",
                       data={"chat_id": chat_id or s["chat_id"], "caption": caption, "parse_mode": "HTML"},
                       files={"photo": ("qr.png", png, "image/png")})


async def api(method: str, http_timeout: float = 20, **params) -> dict | None:
    """Произвольный вызов Bot API (для бота). Возвращает result или None.
    http_timeout — таймаут HTTP-запроса; params — параметры метода Bot API (в т.ч. его timeout)."""
    s = settings()
    try:
        async with httpx.AsyncClient(timeout=http_timeout) as c:
            r = await c.post(f"https://api.telegram.org/bot{s['token']}/{method}", json=params)
        data = r.json()
        return data.get("result") if data.get("ok") else None
    except (httpx.HTTPError, ValueError) as e:
        log.warning("telegram %s: %s", method, e)
        return None


def escape(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
