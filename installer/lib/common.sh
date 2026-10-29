# shellcheck shell=bash
# Общие константы и утилиты установщика. Подключается из installer/setup.sh
# (REPO_ROOT — корень распакованного релиза).

# Намеренно НЕ меняем IFS глобально — IFS=$'\n\t' ломает read, printf и подстановки

# Подавляем интерактивные вопросы dpkg/apt глобально
export DEBIAN_FRONTEND=noninteractive
export APT_LISTCHANGES_FRONTEND=none

APP_VERSION="$(tr -d '[:space:]' < "${REPO_ROOT}/VERSION" 2>/dev/null || echo dev)"
GITHUB_REPO="prg77/tunnelwright-panel-awg"

# ─────────────────────── Цвета и иконки ──────────────────────
RED='\033[0;31m';   GREEN='\033[0;32m';  YELLOW='\033[1;33m'
BLUE='\033[0;34m';  CYAN='\033[0;36m';   BOLD='\033[1m'
DIM='\033[2m';      RESET='\033[0m'
ICON_OK="✅"; ICON_WARN="⚠️ "; ICON_INFO="ℹ️ "; ICON_FAIL="❌"
ICON_DOCKER="🐳";  ICON_GEAR="⚙️ ";  ICON_HEART="💚"; ICON_VPN="🔐"
ICON_ARROW="→";    ICON_REACT="⚛️ "

# ─────────────────────── Пути и файлы ────────────────────────
BASE_DIR="/opt/tunnelwright"
CONFIG_DIR="${BASE_DIR}"
LOG_DIR="/var/log/tunnelwright"
INSTALL_LOG="${LOG_DIR}/install.log"
COMPOSE_FILE="${BASE_DIR}/docker-compose.yml"
SAVED_CONFIG="${BASE_DIR}/.install_state"
PANEL_ENV="${BASE_DIR}/panel.env"             # параметры установки для host-скриптов
SECRETS_DIR="${BASE_DIR}/secrets"             # panel/ → panel-api, node/ → node-agent
TLS_DIR="${BASE_DIR}/tls"
LEGACY_IMPORT_DIR="${BASE_DIR}/legacy"        # данные amnezia-wg для однократного импорта в panel-api
BACKUP_DIR="${BASE_DIR}/backups"
BUILD_DIR="${BASE_DIR}/build"                 # исходники образов для --build-local

# Установка amnezia-wg — только для переноса
LEGACY_BASE="/opt/amnezia-wg"
LEGACY_WG_VOLUME="amnezia_wg_data"

# Путь к файлу с параметрами для non-interactive режима.
# Загрузчик (install.sh) передаёт найденный install.env через переменную INSTALL_ENV.
INSTALL_ENV="${INSTALL_ENV:-$(pwd)/install.env}"

# ─────────────────────── Параметры по умолчанию ──────────────
DEFAULT_WEB_PORT=58821
DEFAULT_WG_PORT=58820
DEFAULT_DNS="1.1.1.1"
PROJECT_NAME="tunnelwright"
WG_EASY_IMAGE="ghcr.io/wg-easy/wg-easy:15.5.0@sha256:071f79a639e9361123a5e57733107320207b844ddbbd92dfa6962f541fe8aac8"
WEB_IMAGE="ghcr.io/prg77/tunnelwright-web:${APP_VERSION}"
API_IMAGE="ghcr.io/prg77/tunnelwright-api:${APP_VERSION}"
NODE_IMAGE="ghcr.io/prg77/tunnelwright-node:${APP_VERSION}"
CONTAINERS=(tunnelwright-wg tunnelwright-node tunnelwright-api tunnelwright-web)

# VPN-нода на сервере панели: yes/no. Новые установки — no (VPN на удалённых нодах),
# перенос с amnezia-wg — yes. Флаги --local-vpn / --no-local-vpn меняют выбор.
local_vpn() { [[ "${LOCAL_VPN:-no}" == "yes" ]]; }

