"""Настройки node-agent из окружения."""
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("NODE_DATA_DIR", "/data"))
TOKEN_FILE = Path(os.environ.get("NODE_TOKEN_FILE", "/run/tunnelwright/node.token"))
# Нода в /opt/vpn-node, получившая новый агент автообновлением: её compose монтирует токен по прежнему пути
_LEGACY_TOKEN = Path("/run/vpn-panel/node.token")
if "NODE_TOKEN_FILE" not in os.environ and not TOKEN_FILE.exists() and _LEGACY_TOKEN.exists():
    TOKEN_FILE = _LEGACY_TOKEN

WG_EASY_URL = os.environ.get("WG_EASY_URL", "http://127.0.0.1:51821")
WG_INTERFACE = os.environ.get("WG_INTERFACE", "wg0")

# Параметры, которые видят клиенты в конфиге
WG_HOST = os.environ.get("WG_HOST", "")
WG_PORT = int(os.environ.get("WG_PORT", "51820"))
WG_DNS = [d.strip() for d in os.environ.get("WG_DNS", "1.1.1.1").split(",") if d.strip()]
WG_KEEPALIVE = int(os.environ.get("WG_KEEPALIVE", "25"))
WG_MTU = int(os.environ.get("WG_MTU", "1420"))
# Подсеть клиентов — та же, что у панели (panel/app/clients.py SUBNET). Только расширение: адреса сохраняются.
WG_IPV4_CIDR = os.environ.get("WG_IPV4_CIDR", "10.8.0.0/20")

APP_VERSION = os.environ.get("APP_VERSION", "dev")

WG_DATA_DIR = Path(os.environ.get("WG_DATA_DIR", "/wg"))  # том wg-easy (только чтение) — для бэкапа
WG_DB_FILE = WG_DATA_DIR / "wg-easy.db"
CREDS_FILE = DATA_DIR / "wg-easy-admin.json"   # учётка администратора wg-easy (создаёт агент)
LIMITS_FILE = DATA_DIR / "limits.json"          # лимиты скорости {ip: {down, up}} в Мбит/с
IMPORT_FILE = DATA_DIR / "import" / "wg0.json"  # wg0.json старой установки для переноса
CIDR_PLAN_FILE = DATA_DIR / "cidr-change.json"  # адреса клиентов на время смены подсети (продолжение после сбоя)

# Удалённая нода: с каких адресов принимать запросы (IP панели). Пусто — без ограничения (локальная нода).
ALLOWED_IPS = {ip.strip() for ip in os.environ.get("NODE_ALLOWED_IPS", "").split(",") if ip.strip()}
# Каталог запросов автообновления (хост: /opt/tunnelwright-node/update, обрабатывает tunnelwright-node-update.path).
# Нет каталога — автообновление на ноде не настроено, обновить её можно только по SSH.
UPDATE_DIR = Path(os.environ.get("NODE_UPDATE_DIR", "/update"))
