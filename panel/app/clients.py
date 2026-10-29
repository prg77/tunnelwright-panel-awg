"""Конфиги пользователей и их профили на нодах.

Конфиг (строка clients) — устройство пользователя: название, IP (один и тот же на всех нодах),
включён ли. На каждой ноде у конфига профиль — клиент wg-easy со своими ключами. Имя, срок и
общее включение — у пользователя (users.py); на ноду уходит итог: имя «Пользователь · устройство»,
срок пользователя, включён — только если включены и конфиг, и пользователь.

Панель — источник правды. Синхронизация ноды (reconcile) создаёт недостающие профили
(новая нода, нода была недоступна), выравнивает имя, IP, состояние и срок, дочищает профили
удалённых конфигов. Клиенты, найденные на ноде без профиля в панели, принимаются в панель
как новые пользователи с одним конфигом.
"""
import asyncio
import ipaddress
import logging
import secrets
from datetime import datetime, timezone

from . import db, limits, nodes, users

log = logging.getLogger("panel.clients")

# Подсеть устройств — одна на всех нодах (агент ноды расширяет до неё подсеть wg-easy, сохраняя адреса).
# Была 10.8.0.0/24: она входит в /20, поэтому прежние адреса и конфиги не меняются. Адреса выдаются
# по порядку — за пределы /24 панель выходит, только когда та заполнена.
SUBNET = ipaddress.ip_network("10.8.0.0/20")
SERVER_IP = SUBNET.network_address + 1


def _usable(addr: ipaddress.IPv4Address) -> bool:
    """Адрес для устройства: в подсети, не сервер, не сеть и не широковещательный, без .0 и .255 в конце
    (такие адреса внутри /20 допустимы, но некоторые устройства и роутеры с ними работают плохо)."""
    return addr in SUBNET and addr != SERVER_IP and addr.packed[-1] not in (0, 255)

_SELECT = ("SELECT c.*, u.name AS user_name, u.uid AS user_uid, u.enabled AS user_enabled, "
           "u.expires_at AS user_expires FROM clients c LEFT JOIN users u ON u.id = c.user_id")
_locks: dict[int, asyncio.Lock] = {}
_warned: set = set()


class ClientError(ValueError):
    pass


def _node_lock(node_id: int) -> asyncio.Lock:
    return _locks.setdefault(node_id, asyncio.Lock())


# ── чтение ─────────────────────────────────────────────────────
def label(c: dict) -> str:
    """Имя конфига для нод, файлов и уведомлений: «Пользователь · устройство» или имя пользователя."""
    user = (c.get("user_name") or "").strip()
    device = (c.get("name") or "").strip()
    if user and device:
        return f"{user} · {device}"
    return user or device or f"client-{c['id']}"


def active(c: dict) -> bool:
    """Конфиг работает, только если включены и он сам, и его пользователь."""
    return bool(c["enabled"]) and bool(c.get("user_enabled"))


def get(cid: int) -> dict | None:
    return db.one(f"{_SELECT} WHERE c.id=? AND c.deleted=0", (cid,))


def all_clients() -> list[dict]:
    return db.query(f"{_SELECT} WHERE c.deleted=0 ORDER BY c.id")


def of_user(user_id: int) -> list[dict]:
    return db.query(f"{_SELECT} WHERE c.user_id=? AND c.deleted=0 ORDER BY c.id", (user_id,))


def profiles(cid: int) -> list[dict]:
    """Профили конфига по нодам (сначала локальная нода, затем по порядку добавления)."""
    return db.query("SELECT p.*, n.name AS node_name FROM profiles p JOIN nodes n ON n.id = p.node_id "
                    "WHERE p.client_id=? ORDER BY n.is_local DESC, n.id", (cid,))


def lookup(cid: int, node_id: int | None = None) -> tuple[nodes.Node, int]:
    """Конфиг → (нода, id профиля в wg-easy). Без node_id — первая нода с профилем."""
    if not get(cid):
        raise nodes.NodeError("конфиг не найден")
    for p in profiles(cid):
        if node_id is None or p["node_id"] == node_id:
            return nodes.get(p["node_id"]), p["wg_id"]
    raise nodes.NodeError("у конфига нет профиля на этой ноде" if node_id else "профили конфига ещё не созданы")


