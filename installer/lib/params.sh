# shellcheck shell=bash
# ─────────────────────── Сохранение/загрузка конфига ─────────
save_config() {
  mkdir -p "${CONFIG_DIR}"
  # Используем printf для безопасной записи — пароль может содержать $, !, \, `
  {
    printf 'SAVED_WG_HOST=%q\n'      "${WG_HOST}"
    printf 'SAVED_WG_PASSWORD=%q\n'  "${WG_PASSWORD}"
    printf 'SAVED_WEB_PORT=%q\n'     "${WEB_PORT}"
    printf 'SAVED_WG_PORT=%q\n'      "${WG_PORT}"
    printf 'SAVED_WG_LANG=%q\n'      "${WG_LANG}"
    printf 'SAVED_TG_TOKEN=%q\n'     "${TG_TOKEN:-}"
    printf 'SAVED_TG_CHAT_ID=%q\n'   "${TG_CHAT_ID:-}"
    printf 'SAVED_PORTAL_NAME=%q\n'  "${PORTAL_NAME:-Private World}"
    printf 'SAVED_LOCAL_VPN=%q\n'    "${LOCAL_VPN:-no}"
    printf 'SAVED_TG_FRESH=%q\n'     "false"  # always false on save — fresh flag is one-time
  } > "${SAVED_CONFIG}"
  chmod 600 "${SAVED_CONFIG}"
  log OK "Конфигурация сохранена"
}

load_saved_config() {
  # Параметры хранятся в /opt/tunnelwright, у amnezia-wg — в /opt/amnezia-wg (формат тот же)
  local f="${SAVED_CONFIG}"
  [[ -f "$f" ]] || f="${LEGACY_BASE}/.install_state"
  [[ -f "$f" ]] || return 1
  # shellcheck disable=SC1090
  source "$f" 2>/dev/null || return 1
  [[ -n "${SAVED_WG_HOST:-}" ]] || return 1
  return 0
}

# Порт: число 1–65535
valid_port() { [[ "$1" =~ ^[0-9]{1,5}$ ]] && (( $1 >= 1 && $1 <= 65535 )); }

