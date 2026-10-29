"""Маршрутизация клиента: какие сети и приложения идут через VPN.

Сети: all — весь трафик; include — только сети из списков (AllowedIPs);
exclude — всё, кроме сетей из списков (#@ws:DisallowedIPs, понимает WireSock).
Приложения: include → #@ws:AllowedApps, exclude → #@ws:DisallowedApps (WireSock).
Свои строки (extra) применяются последними и могут переопределить любой параметр.
"""
import ipaddress
import json
import re
from urllib.parse import quote

from . import clients, db, geoip, lists, nodes

MODES = ("all", "include", "exclude")
MAX_EXTRA = 8000
WS = "#@ws:"
# параметры секции [Interface]; остальные строки без заголовка уходят в [Peer]
INTERFACE_KEYS = {"privatekey", "address", "dns", "mtu", "listenport", "jc", "jmin", "jmax", "jd",
                  "s1", "s2", "s3", "s4", "h1", "h2", "h3", "h4", "i1", "i2", "i3", "i4", "i5",
                  "id", "ip", "ib"}
LINE_RE = re.compile(r"\s*((?:#@ws:)?[A-Za-z][A-Za-z0-9]*)\s*=\s*(.*?)\s*")

DEFAULT = {"net_mode": "all", "net_lists": [], "app_mode": "all", "app_lists": [], "extra": ""}


class RoutingError(ValueError):
    pass


def get(client_id: int) -> dict:
    r = db.one("SELECT * FROM client_routing WHERE client_id=?", (client_id,))
    if not r:
        return dict(DEFAULT)
    return {"net_mode": r["net_mode"], "net_lists": json.loads(r["net_lists"]),
            "app_mode": r["app_mode"], "app_lists": json.loads(r["app_lists"]), "extra": r["extra"]}


def all_routing() -> dict[int, dict]:
    return {r["client_id"]: {"net_mode": r["net_mode"], "app_mode": r["app_mode"],
                             "custom": bool(r["extra"].strip())}
            for r in db.query("SELECT * FROM client_routing")}


def _ids(kind, ids) -> list[int]:
    out = []
    for i in ids or []:
        lst = lists.get(int(i))
        if not lst or lst["kind"] != kind:
            raise RoutingError(f"список {i} не найден")
        if lst["id"] not in out:
            out.append(lst["id"])
    return out


def parse_extra(text: str) -> list[tuple[str | None, str, str]]:
    """Строки «Ключ = значение» → [(секция|None, ключ, значение)]. Ошибка — с номером строки."""
    out, section = [], None
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or (line.startswith("#") and not line.startswith(WS)):
            continue
        if line.lower() in ("[interface]", "[peer]"):
            section = line[1:-1].capitalize()
            continue
        m = LINE_RE.fullmatch(line)
        if not m:
            raise RoutingError(f"строка {n}: ожидается «Параметр = значение»")
        out.append((section, m.group(1), m.group(2)))
    return out


def save(client_id: int, body: dict) -> dict:
    cur = get(client_id)
    new = {**cur, **{k: body[k] for k in DEFAULT if k in body and body[k] is not None}}
    if new["net_mode"] not in MODES or new["app_mode"] not in MODES:
        raise RoutingError("неверный режим")
    new["net_lists"] = _ids("net", new["net_lists"])
    new["app_lists"] = _ids("app", new["app_lists"])
    new["extra"] = str(new["extra"] or "").replace("\r\n", "\n").strip()
    if len(new["extra"]) > MAX_EXTRA:
        raise RoutingError(f"свои параметры — не больше {MAX_EXTRA} символов")
    parse_extra(new["extra"])
    if new["net_mode"] != "all" and not new["net_lists"]:
        raise RoutingError("выберите хотя бы один список сетей")
    if new["app_mode"] != "all" and not new["app_lists"]:
        raise RoutingError("выберите хотя бы один список приложений")
    db.execute("INSERT INTO client_routing(client_id, net_mode, net_lists, app_mode, app_lists, extra) "
               "VALUES(?,?,?,?,?,?) ON CONFLICT(client_id) DO UPDATE SET net_mode=excluded.net_mode, "
               "net_lists=excluded.net_lists, app_mode=excluded.app_mode, app_lists=excluded.app_lists, "
               "extra=excluded.extra",
               (client_id, new["net_mode"], json.dumps(new["net_lists"]), new["app_mode"],
                json.dumps(new["app_lists"]), new["extra"]))
    return new


