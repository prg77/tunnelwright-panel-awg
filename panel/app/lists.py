"""Справочник списков: сети (страны + подсети) и приложения (процессы, папки)."""
import ipaddress
import json
import re

from . import db, geoip

KINDS = ("net", "app")
MAX_ITEMS = 5000
APP_RE = re.compile(r"[^,\r\n\x00-\x1f]{1,260}")


class ListError(ValueError):
    pass


def _name(name) -> str:
    name = str(name or "").strip()[:64]
    if not name:
        raise ListError("имя списка не задано")
    return name


def parse_cidr(s: str) -> str:
    try:
        net = ipaddress.ip_network(s.strip(), strict=False)
    except ValueError:
        raise ListError(f"неверная подсеть: {s.strip()[:50]}")
    if net.version != 4:
        raise ListError(f"IPv6 не поддерживается: {s.strip()[:50]}")
    return str(net)


def clean(kind: str, data: dict) -> dict:
    """Проверка и нормализация содержимого списка."""
    if kind == "net":
        countries = []
        for cc in data.get("countries") or []:
            cc = str(cc).strip().lower()
            if not geoip.valid(cc):
                raise ListError(f"неверный код страны: {cc[:10]}")
            if cc not in countries:
                countries.append(cc)
        cidrs = []
        for s in data.get("cidrs") or []:
            if str(s).strip():
                c = parse_cidr(str(s))
                if c not in cidrs:
                    cidrs.append(c)
        if len(countries) + len(cidrs) > MAX_ITEMS:
            raise ListError(f"не больше {MAX_ITEMS} записей")
        return {"countries": countries, "cidrs": cidrs}
    apps = []
    for a in data.get("apps") or []:
        a = str(a).strip()
        if not a:
            continue
        if not APP_RE.fullmatch(a):
            raise ListError(f"недопустимое приложение или путь: {a[:50]}")
        if a not in apps:
            apps.append(a)
    if len(apps) > MAX_ITEMS:
        raise ListError(f"не больше {MAX_ITEMS} записей")
    return {"apps": apps}


def _row(r) -> dict:
    return {"id": r["id"], "kind": r["kind"], "name": r["name"], "updated_at": r["updated_at"],
            **json.loads(r["data"] or "{}")}


def usage() -> dict[int, list[int]]:
    """{list_id: [client_id, …]} — какие клиенты используют список."""
    out: dict[int, list[int]] = {}
    for r in db.query("SELECT client_id, net_lists, app_lists FROM client_routing"):
        for lid in json.loads(r["net_lists"]) + json.loads(r["app_lists"]):
            out.setdefault(lid, []).append(r["client_id"])
    return out


def all_lists(kind: str | None = None) -> list[dict]:
    used = usage()
    sql, args = "SELECT * FROM lists", ()
    if kind:
        sql, args = sql + " WHERE kind=?", (kind,)
    return [{**_row(r), "clients": used.get(r["id"], [])}
            for r in db.query(sql + " ORDER BY kind, name COLLATE NOCASE", args)]


def get(list_id: int) -> dict | None:
    r = db.one("SELECT * FROM lists WHERE id=?", (list_id,))
    return _row(r) if r else None


def _check_unique(kind, name, exclude_id=None):
    r = db.one("SELECT id FROM lists WHERE kind=? AND name=?", (kind, name))
    if r and r["id"] != exclude_id:
        raise ListError(f"список «{name}» уже есть")


def create(kind: str, name, data: dict) -> dict:
    if kind not in KINDS:
        raise ListError("неверный тип списка")
    name = _name(name)
    _check_unique(kind, name)
    lid = db.execute("INSERT INTO lists(kind, name, data) VALUES(?,?,?)",
                     (kind, name, json.dumps(clean(kind, data))))
    return get(lid)


def update(list_id: int, name=None, data: dict | None = None) -> dict:
    cur = get(list_id)
    if not cur:
        raise ListError("список не найден")
    new_name = _name(name) if name is not None else cur["name"]
    _check_unique(cur["kind"], new_name, list_id)
    new_data = clean(cur["kind"], data) if data is not None else clean(cur["kind"], cur)
    db.execute("UPDATE lists SET name=?, data=?, updated_at=unixepoch() WHERE id=?",
               (new_name, json.dumps(new_data), list_id))
    return get(list_id)


def duplicate(list_id: int) -> dict:
    cur = get(list_id)
    if not cur:
        raise ListError("список не найден")
    base = f"{cur['name']} (копия)"[:60]
    name, n = base, 2
    while db.one("SELECT id FROM lists WHERE kind=? AND name=?", (cur["kind"], name)):
        name, n = f"{base} {n}", n + 1
    return create(cur["kind"], name, cur)


def delete(list_id: int):
    """Удалить список и убрать его из настроек клиентов."""
    with db.tx() as c:
        c.execute("BEGIN")
        try:
            for r in c.execute("SELECT client_id, net_lists, app_lists FROM client_routing").fetchall():
                net = [i for i in json.loads(r["net_lists"]) if i != list_id]
                app = [i for i in json.loads(r["app_lists"]) if i != list_id]
                c.execute("UPDATE client_routing SET net_lists=?, app_lists=? WHERE client_id=?",
                          (json.dumps(net), json.dumps(app), r["client_id"]))
            c.execute("DELETE FROM lists WHERE id=?", (list_id,))
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise


def used_countries() -> set[str]:
    out = set()
    for r in db.query("SELECT data FROM lists WHERE kind='net'"):
        out.update(json.loads(r["data"]).get("countries", []))
    return out