validate_params() {
  [[ "${LOCAL_VPN:-no}" =~ ^(yes|no)$ ]] || die "LOCAL_VPN: yes или no"
  valid_port "${WEB_PORT}" || die "Неверный порт панели: ${WEB_PORT}"
  if local_vpn; then
    valid_port "${WG_PORT}"  || die "Неверный порт WireGuard: ${WG_PORT}"
    [[ "${WEB_PORT}" != "${WG_PORT}" ]] || die "Порты панели и WireGuard должны различаться"
  fi
  [[ "${WG_HOST}" =~ ^[A-Za-z0-9.:-]+$ ]] || die "Неверный IP/домен: ${WG_HOST}"
  [[ ${#WG_PASSWORD} -ge 8 ]] || die "Пароль короче 8 символов"
}

# ─────────────────────── Загрузка install.env ────────────────
load_install_env() {
  [[ -f "$INSTALL_ENV" ]] || return 1
  log INFO "Найден install.env: ${INSTALL_ENV} — non-interactive режим"
  # shellcheck disable=SC1090
  source "$INSTALL_ENV" 2>/dev/null || { log WARN "Не удалось прочитать install.env"; return 1; }

  # Маппинг переменных из install.env в рабочие переменные скрипта
  WG_HOST="${INSTALL_WG_HOST:-${WG_HOST:-}}"
  WG_PASSWORD="${INSTALL_PASSWORD:-${WG_PASSWORD:-}}"
  WEB_PORT="${INSTALL_WEB_PORT:-${WEB_PORT:-$DEFAULT_WEB_PORT}}"
  WG_PORT="${INSTALL_WG_PORT:-${WG_PORT:-$DEFAULT_WG_PORT}}"
  WG_LANG="${INSTALL_LANG:-${WG_LANG:-ru}}"
  LOCAL_VPN="${INSTALL_LOCAL_VPN:-${LOCAL_VPN:-no}}"
  TG_TOKEN="${INSTALL_TG_TOKEN:-${TG_TOKEN:-}}"
  TG_CHAT_ID="${INSTALL_TG_CHAT_ID:-${TG_CHAT_ID:-}}"
  [[ -n "${TG_TOKEN:-}" && -n "${TG_CHAT_ID:-}" ]] && TG_ENABLED="true" || true

  return 0
}

# ─────────────────────── Ввод параметров ─────────────────────
collect_params() {
  echo -e "\n${BOLD}${BLUE}${ICON_VPN} Конфигурация сервера${RESET}"
  echo "  ───────────────────────────────────────"
  # stdin перенаправлен через pipe/tee — каждый read явно читает из /dev/tty

  # ── Non-interactive: install.env ─────────────────────────────
  if load_install_env; then
    [[ -z "${WG_HOST:-}"     ]] && die "install.env: INSTALL_WG_HOST не задан"
    [[ -z "${WG_PASSWORD:-}" ]] && die "install.env: INSTALL_PASSWORD не задан"
    [[ ${#WG_PASSWORD} -lt 8 ]] && die "install.env: INSTALL_PASSWORD короче 8 символов"

    echo -e "  ${ICON_OK} ${GREEN}Non-interactive режим (install.env)${RESET}"
    printf "    %-26s ${CYAN}%s${RESET}\n" "IP/домен:"      "$WG_HOST"
    printf "    %-26s ${CYAN}%s${RESET}\n" "Web UI порт:"   "$WEB_PORT"
    printf "    %-26s ${CYAN}%s${RESET}\n" "WireGuard порт:" "$WG_PORT"
    { [[ -n "${TG_TOKEN:-}" ]] && \
      printf "    %-26s ${GREEN}%s${RESET}\n" "Telegram:" "включён"; } || true
    log OK "Параметры загружены из install.env"
    return 0
  fi

  # ── Saved config (повторная установка) ────────────────────────
  local SAVED_WG_HOST="" SAVED_WG_PASSWORD="" SAVED_WEB_PORT=""
  local SAVED_WG_PORT="" SAVED_WG_LANG="" SAVED_TG_TOKEN="" SAVED_TG_CHAT_ID=""

  if load_saved_config; then
    echo -e "\n  ${ICON_INFO} ${BOLD}Обнаружена предыдущая установка:${RESET}"
    printf "    %-22s ${CYAN}%s${RESET}\n" "IP/домен:"    "${SAVED_WG_HOST:-}"
    printf "    %-22s ${CYAN}%s${RESET}\n" "Web UI порт:" "${SAVED_WEB_PORT:-}"
    printf "    %-22s ${CYAN}%s${RESET}\n" "WG порт:"     "${SAVED_WG_PORT:-}"
    { [[ -n "${SAVED_TG_TOKEN:-}" && -n "${SAVED_TG_CHAT_ID:-}" ]] && \
      printf "    %-22s ${GREEN}%s${RESET}\n" "Telegram:" "настроен"; } || true
    echo ""
    echo -e "  ${BOLD}[1]${RESET} Использовать сохранённые данные"
    echo -e "  ${BOLD}[2]${RESET} Ввести новые данные"
    echo -e "  ${BOLD}[3]${RESET} Отмена"
    echo ""
    if [[ "${REUSE:-0}" == "1" ]]; then
      rc=1   # --reuse: обновление/откат без вопросов
    else
      read -rp "  Выбор [1]: " rc </dev/tty || rc=""; rc="${rc:-1}"
    fi
    case "$rc" in
      1)
        WG_HOST="${SAVED_WG_HOST:-}"; WG_PASSWORD="${SAVED_WG_PASSWORD:-}"; TG_TOKEN="${SAVED_TG_TOKEN:-}"; TG_CHAT_ID="${SAVED_TG_CHAT_ID:-}"
        WEB_PORT="${SAVED_WEB_PORT:-$DEFAULT_WEB_PORT}"; WG_PORT="${SAVED_WG_PORT:-$DEFAULT_WG_PORT}"
        WG_LANG="${SAVED_WG_LANG:-ru}"; TG_TOKEN="${SAVED_TG_TOKEN:-}"; TG_CHAT_ID="${SAVED_TG_CHAT_ID:-}"
        PORTAL_NAME="${SAVED_PORTAL_NAME:-Private World}"
        LOCAL_VPN="${SAVED_LOCAL_VPN:-yes}"   # без сохранённого выбора — с VPN на сервере панели
        { [[ -n "${TG_TOKEN:-}" && -n "${TG_CHAT_ID:-}" ]] && TG_ENABLED="true"; } || true
        log OK "Используем сохранённую конфигурацию"
        if [[ "${REUSE:-0}" != "1" ]]; then
          read -rp "  Продолжить установку? [Y/n]: " confirm </dev/tty || confirm=""
          [[ "${confirm,,}" =~ ^(n|no)$ ]] && die "Установка отменена"
        fi
        return 0 ;;
      3) die "Установка отменена" ;;
      *) echo -e "  ${ICON_INFO} Вводим новые данные...\n" ;;
    esac
  fi

  # ── Interactive ───────────────────────────────────────────────
  local auto_ip
  auto_ip=$(curl -s --max-time 5 https://api.ipify.org 2>/dev/null || \
            curl -s --max-time 5 https://ifconfig.me 2>/dev/null || echo "")

  echo -e "\n  ${ICON_ARROW} ${BOLD}Публичный IP сервера${RESET}"
  if [[ -n "$auto_ip" ]]; then
    echo -e "    Определён: ${CYAN}${auto_ip}${RESET}"
    read -rp "    [Enter = ${auto_ip}, или введите другой]: " inp_ip </dev/tty || inp_ip=""
    WG_HOST="${inp_ip:-$auto_ip}"
  else
    read -rp "    Введите публичный IP или домен: " WG_HOST </dev/tty || WG_HOST=""
    [[ -z "$WG_HOST" ]] && die "IP не может быть пустым"
  fi

  echo -e "\n  ${ICON_ARROW} ${BOLD}Пароль для Web UI${RESET}"
  while true; do
    read -rsp "    Пароль (мин. 8 символов): " WG_PASSWORD  </dev/tty || WG_PASSWORD=""; echo
    read -rsp "    Повторите пароль: "         WG_PASSWORD2 </dev/tty || WG_PASSWORD2=""; echo
    [[ "$WG_PASSWORD" == "$WG_PASSWORD2" && ${#WG_PASSWORD} -ge 8 ]] && break
    echo -e "    ${YELLOW}Пароли не совпадают или < 8 символов${RESET}"
  done

  echo -e "\n  ${ICON_ARROW} ${BOLD}VPN на этом сервере${RESET}"
  echo -e "    ${DIM}Обычно панель ставится отдельно, а VPN-серверы (ноды) добавляются из панели по SSH.${RESET}"
  read -rp "    Поставить VPN-ноду и на сервер панели? [y/N]: " inp_vpn </dev/tty || inp_vpn=""
  if [[ "${inp_vpn,,}" =~ ^(y|yes|д|да)$ ]]; then LOCAL_VPN=yes; else LOCAL_VPN=no; fi

  echo -e "\n  ${ICON_ARROW} ${BOLD}Порты${RESET}"
  WG_PORT="${DEFAULT_WG_PORT}"
  while true; do
    read -rp "    Порт панели (HTTPS) [${DEFAULT_WEB_PORT}]: " inp_web </dev/tty || inp_web=""; WEB_PORT="${inp_web:-$DEFAULT_WEB_PORT}"
    if local_vpn; then
      read -rp "    WireGuard UDP порт [${DEFAULT_WG_PORT}]: "  inp_wg  </dev/tty || inp_wg="";  WG_PORT="${inp_wg:-$DEFAULT_WG_PORT}"
    fi
    valid_port "$WEB_PORT" && valid_port "$WG_PORT" && [[ "$WEB_PORT" != "$WG_PORT" ]] && break
    echo -e "    ${YELLOW}Порты должны быть числами 1–65535 и различаться${RESET}"
  done

  echo -e "\n  ${ICON_ARROW} ${BOLD}Telegram-уведомления${RESET} ${DIM}(оставьте пустым — пропустить)${RESET}"
  TG_TOKEN=""; TG_CHAT_ID=""; TG_ENABLED="false"; TG_FRESH="false"
  read -rp "    Bot Token: "   TG_TOKEN  </dev/tty || TG_TOKEN=""
  read -rp "    Chat ID:   "   TG_CHAT_ID </dev/tty || TG_CHAT_ID=""
  # Если пользователь оставил пустым — это явный выбор "без TG"
  [[ -z "${TG_TOKEN:-}" ]] && TG_FRESH="true"
  { [[ -n "${TG_TOKEN:-}" && -n "${TG_CHAT_ID:-}" ]] && TG_ENABLED="true"; } || true

  echo -e "\n  ${ICON_ARROW} ${BOLD}Имя панели${RESET} ${DIM}(до 15 символов, Enter — оставить \"Private World\"):${RESET}"
  read -rp "    Название: " _pname </dev/tty || _pname=""
  PORTAL_NAME="${_pname:0:15}"
  [[ -z "${PORTAL_NAME:-}" ]] && PORTAL_NAME="Private World"

  echo -e "\n  ${BOLD}${GREEN}Итог:${RESET}"
  printf "    %-26s ${CYAN}%s${RESET}\n" "IP/домен:"       "$WG_HOST"
  printf "    %-26s ${CYAN}%s${RESET}\n" "Web UI порт:"    "$WEB_PORT"
  printf "    %-26s ${CYAN}%s${RESET}\n" "WireGuard порт:" "$WG_PORT"
  { [[ -n "${TG_TOKEN:-}" ]] && \
    printf "    %-26s ${GREEN}%s${RESET}\n" "Telegram:" "включён"; } || true

  echo ""
  read -rp "  Всё верно? Продолжить? [Y/n]: " confirm </dev/tty || confirm=""
  [[ "${confirm,,}" =~ ^(n|no)$ ]] && die "Установка отменена"
  return 0
}
