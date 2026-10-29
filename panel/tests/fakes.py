"""Фейковые ноды для тестов: агент с поведением wg-easy (клиенты, IP, состояние, лимиты, конфиги).

Подменяет nodes.Node.req/health: запрос уходит агенту ноды по её id.
"""
import io
import json
import zipfile

import pytest

from app import db, nodes

CONF = """[Interface]
PrivateKey = {key}
Address = {ip}/32
DNS = 1.1.1.1, 8.8.8.8
MTU = 1420
Jc = 4

[Peer]
PublicKey = cHVibGlj
PresharedKey = cHNr
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
Endpoint = {host}:51820
"""


class Resp:
    def __init__(self, data=None, text=None, content=None):
        self.data = data
        self.text = text if text is not None else json.dumps(data)
        self.content = content if content is not None else self.text.encode()

    def json(self):
        return self.data


class Agent:
    def __init__(self, host="vpn.example"):
        self.host = host
        self.clients: dict[int, dict] = {}
        self.limits: dict = {}
        self.down = False
        self.next_id = 1
        self.calls: list[tuple[str, str]] = []

    def add(self, name, ip, enabled=True, rx=0, tx=0, expires=None, uid=None) -> int:
        wid = self.next_id
        self.next_id += 1
        self.clients[wid] = {"id": wid, "name": name, "ipv4": ip, "enabled": enabled, "publicKey": f"pk-{self.host}-{wid}",
                             "transferRx": rx, "transferTx": tx, "expiresAt": expires, "latestHandshakeAt": None,
                             "uid": uid}
        return wid

    def by_ip(self, ip):
        return next((c for c in self.clients.values() if c["ipv4"] == ip), None)

    def handle(self, method, path, body=None):
        self.calls.append((method, path))
        parts = path.strip("/").split("/")
        if path == "/clients" and method == "GET":
            return Resp([dict(c) for c in self.clients.values()])
        if path == "/clients" and method == "POST":
            ip = body.get("ipv4")
            if ip and self.by_ip(ip):
                raise nodes.NodeError(f"нода: адрес {ip} занят")
            if not ip:
                used = {c["ipv4"] for c in self.clients.values()}
                ip = next(f"10.8.0.{i}" for i in range(2, 255) if f"10.8.0.{i}" not in used)
            wid = self.add(body["name"], ip, expires=body.get("expiresAt"), uid=body.get("uid"))
            return Resp(dict(self.clients[wid]))
        if parts[0] == "clients" and len(parts) >= 2:
            wid = int(parts[1])
            c = self.clients.get(wid)
            if c is None:
                raise nodes.NodeError("нода: клиент не найден")
            if len(parts) == 2 and method == "GET":
                return Resp(dict(c))
            if len(parts) == 2 and method == "PATCH":
                if body.get("ipv4") and body["ipv4"] != c["ipv4"] and self.by_ip(body["ipv4"]):
                    raise nodes.NodeError("нода: адрес занят")
                c.update({k: v for k, v in body.items() if k in ("name", "ipv4", "expiresAt", "uid")})
                return Resp(dict(c))
            if len(parts) == 2 and method == "DELETE":
                del self.clients[wid]
                return Resp({})
            if parts[2] in ("enable", "disable"):
                c["enabled"] = parts[2] == "enable"
                return Resp({})
            if parts[2] == "config":
                return Resp(text=CONF.format(key=f"cHJpdmF0ZQ{wid}==", ip=c["ipv4"], host=self.host))
        if path == "/limits" and method == "GET":
            return Resp(dict(self.limits))
        if path == "/limits" and method == "PUT":
            self.limits = dict(body)
            return Resp({"limits": self.limits, "applied": len(self.limits), "errors": []})
        if path == "/metrics":
            return Resp({"cpu": 3, "ram_pct": 40, "ram_used": 1, "ram_total": 2, "disk_pct": 20,
                         "disk_used": 1, "disk_total": 5, "load1": "0.1", "uptime": 10, "wg_up": True})
        if path == "/backup":
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("wg-easy.db", b"SQLite format 3\x00fake")
                z.writestr("limits.json", json.dumps(self.limits))
            return Resp(content=buf.getvalue(), text="")
        raise AssertionError((method, path))


class Cluster:
    """Ноды панели и их агенты."""

    def __init__(self):
        self.agents: dict[int, Agent] = {}
        local = nodes.ensure_local_node()
        self.local = local
        self.agents[local] = Agent("local.example")

    def add_remote(self, name="Финляндия", host="203.0.113.9") -> int:
        nid = db.execute("INSERT INTO nodes(name, url, token, is_local, host, wg_port, agent_port) "
                         "VALUES(?, ?, 'tok', 0, ?, 51820, 8711)", (name, f"https://{host}:8711", host))
        self.agents[nid] = Agent(host)
        return nid

    def __getitem__(self, nid) -> Agent:
        return self.agents[nid]


@pytest.fixture()
def cluster(client, monkeypatch):
    cl = Cluster()

    async def req(self, method, path, **kw):
        agent = cl.agents[self.id]
        if agent.down:
            raise nodes.NodeError(f"нода «{self.name}» недоступна")
        return agent.handle(method, path, kw.get("json"))

    async def health(self):
        agent = cl.agents.get(self.id)
        return {"ok": bool(agent and not agent.down), "version": "test"}

    monkeypatch.setattr(nodes.Node, "req", req)
    monkeypatch.setattr(nodes.Node, "health", health)
    return cl
