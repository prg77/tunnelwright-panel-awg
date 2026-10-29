"""группы, справочник списков, маршрутизация WireSock, GeoIP."""
import ipaddress

import pytest

from app import clients, db, geoip, routing

from .conftest import login

CONF = """[Interface]
PrivateKey = cHJpdmF0ZQ==
Address = 10.8.0.5/24
DNS = 1.1.1.1, 8.8.8.8
MTU = 1420
Jc = 4

[Peer]
PublicKey = cHVibGlj
PresharedKey = cHNr
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
Endpoint = vpn.example:51820
"""


@pytest.fixture()
def api(client, cluster, monkeypatch):
    cluster[cluster.local].add("Маша", "10.8.0.5")

    async def fake_geo(cc, refresh=False):
        if cc == "xx":
            raise ValueError("страна XX не найдена в базе GeoIP")
        return [ipaddress.ip_network("5.0.0.0/16"), ipaddress.ip_network("5.1.0.0/16")]
    monkeypatch.setattr(geoip, "networks", fake_geo)
    login(client)
    client.get("/api/clients")          # клиент ноды принимается в панель
    pid = db.one("SELECT id FROM clients WHERE ipv4='10.8.0.5'")["id"]
    return client, pid


def test_groups_crud_and_meta(api):
    c, pid = api
    names = [g["name"] for g in c.get("/api/groups").json()]
    assert names == ["Семья", "Работа", "Гости", "VIP", "Тест"]
    g = c.post("/api/groups", json={"name": "Офис", "color": "#112233"}).json()
    assert c.post("/api/groups", json={"name": "Офис"}).status_code == 409
    assert c.post("/api/groups", json={"name": "x", "color": "red"}).status_code == 400

    r = c.patch(f"/api/clients/{pid}", json={"group": "Офис", "note": "n"}).json()
    assert (r["group"], r["note"]) == ("Офис", "n")
    assert db.one("SELECT meta FROM clients WHERE id=?", (pid,))["meta"] == '{"note": "n"}'

    c.put(f"/api/groups/{g['id']}", json={"name": "Офис 2"})
    assert c.get("/api/clients").json()[0]["group"] == "Офис 2"
    assert next(x for x in c.get("/api/groups").json() if x["id"] == g["id"])["clients"] == 1

    c.delete(f"/api/groups/{g['id']}")
    assert c.get("/api/clients").json()[0]["group"] is None


def test_legacy_group_name_creates_group(api):
    _, pid = api
    clients.set_meta(pid, {"group": "Друзья"})
    assert db.one("SELECT g.name FROM groups g JOIN clients c ON c.group_id=g.id WHERE c.id=?", (pid,))["name"] == "Друзья"
    clients.set_meta(pid, {"group": "Без группы"})
    assert db.one("SELECT group_id FROM clients WHERE id=?", (pid,))["group_id"] is None


def test_lists_crud(api):
    c, pid = api
    net = c.post("/api/lists", json={"kind": "net", "name": "РФ", "countries": ["RU", "ru"],
                                     "cidrs": ["10.0.0.1/8", "192.168.1.1"]}).json()
    assert net["countries"] == ["ru"] and net["cidrs"] == ["10.0.0.0/8", "192.168.1.1/32"]
    assert c.post("/api/lists", json={"kind": "net", "name": "РФ"}).status_code == 400
    assert c.post("/api/lists", json={"kind": "net", "name": "b", "cidrs": ["::/0"]}).status_code == 400
    assert c.post("/api/lists", json={"kind": "net", "name": "b", "countries": ["xx"]}).status_code == 400
    assert c.post("/api/lists", json={"kind": "app", "name": "b", "apps": ["a,b"]}).status_code == 400

    copy = c.post(f"/api/lists/{net['id']}/duplicate").json()
    assert copy["name"] == "РФ (копия)" and copy["cidrs"] == net["cidrs"]
    assert c.post(f"/api/lists/{net['id']}/duplicate").json()["name"] == "РФ (копия) 2"
    ren = c.put(f"/api/lists/{copy['id']}", json={"name": "Домашние"}).json()
    assert ren["name"] == "Домашние" and ren["cidrs"] == net["cidrs"]

    c.put(f"/api/clients/{pid}/routing", json={"net_mode": "include", "net_lists": [net["id"], copy["id"]]})
    assert next(x for x in c.get("/api/lists").json() if x["id"] == net["id"])["clients"] == [pid]
    c.delete(f"/api/lists/{net['id']}")
    assert c.get(f"/api/clients/{pid}/routing").json()["net_lists"] == [copy["id"]]


