"""Реестр нод и клиент API node-agent.

Локальная нода — agent в сети Docker по HTTP. Удалённая — HTTPS с самоподписанным сертификатом,
который панель получила при установке и которому одному доверяет (закрепление сертификата).
"""
import hashlib
import ssl

import httpx

from . import config, db


class NodeError(Exception):
    pass


def ensure_local_node() -> int | None:
    """Локальная нода (VPN на сервере панели) — только если установщик её поставил (LOCAL_NODE_URL)."""
    row = db.one("SELECT id FROM nodes WHERE is_local=1")
    if not config.LOCAL_NODE_URL:
        return None
    if row:
        return row["id"]
    return db.execute("INSERT INTO nodes(name, url, is_local) VALUES(?, ?, 1)",
                      ("Этот сервер", config.LOCAL_NODE_URL))


def drop_local_if_disabled() -> str | None:
    """VPN с сервера панели убран установщиком — локальная нода и её профили удаляются из панели.
    Клиенты остаются и получают профили на остальных нодах."""
    row = db.one("SELECT id, name FROM nodes WHERE is_local=1")
    if config.LOCAL_NODE_URL or not row:
        return None
    db.execute("DELETE FROM nodes WHERE id=?", (row["id"],))
    return row["name"]


def local_node_id() -> int | None:
    row = db.one("SELECT id FROM nodes WHERE is_local=1")
    return row["id"] if row else None


_ssl_cache: dict[str, ssl.SSLContext] = {}


def ssl_context(cert_pem: str) -> ssl.SSLContext:
    """Контекст, доверяющий только сертификату ноды. Имя хоста не проверяется: доверие — сам сертификат."""
    key = hashlib.sha256(cert_pem.encode()).hexdigest()
    ctx = _ssl_cache.get(key)
    if ctx is None:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_verify_locations(cadata=cert_pem)
        _ssl_cache[key] = ctx
    return ctx


def cert_fingerprint(cert_pem: str) -> str:
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert_pem)).hexdigest().upper()


class Node:
    def __init__(self, row: dict):
        self.id = row["id"]
        self.name = row["name"]
        self.is_local = bool(row.get("is_local"))
        self.row = row
        self._url = row["url"].rstrip("/")
        self._token = row["token"]
        self._verify = ssl_context(row["tls_cert"]) if row.get("tls_cert") else True

    def _headers(self):
        token = self._token
        if not token:
            try:
                token = config.LOCAL_NODE_TOKEN_FILE.read_text().strip()
            except OSError:
                token = ""
        return {"Authorization": f"Bearer {token}"}

    def _client(self, timeout):
        return httpx.AsyncClient(timeout=timeout, verify=self._verify)

    async def req(self, method, path, **kw):
        try:
            async with self._client(20) as c:
                r = await c.request(method, self._url + path, headers=self._headers(), **kw)
        except httpx.HTTPError as e:
            raise NodeError(f"нода «{self.name}» недоступна: {e}") from e
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail")
            except ValueError:
                detail = r.text[:200]
            if r.status_code == 403 and detail == "forbidden":   # агент привязан к прежнему IP панели
                detail = ("принимает запросы только с прежнего IP панели — "
                          "переустановите агент: Ноды → Обновить (по SSH)")
            raise NodeError(f"нода «{self.name}»: {detail}")
        return r

    async def json(self, method, path, **kw):
        return (await self.req(method, path, **kw)).json()

    async def health(self) -> dict:
        try:
            async with self._client(5) as c:
                return (await c.get(self._url + "/health")).json()
        except (httpx.HTTPError, ValueError) as e:
            return {"ok": False, "error": str(e)}


def get(node_id: int) -> Node:
    row = db.one("SELECT * FROM nodes WHERE id=?", (node_id,))
    if not row:
        raise NodeError(f"нода {node_id} не найдена")
    return Node(row)


def local() -> Node:
    nid = local_node_id()
    if nid is None:
        raise NodeError("VPN на сервере панели не установлен")
    return get(nid)


def all_nodes() -> list[Node]:
    return [Node(r) for r in db.query("SELECT * FROM nodes ORDER BY is_local DESC, id")]
