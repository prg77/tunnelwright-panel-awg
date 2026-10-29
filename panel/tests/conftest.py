import importlib

import pytest
from fastapi.testclient import TestClient

pytest_plugins = ["tests.fakes"]   # фикстура cluster — фейковые ноды

PASSWORD = "correct horse battery"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Чистая БД и первый администратор admin/PASSWORD на каждый тест."""
    pw = tmp_path / "admin-password"
    pw.write_text(PASSWORD)
    monkeypatch.setenv("PANEL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PANEL_ADMIN_PASSWORD_FILE", str(pw))
    monkeypatch.setenv("PANEL_COOKIE_SECURE", "false")
    monkeypatch.setenv("PANEL_DISABLE_TASKS", "1")
    from app import config, db, security, main
    for m in (config, db, security, main):
        importlib.reload(m)
    with TestClient(main.app) as c:
        yield c


def login(client, password=PASSWORD, **kw):
    return client.post("/api/auth/login", json={"username": "admin", "password": password, **kw})
