"""автообновление агентов удалённых нод до версии панели."""
import asyncio

import pytest

from app import config, db, nodeinstall, nodes, nodeupdate

from .conftest import login


@pytest.fixture()
def upd(client, cluster, monkeypatch):
    """Панель 1.1.0, удалённая нода на 1.0.0; запросы к агенту — в calls."""
    monkeypatch.setattr(config, "APP_VERSION", "1.1.0")
    monkeypatch.setattr(nodeinstall, "bundle", lambda: b"tgz-bundle")
    monkeypatch.setattr(nodeupdate, "_requested", {})
    remote = cluster.add_remote()
    calls = []

    async def req(self, method, path, **kw):
        calls.append((self.id, method, path, kw.get("content")))
        return None
    monkeypatch.setattr(nodes.Node, "req", req)
    return nodes.get(remote), calls


def _check(node, **h):
    asyncio.run(nodeupdate.check(node, {"ok": True, "version": "1.0.0", "auto_update": True, **h}))


def _actions():
    return [r["action"] for r in db.query("SELECT action FROM audit_log ORDER BY id")]


def test_outdated_node_gets_update_once(upd):
    node, calls = upd
    _check(node)
    assert calls == [(node.id, "POST", "/update?version=1.1.0", b"tgz-bundle")]
    _check(node)                                   # уже запрошено — не повторяем до RETRY_SEC
    assert len(calls) == 1
    nodeupdate._requested[node.id] = ("1.1.0", 0)  # прошло больше RETRY_SEC — повтор
    _check(node)
    assert len(calls) == 2
    _check(node, version="1.1.0")                 # обновилась
    assert node.id not in nodeupdate._requested
    assert _actions().count("node_update_started") == 2 and _actions()[-1] == "node_updated"


def test_no_update_when_not_possible(upd, monkeypatch):
    node, calls = upd
    _check(node, auto_update=False)                # автообновление не настроено — только по SSH
    _check(node, ok=False)                         # недоступна
    _check(node, version="1.1.0")                 # актуальна
    monkeypatch.setattr(config, "APP_VERSION", "dev")
    _check(node)                                   # сборка без версии
    assert calls == []


def test_local_node_is_never_updated_by_request(upd, cluster):
    _, calls = upd
    _check(nodes.get(cluster.local))
    assert calls == []


def test_request_failure_is_logged(upd, monkeypatch):
    node, _ = upd

    async def fail(self, *a, **kw):
        raise nodes.NodeError("на ноде нет автообновления")
    monkeypatch.setattr(nodes.Node, "req", fail)
    _check(node)
    assert _actions()[-1] == "node_update_failed"


def test_nodes_api_reports_update_state(client, cluster, monkeypatch):
    monkeypatch.setattr(config, "APP_VERSION", "1.1.0")
    cluster.add_remote()
    login(client)
    remote = next(n for n in client.get("/api/nodes").json() if not n["is_local"])
    assert remote["update"] == {"auto": False, "target": "1.1.0", "current": False, "pending": False, "last": None}
