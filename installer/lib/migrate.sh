# shellcheck shell=bash
# ─────────────────────── Перенос с amnezia-wg ───────────
# Порядок: бэкап → данные для импорта → остановка amnezia-wg (без удаления) → запуск Tunnelwright →
# проверка → удаление amnezia-wg. При неудачной проверке — откат на amnezia-wg (rollback_legacy).

LEGACY_CRON_BACKUP=""

legacy_installed() {
  [[ -d "${LEGACY_BASE}" && ! -L "${LEGACY_BASE}" ]] && docker volume inspect "${LEGACY_WG_VOLUME}" >/dev/null 2>&1
}

_legacy_wg0() {
  local mp
  mp=$(docker volume inspect -f '{{.Mountpoint}}' "${LEGACY_WG_VOLUME}" 2>/dev/null) || return 1
  [[ -s "${mp}/wg0.json" ]] && echo "${mp}/wg0.json"
}

migrate_prepare() {
  echo -e "\n${BOLD}${BLUE}${ICON_GEAR} Перенос с amnezia-wg${RESET}"
  echo "  ───────────────────────────────────────"
  local wg0 ts tmp
  wg0=$(_legacy_wg0) || die "Не найден wg0.json установки amnezia-wg (том ${LEGACY_WG_VOLUME})"
  ts=$(date +%Y%m%d-%H%M%S)

  # 1. Полный бэкап amnezia-wg: ключи WireGuard, данные панели, параметры
  tmp=$(mktemp -d)
  mkdir -p "$tmp/amnezia-wg"
  cp -a "$wg0" "$tmp/amnezia-wg/wg0.json"
  cp -a "${LEGACY_BASE}/dashboard" "$tmp/amnezia-wg/" 2>/dev/null || true
  cp -a "${LEGACY_BASE}/.env" "${LEGACY_BASE}/.install_state" "${LEGACY_BASE}/docker-compose.yml" "$tmp/amnezia-wg/" 2>/dev/null || true
  ( umask 077; tar czf "${BACKUP_DIR}/amnezia-wg-${ts}.tar.gz" -C "$tmp" amnezia-wg )
  rm -rf "$tmp"
  log OK "Бэкап amnezia-wg: ${BACKUP_DIR}/amnezia-wg-${ts}.tar.gz"

  # 2. Данные для однократного импорта в panel-api (метаданные, трафик, лимиты, Telegram)
  install -m 600 "$wg0" "${LEGACY_IMPORT_DIR}/wg0.json"
  local f
  for f in meta.json client-usage.json traffic-history.json config.json limits.json; do
    [[ -f "${LEGACY_BASE}/dashboard/$f" ]] && install -m 600 "${LEGACY_BASE}/dashboard/$f" "${LEGACY_IMPORT_DIR}/$f"
  done

  # 3. wg0.json для node-agent: он перенесёт клиентов в wg-easy 15 с сохранением ключей
  docker volume create tunnelwright_node >/dev/null
  local node_mp
  node_mp=$(docker volume inspect -f '{{.Mountpoint}}' tunnelwright_node)
  if [[ ! -s "${node_mp}/wg-easy-admin.json" ]]; then
    mkdir -p "${node_mp}/import"
    install -m 600 "$wg0" "${node_mp}/import/wg0.json"
  fi
  log OK "Данные amnezia-wg подготовлены к импорту"

  # 4. Остановка amnezia-wg без удаления — освобождаем порты
  if [[ -f "${LEGACY_BASE}/docker-compose.yml" ]]; then
    docker compose -f "${LEGACY_BASE}/docker-compose.yml" -p amnezia down --timeout 15 >> "${INSTALL_LOG}" 2>&1 || true
  fi
  for c in amnezia-wg-easy amnezia-web; do docker rm -f "$c" >/dev/null 2>&1 || true; done
  systemctl stop amnezia-save-limits amnezia-docker-watcher >/dev/null 2>&1 || true
  LEGACY_CRON_BACKUP="${BACKUP_DIR}/amnezia-wg-cron-${ts}"
  mkdir -p "$LEGACY_CRON_BACKUP"
  mv /etc/cron.d/amnezia-* "$LEGACY_CRON_BACKUP/" 2>/dev/null || true
  log OK "amnezia-wg остановлена (не удалена)"
}

