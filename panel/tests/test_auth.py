import pyotp

from .conftest import PASSWORD, login


def test_first_admin_created_and_password_file_removed(client, tmp_path):
    assert not (tmp_path / "admin-password").exists()
    assert login(client).status_code == 200


def test_requires_session(client):
    assert client.get("/api/settings").status_code == 401
    assert client.get("/api/auth/session").json() == {"authenticated": False}


def test_login_logout(client):
    r = login(client)
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/api/auth/session").json()["authenticated"] is True
    assert client.get("/api/settings").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/settings").status_code == 401


def test_wrong_password_and_rate_limit(client):
    for _ in range(5):
        assert login(client, "wrong").status_code == 401
    r = login(client)  # верный пароль, но IP заблокирован
    assert r.status_code == 429


def test_totp_flow(client):
    login(client)
    setup = client.post("/api/auth/totp/setup").json()
    assert setup["secret"] and "<svg" in setup["qr_svg"]
    code = pyotp.TOTP(setup["secret"]).now()
    assert client.post("/api/auth/totp/enable", json={"code": "000000"}).status_code == 400
    assert client.post("/api/auth/totp/enable", json={"code": code}).status_code == 200
    client.post("/api/auth/logout")

    r = login(client)
    assert r.status_code == 401 and r.json()["detail"]["need_totp"] is True
    assert login(client, totp="123456").status_code == 401
    assert login(client, totp=pyotp.TOTP(setup["secret"]).now()).status_code == 200

    # отключение требует пароль и код
    assert client.post("/api/auth/totp/disable", json={"code": "1"}).status_code == 400
    r = client.post("/api/auth/totp/disable",
                    json={"code": pyotp.TOTP(setup["secret"]).now(), "password": PASSWORD})
    assert r.status_code == 200


def test_change_password(client):
    login(client)
    assert client.post("/api/auth/password", json={"current": "x", "new": "newpassword1"}).status_code == 400
    assert client.post("/api/auth/password",
                       json={"current": PASSWORD, "new": "newpassword1"}).status_code == 200
    client.post("/api/auth/logout")
    assert login(client).status_code == 401
    assert login(client, "newpassword1").status_code == 200


def test_settings_timezone_and_audit(client):
    login(client)
    assert client.put("/api/settings", json={"timezone": "Mars/Base"}).status_code == 400
    r = client.put("/api/settings", json={"timezone": "Asia/Yekaterinburg", "portal_name": "Хельсинки"})
    assert r.json()["timezone"] == "Asia/Yekaterinburg"
    assert client.get("/api/settings").json()["portal_name"] == "Хельсинки"
    assert "Europe/Moscow" in client.get("/api/timezones").json()
    actions = [e["action"] for e in client.get("/api/audit").json()]
    assert "settings_changed" in actions and "login" in actions
