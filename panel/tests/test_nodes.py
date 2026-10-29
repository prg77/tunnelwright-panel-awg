"""удалённые ноды — параметры установки, закрепление сертификата, клиенты и лимиты на нескольких нодах."""
import datetime

import ssl

import asyncssh
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app import db, nodeinstall, nodes

from .conftest import login


def self_signed() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "vpn-node")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def test_params_validation():
    p = nodeinstall.params({"host": " VPN.Example.com ", "wg_dns": "1.1.1.1, 9.9.9.9"})
    assert p == {"name": "vpn.example.com", "host": "vpn.example.com", "ssh_port": 22, "wg_port": 51820,
                 "agent_port": 8711, "wg_dns": "1.1.1.1,9.9.9.9", "new_host_key": False, "restore": False}
    for bad in ({"host": "bad host;rm"}, {"host": "1.2.3.4", "wg_port": 70000},
                {"host": "1.2.3.4", "wg_port": 8711}, {"host": "1.2.3.4", "wg_dns": "dns.google"}):
        with pytest.raises(nodeinstall.InstallError):
            nodeinstall.params(bad)
    upd = nodeinstall.params({}, {"name": "A", "host": "1.2.3.4", "ssh_port": 2222, "wg_port": 443, "agent_port": 9000})
    assert (upd["ssh_port"], upd["wg_port"], upd["agent_port"]) == (2222, 443, 9000)


def test_credentials():
    with pytest.raises(nodeinstall.InstallError):
        nodeinstall.credentials({})
    with pytest.raises(nodeinstall.InstallError):
        nodeinstall.credentials({"private_key": "not a key"})
    key = asyncssh.generate_private_key("ssh-ed25519").export_private_key().decode()
    assert nodeinstall.credentials({"private_key": key})["key"] is not None
    assert nodeinstall.credentials({"password": "pw"}) == {"password": "pw", "key": None}


def test_pinned_certificate():
    pem = self_signed()
    ctx = nodes.ssl_context(pem)
    assert ctx.verify_mode == ssl.CERT_REQUIRED and not ctx.check_hostname
    assert nodes.ssl_context(pem) is ctx
    assert len(nodes.cert_fingerprint(pem)) == 64


def test_install_rejects_duplicates_and_missing_creds(client, cluster):
    cluster.add_remote(host="203.0.113.9")
    login(client)
    assert client.post("/api/nodes/install", json={"host": "203.0.113.10"}).status_code == 400
    r = client.post("/api/nodes/install", json={"host": "203.0.113.9", "wg_port": 51820, "password": "pw"})
    assert r.status_code == 400 and "уже добавлена" in r.json()["detail"]


def test_nodes_list_and_delete(client, cluster):
    remote = cluster.add_remote()
    db.execute("UPDATE nodes SET tls_cert=? WHERE id=?", (self_signed(), remote))
    login(client)
    client.post("/api/clients", json={"name": "Маша"})
    cluster[remote].down = True
    lst = {n["id"]: n for n in client.get("/api/nodes").json()}
    assert lst[cluster.local]["is_local"] and lst[cluster.local]["ok"]
    assert not lst[remote]["ok"] and lst[remote]["clients"] == 1 and len(lst[remote]["cert_sha256"]) == 64
    assert client.put(f"/api/nodes/{remote}", json={"name": "FI"}).json()["ok"]
    assert client.delete(f"/api/nodes/{cluster.local}").status_code == 400
    assert client.post(f"/api/nodes/{cluster.local}/update", json={"password": "x"}).status_code == 400
    assert client.delete(f"/api/nodes/{remote}").json()["ok"]
    assert db.one("SELECT COUNT(*) n FROM profiles WHERE node_id=?", (remote,))["n"] == 0
    assert [c["name"] for c in client.get("/api/clients").json()] == ["Маша"]
