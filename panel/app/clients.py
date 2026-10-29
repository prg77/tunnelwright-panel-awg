"""Клиенты панели и их профили на нодах.

Клиент — пользователь VPN: имя, IP (один и тот же на всех нодах), включён ли, срок, группа и
метаданные. На каждой ноде у него профиль — клиент wg-easy со своими ключами.

Панель — источник правды. Синхронизация ноды (reconcile) создаёт недостающие профили
(новая нода, нода была недоступна), выравнивает имя, IP, состояние и срок, дочищает профили
удалённых клиентов. Клиенты, найденные на ноде без профиля в панели, принимаются в панель.
"""
import asyncio
import ipaddress
import json
import logging
import secrets
from datetime import datetime, timezone

from . import db, limits, nodes

log = logging.getLogger("panel.clients")

NO_GROUP = "Без группы"
SUBNET = ipaddress.ip_network("10.8.0.0/24")   # подсеть wg-easy по умолчанию — одинакова на всех нодах

_SELECT = "SELECT c.*, g.name AS group_name FROM clients c LEFT JOIN groups g ON g.id = c.group_id"
_locks: dict[int, asyncio.Lock] = {}
_warned: set = set()


class ClientError(ValueError):
    pass


def _node_lock(node_id: int) -> asyncio.Lock:
    return _locks.setdefault(node_id, asyncio.Lock())


# ── чтение ─────────────────────────────────────────────────────
def _meta(row) -> dict:
    try:
        meta = json.loads(row["meta"] or "{}")
    except ValueError:
        meta = {}
    if row.get("group_name"):
        meta["group"] = row["group_name"]
    if row.get("expires_at"):
        meta["expiresAt"] = row["expires_at"]
    return meta


def get(cid: int) -> dict | None:
    return db.one(f"{_SELECT} WHERE c.id=? AND c.deleted=0", (cid,))


def all_clients() -> list[dict]:
    return db.query(f"{_SELECT} WHERE c.deleted=0 ORDER BY c.id")


def profiles(cid: int) -> list[dict]:
    """Профили клиента по нодам (сначала локальная нода, затем по порядку добавления)."""
    return db.query("SELECT p.*, n.name AS node_name FROM profiles p JOIN nodes n ON n.id = p.node_id "
                    "WHERE p.client_id=? ORDER BY n.is_local DESC, n.id", (cid,))


def lookup(cid: int, node_id: int | None = None) -> tuple[nodes.Node, int, dict]:
    """Клиент → (нода, id профиля в wg-easy, метаданные). Без node_id — первая нода с профилем."""
    row = get(cid)
    if not row:
        raise nodes.NodeError("клиент не найден")
    for p in profiles(cid):
        if node_id is None or p["node_id"] == node_id:
            return nodes.get(p["node_id"]), p["wg_id"], _meta(row)
    raise nodes.NodeError("у клиента нет профиля на этой ноде" if node_id else "профили клиента ещё не созданы")


def all_meta() -> dict:
    return {str(r["id"]): _meta(r) for r in all_clients()}


# ── изменение ──────────────────────────────────────────────────
def group_id(name) -> int | None:
    """Группа по имени; неизвестное имя создаёт группу (импорт amnezia-wg)."""
    name = str(name or "").strip()[:32]
    if not name or name == NO_GROUP:
        return None
    row = db.one("SELECT id FROM groups WHERE name=?", (name,))
    if row:
        return row["id"]
    return db.execute("INSERT INTO groups(name, sort) VALUES(?, 100)", (name,))


def set_meta(cid: int, meta: dict):
    """Метаданные клиента. Группа и срок хранятся отдельными колонками, остальное — JSON."""
    meta = dict(meta)
    gid = group_id(meta.pop("group", None))
    meta.pop("expiresAt", None)
    db.execute("UPDATE clients SET meta=?, group_id=? WHERE id=?",
               (json.dumps(meta, ensure_ascii=False), gid, cid))


