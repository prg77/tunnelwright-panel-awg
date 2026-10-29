"""клиент = профили на всех нодах с одним IP; панель без локальной ноды."""
import asyncio
import importlib
import sqlite3
from urllib.parse import quote

from app import clients, config, db, limits, nodes

from .conftest import login


def _sync():
    asyncio.run(clients.reconcile_all())


def test_client_created_on_all_nodes_with_one_ip(client, cluster):
    remote = cluster.add_remote()
    login(client)
    c = client.post("/api/clients", json={"name": "Маша", "expiresAt": "2099-01-01T00:00:00.000Z"}).json()
    assert c["ip"] == "10.8.0.2"
    for nid in (cluster.local, remote):
        p = cluster[nid].by_ip("10.8.0.2")
        assert p["name"] == "Маша" and p["expiresAt"] == "2099-01-01T00:00:00.000Z"
    (row,) = client.get("/api/clients").json()
    assert sorted(n["name"] for n in row["nodes"]) == ["Финляндия", "Этот сервер"]
    assert client.post("/api/clients", json={"name": "x", "ip": "10.8.0.2"}).status_code == 400
    assert client.post("/api/clients", json={"name": "y"}).json()["ip"] == "10.8.0.3"


def test_unreachable_node_gets_profile_later(client, cluster):
    remote = cluster.add_remote()
    cluster[remote].down = True
    login(client)
    client.post("/api/clients", json={"name": "Петя"})
    assert cluster[cluster.local].by_ip("10.8.0.2") and not cluster[remote].clients
    cluster[remote].down = False
    _sync()
    assert cluster[remote].by_ip("10.8.0.2")["name"] == "Петя"


def test_new_node_receives_existing_clients(client, cluster):
    login(client)
    client.post("/api/clients", json={"name": "a"})
    client.post("/api/clients", json={"name": "b"})
    client.patch(f"/api/clients/1", json={"enabled": False})
    remote = cluster.add_remote("Швеция", "198.51.100.7")
    _sync()
    got = {c["ipv4"]: c["enabled"] for c in cluster[remote].clients.values()}
    assert got == {"10.8.0.2": False, "10.8.0.3": True}


def test_toggle_expiry_rename_address_propagate(client, cluster):
    remote = cluster.add_remote()
    login(client)
    cid = client.post("/api/clients", json={"name": "Оля"}).json()["id"]
    client.patch(f"/api/clients/{cid}", json={"enabled": False})
    client.patch(f"/api/clients/{cid}", json={"expiresAt": "2030-05-01T00:00:00.000Z", "note": "n"})
    client.patch(f"/api/clients/{cid}", json={"ip": "10.8.0.50"})
    for nid in (cluster.local, remote):
        p = cluster[nid].by_ip("10.8.0.50")
        assert p and p["enabled"] is False and p["expiresAt"] == "2030-05-01T00:00:00.000Z"
    (row,) = client.get("/api/clients").json()
    assert (row["note"], row["expiresAt"], row["ip"], row["enabled"]) == ("n", "2030-05-01T00:00:00.000Z", "10.8.0.50", False)


def test_delete_cleans_nodes_even_if_down(client, cluster):
    remote = cluster.add_remote()
    login(client)
    cid = client.post("/api/clients", json={"name": "Удалить"}).json()["id"]
    cluster[remote].down = True
    assert client.delete(f"/api/clients/{cid}").status_code == 204
    assert client.get("/api/clients").json() == []
    assert not cluster[cluster.local].clients and cluster[remote].clients
    assert db.one("SELECT deleted FROM clients WHERE id=?", (int(cid),))["deleted"] == 1
    cluster[remote].down = False
    _sync()
    assert not cluster[remote].clients and db.one("SELECT * FROM clients WHERE id=?", (int(cid),)) is None


