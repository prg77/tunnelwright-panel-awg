"""Адаптер к API wg-easy 15.x: первичная настройка, перенос со старой установки, клиенты.

API wg-easy работает по Basic-auth логином его администратора. Эту учётку создаёт
агент при первой настройке и хранит в CREDS_FILE (права 600) — больше её никто не знает.
"""
import json
import logging
import os
import secrets

import httpx

from . import config

log = logging.getLogger("node.wgeasy")

# Поля, которые принимает POST /api/client/{id} (ClientUpdateSchema wg-easy 15.5)
CLIENT_UPDATE_FIELDS = (
    "name", "enabled", "expiresAt", "ipv4Address", "ipv6Address",
    "preUp", "postUp", "preDown", "postDown",
    "allowedIps", "serverAllowedIps", "firewallIps", "mtu",
    "jC", "jMin", "jMax", "i1", "i2", "i3", "i4", "i5",
    "contentPaddingAddition", "rekeyAfterTime", "rekeyTimeout", "rejectAfterTime",
    "keepaliveTimeout", "maxHandshakeAttempts", "disableCookies",
    "persistentKeepalive", "serverEndpoint", "dns",
)

# Параметры AmneziaWG сервера: поле wg0.json старого форка → поле интерфейса wg-easy
AWG_IMPORT_MAP = {"jC": "jc", "jMin": "jmin", "jMax": "jmax", "s1": "s1", "s2": "s2",
                  "h1": "h1", "h2": "h2", "h3": "h3", "h4": "h4"}


class WgEasyError(Exception):
    pass


def _load_creds():
    try:
        return json.loads(config.CREDS_FILE.read_text())
    except (OSError, ValueError):
        return None


def _save_creds(creds):
    config.CREDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = config.CREDS_FILE.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(creds, f)
    os.replace(tmp, config.CREDS_FILE)


