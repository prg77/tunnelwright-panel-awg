# shellcheck shell=bash
# ─────────────────────── Проверка ОС ─────────────────────────
check_os() {
  echo -e "\n${BOLD}${BLUE}${ICON_INFO} Проверка системы${RESET}"
  echo "  ───────────────────────────────────────"
  local os_id kernel
  os_id=$(grep '^ID=' /etc/os-release 2>/dev/null | sed 's/^ID=//;s/"//g' || echo "unknown")
  kernel=$(uname -r)
  log INFO "ОС: ${os_id}, ядро: ${kernel}"
  case "$os_id" in
    ubuntu|debian|raspbian) ;;
    centos|rhel|fedora|rocky|almalinux) ;;
    *) log WARN "Нестандартная ОС: ${os_id}. Продолжаем на ваш риск." ;;
  esac
  if ! lsmod | grep -q wireguard 2>/dev/null && \
     ! modprobe wireguard 2>/dev/null; then
    log WARN "Модуль wireguard не загружен. AmneziaWG использует userspace."
  fi
  log OK "Проверка ОС пройдена"
}

# ─────────────────────── Установка зависимостей ──────────────
install_deps() {
  echo -e "\n${BOLD}${BLUE}${ICON_GEAR} Зависимости${RESET}"
  echo "  ───────────────────────────────────────"

  export DEBIAN_FRONTEND=noninteractive

  # Маппинг: имя_пакета → бинарник для проверки (пустая строка = dpkg-query)
  declare -A PKG_BIN=(
    ["curl"]="curl"
    ["wget"]="wget"
    ["ca-certificates"]=""
    ["gnupg"]="gpg"
    ["bc"]="bc"
    ["iproute2"]="ip"
    ["cron"]=""
    ["python3"]="python3"
    ["iptables"]="iptables"
    ["openssl"]="openssl"
  )

  local missing=()
  for pkg in "${!PKG_BIN[@]}"; do
    local bin="${PKG_BIN[$pkg]}"
    if [[ -n "$bin" ]]; then
      command -v "$bin" &>/dev/null || missing+=("$pkg")
    else
      dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed" || missing+=("$pkg")
    fi
  done

  if [[ ${#missing[@]} -gt 0 ]]; then
    log INFO "Не хватает пакетов: ${missing[*]}"
    echo -e "  ${ICON_GEAR} apt-get update..."
    apt-get update -qq >> "${INSTALL_LOG}" 2>&1 || \
      log WARN "apt-get update вернул ненулевой код — продолжаем"
    log OK "apt-get update"
    # apt-get install: не останавливаемся при частичных ошибках
    echo -e "  ${ICON_GEAR} Установка пакетов: ${missing[*]}..."
    if ! apt-get install -y -qq --no-install-recommends "${missing[@]}" \
        2>&1 | tee -a "${INSTALL_LOG}" | \
        grep --line-buffered -E "Setting up|Unpacking|Installing|error" | \
        sed "s/^/    /"; then
      log WARN "apt-get install завершился с предупреждениями — проверьте ${INSTALL_LOG}"
    fi
    log OK "Пакеты установлены"
  else
    log INFO "Все зависимости уже установлены"
  fi

  # Проверяем критичные утилиты
  local critical_ok=true
  for bin in curl wget python3; do
    command -v "$bin" &>/dev/null || { log ERROR "Критичный пакет $bin не установлен"; critical_ok=false; }
  done
  [[ "$critical_ok" == false ]] && die "Не удалось установить критичные зависимости. Проверьте ${INSTALL_LOG}"

  log OK "Зависимости установлены"
}

# ─────────────────────── Docker ──────────────────────────────
# Недонастроенные пакеты ломают любой apt install (частый случай — DKMS-модуль,
# который не собирается под новое ядро). Чиним не сами, а останавливаемся с подсказкой.
check_dpkg_health() {
  local broken
  broken=$(dpkg --audit 2>/dev/null || true)
  [[ -z "$broken" ]] && return 0
  echo -e "\n  ${RED}dpkg в неконсистентном состоянии — apt не сможет ставить пакеты:${RESET}"
  echo "$broken" | sed 's/^/    /' | head -20
  local dkms_pkgs
  dkms_pkgs=$(dpkg -l 2>/dev/null | awk '/^ii/ && $2 ~ /-dkms$/ {print $2}' | tr '\n' ' ')
  if [[ -n "$dkms_pkgs" ]] && grep -q "dkms" /var/log/apt/term.log 2>/dev/null; then
    echo -e "\n  ${YELLOW}Похоже, ядро не настраивается из-за DKMS-модуля: ${dkms_pkgs}${RESET}"
    echo -e "  ${DIM}Если модуль не нужен (панели он не нужен), удалите его и донастройте пакеты:${RESET}"
    echo -e "    apt-get purge -y ${dkms_pkgs}"
  fi
  echo -e "    dpkg --configure -a"
  die "Исправьте состояние dpkg и запустите установку ещё раз"
}

install_docker() {
  echo -e "\n${BOLD}${BLUE}${ICON_DOCKER} Docker${RESET}"
  echo "  ───────────────────────────────────────"
  if command -v docker &>/dev/null; then
    local ver; ver=$(docker --version | sed 's/[^0-9.]*\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\).*/\1/' | head -1)
    log OK "Docker уже установлен: v${ver}"
  else
    check_dpkg_health
    log INFO "Устанавливаем Docker..."
    echo -e "  ${ICON_GEAR} Установка Docker (может занять ~3 мин)..."
    curl -fsSL https://get.docker.com | sh 2>&1 | tee -a "${INSTALL_LOG}" | \
      grep --line-buffered -E "apt|Installing|Installed|Setting up|docker|ERROR" | \
      sed "s/^/    /" || true
    # get.docker.com может не поддерживать свежий релиз дистрибутива — берём пакеты дистрибутива
    if ! command -v docker &>/dev/null; then
      log WARN "get.docker.com не установил Docker — пробуем пакет docker.io из репозитория дистрибутива"
      apt-get install -y -qq --no-install-recommends docker.io >> "${INSTALL_LOG}" 2>&1 || true
    fi
    command -v docker &>/dev/null || die "Docker не установился. Подробности: ${INSTALL_LOG}"
    systemctl enable docker >> "${INSTALL_LOG}" 2>&1 || true
    systemctl start  docker >> "${INSTALL_LOG}" 2>&1 || true
    log OK "Docker установлен: $(docker --version 2>/dev/null)"
  fi
  docker info &>/dev/null || die "Docker установлен, но демон не отвечает: systemctl status docker"

  if ! docker compose version &>/dev/null; then
    echo -e "  ${ICON_GEAR} Установка docker compose..."
    # docker-compose-plugin — репозиторий Docker, docker-compose-v2 — пакет Ubuntu
    local pkg
    for pkg in docker-compose-plugin docker-compose-v2; do
      apt-get install -y -qq --no-install-recommends "$pkg" >> "${INSTALL_LOG}" 2>&1 || true
      docker compose version &>/dev/null && break
    done
    # Fallback: standalone docker compose v2 как CLI-плагин
    if ! docker compose version &>/dev/null; then
      local DC_URL="https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)"
      log INFO "Загружаем docker compose (CLI-плагин)..."
      mkdir -p /usr/local/lib/docker/cli-plugins
      curl -fsSL "$DC_URL" -o /usr/local/lib/docker/cli-plugins/docker-compose 2>>"${INSTALL_LOG}" && \
        chmod +x /usr/local/lib/docker/cli-plugins/docker-compose || true
    fi
    docker compose version &>/dev/null || die "docker compose недоступен после всех попыток установки"
  fi
  log OK "docker compose доступен"
}