# ── изменение ──────────────────────────────────────────────────
def check_ip(ip: str, exclude_id: int | None = None) -> str:
    try:
        addr = ipaddress.IPv4Address(str(ip).split("/")[0].strip())
    except ValueError:
        raise ClientError("неверный адрес")
    if not _usable(addr):
        raise ClientError(f"адрес должен быть в {SUBNET} (кроме {SERVER_IP} и адресов на .0 и .255)")
    row = db.one("SELECT id FROM clients WHERE ipv4=?", (str(addr),))
    if row and row["id"] != exclude_id:
        raise ClientError(f"адрес {addr} уже занят")
    return str(addr)


def free_ip() -> str:
    used = {r["ipv4"] for r in db.query("SELECT ipv4 FROM clients WHERE ipv4 IS NOT NULL")}
    for addr in SUBNET.hosts():
        if _usable(addr) and str(addr) not in used:
            return str(addr)
    raise ClientError("в подсети нет свободных адресов")


def new_uid() -> str:
    """Скрытый ID конфига: 8 hex-символов, записывается агенту ноды и связывает профили при восстановлении."""
    while True:
        uid = secrets.token_hex(4)
        if not db.one("SELECT 1 FROM clients WHERE uid=?", (uid,)):
            return uid


def by_uid(uid: str | None) -> dict | None:
    return db.one("SELECT * FROM clients WHERE uid=?", (uid,)) if uid else None


def _device(name) -> str | None:
    return str(name or "").strip()[:64] or None


def create(user_id: int, name: str | None = None, ipv4: str | None = None) -> int:
    """Новый конфиг пользователя; профили на нодах создаст sync_all."""
    if not users.get(user_id):
        raise ClientError("пользователь не найден")
    ip = check_ip(ipv4) if ipv4 else free_ip()
    return db.execute("INSERT INTO clients(uid, user_id, name, ipv4, enabled, adopted) VALUES(?,?,?,?,1,1)",
                      (new_uid(), user_id, _device(name), ip))


