"""Настройки panel-api из окружения."""
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("PANEL_DATA_DIR", "/data"))
DB_FILE = DATA_DIR / "panel.db"

# Пароль первого администратора: файл кладёт установщик, после создания учётки он удаляется
ADMIN_PASSWORD_FILE = Path(os.environ.get("PANEL_ADMIN_PASSWORD_FILE", "/run/tunnelwright/admin-password"))
ADMIN_USERNAME = os.environ.get("PANEL_ADMIN_USERNAME", "admin")
# Начальные настройки чистой установки (имя панели, Telegram) — тоже удаляются после применения
INIT_SETTINGS_FILE = Path(os.environ.get("PANEL_INIT_SETTINGS_FILE", "/run/tunnelwright/initial-settings.json"))

# Локальная нода (этот же сервер)
# Пусто — VPN на сервере панели не ставится, только удалённые ноды
LOCAL_NODE_URL = os.environ.get("LOCAL_NODE_URL", "http://wg-easy:8710")
LOCAL_NODE_TOKEN_FILE = Path(os.environ.get("LOCAL_NODE_TOKEN_FILE", "/run/tunnelwright/node.token"))

# Данные установки amnezia-wg для однократного импорта (каталог dashboard и wg0.json)
LEGACY_DIR = Path(os.environ.get("PANEL_LEGACY_DIR", "/legacy"))

SESSION_COOKIE = "vp_session"
SESSION_TTL_DAYS = int(os.environ.get("PANEL_SESSION_DAYS", "14"))
COOKIE_SECURE = os.environ.get("PANEL_COOKIE_SECURE", "true") == "true"

LOGIN_MAX_FAILS = 5        # неудачных попыток с одного IP …
LOGIN_WINDOW_SEC = 900     # … за 15 минут → блокировка до конца окна

APP_VERSION = os.environ.get("APP_VERSION", "dev")

# Параметры установки — показываются в интерфейсе и уведомлениях
WG_HOST = os.environ.get("PANEL_WG_HOST", "")
WEB_PORT = int(os.environ.get("PANEL_WEB_PORT", "58821"))
WG_PORT = int(os.environ.get("PANEL_WG_PORT", "58820"))
# Адрес панели снаружи (ссылки пользователей из Telegram-бота). За обратным прокси NAS он другой,
# например https://vpn.example.com — тогда задаётся явно
PUBLIC_URL = (os.environ.get("PANEL_PUBLIC_URL") or f"https://{WG_HOST}:{WEB_PORT}").rstrip("/")

# Удалённые ноды: образы, которые ставятся на ноду (совпадают с локальной установкой)
NODE_IMAGE = os.environ.get("PANEL_NODE_IMAGE", f"ghcr.io/prg77/tunnelwright-node:{APP_VERSION}")
WG_EASY_IMAGE = os.environ.get("PANEL_WG_EASY_IMAGE", "ghcr.io/wg-easy/wg-easy:15.5.0")
NODE_BUNDLE_DIR = Path(os.environ.get("PANEL_NODE_BUNDLE_DIR", "/app/node_bundle"))

# Удалённая нода принимает запросы агента только с IP панели (определяется при установке по SSH).
# false — с любого адреса (панель на NAS за домашним интернетом с меняющимся IP); защита остаётся:
# токен ноды и TLS с закреплённым сертификатом. Действует при установке/обновлении ноды по SSH.
NODE_IP_LOCK = os.environ.get("PANEL_NODE_IP_LOCK", "true") != "false"