def test_routing_validation(api):
    c, pid = api
    app = c.post("/api/lists", json={"kind": "app", "name": "Браузеры", "apps": ["chrome.exe"]}).json()
    assert c.put(f"/api/clients/{pid}/routing", json={"net_mode": "include"}).status_code == 400
    assert c.put(f"/api/clients/{pid}/routing", json={"net_mode": "bad"}).status_code == 400
    assert c.put(f"/api/clients/{pid}/routing", json={"net_mode": "include", "net_lists": [app["id"]]}).status_code == 400
    assert c.put(f"/api/clients/{pid}/routing", json={"extra": "просто текст"}).status_code == 400
    assert c.put(f"/api/clients/{pid}/routing", json={"app_mode": "exclude", "app_lists": [app["id"]]}).status_code == 200
    assert c.get("/api/routing").json() == {str(pid): {"net_mode": "all", "app_mode": "exclude", "custom": False}}


def test_config_include_apps_extra(api):
    c, pid = api
    net = c.post("/api/lists", json={"kind": "net", "name": "n", "countries": ["ru"], "cidrs": ["10.1.0.0/16"]}).json()
    app = c.post("/api/lists", json={"kind": "app", "name": "a",
                                     "apps": ["chrome", "C:\\Program Files\\Mozilla Firefox"]}).json()
    extra = "Jc = 7\n#@ws:Socks5Proxy = 127.0.0.1:1080\nPersistentKeepalive =\n[Interface]\n#@ws:Id = 1"
    c.put(f"/api/clients/{pid}/routing", json={"net_mode": "include", "net_lists": [net["id"]],
                                               "app_mode": "include", "app_lists": [app["id"]], "extra": extra})
    r = c.get(f"/api/clients/{pid}/config")
    assert r.status_code == 200
    text = r.text
    assert "AllowedIPs = 1.1.1.1/32, 5.0.0.0/15, 8.8.8.8/32, 10.1.0.0/16" in text
    assert "#@ws:AllowedApps = chrome, C:\\Program Files\\Mozilla Firefox" in text
    assert "Jc = 7" in text and "Jc = 4" not in text
    assert "#@ws:Socks5Proxy = 127.0.0.1:1080" in text and "PersistentKeepalive" not in text
    iface, peer = text.split("[Peer]")
    assert "#@ws:Id = 1" in iface and "Jc = 7" in iface and "#@ws:AllowedApps" in peer
    assert "attachment" in r.headers["content-disposition"]

    p = c.get(f"/api/clients/{pid}/routing/preview").json()
    assert p["allowed"] == 4 and p["apps"] == 2 and p["qr"] is True
    assert "PrivateKey = •••" in p["config"] and "cHJpdmF0ZQ" not in p["config"]
    assert c.get(f"/api/clients/{pid}/qr.svg").headers["content-type"].startswith("image/svg")


def test_config_exclude(api):
    c, pid = api
    net = c.post("/api/lists", json={"kind": "net", "name": "n", "cidrs": ["192.168.0.0/16"]}).json()
    c.put(f"/api/clients/{pid}/routing", json={"net_mode": "exclude", "net_lists": [net["id"]]})
    text = c.get(f"/api/clients/{pid}/config").text
    assert "AllowedIPs = 0.0.0.0/0" in text and "#@ws:DisallowedIPs = 192.168.0.0/16" in text


def test_conf_roundtrip_untouched():
    text, info = __import__("asyncio").run(routing.render(CONF, dict(routing.DEFAULT)))
    assert text == CONF and info["allowed"] is None


def test_qr_overflow(api, monkeypatch):
    c, pid = api

    async def many(cc, refresh=False):
        return [ipaddress.ip_network(f"{a}.{b}.0.0/16") for a in range(11, 60) for b in range(0, 256, 2)]
    monkeypatch.setattr(geoip, "networks", many)
    net = c.post("/api/lists", json={"kind": "net", "name": "big", "countries": ["cn"]}).json()
    c.put(f"/api/clients/{pid}/routing", json={"net_mode": "include", "net_lists": [net["id"]]})
    assert c.get(f"/api/clients/{pid}/qr.svg").status_code == 413
    assert c.get(f"/api/clients/{pid}/routing/preview").json()["qr"] is False
