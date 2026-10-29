"""бэкапы, квоты трафика, Telegram-бот."""
import asyncio
import time

import pytest

from app import backup, bot, clients, db, quotas, telegram

from .conftest import login


@pytest.fixture()
def node(client, cluster, monkeypatch):
    """Локальная нода с тремя клиентами (в панели — три пользователя); сообщения Telegram — в node.sent."""
    agent = cluster[cluster.local]
    for i, name in enumerate(("Маша телефон", "Маша ноутбук", "Петя"), 5):
        agent.add(name, f"10.8.0.{i}")
    asyncio.run(clients.reconcile_all())
    sent = []

    async def fake_send(text, **kw):
        sent.append(text)
        return True
    monkeypatch.setattr(telegram, "send", fake_send)
    agent.sent = sent
    agent.pid = {r["name"]: r["id"] for r in db.query("SELECT id, name FROM users")}    # id пользователей
    return agent


# ── бэкап ───────────────────────────────────────────────────────
def test_backup_requires_password_and_encrypts(node, tmp_path):
    with pytest.raises(ValueError):
        backup.save_settings(password="short")
    res = asyncio.run(backup.run(send_telegram=False))
    assert not res["ok"] and "пароль" in res["error"]

    backup.save_settings(password="backup-pass-123", schedule="daily", hour=3)
    res = asyncio.run(backup.run(send_telegram=False))
    assert res["ok"], res
    path = backup.path_of(res["file"])
    with pytest.raises(RuntimeError):
        backup.extract(path, "wrong-password", tmp_path / "x")
    info = backup.extract(path, "backup-pass-123", tmp_path / "ok")
    assert info["nodes"][0]["id"] == 1
    assert (tmp_path / "ok/panel/panel.db").read_bytes()[:15] == b"SQLite format 3"
    assert (tmp_path / "ok/nodes/1/wg-easy.db").exists()
    assert backup.public_settings()["password_set"] is True
    assert "password" not in backup.public_settings()


def test_backup_rotation_and_schedule(node, monkeypatch):
    backup.save_settings(password="backup-pass-123", schedule="daily", hour=0)
    names = iter(f"vpn-panel-backup-2026010{i}-0000.zip" for i in range(1, 9))
    real_create = backup.create

    async def create_named():
        p = await real_create()
        return p.rename(p.with_name(next(names)))
    monkeypatch.setattr(backup, "create", create_named)
    for _ in range(7):
        asyncio.run(backup.run(send_telegram=False))
    assert len(backup.list_backups()) == backup.KEEP
    assert not backup.due()                          # только что сделан
    s = db.get_setting("backup")
    s["last_ts"] = time.time() - 2 * 86400
    db.set_setting("backup", s)
    assert backup.due()
    backup.save_settings(schedule="off")
    assert not backup.due()


# ── квоты ───────────────────────────────────────────────────────
def test_quota_warn_block_and_monthly_reset(node):
    pid = node.pid["Петя"]
    tz = "Europe/Moscow"
    m = quotas.month(tz)
    quotas.set_quota(pid, 1000)
    cfg = db.one("SELECT id FROM clients WHERE user_id=?", (pid,))["id"]
    db.execute("INSERT INTO traffic_daily(client_id, day, rx, tx) VALUES(?,?,?,?)", (cfg, f"{m}-02", 500, 350))
    asyncio.run(quotas.check(tz))
    assert any("85 %" in t for t in node.sent) and node.by_ip("10.8.0.7")["enabled"]

    db.execute("UPDATE traffic_daily SET rx=900 WHERE client_id=?", (cfg,))
    asyncio.run(quotas.check(tz))
    assert not node.by_ip("10.8.0.7")["enabled"] and quotas.get_all(tz)[str(pid)]["blocked"]

    db.execute("UPDATE quotas SET blocked='2000-01' WHERE user_id=?", (pid,))   # «наступил новый месяц»
    asyncio.run(quotas.check(tz))
    assert node.by_ip("10.8.0.7")["enabled"] and db.one("SELECT blocked FROM quotas")["blocked"] is None


def test_quota_api(node, client):
    pid = node.pid["Петя"]
    assert client.put(f"/api/users/{pid}/quota", json={"limit_gb": 50}).status_code == 401
    login(client)
    assert client.put(f"/api/users/{pid}/quota", json={"limit_gb": 50}).status_code == 200
    assert client.get("/api/quotas").json()[str(pid)]["limit_bytes"] == 50 * 1024**3
    client.put(f"/api/users/{pid}/quota", json={"limit_gb": None})
    assert client.get("/api/quotas").json() == {}


# ── бот ─────────────────────────────────────────────────────────
def test_bot_find_and_commands(node):
    items = asyncio.run(bot._clients())
    c, err = bot._find(items, "петя")
    assert c["name"] == "Петя" and err is None
    c, err = bot._find(items, "маша")
    assert c is None and "несколько" in err
    c, err = bot._find(items, "Маша ноутбук")
    assert c["name"] == "Маша ноутбук"

    asyncio.run(bot.handle("/disable Петя", "42"))
    assert not node.by_ip("10.8.0.7")["enabled"] and any("Отключён" in t for t in node.sent)
    asyncio.run(bot.handle("/clients", "42"))
    assert any("Петя" in t for t in node.sent)
    actions = [r["action"] for r in db.query("SELECT action FROM audit_log")]
    assert "user_disabled" in actions


def test_new_endpoints_require_login(client):
    for path in ("/api/backups", "/api/quotas", "/api/telegram/bot"):
        assert client.get(path).status_code == 401, path
    assert client.post("/api/backups/run").status_code == 401
    login(client)
    assert client.put("/api/backups/settings", json={"password": "123"}).status_code == 400
    assert client.put("/api/telegram/bot", json={"enabled": True}).json()["enabled"] is True
