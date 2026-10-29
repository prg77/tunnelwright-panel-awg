"""лимит скорости следует за IP клиента; бэкап и удаление нод."""
from app import limits

from .conftest import login


def test_limit_moves_with_ip_and_drops_on_delete(client, cluster):
    remote = cluster.add_remote()
    login(client)
    a = client.post("/api/clients", json={"name": "a"}).json()["id"]
    client.post("/api/clients", json={"name": "b"})
    b = client.get("/api/clients").json()[1]["id"]
    client.put(f"/api/clients/{a}/limit", json={"down": 5, "up": 2})
    client.put(f"/api/clients/{b}/limit", json={"down": 1, "up": 1})

    client.patch(f"/api/clients/{a}", json={"ip": "10.8.0.40"})
    want = {"10.8.0.40": {"down": 5.0, "up": 2.0}, "10.8.0.3": {"down": 1.0, "up": 1.0}}
    assert limits.get() == want
    assert client.get("/api/clients").json()[0]["limit"] == {"down": 5.0, "up": 2.0}
    for nid in (cluster.local, remote):
        assert cluster[nid].limits == want

    client.delete(f"/api/clients/{a}")
    assert limits.get() == {"10.8.0.3": {"down": 1.0, "up": 1.0}}
    assert cluster[remote].limits == {"10.8.0.3": {"down": 1.0, "up": 1.0}}


def test_rejected_ip_change_keeps_limit(client, cluster):
    login(client)
    a = client.post("/api/clients", json={"name": "a"}).json()["id"]
    client.post("/api/clients", json={"name": "b"})
    client.put(f"/api/clients/{a}/limit", json={"down": 5, "up": 5})
    assert client.patch(f"/api/clients/{a}", json={"ip": "10.8.0.3"}).status_code == 400
    assert limits.get() == {"10.8.0.2": {"down": 5.0, "up": 5.0}}


# ── бэкап и ноды ────────────────────────────────────────────────
def test_backup_skips_unreachable_node_and_finds_node_data(client, cluster, tmp_path):
    import asyncio
    from app import backup, cli

    fin = cluster.add_remote()
    swe = cluster.add_remote("Швеция", "198.51.100.7")
    backup.save_settings(password="backup-pass-123")
    assert backup.node_data(fin) is None                     # бэкапов ещё нет
    cluster[swe].down = True
    res = asyncio.run(backup.run(send_telegram=False))
    assert res["ok"] and res["skipped"] == ["Швеция"]
    assert res["file"].startswith("tunnelwright-backup-")

    name, files = backup.node_data(fin)
    assert name == res["file"] and files["wg-easy.db"].startswith(b"SQLite format 3")
    assert backup.node_data(swe) is None                     # нода была недоступна — данных нет

    # restore-extract отмечает локальную ноду для tunnelwright restore
    import io, sys
    out = tmp_path / "out"
    sys.stdin = io.StringIO("backup-pass-123\n")
    try:
        assert cli.main(["restore-extract", str(backup.path_of(res["file"])), str(out)]) == 0
    finally:
        sys.stdin = sys.__stdin__
    assert (out / "local-node").read_text() == str(cluster.local)
    assert (out / "nodes" / str(fin) / "wg-easy.db").exists()


def test_reinstall_flags_only_for_update():
    from app import nodeinstall

    new = nodeinstall.params({"host": "203.0.113.5", "restore": True, "new_host_key": True})
    assert not new["restore"] and not new["new_host_key"]
    row = {"name": "n", "host": "203.0.113.5", "ssh_port": 22, "wg_port": 51820, "agent_port": 8711}
    upd = nodeinstall.params({"restore": True, "new_host_key": True}, row)
    assert upd["restore"] and upd["new_host_key"]


def test_remove_node_endpoints(client, cluster):
    fin = cluster.add_remote()
    login(client)
    assert client.get(f"/api/nodes/{fin}/backup").json() == {"archive": None}
    assert client.post(f"/api/nodes/{fin}/remove", json={}).status_code == 400          # нужны пароль или ключ
    assert client.post(f"/api/nodes/{cluster.local}/remove", json={"password": "x"}).status_code == 400
    assert client.delete(f"/api/nodes/{fin}").json() == {"ok": True}                       # только из панели
    assert client.get(f"/api/nodes/{fin}/backup").status_code == 404
