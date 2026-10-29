# shellcheck shell=bash
# ─────────────────────── Каталоги, секреты, TLS ───────────────
prepare_config() {
  echo -e "\n${BOLD}${BLUE}${ICON_GEAR} Конфигурация${RESET}"
  echo "  ───────────────────────────────────────"
  mkdir -p "${BASE_DIR}" "${LOG_DIR}" "${BACKUP_DIR}" "${LEGACY_IMPORT_DIR}" "${TLS_DIR}" \
           "${SECRETS_DIR}/panel" "${SECRETS_DIR}/node"
  chmod 700 "${SECRETS_DIR}" "${BACKUP_DIR}" "${LEGACY_IMPORT_DIR}"

  # Параметры установки для host-скриптов
  {
    printf 'WG_HOST=%q\n'  "${WG_HOST}"
    printf 'WEB_PORT=%q\n' "${WEB_PORT}"
    printf 'WG_PORT=%q\n'  "${WG_PORT}"
  } > "${PANEL_ENV}"
  chmod 644 "${PANEL_ENV}"

  # Токен локальной ноды: panel-api → node-agent. Создаётся один раз.
  local token="${SECRETS_DIR}/node/node.token"
  if [[ ! -s "$token" ]]; then
    ( umask 077; openssl rand -hex 32 > "$token" )
    log OK "Создан токен ноды"
  fi
  install -m 600 "$token" "${SECRETS_DIR}/panel/node.token"

  # Пароль администратора панели и начальные настройки: panel-api применит их при первом
  # запуске и удалит файлы. Если администратор уже есть — panel-api их проигнорирует.
  if ! panel_db_exists; then
    ( umask 077; printf '%s' "${WG_PASSWORD}" > "${SECRETS_DIR}/panel/admin-password" )
    python3 - "${SECRETS_DIR}/panel/initial-settings.json" "${PORTAL_NAME:-}" "${TG_TOKEN:-}" "${TG_CHAT_ID:-}" <<'PY'
import json, os, sys
path, name, tok, chat = sys.argv[1:5]
data = {"portal_name": name or "Private World"}
if tok and chat:
    data["telegram"] = {"token": tok, "chat_id": chat}
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    json.dump(data, f)
PY
  fi

  # TLS: самоподписанный сертификат на адрес сервера
  install -m 755 "${REPO_ROOT}/host/tunnelwright-cert" /usr/local/bin/tunnelwright-cert
  /usr/local/bin/tunnelwright-cert >> "${INSTALL_LOG}" 2>&1 || die "Не удалось выпустить TLS-сертификат"
  log OK "TLS-сертификат: ${TLS_DIR}/cert.pem"

  # Исходники образов — build-контекст для сборки на сервере (--build-local или нет GHCR)
  rm -rf "${BUILD_DIR}"
  mkdir -p "${BUILD_DIR}"
  cp -a "${REPO_ROOT}/web" "${REPO_ROOT}/panel" "${REPO_ROOT}/node" "${BUILD_DIR}/"
  log OK "Конфигурация готова (${BASE_DIR})"
}

panel_db_exists() {
  local mp
  mp=$(docker volume inspect -f '{{.Mountpoint}}' tunnelwright_data 2>/dev/null) || return 1
  [[ -s "${mp}/panel.db" ]]
}