def test_limits_same_on_all_nodes(client, cluster):
    remote = cluster.add_remote()
    cluster[cluster.local].limits = {"10.8.0.9": {"down": 9, "up": 9}}
    login(client)
    assert limits.get() == {}
    _sync()                                    # первый запуск: лимиты берутся с ноды
    assert limits.get() == {"10.8.0.9": {"down": 9, "up": 9}}
    assert cluster[remote].limits == {"10.8.0.9": {"down": 9, "up": 9}}
    cluster[remote].down = True
    cid = client.post("/api/clients", json={"name": "a"}).json()["id"]
    r = client.put(f"/api/clients/{cid}/limit", json={"down": 5, "up": 5}).json()
    assert r["limit"] == {"down": 5.0, "up": 5.0} and r["errors"] and cluster[cluster.local].limits["10.8.0.2"] == {"down": 5.0, "up": 5.0}
    cluster[remote].down = False
    _sync()
    assert cluster[remote].limits == cluster[cluster.local].limits
    assert client.put(f"/api/clients/{cid}/limit", json={"down": 0, "up": 1}).status_code == 422


def test_config_and_qr_per_node(client, cluster):
    remote = cluster.add_remote(host="203.0.113.9")
    login(client)
    cid = client.post("/api/clients", json={"name": "Маша"}).json()["id"]
    r = client.get(f"/api/clients/{cid}/config?node={remote}")
    assert "Endpoint = 203.0.113.9:51820" in r.text
    assert r.headers["content-disposition"].endswith("UTF-8''" + quote("Маша-Финляндия.conf"))
    assert "Endpoint = local.example:51820" in client.get(f"/api/clients/{cid}/config").text
    assert client.get(f"/api/clients/{cid}/qr.svg?node={remote}").status_code == 200
    assert client.get(f"/api/clients/{cid}/config?node=999").status_code == 502

    token = client.post(f"/api/clients/{cid}/link").json()["token"]
    page = client.get(f"/u/{token}").text
    assert page.count("Скачать конфигурацию") == 2 and "Финляндия" in page
    assert "203.0.113.9" in client.get(f"/u/{token}/config?node={remote}").text


def test_panel_without_local_node(client, cluster, monkeypatch):
    remote = cluster.add_remote()
    login(client)
    cid = client.post("/api/clients", json={"name": "Маша"}).json()["id"]
    monkeypatch.setattr(config, "LOCAL_NODE_URL", "")
    assert nodes.drop_local_if_disabled() == "Этот сервер"
    assert nodes.local_node_id() is None and nodes.ensure_local_node() is None
    (row,) = client.get("/api/clients").json()
    assert row["id"] == cid and [n["id"] for n in row["nodes"]] == [remote]
    s = client.get("/api/stats").json()
    assert s["nodes_up"] == 1 and s["nodes_total"] == 1 and "cpu" in s
    assert "Endpoint = 203.0.113.9" in client.get(f"/api/clients/{cid}/config").text