rollback_legacy() {
  log WARN "Откат на amnezia-wg..."
  docker compose -f "${COMPOSE_FILE}" -p "${PROJECT_NAME}" down --timeout 15 >> "${INSTALL_LOG}" 2>&1 || true
  [[ -n "$LEGACY_CRON_BACKUP" ]] && mv "$LEGACY_CRON_BACKUP"/amnezia-* /etc/cron.d/ 2>/dev/null || true
  systemctl start amnezia-save-limits amnezia-docker-watcher >/dev/null 2>&1 || true
  docker compose -f "${LEGACY_BASE}/docker-compose.yml" -p amnezia up -d >> "${INSTALL_LOG}" 2>&1 || true
  log WARN "amnezia-wg снова запущена. Логи Tunnelwright: ${INSTALL_LOG}, docker logs tunnelwright-node"
}

# Импорт в panel-api завершён (клиенты сопоставлены, данные перенесены)
legacy_import_done() {
  local i
  for i in $(seq 1 40); do
    docker exec tunnelwright-api python -c \
      "from app import db;db.connect();exit(0 if db.get_setting('legacy_imported') else 1)" >/dev/null 2>&1 && return 0
    sleep 3
  done
  return 1
}

migrate_cleanup() {
  # Сервисы, скрипты и правила amnezia-wg
  systemctl disable amnezia-save-limits amnezia-docker-watcher >/dev/null 2>&1 || true
  rm -f /etc/systemd/system/amnezia-save-limits.service /etc/systemd/system/amnezia-docker-watcher.service
  systemctl daemon-reload >/dev/null 2>&1 || true
  rm -f /usr/local/bin/amnezia-save-limits /usr/local/bin/amnezia-stats /usr/local/bin/amnezia-healthcheck \
        /usr/local/bin/amnezia-ratelimit /usr/local/bin/amnezia-ratelimit-apply.py /usr/local/bin/amnezia-docker-watcher \
        /etc/network/if-pre-up.d/amnezia-iptables
  local cidr br
  for cidr in 172.16.0.0/12 192.168.0.0/16; do
    while iptables -D INPUT -s "$cidr" -p tcp --dport 51822 -j ACCEPT 2>/dev/null; do :; done
  done
  while iptables -D INPUT -i docker0 -p tcp --dport 51822 -j ACCEPT 2>/dev/null; do :; done
  for br in $(iptables -S INPUT 2>/dev/null | grep -- '--dport 51822' | grep -oE 'br-[0-9a-f]+' | sort -u); do
    while iptables -D INPUT -i "$br" -p tcp --dport 51822 -j ACCEPT 2>/dev/null; do :; done
  done
  if command -v ufw >/dev/null 2>&1; then
    local n
    while n=$(ufw status numbered 2>/dev/null | grep -m1 -E '51822' | sed -E 's/^\[ *([0-9]+)\].*/\1/') && [[ -n "$n" ]]; do
      ufw --force delete "$n" >/dev/null 2>&1 || break
    done
  fi

  # Каталог amnezia-wg → в бэкапы, на его месте ссылка на /opt/tunnelwright (старые пути и amnezia-ctl update)
  if [[ -d "${LEGACY_BASE}" && ! -L "${LEGACY_BASE}" ]]; then
    mv "${LEGACY_BASE}" "${BACKUP_DIR}/amnezia-wg"
    ln -s "${BASE_DIR}" "${LEGACY_BASE}"
  fi
  docker network rm amnezia_net >/dev/null 2>&1 || true
  docker image rm ghcr.io/spcfox/amnezia-wg-easy amnezia-web:latest >/dev/null 2>&1 || true
  # Том amnezia_wg_data оставляем: в нём исходные ключи amnezia-wg (копия есть и в бэкапе)
  log OK "amnezia-wg удалена (бэкап и том ${LEGACY_WG_VOLUME} сохранены)"
}