def update(cid: int, **fields):
    """name (устройство) / ipv4 / enabled в панели; на ноды уходит через sync_all."""
    allowed = {k: v for k, v in fields.items() if k in ("name", "ipv4", "enabled")}
    old_ip = None
    if "name" in allowed:
        allowed["name"] = _device(allowed["name"])
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
    """Лимит скорости привязан к IP: при смене адреса переезжает, при удалении конфига снимается.
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


def delete_user(user_id: int):
    """Пользователь и все его конфиги: лимиты снимаются, профили на нодах дочистит синхронизация."""
    for c in of_user(user_id):
        mark_deleted(c["id"])
    users.delete(user_id)


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


def _adopt_foreign(rc: dict) -> int:
    """Клиент ноды, которого панель не знает, — новый пользователь с одним конфигом."""
    user_id = users.create(rc.get("name") or f"client-{rc['id']}", rc.get("expiresAt"),
                           bool(rc.get("enabled")), rc.get("uid"))
    uid = rc.get("uid") if rc.get("uid") and not by_uid(rc.get("uid")) else new_uid()
    return db.execute("INSERT INTO clients(uid, user_id, ipv4, enabled, adopted) VALUES(?,?,?,1,1)",
                      (uid, user_id, rc.get("ipv4")))


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
                _warn_once((node.id, wid), "нода %s: клиент %s (%s) — второй профиль того же конфига или адрес занят",
                           node.name, rc.get("name"), ip)
                continue
            if owner:
                cid = owner["id"]
            elif ip and db.one("SELECT 1 FROM clients WHERE ipv4=?", (ip,)):
                _warn_once((node.id, wid), "нода %s: клиент %s (%s) — адрес занят другим конфигом панели",
                           node.name, rc.get("name"), ip)
                continue
            else:
                cid = _adopt_foreign(rc)
            pid = db.execute("INSERT INTO profiles(client_id, node_id, wg_id, public_key) VALUES(?,?,?,?)",
                             (cid, node.id, wid, rc.get("publicKey")))
            profs[wid] = {"id": pid, "client_id": cid, "node_id": node.id, "wg_id": wid}

        # 2. Профиль есть в панели, а на ноде клиента нет — профиль забываем (создадим заново ниже)
        for wid in [w for w in profs if w not in remote]:
            db.execute("DELETE FROM profiles WHERE id=?", (profs.pop(wid)["id"],))

        clients_by_id = {c["id"]: c for c in db.query(_SELECT)}

        # 3. Удалённые конфиги (и конфиги без пользователя) — удалить; не принятые после миграции —
        #    принять; остальные — выровнять
        for wid, p in list(profs.items()):
            cl, rc = clients_by_id.get(p["client_id"]), remote[wid]
            if not cl or cl["deleted"] or cl["user_id"] is None:
                await node.req("DELETE", f"/clients/{wid}")
                db.execute("DELETE FROM profiles WHERE id=?", (p["id"],))
                profs.pop(wid)
                continue
            if not cl["adopted"]:
                ip = rc.get("ipv4")
                if not ip or db.one("SELECT 1 FROM clients WHERE ipv4=? AND id<>?", (ip, cl["id"])):
                    ip = cl["ipv4"]
                db.execute("UPDATE users SET name=CASE WHEN name='' THEN COALESCE(?, '') ELSE name END, "
                           "enabled=?, expires_at=? WHERE id=?",
                           (rc.get("name"), int(bool(rc.get("enabled"))), rc.get("expiresAt"), cl["user_id"]))
                db.execute("UPDATE clients SET ipv4=?, adopted=1 WHERE id=?", (ip, cl["id"]))
                cl = clients_by_id[cl["id"]] = db.one(f"{_SELECT} WHERE c.id=?", (cl["id"],))
            want_name, want_on = label(cl), active(cl)
            patch = {}
            if rc.get("name") != want_name:
                patch["name"] = want_name
            if parse_ts(rc.get("expiresAt")) != parse_ts(cl["user_expires"]):
                patch["expiresAt"] = cl["user_expires"]
            if cl["ipv4"] and rc.get("ipv4") != cl["ipv4"]:
                patch["ipv4"] = cl["ipv4"]
            if "uid" in rc and rc["uid"] != cl["uid"]:      # агент хранит скрытый ID профиля
                patch["uid"] = cl["uid"]
            if patch:
                try:
                    rc.update(await node.json("PATCH", f"/clients/{wid}", json=patch))
                except nodes.NodeError as e:
                    _warn_once((node.id, wid, "patch"), "нода %s: клиент %s не обновлён: %s", node.name, want_name, e)
            if bool(rc.get("enabled")) != want_on:
                await node.req("POST", f"/clients/{wid}/{'enable' if want_on else 'disable'}")
                rc["enabled"] = want_on

        # 4. Конфиги без профиля на этой ноде — создать (тот же IP, срок, состояние).
        # Клиент из 2.4, чья нода исчезла до первой синхронизации (VPN убран с сервера панели),
        # не может взять состояние с ноды — принимаем его со свободным IP.
        for cl in clients_by_id.values():
            if not cl["adopted"] and not cl["deleted"] and \
                    not db.one("SELECT 1 FROM profiles WHERE client_id=?", (cl["id"],)):
                ip = cl["ipv4"] or free_ip()
                db.execute("UPDATE clients SET ipv4=?, adopted=1 WHERE id=?", (ip, cl["id"]))
                cl.update(ipv4=ip, adopted=1)
                log.info("конфиг %s без профилей принят в панель с адресом %s", label(cl), ip)
        have = {p["client_id"] for p in profs.values()}
        for cl in clients_by_id.values():
            if cl["deleted"] or cl["user_id"] is None or not cl["adopted"] or cl["id"] in have or not cl["ipv4"]:
                continue
            try:
                rc = await node.json("POST", "/clients", json={"name": label(cl), "ipv4": cl["ipv4"],
                                                               "expiresAt": cl["user_expires"], "uid": cl["uid"]})
            except nodes.NodeError as e:
                _warn_once((node.id, "create", cl["id"]), "нода %s: профиль конфига %s не создан: %s",
                           node.name, label(cl), e)
                continue
            if not active(cl):
                await node.req("POST", f"/clients/{rc['id']}/disable")
                rc["enabled"] = False
            pid = db.execute("INSERT INTO profiles(client_id, node_id, wg_id, public_key) VALUES(?,?,?,?)",
                             (cl["id"], node.id, rc["id"], rc.get("publicKey")))
            profs[rc["id"]] = {"id": pid, "client_id": cl["id"], "node_id": node.id, "wg_id": rc["id"]}
            remote[rc["id"]] = rc
            log.info("нода %s: создан профиль конфига %s (%s)", node.name, label(cl), cl["ipv4"])

        # 5. Удалённые конфиги без профилей ни на одной ноде — удалить из панели окончательно
        db.execute("DELETE FROM clients WHERE (deleted=1 OR user_id IS NULL) "
                   "AND NOT EXISTS (SELECT 1 FROM profiles WHERE client_id=clients.id)")

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
    """Профили → по конфигу: последний handshake, суммарный трафик, ноды."""
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
