"""Администраторы, пароли (argon2), TOTP, сессии, ограничение попыток входа."""
import hashlib
import secrets
import time
from collections import defaultdict, deque

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request

from . import config, db

_ph = PasswordHasher()
_fails: dict[str, deque] = defaultdict(deque)


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def client_ip(request: Request) -> str:
    # web (nginx) — единственный, кто ходит в panel-api, и выставляет X-Real-IP
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "")


# ── ограничение попыток входа ───────────────────────────────────
def login_blocked(ip: str) -> int:
    """Сколько секунд осталось до разблокировки (0 — не заблокирован)."""
    q = _fails[ip]
    now = time.time()
    while q and now - q[0] > config.LOGIN_WINDOW_SEC:
        q.popleft()
    if len(q) >= config.LOGIN_MAX_FAILS:
        return int(config.LOGIN_WINDOW_SEC - (now - q[0])) + 1
    return 0


def login_failed(ip: str):
    _fails[ip].append(time.time())


def login_succeeded(ip: str):
    _fails.pop(ip, None)


# ── TOTP ────────────────────────────────────────────────────────
def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, username: str, issuer: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=issuer)


def verify_totp(secret: str, code: str) -> bool:
    return bool(secret) and pyotp.TOTP(secret).verify((code or "").replace(" ", ""), valid_window=1)


# ── сессии ──────────────────────────────────────────────────────
def _sid(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(admin_id: int, request: Request) -> str:
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    db.execute("INSERT INTO sessions(id, admin_id, created_at, expires_at, ip, user_agent) "
               "VALUES(?,?,?,?,?,?)",
               (_sid(token), admin_id, now, now + config.SESSION_TTL_DAYS * 86400,
                client_ip(request), request.headers.get("user-agent", "")[:200]))
    db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
    return token


def drop_session(token: str):
    if token:
        db.execute("DELETE FROM sessions WHERE id=?", (_sid(token),))


def drop_admin_sessions(admin_id: int, keep_token: str = ""):
    db.execute("DELETE FROM sessions WHERE admin_id=? AND id<>?", (admin_id, _sid(keep_token)))


def session_admin(request: Request) -> dict | None:
    token = request.cookies.get(config.SESSION_COOKIE, "")
    if not token:
        return None
    return db.one("SELECT a.* FROM sessions s JOIN admins a ON a.id=s.admin_id "
                  "WHERE s.id=? AND s.expires_at>?", (_sid(token), int(time.time())))


def require_admin(request: Request) -> dict:
    admin = session_admin(request)
    if not admin:
        raise HTTPException(401, "unauthorized")
    return admin


Admin = Depends(require_admin)


def ensure_first_admin() -> bool | str:
    """Первый запуск: создаём администратора из пароля, который положил установщик.
    Без установщика (стек Portainer) файла нет — пароль генерируется и возвращается, чтобы
    показать его один раз в логе контейнера. Возвращает False, если администратор уже есть."""
    if db.one("SELECT id FROM admins LIMIT 1"):
        return False
    generated = None
    try:
        password = config.ADMIN_PASSWORD_FILE.read_text().strip()
    except OSError:
        password = generated = secrets.token_urlsafe(12)
    if len(password) < 8:
        return False
    db.execute("INSERT INTO admins(username, password_hash) VALUES(?, ?)",
               (config.ADMIN_USERNAME, hash_password(password)))
    if generated:
        return generated
    try:
        config.ADMIN_PASSWORD_FILE.unlink()
    except OSError:
        pass  # смонтирован только для чтения — установщик удалит сам
    return True


def apply_initial_settings():
    """Имя панели и Telegram, введённые в установщике при чистой установке."""
    import json
    from . import telegram
    try:
        s = json.loads(config.INIT_SETTINGS_FILE.read_text())
    except (OSError, ValueError):
        return False
    if s.get("portal_name"):
        db.set_setting("portal_name", str(s["portal_name"]).strip()[:32])
    if s.get("timezone"):
        db.set_setting("timezone", str(s["timezone"]))
    tg = s.get("telegram") or {}
    if tg.get("token") and tg.get("chat_id"):
        telegram.save(True, str(tg["token"]), str(tg["chat_id"]), None)
    try:
        config.INIT_SETTINGS_FILE.unlink()
    except OSError:
        pass
    return True


def reset_admin() -> str:
    """Новый случайный пароль, 2FA выключена, все сессии завершены. Возвращает пароль."""
    password = secrets.token_urlsafe(12)
    admin = db.one("SELECT id FROM admins WHERE username=?", (config.ADMIN_USERNAME,))
    if admin:
        db.execute("UPDATE admins SET password_hash=?, totp_enabled=0, totp_secret=NULL WHERE id=?",
                   (hash_password(password), admin["id"]))
        db.execute("DELETE FROM sessions WHERE admin_id=?", (admin["id"],))
    else:
        db.execute("INSERT INTO admins(username, password_hash) VALUES(?, ?)",
                   (config.ADMIN_USERNAME, hash_password(password)))
    return password