def test_migration_8_keeps_clients(tmp_path, monkeypatch):
    """База 2.4 (клиент принадлежит ноде) → профили; связанные данные не теряются."""
    monkeypatch.setenv("PANEL_DATA_DIR", str(tmp_path / "d"))
    importlib.reload(config)
    importlib.reload(db)
    config.DATA_DIR.mkdir(parents=True)
    raw = sqlite3.connect(config.DB_FILE)
    for i, sql in enumerate(db.MIGRATIONS[:7], 1):
        raw.executescript(f"BEGIN; {sql}; PRAGMA user_version={i}; COMMIT;")
    raw.execute("INSERT INTO nodes(id, name, url, is_local) VALUES(1, 'local', 'http://x', 1)")
    raw.execute("INSERT INTO clients(id, node_id, wg_id, public_key, name, meta) VALUES(4, 1, 9, 'pk', 'Маша', '{\"note\":\"n\"}')")
    raw.execute("INSERT INTO traffic_daily(client_id, day, rx, tx) VALUES(4, '2026-10-01', 10, 20)")
    raw.execute("INSERT INTO quotas(client_id, limit_bytes) VALUES(4, 100)")
    raw.execute("INSERT INTO user_links(client_id, token, created_at) VALUES(4, 'tok', 1)")
    raw.commit()
    raw.close()
    db.connect()
    assert db.one("PRAGMA user_version")["user_version"] == len(db.MIGRATIONS)
    c = db.one("SELECT * FROM clients WHERE id=4")
    assert c["name"] == "Маша" and c["adopted"] == 0 and c["meta"] == '{"note":"n"}'
    assert db.one("SELECT node_id, wg_id FROM profiles WHERE client_id=4") == {"node_id": 1, "wg_id": 9}
    assert db.one("SELECT rx FROM traffic_daily WHERE client_id=4")["rx"] == 10
    assert db.one("SELECT limit_bytes FROM quotas WHERE client_id=4")["limit_bytes"] == 100
    assert db.one("SELECT token FROM user_links WHERE client_id=4")["token"] == "tok"
    db.execute("DELETE FROM nodes WHERE id=1")       # нода ушла — клиент остаётся, профиль удаляется
    assert db.one("SELECT id FROM clients WHERE id=4") and not db.one("SELECT 1 FROM profiles")


def test_orphan_from_removed_local_node_is_recreated(client, cluster):
    """VPN убран с сервера панели до первой синхронизации: клиент 2.4 создаётся на остальных нодах."""
    remote = cluster.add_remote()
    db.execute("INSERT INTO clients(id, name, meta, adopted, expires_at) VALUES(7, 'Старый', '{}', 0, "
               "'2099-02-02T00:00:00.000Z')")
    _sync()
    p = cluster[remote].by_ip("10.8.0.2")
    assert p and p["name"] == "Старый" and p["expiresAt"] == "2099-02-02T00:00:00.000Z"
    assert db.one("SELECT adopted, ipv4 FROM clients WHERE id=7") == {"adopted": 1, "ipv4": "10.8.0.2"}


def test_duplicate_names_are_told_apart_by_uid(client, cluster):
    remote = cluster.add_remote()
    login(client)
    a = client.post("/api/clients", json={"name": "Мама"}).json()
    b = client.post("/api/clients", json={"name": "Мама"}).json()
    assert a["uid"] != b["uid"] and len(a["uid"]) == 8
    for nid in (cluster.local, remote):           # агенты знают скрытый ID каждого профиля
        assert {c["uid"] for c in cluster[nid].clients.values()} == {a["uid"], b["uid"]}

    # Панель «потеряла» профили (восстановление бэкапа) и адрес на ноде сменили вручную —
    # профили всё равно привязываются к своим клиентам по скрытому ID
    db.execute("DELETE FROM profiles")
    cluster[remote].by_ip(b["ip"])["ipv4"] = "10.8.0.77"
    _sync()
    for c in (a, b):
        nodes_of = {p["node_id"] for p in clients.profiles(int(c["id"]))}
        assert nodes_of == {cluster.local, remote}
    assert cluster[remote].by_ip(b["ip"])["uid"] == b["uid"]     # адрес вернулся к панельному
    assert len(client.get("/api/clients").json()) == 2


def test_uid_written_to_old_profiles(client, cluster):
    agent = cluster[cluster.local]
    wid = agent.add("Старая", "10.8.0.9")         # профиль без uid
    _sync()
    uid = db.one("SELECT uid FROM clients WHERE ipv4='10.8.0.9'")["uid"]
    assert uid and agent.clients[wid]["uid"] == uid


def test_bot_find_by_uid(client, cluster):
    from app import bot
    login(client)
    a = client.post("/api/clients", json={"name": "Мама"}).json()
    client.post("/api/clients", json={"name": "Мама"})
    items = asyncio.run(bot._clients())
    c, err = bot._find(items, "мама")
    assert c is None and f"#{a['uid']}" in err
    c, err = bot._find(items, "#" + a["uid"][:5])
    assert err is None and c["uid"] == a["uid"]
