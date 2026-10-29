"""Блокировка торрент-трафика клиентов VPN (всегда включена).

Агент работает в сетевом namespace wg-easy, поэтому правила iptables ставятся в цепочку FORWARD
этого namespace — через неё идёт весь трафик клиентов в обе стороны.

Блокировка только по содержимому пакетов — сигнатурам протокола BitTorrent: рукопожатие пиров,
запросы к HTTP- и UDP-трекерам, DHT. Порты и число соединений не ограничиваются: у клиентов
бывают любые порты и много соединений, обычный трафик не должен страдать. Зашифрованный
торрент (MSE/PE) сигнатур не содержит — без DPI его не распознать, это осознанный компромисс.

Правила идемпотентны: своя цепочка очищается и заполняется заново, переходы из FORWARD
добавляются, только если их нет. Повторное применение — вместе с лимитами скорости.
"""
import logging
import subprocess

from . import config

log = logging.getLogger("node.firewall")

CHAIN = "VPN_TORRENT"

# Строки протокола: рукопожатие пиров, HTTP-трекеры, DHT (bencode-запросы и ответы)
STRINGS = [
    ("all", "BitTorrent protocol"),
    ("tcp", "info_hash="),
    ("tcp", "peer_id="),
    ("udp", "d1:ad2:id20:"),
    ("udp", "d1:rd2:id20:"),
    ("udp", "get_peers"),
    ("udp", "announce_peer"),
    ("udp", "find_node"),
]
# UDP-трекер (BEP 15): connect-запрос начинается с магического числа 0x41727101980
UDP_TRACKER_U32 = "0>>22&0x3C@8=0x417&&0>>22&0x3C@12=0x27101980"

state = {"active": False, "error": None}


def _ipt(*args, check=True) -> subprocess.CompletedProcess:
    r = subprocess.run(["iptables", "-w", "5", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"iptables {' '.join(args)}: {r.stderr.strip()}")
    return r


def rules() -> list[list[str]]:
    out = []
    for proto, s in STRINGS:
        p = [] if proto == "all" else ["-p", proto]
        out.append([*p, "-m", "string", "--algo", "bm", "--string", s, "-j", "DROP"])
    out.append(["-p", "udp", "-m", "u32", "--u32", UDP_TRACKER_U32, "-j", "DROP"])
    return out


def jumps() -> list[list[str]]:
    dev = config.WG_INTERFACE
    return [["-i", dev, "-j", CHAIN], ["-o", dev, "-j", CHAIN]]


def apply() -> dict:
    """Создать/обновить правила. Ошибка (нет модуля ядра) не роняет агента — видна в state."""
    try:
        if _ipt("-n", "-L", CHAIN, check=False).returncode != 0:
            _ipt("-N", CHAIN)
        _ipt("-F", CHAIN)
        for args in rules():
            _ipt("-A", CHAIN, *args)
        for pos, j in enumerate(jumps(), 1):          # наши переходы — в начале FORWARD
            if _ipt("-C", "FORWARD", *j, check=False).returncode != 0:
                _ipt("-I", "FORWARD", str(pos), *j)
        state.update(active=True, error=None)
    except (RuntimeError, OSError) as e:
        state.update(active=False, error=str(e))
        log.error("блокировка торрентов не применена: %s", e)
    return dict(state)


def blocked() -> int | None:
    """Сколько пакетов отброшено правилами (с запуска ноды); None — правила не стоят."""
    r = _ipt("-n", "-v", "-x", "-L", CHAIN, check=False)
    if r.returncode != 0:
        return None
    return sum(int(p[0]) for p in (line.split() for line in r.stdout.splitlines()[2:]) if p and p[0].isdigit())