# ── сборка конфига ──────────────────────────────────────────────
class Conf:
    """Конфиг WireGuard как секции со строками; ключи сравниваются без учёта регистра."""

    def __init__(self, text: str):
        self.head: list[str] = []
        self.sections: list[tuple[str, list[str]]] = []
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("[") and s.endswith("]"):
                self.sections.append((s[1:-1].capitalize(), []))
            elif self.sections:
                self.sections[-1][1].append(line)
            else:
                self.head.append(line)

    def _lines(self, section):
        for name, lines in self.sections:
            if name == section:
                return lines
        lines: list[str] = []
        self.sections.append((section, lines))
        return lines

    @staticmethod
    def _key(line):
        m = LINE_RE.fullmatch(line)
        return m.group(1).lower() if m else None

    def get(self, section, key):
        for line in self._lines(section):
            if self._key(line) == key.lower():
                return LINE_RE.fullmatch(line).group(2)
        return None

    def set(self, section, key, value):
        lines = self._lines(section)
        idx = [i for i, l in enumerate(lines) if self._key(l) == key.lower()]
        for i in reversed(idx[1:]):
            del lines[i]
        if value == "":
            if idx:
                del lines[idx[0]]
            return
        new = f"{key} = {value}"
        if idx:
            lines[idx[0]] = new
        else:
            while lines and not lines[-1].strip():
                lines.pop()
            lines.append(new)

    def text(self) -> str:
        out = list(self.head)
        for name, lines in self.sections:
            body = list(lines)
            while body and not body[-1].strip():
                body.pop()
            if out and out[-1].strip():
                out.append("")
            out += [f"[{name}]"] + body
        return "\n".join(out).strip() + "\n"


async def _networks(list_ids) -> list[ipaddress.IPv4Network]:
    nets = []
    for lid in list_ids:
        lst = lists.get(lid)
        if not lst:
            continue
        for cc in lst.get("countries", []):
            nets += await geoip.networks(cc)
        nets += [ipaddress.ip_network(c) for c in lst.get("cidrs", [])]
    return list(ipaddress.collapse_addresses(nets))


def _apps(list_ids) -> list[str]:
    out = []
    for lid in list_ids:
        lst = lists.get(lid)
        for a in (lst or {}).get("apps", []):
            if a not in out:
                out.append(a)
    return out


async def render(text: str, r: dict) -> tuple[str, dict]:
    """Конфиг ноды + настройки маршрутизации → итоговый конфиг и сводка."""
    conf = Conf(text)
    info = {"allowed": None, "disallowed": 0, "apps": 0}
    if r["net_mode"] != "all":
        nets = await _networks(r["net_lists"])
        if not nets:
            raise RoutingError("в выбранных списках сетей нет ни одной подсети")
        if r["net_mode"] == "include":
            # DNS-серверы из конфига тоже идут через туннель, иначе имена не резолвятся
            for d in (conf.get("Interface", "DNS") or "").split(","):
                try:
                    ip = ipaddress.ip_address(d.strip())
                except ValueError:
                    continue
                if ip.version == 4:
                    nets.append(ipaddress.ip_network(f"{ip}/32"))
            nets = list(ipaddress.collapse_addresses(nets))
            conf.set("Peer", "AllowedIPs", ", ".join(map(str, nets)))
            info["allowed"] = len(nets)
        else:
            conf.set("Peer", WS + "DisallowedIPs", ", ".join(map(str, nets)))
            info["disallowed"] = len(nets)
    if r["app_mode"] != "all":
        apps = _apps(r["app_lists"])
        if not apps:
            raise RoutingError("в выбранных списках приложений пусто")
        key = "AllowedApps" if r["app_mode"] == "include" else "DisallowedApps"
        conf.set("Peer", WS + key, ", ".join(apps))
        info["apps"] = len(apps)
    for section, key, value in parse_extra(r["extra"]):
        if section is None:
            section = "Interface" if key.lower().removeprefix(WS.lower()) in INTERFACE_KEYS else "Peer"
        conf.set(section, key, value)
    out = conf.text()
    info["size"] = len(out.encode())
    return out, info


async def client_config(panel_id: int, node_id: int | None = None) -> tuple[str, str, dict]:
    """Итоговый конфиг профиля клиента на ноде (без node_id — первая нода): (текст, имя файла, сводка)."""
    node, wg_id, _ = clients.lookup(panel_id, node_id)
    raw = (await node.req("GET", f"/clients/{wg_id}/config")).text
    text, info = await render(raw, get(panel_id))
    name = (clients.get(panel_id) or {}).get("name") or f"client-{panel_id}"
    if len(nodes.all_nodes()) > 1:
        name = f"{name}-{node.name}"
    info["node_id"], info["node_name"] = node.id, node.name
    return text, name, info


def attachment(name: str, fallback: str) -> str:
    """Content-Disposition для .conf: ASCII-имя для старых клиентов и полное имя в UTF-8 (RFC 6266)."""
    ascii_name = re.sub(r"[^a-zA-Z0-9_=+.-]", "-", name)[:40].strip("-") or fallback
    full = re.sub(r'[\/:*?"<>|\x00-\x1f]', "_", name)[:60] or fallback
    return f'attachment; filename="{ascii_name}.conf"; filename*=UTF-8\'\'{quote(full + ".conf")}'
