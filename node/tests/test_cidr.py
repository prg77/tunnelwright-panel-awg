"""Расширение подсети wg-easy без смены адресов клиентов (WgEasy.ensure_cidr).

Фейковый wg-easy ведёт себя как 15.5: смена подсети перенумеровывает всех клиентов,
адреса клиентов уникальны.
"""
import asyncio
import ipaddress
import json

import httpx
import pytest

from app import config, wgeasy


class FakeWgEasy:
    def __init__(self, cidr, addresses):
        self.iface = {"ipv4Cidr": cidr, "ipv6Cidr": "fdcc:ad94:bacf:61a4::cafe:0/112"}
        self.clients = {i: {"id": i, "name": f"c{i}", "ipv4Address": ip} for i, ip in enumerate(addresses, 1)}
        self.restarts = 0
        self.cidr_calls = 0

    def renumber(self, cidr):
        """Как InterfaceService.updateCidr: каждому — первый свободный адрес новой подсети."""
        self.iface["ipv4Cidr"] = cidr
        used = {c["ipv4Address"] for c in self.clients.values()}
        hosts = list(ipaddress.ip_network(cidr).hosts())[1:]      # .1 — сервер
        for c in self.clients.values():
            nxt = next(str(h) for h in hosts if str(h) not in used)
            used.add(nxt)
            used.discard(c["ipv4Address"])
            c["ipv4Address"] = nxt

    def handle(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path.removeprefix("/api"), request.method
        if path == "/admin/interface" and method == "GET":
            return httpx.Response(200, json=self.iface)
        if path == "/admin/interface/cidr" and method == "POST":
            self.cidr_calls += 1
            self.renumber(json.loads(request.content)["ipv4Cidr"])
            return httpx.Response(200, json={"success": True})
        if path == "/admin/interface/restart":
            self.restarts += 1
            return httpx.Response(200, json={"success": True})
        if path == "/client" and method == "GET":
            return httpx.Response(200, json=list(self.clients.values()))
        cid = int(path.split("/")[2])
        if method == "GET":
            return httpx.Response(200, json=self.clients[cid])
        new = json.loads(request.content)["ipv4Address"]
        if any(c["ipv4Address"] == new for i, c in self.clients.items() if i != cid):
            return httpx.Response(500, text="UNIQUE constraint failed: clients_table.ipv4_address")
        self.clients[cid]["ipv4Address"] = new
        return httpx.Response(200, json={"success": True})


@pytest.fixture()
def make(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CIDR_PLAN_FILE", tmp_path / "cidr-change.json")
    monkeypatch.setattr(config, "WG_IPV4_CIDR", "10.8.0.0/20")

    def build(cidr, addresses):
        fake = FakeWgEasy(cidr, addresses)
        wg = wgeasy.WgEasy()
        wg._http = httpx.AsyncClient(transport=httpx.MockTransport(fake.handle), base_url="http://wg-easy")
        wg._creds = {"username": "u", "password": "p"}
        return fake, wg
    return build


ADDRS = ["10.8.0.2", "10.8.0.3", "10.8.0.5", "10.8.0.99", "10.8.0.7"]


def test_expand_keeps_addresses(make):
    fake, wg = make("10.8.0.0/24", ADDRS)
    asyncio.run(wg.ensure_cidr())
    assert fake.iface["ipv4Cidr"] == "10.8.0.0/20" and fake.restarts == 1
    assert [c["ipv4Address"] for c in fake.clients.values()] == ADDRS
    assert not config.CIDR_PLAN_FILE.exists()
    asyncio.run(wg.ensure_cidr())                 # уже нужная подсеть — ничего не меняется
    assert fake.cidr_calls == 1 and fake.restarts == 1


def test_resume_after_crash(make):
    """Агент упал после смены подсети: адреса перемешаны, план в файле — продолжает по нему."""
    fake, wg = make("10.8.0.0/24", ADDRS)
    config.CIDR_PLAN_FILE.write_text(json.dumps(
        {"target": "10.8.0.0/20", "addresses": {str(i): ip for i, ip in enumerate(ADDRS, 1)}}))
    fake.renumber("10.8.0.0/20")
    assert [c["ipv4Address"] for c in fake.clients.values()] != ADDRS
    asyncio.run(wg.ensure_cidr())
    assert [c["ipv4Address"] for c in fake.clients.values()] == ADDRS
    assert fake.cidr_calls == 0 and not config.CIDR_PLAN_FILE.exists()


def test_not_an_expansion_is_skipped(make):
    fake, wg = make("10.9.0.0/24", ["10.9.0.2"])
    asyncio.run(wg.ensure_cidr())
    assert fake.iface["ipv4Cidr"] == "10.9.0.0/24" and fake.cidr_calls == 0
    assert fake.clients[1]["ipv4Address"] == "10.9.0.2"