def check_ip(ip: str, exclude_id: int | None = None) -> str:
    try:
        addr = ipaddress.IPv4Address(str(ip).split("/")[0].strip())
    except ValueError:
        raise ClientError("неверный адрес")
    if addr not in SUBNET or addr in (SUBNET.network_address, SUBNET.broadcast_address, SUBNET.network_address + 1):
        raise ClientError(f"адрес должен быть в {SUBNET} (кроме .0, .1 и .255)")
    row = db.one("SELECT id FROM clients WHERE ipv4=?", (str(addr),))
    if row and row["id"] != exclude_id:
        raise ClientError(f"адрес {addr} уже занят")
    return str(addr)


def free_ip() -> str:
    used = {r["ipv4"] for r in db.query("SELECT ipv4 FROM clients WHERE ipv4 IS NOT NULL")}
    for addr in list(SUBNET.hosts())[1:]:          # .1 — сервер
        if str(addr) not in used:
            return str(addr)
    raise ClientError("в подсети нет свободных адресов")


def new_uid() -> str:
    """Скрытый ID клиента: 8 hex-символов, уникален в панели. Имена могут повторяться — ID нет."""
    while True:
        uid = secrets.token_hex(4)
        if not db.one("SELECT 1 FROM clients WHERE uid=?", (uid,)):
            return uid


def by_uid(uid: str | None) -> dict | None:
    return db.one("SELECT * FROM clients WHERE uid=?", (uid,)) if uid else None


def create(name: str, ipv4: str | None = None, expires_at: str | None = None) -> int:
    name = str(name or "").strip()[:64]
    if not name:
        raise ClientError("имя не задано")
    ip = check_ip(ipv4) if ipv4 else free_ip()
    return db.execute("INSERT INTO clients(uid, name, ipv4, enabled, expires_at, adopted) VALUES(?,?,?,1,?,1)",
                      (new_uid(), name, ip, expires_at))


def update(cid: int, **fields):
    """name / ipv4 / enabled / expires_at в панели; на ноды уходит через sync_all."""
    allowed = {k: v for k, v in fields.items() if k in ("name", "ipv4", "enabled", "expires_at")}
    old_ip = None
    if "ipv4" in allowed:
        allowed["ipv4"] = check_ip(allowed["ipv4"], cid)
        old_ip = (get(cid) or {}).get("ipv4")
    if "enabled" in allowed:
        allowed["enabled"] = int(bool(allowed["enabled"]))
    if allowed:
        db.execute(f"UPDATE clients SET {', '.join(k + '=?' for k in allowed)} WHERE id=?", (*allowed.values(), cid))
    if old_ip and old_ip != allowed["ipv4"]:
        _move_limit(old_ip, allowed["ipv4"])


def _move_limit(old_ip: str, new_ip: str | None):
    """Лимит скорости привязан к IP: при смене адреса переезжает, при удалении клиента снимается.
    На ноды уходит со следующей синхронизацией."""
    cur = limits.get()
    if old_ip not in cur:
        return
    lim = cur.pop(old_ip)
    if new_ip:
        cur[new_ip] = lim
    limits.save(cur)


def mark_deleted(cid: int):
    ip = (get(cid) or {}).get("ipv4")
    db.execute("UPDATE clients SET deleted=1 WHERE id=?", (cid,))
    if ip:
        _move_limit(ip, None)


async def sync_all() -> list[str]:
    """Применить изменения на всех нодах сейчас. Недоступные ноды — в ответ; их доделает фоновая синхронизация."""
    _, down = await reconcile_all()
    return [n.name for n in down]


# ── синхронизация ноды ─────────────────────────────────────────
def parse_ts(v) -> datetime | None:
    if not v:
        return None
    try:
        t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _warn_once(key, msg, *args):
    if key not in _warned:
        _warned.add(key)
        log.warning(msg, *args)