# Pre-initialize optional vars
TG_TOKEN=""; TG_CHAT_ID=""; TG_ENABLED="false"
PORTAL_NAME="Private World"
WG_HOST=""; WG_PASSWORD=""; WEB_PORT=${DEFAULT_WEB_PORT}
WG_PORT=${DEFAULT_WG_PORT}; WG_LANG="ru"

# ─────────────────────── Утилиты ─────────────────────────────
timestamp() { date '+%Y-%m-%d %H:%M:%S'; }

log() {
  local lvl="$1"; shift
  local msg="$*"
  local ts; ts=$(timestamp)
  echo "[${ts}] [${lvl}] ${msg}" >> "${INSTALL_LOG}" 2>/dev/null || true
  case "$lvl" in
    OK)   echo -e "  ${ICON_OK} ${GREEN}${msg}${RESET}" ;;
    WARN) echo -e "  ${ICON_WARN} ${YELLOW}${msg}${RESET}" ;;
    INFO) echo -e "  ${ICON_INFO} ${DIM}${msg}${RESET}" ;;
    ERROR)echo -e "  ${ICON_FAIL} ${RED}${msg}${RESET}" ;;
  esac
}
die() { log ERROR "$*"; exit 1; }
require_root() { [[ $EUID -eq 0 ]] || die "Запустите от root: sudo bash $0"; }

# ─────────────────────── Прогресс-бар ────────────────────────
progress_bar() {
  local cur="$1" tot="$2" lbl="${3:-}"
  local pct=$(( cur * 100 / tot ))
  local filled=$(( pct / 4 ))
  local bar=""; for ((i=0;i<25;i++)); do bar+=$([[ $i -lt $filled ]] && echo "█" || echo "░"); done
  printf "\r  [%s] %3d%%  %s          " "$bar" "$pct" "$lbl"
  [[ $cur -eq $tot ]] && echo ""
}

run_with_progress() {
  local lbl="$1" secs="$2"; shift 2
  echo -e "  ${ICON_GEAR} ${lbl}..."
  # Запускаем команду, вывод идёт в лог
  local exit_code=0
  "$@" >> "${INSTALL_LOG}" 2>&1 || exit_code=$?
  if [[ $exit_code -ne 0 ]]; then
    echo ""
    echo -e "  ${RED}Последние строки лога (${INSTALL_LOG}):${RESET}"
    tail -10 "${INSTALL_LOG}" | sed 's/^/    /'
    log ERROR "${lbl} завершился с ошибкой (код: ${exit_code})"
    return $exit_code
  fi
  log OK "${lbl}"
}

# ─────────────────────── Баннер ──────────────────────────────
print_banner() {
  echo -e "${CYAN}${BOLD}"
  cat << 'EOF'
   _____                             _                  _         _      _
  |_   _| _   _  _ __   _ __    ___ | |__      __ _ __ (_)  __ _ | |__  | |_
    | |  | | | || '_ \ | '_ \  / _ \| |\ \ /\ / /| '__|| | / _` || '_ \ | __|
    | |  | |_| || | | || | | ||  __/| | \ V  V / | |   | || (_| || | | || |_
    |_|   \__,_||_| |_||_| |_| \___||_|  \_/\_/  |_|   |_| \__, ||_| |_| \__|
                                                           |___/
EOF
  echo -e "${RESET}"
  echo -e "  ${BOLD}Tunnelwright Panel AWG v${APP_VERSION}${RESET} — VPN-панель для AmneziaWG"
  echo -e "  ${DIM}панель, ноды VPN по SSH, Telegram-бот, бэкапы${RESET}"
  echo ""
}

# ─────────────────────── Шаблоны ─────────────────────────────
# render <шаблон> <результат> KEY=VALUE... — заменяет @@KEY@@ на VALUE.
# Подстановка строковая (без eval/sed), безопасна для любых символов в значениях.
render() {
  local src="$1" dst="$2" kv content
  shift 2
  content="$(<"$src")"
  for kv in "$@"; do
    content="${content//"@@${kv%%=*}@@"/"${kv#*=}"}"
  done
  printf '%s\n' "$content" > "$dst"
}
