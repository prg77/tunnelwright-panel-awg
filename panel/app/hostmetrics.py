"""Метрики сервера панели (дашборд). /proc/stat, /proc/meminfo и /proc/loadavg в контейнере — общие с хостом.

Копия node/app/metrics.py: панель может работать без локальной ноды."""
import shutil
import time

_last_cpu = None


def _cpu_times():
    with open("/proc/stat") as f:
        parts = [int(x) for x in f.readline().split()[1:]]
    idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
    return idle, sum(parts)


def cpu_percent() -> float:
    """Загрузка CPU с прошлого вызова (первый вызов — с момента загрузки системы)."""
    global _last_cpu
    idle, total = _cpu_times()
    prev = _last_cpu or (0, 0)
    _last_cpu = (idle, total)
    d_total = total - prev[1]
    return round(100.0 * (1 - (idle - prev[0]) / d_total), 1) if d_total > 0 else 0.0


def snapshot() -> dict:
    mem = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":", 1)
            mem[k] = int(v.split()[0]) * 1024
    ram_total = mem.get("MemTotal", 0)
    ram_used = ram_total - mem.get("MemAvailable", 0)
    disk = shutil.disk_usage("/")
    with open("/proc/loadavg") as f:
        load1 = f.read().split()[0]
    with open("/proc/uptime") as f:
        uptime = int(float(f.read().split()[0]))
    return {
        "cpu": cpu_percent(),
        "ram_total": ram_total, "ram_used": ram_used,
        "ram_pct": round(100 * ram_used / ram_total, 1) if ram_total else 0,
        "disk_total": disk.total, "disk_used": disk.used,
        "disk_pct": round(100 * disk.used / disk.total) if disk.total else 0,
        "load1": load1, "uptime": uptime, "ts": int(time.time()),
    }
