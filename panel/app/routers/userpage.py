"""Страница пользователя: публичные /u/<токен> и управление ссылками и шаблоном."""

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from .. import audit, db, nodes, routing, userpage
from ..security import Admin, client_ip

router = APIRouter(tags=["userpage"])

HEADERS = {"Content-Security-Policy": userpage.CSP, "Cache-Control": "no-store",
           "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex, nofollow"}


def _plain(code: int, text: str) -> HTMLResponse:
    return HTMLResponse(f'<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
                        f'<title>{code}</title><p style="font:16px system-ui;margin:40px;text-align:center">{text}</p>',
                        status_code=code, headers=HEADERS)


def _client(token: str, request: Request) -> int | None:
    ip = client_ip(request)
    if userpage.blocked(ip):
        raise HTTPException(429)
    if not userpage.settings()["enabled"]:
        return None
    return userpage.resolve(token, ip)


# ── публичная часть ────────────────────────────────────────────
PING = "tunnelwright-user-page"


@router.get("/u/ping", include_in_schema=False)
def user_page_ping():
    """По этому ответу «Проверить» в настройках узнаёт, что адрес ссылок ведёт на эту панель.
    Объявлен до /u/{token}: иначе «ping» считался бы неверным токеном."""
    return PlainTextResponse(PING, headers={"Cache-Control": "no-store"})


@router.get("/api/host-check", include_in_schema=False)
def host_check(request: Request):
    """Для nginx (auth_request): на отдельном адресе страниц пользователей панель не открывается."""
    host = (request.headers.get("host") or "").split(":")[0].lower()
    return Response(status_code=403 if host and host == userpage.user_host() else 204)


@router.get("/u/{token}", include_in_schema=False)
async def user_page(token: str, request: Request):
    try:
        cid = _client(token, request)
    except HTTPException:
        return _plain(429, "Слишком много запросов. Попробуйте позже.")
    if cid is None:
        return _plain(404, "Ссылка недействительна. Запросите новую у администратора.")
    return HTMLResponse(await userpage.render(cid, token), headers=HEADERS)


@router.get("/u/{token}/config", include_in_schema=False)
async def user_config(token: str, request: Request, node: int | None = None):
    try:
        cid = _client(token, request)
    except HTTPException:
        return _plain(429, "Слишком много запросов. Попробуйте позже.")
    if cid is None:
        return _plain(404, "Ссылка недействительна. Запросите новую у администратора.")
    d = await userpage.page_data(cid)
    if not userpage.can_download(d):
        return _plain(403, "Доступ сейчас не активен — обратитесь к администратору.")
    try:
        text, name, _ = await routing.client_config(cid, node)
    except (nodes.NodeError, ValueError):
        return _plain(503, "Конфигурация временно недоступна. Попробуйте позже.")
    audit.log(request, "user-page", "user_config_download", str(cid), name=name, node=node)
    return PlainTextResponse(text, headers={**HEADERS, "Content-Disposition": routing.attachment(name, f"client-{cid}")})


# ── администрирование ──────────────────────────────────────────
class PageBody(BaseModel):
    enabled: bool | None = None
    show_qr: bool | None = None
    template: str | None = None
    user_url: str | None = Field(default=None, max_length=200)


@router.get("/api/user-page")
def get_page(_admin=Admin):
    return {**userpage.settings(), "default_template": userpage.DEFAULT_TEMPLATE,
            "placeholders": userpage.PLACEHOLDERS}


@router.put("/api/user-page")
def put_page(body: PageBody, request: Request, admin=Admin):
    try:
        s = userpage.save_settings(body.enabled, body.template, body.show_qr, body.user_url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    audit.log(request, admin, "user_page_settings", enabled=s["enabled"], custom=s["custom"],
              **({"user_url": s["user_url"]} if body.user_url is not None else {}))
    return {**s, "default_template": userpage.DEFAULT_TEMPLATE, "placeholders": userpage.PLACEHOLDERS}


class CheckBody(BaseModel):
    url: str = Field(max_length=200)


@router.post("/api/user-page/check")
async def check_url(body: CheckBody, _admin=Admin):
    """Открывается ли <адрес>/u/ping снаружи и отвечает ли там эта панель (с проверкой сертификата)."""
    try:
        url = userpage.normalize_url(body.url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not url:
        raise HTTPException(400, "адрес не задан")
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as c:
            r = await c.get(f"{url}/u/ping")
    except httpx.HTTPError as e:
        return {"ok": False, "message": f"не открывается: {type(e).__name__}: {str(e)[:150]}"}
    if r.status_code == 200 and r.text.strip() == PING:
        return {"ok": True, "message": f"{url} ведёт на эту панель"}
    return {"ok": False, "message": f"{url}/u/ping ответил {r.status_code} — запрос не доходит до панели "
                                    "(проверьте обратный прокси и DNS)"}


@router.post("/api/user-page/preview")
def preview(body: PageBody, _admin=Admin):
    """Шаблон на примере вымышленного клиента — без ключей и реальных данных."""
    template = body.template if body.template is not None else userpage.settings()["template"]
    if len(template) > userpage.MAX_TEMPLATE:
        raise HTTPException(400, "шаблон слишком большой")
    return {"html": userpage.render_sample(template)}


@router.get("/api/user-links")
def links(_admin=Admin):
    """{clientId: {token, last_seen}}"""
    return userpage.all_links()


@router.post("/api/clients/{cid}/link")
def issue_link(cid: int, request: Request, regenerate: bool = False, admin=Admin):
    if not db.one("SELECT id FROM clients WHERE id=?", (cid,)):
        raise HTTPException(404, "клиент не найден")
    had = userpage.link(cid)
    token = userpage.issue(cid, regenerate)
    if token != had:
        audit.log(request, admin, "user_link_regenerated" if had else "user_link_created", str(cid))
    return {"token": token, "path": f"/u/{token}"}


@router.delete("/api/clients/{cid}/link")
def revoke_link(cid: int, request: Request, admin=Admin):
    if userpage.link(cid):
        userpage.revoke(cid)
        audit.log(request, admin, "user_link_revoked", str(cid))
    return {"ok": True}
