import asyncio

from app import clients, db, traffic

from .conftest import login


def _collect():
    asyncio.run(traffic.collect("Europe/Moscow"))


def test_traffic_deltas_and_reset(client, cluster):
    agent = cluster[cluster.local]
    wid = agent.add("c7", "10.8.0.2", rx=1000, tx=500)
    _collect()                                 # первый замер — только точка отсчёта
    assert traffic.usage() == {}

    agent.clients[wid].update(transferRx=1600, transferTx=700)   # +600 rx, +200 tx
    _collect()
    (rec,) = traffic.usage().values()
    (day,) = rec["daily"].values()
    assert day == {"rx": 600, "tx": 200}

    agent.clients[wid].update(transferRx=100, transferTx=50)     # счётчик сбросился — считаем от нуля
    _collect()
    (day,) = next(iter(traffic.usage().values()))["daily"].values()
    assert day == {"rx": 700, "tx": 250}

    pts = traffic.points()
    assert pts[-1]["rx"] == 700 and pts[-1]["ts"] % 60000 == 0

    login(client)
    assert client.delete("/api/traffic").status_code == 204
    assert traffic.usage() == {} and traffic.points() == []


def test_traffic_sums_profiles_of_all_nodes(client, cluster):
    remote = cluster.add_remote()
    a, b = cluster[cluster.local], cluster[remote]
    wa = a.add("Маша", "10.8.0.2")
    _collect()                                 # клиент принят и создан на второй ноде
    wb = b.by_ip("10.8.0.2")["id"]
    a.clients[wa]["transferRx"] = 100
    b.clients[wb]["transferRx"] = 50
    _collect()
    (rec,) = traffic.usage().values()
    assert sum(d["rx"] for d in rec["daily"].values()) == 150


def test_reconcile_adopts_and_restores(client, cluster):
    agent = cluster[cluster.local]
    agent.add("one", "10.8.0.2")
    w2 = agent.add("two", "10.8.0.3", enabled=False)
    asyncio.run(clients.reconcile_all())
    rows = {r["name"]: r for r in db.query("SELECT * FROM clients")}
    assert rows["two"]["ipv4"] == "10.8.0.3" and rows["two"]["enabled"] == 0
    del agent.clients[w2]                      # удалён на ноде вручную — панель вернёт профиль
    asyncio.run(clients.reconcile_all())
    again = agent.by_ip("10.8.0.3")
    assert again and again["name"] == "two" and again["enabled"] is False


def test_api_requires_login(client):
    for path in ("/api/clients", "/api/stats", "/api/traffic/history", "/api/traffic/usage",
                 "/api/telegram", "/api/settings", "/api/clients/1/config"):
        assert client.get(path).status_code == 401, path
    assert client.post("/api/clients", json={"name": "x"}).status_code == 401
    assert client.patch("/api/clients/1", json={}).status_code == 401
    assert client.delete("/api/traffic").status_code == 401
    assert client.get("/api/portal-name").status_code == 404     # имя панели до входа не раскрывается