async def reconcile(node: nodes.Node) -> list[dict]:
    """Привести ноду к состоянию панели. Возвращает профили ноды со счётчиками трафика."""
    async with _node_lock(node.id):
        remote = {c["id"]: c for c in await node.json("GET", "/clients")}
        profs = {p["wg_id"]: p for p in db.query("SELECT * FROM profiles WHERE node_id=?", (node.id,))}

        # 1. Клиент на ноде без профиля в панели: свой — привязать (по скрытому ID, без него — по IP),
        #    чужой — принять в панель
        for wid, rc in remote.items():
            if wid in profs:
                continue
            ip = rc.get("ipv4")
            owner = by_uid(rc.get("uid"))
            if not owner and ip:
                owner = db.one("SELECT * FROM clients WHERE ipv4=? AND (uid IS NULL OR uid=? OR ? IS NULL)",
                               (ip, rc.get("uid"), rc.get("uid")))
            if owner and owner["deleted"]:
                await node.req("DELETE", f"/clients/{wid}")
                continue
            if owner and db.one("SELECT 1 FROM profiles WHERE client_id=? AND node_id=?", (owner["id"], node.id)):
                _warn_once((node.id, wid), "нода %s: клиент %s (%s) — второй профиль того же клиента или адрес занят",
                           node.name, rc.get("name"), ip)
                continue
            if owner:
                cid = owner["id"]
            elif ip and db.one("SELECT 1 FROM clients WHERE ipv4=?", (ip,)):
                _warn_once((node.id, wid), "нода %s: клиент %s (%s) — адрес занят другим клиентом панели",
                           node.name, rc.get("name"), ip)
                continue
            else:
                uid = rc.get("uid") if rc.get("uid") and not by_uid(rc.get("uid")) else new_uid()
                cid = db.execute("INSERT INTO clients(uid, name, ipv4, enabled, expires_at, adopted) VALUES(?,?,?,?,?,1)",
                                 (uid, rc.get("name"), ip, int(bool(rc.get("enabled"))), rc.get("expiresAt")))
            pid = db.execute("INSERT INTO profiles(client_id, node_id, wg_id, public_key) VALUES(?,?,?,?)",
                             (cid, node.id, wid, rc.get("publicKey")))
            profs[wid] = {"id": pid, "client_id": cid, "node_id": node.id, "wg_id": wid}

        # 2. Профиль есть в панели, а на ноде клиента нет — профиль забываем (создадим заново ниже)
        for wid in [w for w in profs if w not in remote]:
            db.execute("DELETE FROM profiles WHERE id=?", (profs.pop(wid)["id"],))

        clients_by_id = {c["id"]: c for c in db.query("SELECT * FROM clients")}

        # 3. Удалённые клиенты — удалить; не принятые после миграции — принять; остальные — выровнять
        for wid, p in list(profs.items()):
            cl, rc = clients_by_id.get(p["client_id"]), remote[wid]
            if not cl or cl["deleted"]:
                await node.req("DELETE", f"/clients/{wid}")
                db.execute("DELETE FROM profiles WHERE id=?", (p["id"],))
                profs.pop(wid)
                continue
            if not cl["adopted"]:
                ip = rc.get("ipv4")
                if not ip or db.one("SELECT 1 FROM clients WHERE ipv4=? AND id<>?", (ip, cl["id"])):
                    ip = cl["ipv4"]
                db.execute("UPDATE clients SET name=COALESCE(name, ?), ipv4=?, enabled=?, expires_at=?, adopted=1 "
                           "WHERE id=?", (rc.get("name"), ip, int(bool(rc.get("enabled"))), rc.get("expiresAt"), cl["id"]))
                cl = clients_by_id[cl["id"]] = db.one("SELECT * FROM clients WHERE id=?", (cl["id"],))
            patch = {}
            if cl["name"] and rc.get("name") != cl["name"]:
                patch["name"] = cl["name"]
            if parse_ts(rc.get("expiresAt")) != parse_ts(cl["expires_at"]):
                patch["expiresAt"] = cl["expires_at"]
            if cl["ipv4"] and rc.get("ipv4") != cl["ipv4"]:
                patch["ipv4"] = cl["ipv4"]
            if "uid" in rc and rc["uid"] != cl["uid"]:      # агент хранит скрытый ID профиля
                patch["uid"] = cl["uid"]
            if patch:
                try:
                    rc.update(await node.json("PATCH", f"/clients/{wid}", json=patch))
                except nodes.NodeError as e:
                    _warn_once((node.id, wid, "patch"), "нода %s: клиент %s не обновлён: %s", node.name, cl["name"], e)
            if bool(rc.get("enabled")) != bool(cl["enabled"]):
                await node.req("POST", f"/clients/{wid}/{'enable' if cl['enabled'] else 'disable'}")
                rc["enabled"] = bool(cl["enabled"])

        # 4. Клиенты панели без профиля на этой ноде — создать (тот же IP, срок, состояние).
        # Клиент из 2.4, чья нода исчезла до первой синхронизации (VPN убран с сервера панели),
        # не может взять состояние с ноды — принимаем его со свободным IP.
        for cl in clients_by_id.values():
            if not cl["adopted"] and not cl["deleted"] and \
                    not db.one("SELECT 1 FROM profiles WHERE client_id=?", (cl["id"],)):
                ip = cl["ipv4"] or free_ip()
                db.execute("UPDATE clients SET ipv4=?, adopted=1 WHERE id=?", (ip, cl["id"]))
                cl.update(ipv4=ip, adopted=1)
                log.info("клиент %s без профилей принят в панель с адресом %s", cl["name"], ip)
        have = {p["client_id"] for p in profs.values()}
        for cl in clients_by_id.values():
            if cl["deleted"] or not cl["adopted"] or cl["id"] in have or not cl["ipv4"]:
                continue
            try:
                rc = await node.json("POST", "/clients", json={"name": cl["name"] or f"client-{cl['id']}",
                                                               "ipv4": cl["ipv4"], "expiresAt": cl["expires_at"],
                                                               "uid": cl["uid"]})
            except nodes.NodeError as e:
                _warn_once((node.id, "create", cl["id"]), "нода %s: профиль клиента %s не создан: %s",
                           node.name, cl["name"], e)
                continue
            if not cl["enabled"]:
                await node.req("POST", f"/clients/{rc['id']}/disable")
                rc["enabled"] = False
            pid = db.execute("INSERT INTO profiles(client_id, node_id, wg_id, public_key) VALUES(?,?,?,?)",
                             (cl["id"], node.id, rc["id"], rc.get("publicKey")))
            profs[rc["id"]] = {"id": pid, "client_id": cl["id"], "node_id": node.id, "wg_id": rc["id"]}
            remote[rc["id"]] = rc
            log.info("нода %s: создан профиль клиента %s (%s)", node.name, cl["name"], cl["ipv4"])

        # 5. Удалённые клиенты без профилей ни на одной ноде — удалить из панели окончательно
        db.execute("DELETE FROM clients WHERE deleted=1 AND NOT EXISTS (SELECT 1 FROM profiles WHERE client_id=clients.id)")

        await limits.push(node)

        return [{"profile_id": p["id"], "client_id": p["client_id"], "node_id": node.id, "node_name": node.name,
                 "wg_id": wid, "enabled": bool(remote[wid].get("enabled")),
                 "latestHandshakeAt": remote[wid].get("latestHandshakeAt"),
                 "transferRx": int(remote[wid].get("transferRx") or 0),
                 "transferTx": int(remote[wid].get("transferTx") or 0)}
                for wid, p in profs.items()]


