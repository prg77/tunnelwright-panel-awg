"""API клиентов и настроек; уведомления Telegram отправляет сервер."""
import asyncio

from app import db, limits, notify, telegram

from .conftest import login


def test_create_with_group_note_limit_on_all_nodes(client, cluster):
    remote = cluster.add_remote()
    login(client)
    c = client.post("/api/clients", json={"name": "Маша", "group": "Семья", "note": "телефон",
                                          "limit": {"down": 10, "up": 5}}).json()
    assert (c["ip"], c["group"], c["note"], c["limit"]) == ("10.8.0.2", "Семья", "телефон", {"down": 10.0, "up": 5.0})
    assert isinstance(c["id"], int) and len(c["uid"]) == 8 and c["enabled"] is True
    assert sorted(n["name"] for n in c["nodes"]) == ["Финляндия", "Этот сервер"]
    for nid in (cluster.local, remote):
        assert cluster[nid].limits == {"10.8.0.2": {"down": 10.0, "up": 5.0}}
    assert client.post("/api/clients", json={"name": ""}).status_code == 422
    assert client.post("/api/clients", json={"name": "x", "ip": "10.8.0.2"}).status_code == 400


def test_patch_fields_and_unknown_client(client, cluster):
    login(client)
    cid = client.post("/api/clients", json={"name": "a", "group": "Работа"}).json()["id"]
    r = client.patch(f"/api/clients/{cid}", json={"name": "b", "note": "n"}).json()
    assert (r["name"], r["note"], r["group"]) == ("b", "n", "Работа")      # группа не сбрасывается
    r = client.patch(f"/api/clients/{cid}", json={"group": ""}).json()
    assert r["group"] is None and r["note"] == "n"
    r = client.patch(f"/api/clients/{cid}", json={"expiresAt": None, "enabled": False}).json()
    assert r["enabled"] is False and cluster[cluster.local].by_ip("10.8.0.2")["enabled"] is False
    assert client.patch("/api/clients/999", json={"name": "x"}).status_code == 404
    acts = [a["action"] for a in db.query("SELECT action FROM audit_log ORDER BY id")]
    assert "client_renamed" in acts and "client_disabled" in acts


def test_limit_endpoints(client, cluster):
    login(client)
    cid = client.post("/api/clients", json={"name": "a"}).json()["id"]
    assert client.put(f"/api/clients/{cid}/limit", json={"down": 3, "up": 2}).json()["limit"] == {"down": 3.0, "up": 2.0}
    assert limits.get() == {"10.8.0.2": {"down": 3.0, "up": 2.0}}
    assert client.delete(f"/api/clients/{cid}/limit").json() == {"limit": None}
    assert limits.get() == {} and cluster[cluster.local].limits == {}


def test_telegram_settings_never_expose_token(client, cluster):
    login(client)
    s = client.get("/api/telegram").json()
    assert s["token_set"] is False and "token" not in s
    assert client.post("/api/telegram/test").status_code == 409
    s = client.put("/api/telegram", json={"enabled": True, "token": "123:secret-token-abcd", "chat_id": "42",
                                          "events": {"on_toggle": True, "bogus": True}}).json()
    assert s == {**s, "token_set": True, "token_hint": "abcd", "chat_id": "42", "active": True}
    assert "bogus" not in s["events"] and s["events"]["on_toggle"] is True
    assert "secret" not in client.get("/api/telegram").text
    s = client.put("/api/telegram", json={"chat_id": "43"}).json()       # токен не передан — прежний
    assert telegram.settings()["token"] == "123:secret-token-abcd" and s["chat_id"] == "43"
    cid = client.post("/api/clients", json={"name": "a"}).json()["id"]
    assert client.post(f"/api/clients/{cid}/telegram?node=999").status_code == 502


def test_send_config_requires_telegram(client, cluster):
    login(client)
    cid = client.post("/api/clients", json={"name": "a"}).json()["id"]
    assert client.post(f"/api/clients/{cid}/telegram").status_code == 409


def test_notifications_are_composed_on_server(client, cluster, monkeypatch):
    sent, docs = [], []

    async def fake_send(text, **kw):
        sent.append((text, kw.get("event")))
        return True

    async def fake_doc(name, content, caption="", **kw):
        docs.append(name)
        return True

    async def fake_photo(png, caption="", **kw):
        docs.append("qr")
        return True
    monkeypatch.setattr(telegram, "send", fake_send)
    monkeypatch.setattr(telegram, "send_document", fake_doc)
    monkeypatch.setattr(telegram, "send_photo", fake_photo)
    pending = []
    monkeypatch.setattr(notify, "background", pending.append)   # фоновые отправки выполняем сами
    telegram.save(True, "1:t", "42", {"on_client_add": True, "on_toggle": True})
    login(client)
    cid = client.post("/api/clients", json={"name": "<Маша & Co>"}).json()["id"]
    client.patch(f"/api/clients/{cid}", json={"enabled": False})
    assert len(pending) == 2
    for coro in pending:
        asyncio.run(coro)
    assert sent[-1][1] == "on_toggle" and "отключён" in sent[-1][0]
    sent.pop()
    text, event = sent[-1]
    assert event == "on_client_add" and "&lt;Маша &amp; Co&gt;" in text
    assert len(docs) == 2 and docs[0].endswith(".conf") and docs[1] == "qr"   # файл и QR единственной ноды


def test_stats_traffic_and_settings(client, cluster):
    login(client)
    s = client.get("/api/stats").json()
    assert s["nodes_up"] == 1 and s["nodes_total"] == 1 and "cpu" in s
    assert client.get("/api/traffic/history").json() == []
    assert client.get("/api/traffic/usage").json() == {}
    st = client.get("/api/settings").json()
    assert {"portal_name", "timezone", "version", "wg_host", "web_port", "wg_port"} <= set(st)
    for path in ("/api/wireguard/client", "/config.json", "/limits.json", "/meta.json", "/stats.json"):
        assert client.get(path).status_code == 404, path       # старый API убран