class WgEasy:
    def __init__(self):
        self._http = httpx.AsyncClient(base_url=config.WG_EASY_URL, timeout=15)
        self._creds = _load_creds()

    async def close(self):
        await self._http.aclose()

    # ── низкоуровневые запросы ──────────────────────────────────
    async def _req(self, method, path, *, auth=True, **kw):
        if auth:
            if not self._creds:
                raise WgEasyError("wg-easy ещё не настроен агентом")
            kw["auth"] = (self._creds["username"], self._creds["password"])
        r = await self._http.request(method, "/api" + path, **kw)
        if r.status_code >= 400:
            raise WgEasyError(f"{method} {path}: {r.status_code} {r.text[:200]}")
        return r

    async def _json(self, method, path, **kw):
        return (await self._req(method, path, **kw)).json()

    # ── первичная настройка ─────────────────────────────────────
    async def ready(self) -> bool:
        """wg-easy отвечает и наша учётка работает."""
        if not self._creds:
            return False
        try:
            await self._req("GET", "/client")
            return True
        except (WgEasyError, httpx.HTTPError):
            return False

    async def bootstrap(self):
        """Идемпотентная настройка wg-easy: учётка, перенос или новая установка, userconfig."""
        if await self.ready():
            await self._apply_import_if_pending()
            return
        if self._creds:
            raise WgEasyError("учётка агента не подходит к wg-easy — нужен сброс wg-easy")

        creds = {"username": "tunnelwright-node", "password": secrets.token_urlsafe(32)}
        _save_creds(creds)  # до setup/2, чтобы не потерять пароль при сбое
        try:
            await self._req("POST", "/setup/2", auth=False,
                            json={"username": creds["username"], "password": creds["password"],
                                  "confirmPassword": creds["password"]})
        except WgEasyError:
            config.CREDS_FILE.unlink(missing_ok=True)
            raise WgEasyError("wg-easy уже настроен не агентом (setup/2 отклонён) — нужен сброс wg-easy")
        self._creds = creds

        if config.IMPORT_FILE.exists():
            old = config.IMPORT_FILE.read_text()
            await self._req("POST", "/setup/migrate", auth=False, json={"file": old})
            log.info("перенос wg0.json выполнен")
            await self._apply_interface(json.loads(old).get("server", {}))
            config.IMPORT_FILE.rename(config.IMPORT_FILE.with_suffix(".imported"))
        else:
            await self._req("POST", "/setup/4", auth=False,
                            json={"host": config.WG_HOST, "port": config.WG_PORT})
            await self._apply_interface({})
        await self.apply_userconfig()
        await self._reset_client_defaults()
        await self._req("POST", "/admin/interface/restart")
        log.info("wg-easy настроен")

    async def _reset_client_defaults(self):
        """Импорт копирует в клиентов тогдашние значения по умолчанию (IPv6, keepalive 0) —
        сбрасываем DNS и AllowedIPs на общие настройки, keepalive — на WG_KEEPALIVE."""
        for c in await self.list_clients():
            await self.update_client(c["id"], {"dns": None, "allowedIps": None,
                                               "persistentKeepalive": config.WG_KEEPALIVE})

    async def _apply_import_if_pending(self):
        # Перенос, прерванный после setup/migrate: параметры AmneziaWG ещё не записаны
        if config.IMPORT_FILE.exists():
            old = json.loads(config.IMPORT_FILE.read_text())
            await self._apply_interface(old.get("server", {}))
            config.IMPORT_FILE.rename(config.IMPORT_FILE.with_suffix(".imported"))
            await self._req("POST", "/admin/interface/restart")

    async def _apply_interface(self, old_server):
        """Порт интерфейса = WG_PORT (в compose проброс WG_PORT:WG_PORT) и параметры AmneziaWG
        старой установки: импорт wg-easy их теряет, а без них старые клиенты не подключатся."""
        iface = await self._json("GET", "/admin/interface")
        iface["port"] = config.WG_PORT
        for new_key, old_key in AWG_IMPORT_MAP.items():
            v = old_server.get(old_key)
            if v not in (None, ""):
                iface[new_key] = str(v) if new_key.startswith("h") else int(v)
        await self._req("POST", "/admin/interface", json=iface)
        if old_server:
            log.info("параметры AmneziaWG перенесены")

    async def apply_userconfig(self):
        """Шаблон клиентских конфигов: адрес, порт, DNS, только IPv4, keepalive."""
        uc = await self._json("GET", "/admin/userconfig")
        uc.update({
            "host": config.WG_HOST or uc.get("host"),
            "port": config.WG_PORT,
            "defaultDns": config.WG_DNS,
            "defaultAllowedIps": ["0.0.0.0/0"],
            "defaultPersistentKeepalive": config.WG_KEEPALIVE,
            "defaultMtu": config.WG_MTU,
        })
        uc = {k: v for k, v in uc.items() if k not in ("id", "createdAt", "updatedAt")}
        await self._req("POST", "/admin/userconfig", json=uc)

    # ── клиенты ─────────────────────────────────────────────────
    async def list_clients(self):
        return await self._json("GET", "/client")

    async def get_client(self, cid):
        return await self._json("GET", f"/client/{cid}")

    async def create_client(self, name, expires_at=None):
        r = await self._json("POST", "/client", json={"name": name, "expiresAt": expires_at})
        return r["clientId"]

    async def update_client(self, cid, patch):
        cur = await self.get_client(cid)
        body = {k: cur.get(k) for k in CLIENT_UPDATE_FIELDS}
        body.update({k: v for k, v in patch.items() if k in CLIENT_UPDATE_FIELDS})
        await self._req("POST", f"/client/{cid}", json=body)

    async def delete_client(self, cid):
        await self._req("DELETE", f"/client/{cid}")

    async def set_enabled(self, cid, enabled: bool):
        await self._req("POST", f"/client/{cid}/{'enable' if enabled else 'disable'}")

    async def configuration(self, cid) -> str:
        return (await self._req("GET", f"/client/{cid}/configuration")).text

    async def qrcode(self, cid) -> str:
        return (await self._req("GET", f"/client/{cid}/qrcode.svg")).text

    async def interface(self):
        iface = await self._json("GET", "/admin/interface")
        iface.pop("privateKey", None)
        return iface