async def reconcile_all() -> tuple[list[dict], list[nodes.Node]]:
    """Синхронизация всех нод параллельно → (профили доступных нод, недоступные ноды)."""
    all_n = nodes.all_nodes()
    res = await asyncio.gather(*(reconcile(n) for n in all_n), return_exceptions=True)
    out, down = [], []
    for n, r in zip(all_n, res):
        if isinstance(r, nodes.NodeError):
            down.append(n)
        elif isinstance(r, BaseException):
            raise r
        else:
            out += r
    return out, down


def summary(rows: list[dict]) -> dict[int, dict]:
    """Профили → по клиенту: последний handshake, суммарный трафик, ноды."""
    out: dict[int, dict] = {}
    for p in rows:
        s = out.setdefault(p["client_id"], {"latestHandshakeAt": None, "transferRx": 0, "transferTx": 0, "nodes": []})
        s["transferRx"] += p["transferRx"]
        s["transferTx"] += p["transferTx"]
        hs = p["latestHandshakeAt"]
        if hs and (not s["latestHandshakeAt"] or parse_ts(hs) > parse_ts(s["latestHandshakeAt"])):
            s["latestHandshakeAt"] = hs
        s["nodes"].append({"nodeId": p["node_id"], "nodeName": p["node_name"], "latestHandshakeAt": hs})
    return out
