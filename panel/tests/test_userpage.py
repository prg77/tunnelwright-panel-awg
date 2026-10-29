"""страница пользователя по личной ссылке."""
import pytest

from app import db, userpage, users

from .conftest import login



@pytest.fixture()
def env(client, cluster):
    cluster[cluster.local].add("Маша <телефон>", "10.8.0.5", expires="2099-01-01T00:00:00.000Z")
    userpage._misses.clear()
    login(client)
    client.get("/api/clients")
    pid = db.one("SELECT user_id FROM clients WHERE ipv4='10.8.0.5'")["user_id"]   # ссылка — у пользователя
    return client, cluster, pid


def test_markup_escapes_and_formats():
    out = userpage.render_markup(
        "# Привет\n<script>alert(1)</script>\n**жирный** и `код`\n"
        "[ok](https://example.com) [bad](javascript:alert(1))\n\n"
        "1. раз\n  - вложенный\n  - ещё\n2. два\n- другой список")
    assert "<h2>Привет</h2>" in out
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert "<b>жирный</b>" in out and "<code>код</code>" in out
    assert '<a href="https://example.com"' in out and 'href="javascript' not in out
    assert out.count("<ol>") == 1 and out.count("<ul>") == 2
    assert out.count("<li>") == out.count("</li>") == 5


def test_fill_escapes_values():
    html = userpage.fill("<p>{name} {unknown}</p>", {"name": "<b>x</b>"})
    assert html == "<p>&lt;b&gt;x&lt;/b&gt; {unknown}</p>"


def test_link_lifecycle_and_page(env):
    c, n, pid = env
    r = c.post(f"/api/users/{pid}/link").json()
    token = r["token"]
    assert r["path"] == f"/u/{token}" and c.post(f"/api/users/{pid}/link").json()["token"] == token

    c.cookies.clear()                                 # страница открывается без входа
    page = c.get(f"/u/{token}")
    assert page.status_code == 200
    assert "default-src 'none'" in page.headers["content-security-policy"]
    assert "Маша &lt;телефон&gt;" in page.text and page.text.count("<svg") == 2 and "Активен" in page.text   # логотип и QR
    assert f'href="{token}/config?c=' in page.text and "01.01.2099" in page.text
    conf = c.get(f"/u/{token}/config")
    assert conf.status_code == 200 and "PrivateKey" in conf.text and "attachment" in conf.headers["content-disposition"]
    assert db.one("SELECT last_seen FROM user_links WHERE user_id=?", (pid,))["last_seen"]

    users.update(pid, enabled=False)
    assert "Отключён" in c.get(f"/u/{token}").text
    assert c.get(f"/u/{token}/config").status_code == 403

    login(c)
    new = c.post(f"/api/users/{pid}/link?regenerate=true").json()["token"]
    assert new != token
    c.cookies.clear()
    assert c.get(f"/u/{token}").status_code == 404
    login(c)
    c.delete(f"/api/users/{pid}/link")
    assert c.get("/api/user-links").json() == {}
    assert c.get(f"/u/{new}").status_code == 404


def test_expired_and_disabled_feature(env):
    c, n, pid = env
    token = c.post(f"/api/users/{pid}/link").json()["token"]
    users.update(pid, expires_at="2020-01-01T00:00:00.000Z")
    assert "Срок истёк" in c.get(f"/u/{token}").text
    assert c.get(f"/u/{token}/config").status_code == 403
    c.put("/api/user-page", json={"enabled": False})
    assert c.get(f"/u/{token}").status_code == 404


def test_bruteforce_limit(env):
    c, _, pid = env
    token = c.post(f"/api/users/{pid}/link").json()["token"]
    for _ in range(userpage.MISS_LIMIT):
        assert c.get("/u/" + "x" * 32).status_code == 404
    assert c.get(f"/u/{token}").status_code == 429


def test_template_settings_and_preview(env):
    c, _, _ = env
    s = c.get("/api/user-page").json()
    assert s["enabled"] and not s["custom"] and s["template"] == s["default_template"]
    s = c.put("/api/user-page", json={"template": "# Здравствуйте, {name}", "show_qr": False}).json()
    assert s["custom"] and s["template"] == "# Здравствуйте, {name}" and s["show_qr"] is False
    p = c.post("/api/user-page/preview", json={"template": "Срок: {expires}, <i>"}).json()["html"]
    assert "Срок: 31.12.2026" in p and "&lt;i&gt;" in p and "PrivateKey" not in p
    s = c.put("/api/user-page", json={"template": s["default_template"]}).json()
    assert not s["custom"]
    assert c.put("/api/user-page", json={"template": "x" * 20001}).status_code == 400


# ── адрес ссылок: отдельный домен для страниц пользователей ──
def test_user_url_setting_and_host_restriction(client, monkeypatch):
    login(client)
    assert client.get("/api/user-page").json()["user_url"] == ""
    assert client.put("/api/user-page", json={"user_url": "https://example.com/path"}).status_code == 400
    assert client.put("/api/user-page", json={"user_url": "ftp://example.com"}).status_code == 400
    r = client.put("/api/user-page", json={"user_url": "https://Example.com/"})
    assert r.status_code == 200 and r.json()["user_url"] == "https://example.com"
    assert userpage.user_host() == "example.com"

    # на домене ссылок: интерфейс (host-check для nginx) и API — нет, /u/ — да
    other = {"Host": "example.com"}
    assert client.get("/api/host-check", headers=other).status_code == 403
    assert client.get("/api/clients", headers=other).status_code == 404
    assert client.get("/u/ping", headers=other).text == "tunnelwright-user-page"
    assert client.get("/u/" + "x" * 30, headers=other).status_code == 404   # обычная страница «ссылка недействительна»
    # на адресе панели всё как раньше
    assert client.get("/api/host-check", headers={"Host": "panel.example.com"}).status_code == 204
    assert client.get("/api/clients", headers={"Host": "panel.example.com"}).status_code == 200

    # пусто — ссылки снова на адресе панели, ограничения нет
    assert client.put("/api/user-page", json={"user_url": ""}).json()["user_url"] == ""
    assert userpage.user_host() is None
    assert client.get("/api/host-check", headers=other).status_code == 204


def test_user_url_initial_value_from_env(client, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "USER_URL", "https://example.com")
    login(client)
    assert client.get("/api/user-page").json()["user_url"] == "https://example.com"
    client.put("/api/user-page", json={"user_url": ""})          # сохранённая настройка важнее переменной
    assert client.get("/api/user-page").json()["user_url"] == ""


def test_user_url_check(client, monkeypatch):
    import httpx
    from app.routers import userpage as router

    class Fake:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, url):
            if "good" in url:
                return httpx.Response(200, text=router.PING)
            if "down" in url:
                raise httpx.ConnectError("refused")
            return httpx.Response(404, text="nope")
    monkeypatch.setattr(router.httpx, "AsyncClient", Fake)
    login(client)
    assert client.post("/api/user-page/check", json={"url": "https://good.example"}).json()["ok"] is True
    bad = client.post("/api/user-page/check", json={"url": "https://other.example"}).json()
    assert bad["ok"] is False and "404" in bad["message"]
    assert client.post("/api/user-page/check", json={"url": "https://down.example"}).json()["ok"] is False
    assert client.post("/api/user-page/check", json={"url": "not a url"}).status_code == 400
