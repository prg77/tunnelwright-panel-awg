"""Уведомления администратору в Telegram о действиях с клиентами и отправка конфигов.

Сообщения собирает сервер (раньше — браузер, которому для этого приходилось знать токен бота).
Отправка идёт фоном: ответ API не ждёт Telegram.
"""
import asyncio
import io
import logging

import segno

from . import clients, routing, telegram
from .telegram import escape

log = logging.getLogger("panel.notify")

_tasks: set[asyncio.Task] = set()


def background(coro):
    """Запустить отправку фоном; ссылка на задачу держится до её завершения."""
    t = asyncio.create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


def _who(c: dict) -> str:
    return f"👤 <code>{escape(c['name'] or '')}</code> · <code>{c['ipv4']}</code>"


async def client_config(cid: int, chat_id=None, node_id: int | None = None) -> bool:
    """Конфиг (.conf) и QR клиента — по одному на каждую ноду (или на одну, если node_id)."""
    c = clients.get(cid)
    profs = [p for p in clients.profiles(cid) if node_id is None or p["node_id"] == node_id]
    if not c or not profs:
        await telegram.send("Профили клиента ещё создаются на нодах — повторите через минуту.",
                            token=telegram.settings()["token"], chat_id=chat_id)
        return False
    ok = True
    for p in profs:
        conf, fname, _ = await routing.client_config(cid, p["node_id"])
        caption = f"<b>{escape(c['name'] or '')}</b> · {escape(p['node_name'])} · <code>{c['ipv4']}</code>"
        ok &= await telegram.send_document(f"{fname[:40]}.conf", conf.encode(), f"📄 {caption}", chat_id=chat_id)
        try:
            qr = segno.make(conf, error="l")
        except segno.DataOverflowError:
            await telegram.send("QR не помещается: конфиг слишком большой (списки сетей). Отправлен только файл.",
                                token=telegram.settings()["token"], chat_id=chat_id)
            continue
        png = io.BytesIO()
        qr.save(png, kind="png", scale=6, border=2)
        ok &= await telegram.send_photo(png.getvalue(), f"📲 QR · {caption}", chat_id=chat_id)
    return ok


async def _client_added(cid: int):
    c = clients.get(cid)
    if not c or not telegram.active("on_client_add"):
        return
    await telegram.send(f"➕ <b>Новый клиент</b>\n\n{_who(c)}", event="on_client_add")
    await client_config(cid)


def client_added(cid: int):
    background(_client_added(cid))


def client_deleted(c: dict):
    background(telegram.send(f"🗑 <b>Клиент удалён</b>\n\n{_who(c)}", event="on_client_del"))


def client_toggled(c: dict, enabled: bool):
    text = "▶️ <b>Клиент включён</b>" if enabled else "⏸ <b>Клиент отключён</b>"
    background(telegram.send(f"{text}\n\n{_who(c)}", event="on_toggle"))


def limit_set(c: dict, lim: dict | None):
    if lim:
        background(telegram.send(f"⚡ <b>Лимит скорости</b>\n\n{_who(c)}\n↓ {lim['down']:g} / ↑ {lim['up']:g} Мбит/с",
                                 event="on_limit_set"))
    else:
        background(telegram.send(f"🚫 <b>Лимит скорости снят</b>\n\n{_who(c)}", event="on_limit_del"))
