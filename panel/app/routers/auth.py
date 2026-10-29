"""Вход, выход, сессия, смена пароля, TOTP 2FA."""
import segno
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .. import audit, config, db, security
from ..security import Admin

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str = Field(default=config.ADMIN_USERNAME, max_length=64)
    password: str = Field(max_length=256)
    totp: str | None = Field(default=None, max_length=12)


def _set_cookie(response: Response, request: Request, token: str):
    # Secure — когда браузер пришёл по HTTPS (схему передаёт web в X-Forwarded-Proto). Панель за
    # обратным прокси NAS, открытая напрямую по HTTP из локальной сети, иначе не смогла бы войти.
    secure = config.COOKIE_SECURE and request.url.scheme == "https"
    response.set_cookie(config.SESSION_COOKIE, token, max_age=config.SESSION_TTL_DAYS * 86400,
                        httponly=True, secure=secure, samesite="strict", path="/")


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response):
    ip = security.client_ip(request)
    wait = security.login_blocked(ip)
    if wait:
        raise HTTPException(429, f"Слишком много попыток. Повторите через {wait // 60 + 1} мин.")
    admin = db.one("SELECT * FROM admins WHERE username=?", (body.username.strip(),))
    if not admin or not security.verify_password(admin["password_hash"], body.password):
        security.login_failed(ip)
        audit.log(request, body.username[:64], "login_failed")
        raise HTTPException(401, "Неверный логин или пароль")
    if admin["totp_enabled"]:
        if not body.totp:
            # пароль верный, нужен второй фактор — попытку не считаем неудачной
            raise HTTPException(401, detail={"need_totp": True, "message": "Введите код 2FA"})
        if not security.verify_totp(admin["totp_secret"], body.totp):
            security.login_failed(ip)
            audit.log(request, admin, "login_failed", details="totp")
            raise HTTPException(401, "Неверный код 2FA")
    security.login_succeeded(ip)
    _set_cookie(response, request, security.create_session(admin["id"], request))
    audit.log(request, admin, "login")
    return {"ok": True, "username": admin["username"]}


@router.post("/logout")
def logout(request: Request, response: Response):
    security.drop_session(request.cookies.get(config.SESSION_COOKIE, ""))
    response.delete_cookie(config.SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/session")
def session(request: Request):
    admin = security.session_admin(request)
    if not admin:
        return {"authenticated": False}
    return {"authenticated": True, "username": admin["username"],
            "totp_enabled": bool(admin["totp_enabled"])}


class PasswordBody(BaseModel):
    current: str = Field(max_length=256)
    new: str = Field(min_length=8, max_length=256)


@router.post("/password")
def change_password(body: PasswordBody, request: Request, admin=Admin):
    if not security.verify_password(admin["password_hash"], body.current):
        raise HTTPException(400, "Текущий пароль неверен")
    db.execute("UPDATE admins SET password_hash=? WHERE id=?",
               (security.hash_password(body.new), admin["id"]))
    security.drop_admin_sessions(admin["id"], request.cookies.get(config.SESSION_COOKIE, ""))
    audit.log(request, admin, "password_changed")
    return {"ok": True}


@router.post("/totp/setup")
def totp_setup(request: Request, admin=Admin):
    """Новый секрет (ещё не включён): вернуть QR и ключ для приложения-аутентификатора."""
    if admin["totp_enabled"]:
        raise HTTPException(400, "2FA уже включена")
    secret = security.new_totp_secret()
    db.execute("UPDATE admins SET totp_secret=? WHERE id=?", (secret, admin["id"]))
    issuer = db.get_setting("portal_name", "Tunnelwright Panel AWG") or "Tunnelwright Panel AWG"
    uri = security.totp_uri(secret, admin["username"], issuer)
    return {"secret": secret, "uri": uri, "qr_svg": segno.make(uri, error="m").svg_inline(scale=5)}


class CodeBody(BaseModel):
    code: str = Field(max_length=12)
    password: str | None = Field(default=None, max_length=256)


@router.post("/totp/enable")
def totp_enable(body: CodeBody, request: Request, admin=Admin):
    if not security.verify_totp(admin["totp_secret"], body.code):
        raise HTTPException(400, "Код не подходит — проверьте время на телефоне")
    db.execute("UPDATE admins SET totp_enabled=1 WHERE id=?", (admin["id"],))
    audit.log(request, admin, "totp_enabled")
    return {"ok": True}


@router.post("/totp/disable")
def totp_disable(body: CodeBody, request: Request, admin=Admin):
    if not admin["totp_enabled"]:
        return {"ok": True}
    if not (body.password and security.verify_password(admin["password_hash"], body.password)) \
            or not security.verify_totp(admin["totp_secret"], body.code):
        raise HTTPException(400, "Нужны текущий пароль и код 2FA")
    db.execute("UPDATE admins SET totp_enabled=0, totp_secret=NULL WHERE id=?", (admin["id"],))
    audit.log(request, admin, "totp_disabled")
    return {"ok": True}
