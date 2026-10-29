"""панель в Portainer на NAS — без установщика и хоста."""
import asyncio
import importlib
from urllib.parse import quote

import httpx
from fastapi.testclient import TestClient

from app import backup, config, db, nodes

from .conftest import login


def test_first_admin_password_generated_without_installer(tmp_path, monkeypatch):
    monkeypatch.setenv("PANEL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PANEL_ADMIN_PASSWORD_FILE", str(tmp_path / "нет-файла"))
    monkeypatch.setenv("PANEL_DISABLE_TASKS", "1")
    from app import main, security
    for m in (config, db, security, main):
        importlib.reload(m)
    db.connect()
    pw = security.ensure_first_admin()
    assert isinstance(pw, str) and len(pw) >= 12
    assert security.ensure_first_admin() is False            # уже есть — второй раз не создаётся
    with TestClient(main.app) as c:
        assert login(c, pw).status_code == 200


def test_session_cookie_secure_only_over_https(client, monkeypatch):
    monkeypatch.setattr(config, "COOKIE_SECURE", True)
    plain = login(client)                                    # HTTP напрямую в локальной сети
    assert "secure" not in plain.headers["set-cookie"].lower()
    https = TestClient(client.app, base_url="https://testserver")
    assert "secure" in login(https).headers["set-cookie"].lower()


def _archive(tmp_path, password="backup-pass-123", local=False) -> bytes:
    import json
    import pyzipper
    snap = tmp_path / "snap.db"
    backup._panel_db_copy(snap)
    path = tmp_path / "b.zip"
    with pyzipper.AESZipFile(path, "w", encryption=pyzipper.WZ_AES) as z:
        z.setpassword(password.encode())
        z.write(snap, "panel/panel.db")
        z.writestr("backup-info.json", json.dumps({"version": "1.0.0", "created": 1, "host": "203.0.113.1",
                                                    "nodes": [{"id": 1, "name": "Этот сервер", "local": local}]}))
    return path.read_bytes()


def test_restore_from_ui(client, monkeypatch, tmp_path):
    from app import clients
    monkeypatch.setattr(config, "LOCAL_NODE_URL", "")
    restarts = []
    monkeypatch.setattr(backup, "restart_soon", lambda: restarts.append(1))
    login(client)
    assert client.get("/api/backups").json()["restore"] is True
    clients.create("из-бэкапа")
    data = _archive(tmp_path, local=True)
    db.execute("DELETE FROM clients")

    def post(body, pw, name="vpn-panel-backup-20261029-0400.zip"):
        return client.post(f"/api/backups/restore?name={name}", content=body,
                           headers={"Content-Type": "application/zip", "X-Backup-Password": quote(pw)})
    assert post(data, "неверный").json()["detail"] == "неверный пароль бэкапа"
    assert post(b"not a zip", "x").status_code == 400
    r = post(data, "backup-pass-123")
    assert r.status_code == 200 and r.json()["local_dropped"] and restarts == [1]
    assert (config.DATA_DIR / "backups" / "vpn-panel-backup-20261029-0400.zip").exists()

    # перезапуск: подмена БД до подключения
    db._conn.close()
    assert backup.apply_staged_restore() == "vpn-panel-backup-20261029-0400.zip"
    db.connect()
    assert [c["name"] for c in clients.all_clients()] == ["из-бэкапа"]
    assert (config.DATA_DIR / "panel.db.before-restore").exists()
    assert backup.apply_staged_restore() is None             # повторно не применяется


def test_restore_from_ui_refused_with_local_vpn(client, tmp_path):
    login(client)
    assert config.LOCAL_NODE_URL and client.get("/api/backups").json()["restore"] is False
    r = client.post("/api/backups/restore", content=_archive(tmp_path), headers={"X-Backup-Password": "backup-pass-123"})
    assert r.status_code == 400 and "tunnelwright restore" in r.json()["detail"]


def test_ip_locked_node_explains_how_to_fix(client, monkeypatch):
    nid = db.execute("INSERT INTO nodes(name, url, token, is_local, host) "
                     "VALUES('Швеция', 'https://198.51.100.7:8711', 'tok', 0, '198.51.100.7')")
    node = nodes.get(nid)
    transport = httpx.MockTransport(lambda req: httpx.Response(403, json={"detail": "forbidden"}))
    monkeypatch.setattr(nodes.Node, "_client", lambda self, t: httpx.AsyncClient(transport=transport))
    try:
        asyncio.run(nodes.Node.req(node, "GET", "/health"))
    except nodes.NodeError as e:
        assert "прежнего IP панели" in str(e)
    else:
        raise AssertionError("ожидалась NodeError")


def test_public_url(monkeypatch):
    monkeypatch.setenv("PANEL_WG_HOST", "203.0.113.1")
    monkeypatch.delenv("PANEL_PUBLIC_URL", raising=False)
    importlib.reload(config)
    assert config.PUBLIC_URL == "https://203.0.113.1:58821" and config.NODE_IP_LOCK
    monkeypatch.setenv("PANEL_PUBLIC_URL", "https://vpn.example.com/")
    monkeypatch.setenv("PANEL_NODE_IP_LOCK", "false")
    importlib.reload(config)
    assert config.PUBLIC_URL == "https://vpn.example.com" and not config.NODE_IP_LOCK
