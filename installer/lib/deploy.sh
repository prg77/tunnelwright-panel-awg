# shellcheck shell=bash
# ─────────────────────── docker-compose.yml ──────────────────
create_compose() {
  render "${REPO_ROOT}/installer/templates/docker-compose.yml" "${COMPOSE_FILE}" \
    "APP_VERSION=${APP_VERSION}" \
    "WG_EASY_IMAGE=${WG_EASY_IMAGE}" "WEB_IMAGE=${WEB_IMAGE}" \
    "API_IMAGE=${API_IMAGE}" "NODE_IMAGE=${NODE_IMAGE}" \
    "BUILD_DIR=${BUILD_DIR}" "SECRETS_DIR=${SECRETS_DIR}" "TLS_DIR=${TLS_DIR}" \
    "LEGACY_IMPORT_DIR=${LEGACY_IMPORT_DIR}" \
    "WG_HOST=${WG_HOST}" "WG_PORT=${WG_PORT}" "WEB_PORT=${WEB_PORT}" "WG_DNS=${DEFAULT_DNS}" \
    "LOCAL_NODE_URL=$(local_vpn && echo "http://wg-easy:8710")"
  # Без VPN на сервере панели — сервисы wg-easy и node-agent не нужны
  local_vpn || sed -i '/# >>> local-vpn/,/# <<< local-vpn/d' "${COMPOSE_FILE}"
  docker compose -f "${COMPOSE_FILE}" config -q >> "${INSTALL_LOG}" 2>&1 \
    || die "docker-compose.yml не прошёл проверку — см. ${INSTALL_LOG}"
  if local_vpn; then
    log OK "docker-compose.yml создан (wg-easy, node-agent, panel-api, web)"
  else
    log OK "docker-compose.yml создан (panel-api, web; VPN — на удалённых нодах)"
  fi
}

# ─────────────────────── Образы ──────────────────────────────
# Сначала готовые образы из GHCR, при неудаче (или --build-local) — сборка на сервере
prepare_images() {
  local missing=() img svc pairs=("web:${WEB_IMAGE}" "panel-api:${API_IMAGE}")
  if local_vpn; then
    echo -e "  ${ICON_GEAR} Загрузка образа wg-easy..."
    docker pull -q "${WG_EASY_IMAGE}" >> "${INSTALL_LOG}" 2>&1 || die "Не удалось загрузить ${WG_EASY_IMAGE%@*}"
    pairs+=("node-agent:${NODE_IMAGE}")
  fi
  for pair in "${pairs[@]}"; do
    svc="${pair%%:*}"; img="${pair#*:}"
    if [[ "${BUILD_LOCAL:-0}" != "1" ]] && docker pull -q "$img" >> "${INSTALL_LOG}" 2>&1; then
      log OK "Образ ${img} загружен"
    else
      missing+=("$svc")
    fi
  done
  [[ ${#missing[@]} -eq 0 ]] && return 0

  echo -e "  ${ICON_REACT} ${BOLD}Сборка на сервере: ${missing[*]} (1–5 мин)...${RESET}"
  set +e
  docker compose -f "${COMPOSE_FILE}" -p "${PROJECT_NAME}" build "${missing[@]}" 2>&1 \
    | tee -a "${INSTALL_LOG}" | grep --line-buffered -E "^#[0-9]+ (DONE|ERROR)|error|built in" | sed "s/^/    /"
  local rc=${PIPESTATUS[0]}
  set -e
  [[ $rc -eq 0 ]] || { tail -30 "${INSTALL_LOG}" | sed 's/^/    /'; die "Сборка образов не удалась (код ${rc})"; }
  log OK "Образы собраны: ${missing[*]}"
}

# ─────────────────────── Запуск и проверка ───────────────────
deploy_stack() {
  echo -e "  ${ICON_GEAR} ${BOLD}Запуск контейнеров...${RESET}"
  docker compose -f "${COMPOSE_FILE}" -p "${PROJECT_NAME}" up -d --remove-orphans >> "${INSTALL_LOG}" 2>&1 \
    || { tail -20 "${INSTALL_LOG}" | sed 's/^/    /'; die "docker compose up завершился с ошибкой"; }
}

# Нода настроена (агент поднял wg-easy) и панель отвечает. Возвращает 0/1, не завершает установку.
wait_healthy() {
  local timeout="${1:-180}" waited=0 node_ok=false web_ok=false
  local_vpn || node_ok=true      # VPN на сервере панели нет — ждём только панель
  echo -ne "  ${ICON_GEAR} Ожидание готовности"
  while (( waited < timeout )); do
    if ! $node_ok && docker exec tunnelwright-api python -c \
        "import json,urllib.request;h=json.load(urllib.request.urlopen('http://wg-easy:8710/health',timeout=3));exit(0 if h.get('ok') else 1)" \
        >/dev/null 2>&1; then
      node_ok=true
    fi
    if ! $web_ok && curl -skf --max-time 5 "https://127.0.0.1:${WEB_PORT}/api/health" >/dev/null 2>&1; then
      web_ok=true
    fi
    if $node_ok && $web_ok; then echo ""; log OK "Нода и панель готовы"; return 0; fi
    echo -ne "."; sleep 3; waited=$((waited + 3))
  done
  echo ""
  log WARN "Не дождались готовности за ${timeout}с (нода: ${node_ok}, панель: ${web_ok})"
  docker logs tunnelwright-node --tail=20 2>&1 | sed 's/^/    /' >> "${INSTALL_LOG}"
  return 1
}
