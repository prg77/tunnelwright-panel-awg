#!/usr/bin/env bash
# =============================================================================
#  Tunnelwright Panel AWG — установщик панели и VPN на AmneziaWG (wg-easy)
#  https://github.com/prg77/tunnelwright-panel-awg
#
#  Обычно запускается загрузчиком install.sh из корня репозитория.
#  Можно запустить и напрямую из распакованного релиза:
#    sudo bash installer/setup.sh [--reuse] [--build-local]
#
#  Установка amnezia-wg (/opt/amnezia-wg) переносится автоматически: клиенты сохраняют ключи,
#  при ошибке установщик возвращает amnezia-wg в рабочее состояние.
# =============================================================================

set -euo pipefail

# pwd -P: загрузчик и tunnelwright запускают установщик через симлинк current —
# нужен реальный каталог релиза (releases/<версия>), а не имя симлинка
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

# shellcheck source=lib/common.sh
source "${REPO_ROOT}/installer/lib/common.sh"
for _lib in system params config deploy migrate host firewall summary; do
  # shellcheck disable=SC1090
  source "${REPO_ROOT}/installer/lib/${_lib}.sh"
done

usage() {
  cat <<EOF

Tunnelwright Panel AWG v${APP_VERSION}

Использование:
  sudo bash installer/setup.sh                 # Установка / переустановка
  sudo bash installer/setup.sh --reuse         # С сохранёнными параметрами, без вопросов (обновление)
  sudo bash installer/setup.sh --build-local   # Собрать образы на сервере (не брать из GHCR)
  sudo bash installer/setup.sh --no-local-vpn  # Без VPN на сервере панели (только удалённые ноды)
  sudo bash installer/setup.sh --local-vpn     # VPN-нода и на сервере панели
  sudo bash installer/setup.sh --version       # Версия

EOF
}

main() {
  trap 'echo -e "\n[FATAL] Скрипт упал на строке $LINENO: $BASH_COMMAND" | tee -a "${INSTALL_LOG:-/tmp/tunnelwright-err.log}"; exit 1' ERR

  REUSE=0; BUILD_LOCAL=0; LOCAL_VPN_FLAG=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --version|-v)   echo "Tunnelwright Panel AWG v${APP_VERSION}"; exit 0 ;;
      --help|-h)      usage; exit 0 ;;
      --reuse)        REUSE=1 ;;
      --build-local)  BUILD_LOCAL=1 ;;
      --local-vpn)    LOCAL_VPN_FLAG=yes ;;
      --no-local-vpn) LOCAL_VPN_FLAG=no ;;
      *) usage; die "Неизвестный параметр: $1" ;;
    esac
    shift
  done
  export REUSE BUILD_LOCAL LOCAL_VPN_FLAG

  require_root
  mkdir -p "${LOG_DIR}"
  echo "=== Tunnelwright Panel AWG ${APP_VERSION} install — $(timestamp) ===" >> "${INSTALL_LOG}"
  chmod 640 "${INSTALL_LOG}"

  print_banner
  # vpn-panel — другие пути, контейнеры и тома; поверх неё не ставим (заняты порты)
  if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qxE 'vpn-panel-(api|web|wg|node)'; then
    die "Найдена установка vpn-panel в /opt/vpn-panel. Tunnelwright ставится заново:
  1) бэкап на старой панели: vpn-panel backup (архив — в /var/lib/docker/volumes/vpn_panel_data/_data/backups
     или «Настройки → Резервные копии → Скачать»);
  2) остановите её: rm -f /etc/cron.d/vpn-panel  (иначе watchdog поднимет её снова)
                    docker compose -f /opt/vpn-panel/docker-compose.yml -p vpn-panel down;
  3) повторите установку, затем: tunnelwright restore <архив>.zip"
  fi
  # Остановленная vpn-panel: её watchdog, таймер сертификата и команды больше не нужны
  # (данные — /opt/vpn-panel и тома vpn_panel_* — не трогаем, удалить их можно вручную)
  if [[ -f /etc/cron.d/vpn-panel || -f /etc/systemd/system/vpn-panel-cert.timer ]]; then
    rm -f /etc/cron.d/vpn-panel /etc/logrotate.d/vpn-panel
    systemctl disable --now vpn-panel-cert.timer >/dev/null 2>&1 || true
    rm -f /etc/systemd/system/vpn-panel-cert.timer /etc/systemd/system/vpn-panel-cert.service
    systemctl daemon-reload >/dev/null 2>&1 || true
    rm -f /usr/local/bin/vpn-panel /usr/local/bin/vpn-panel-cert /usr/local/bin/vpn-panel-watchdog
    log INFO "Службы vpn-panel отключены; её данные остались в /opt/vpn-panel и томах vpn_panel_*"
  fi
  check_os
  install_deps
  install_docker
  collect_params
  [[ -n "${LOCAL_VPN_FLAG}" ]] && LOCAL_VPN="${LOCAL_VPN_FLAG}"

  local legacy=0
  if legacy_installed && ! panel_db_exists; then
    legacy=1
    LOCAL_VPN=yes          # ключи клиентов amnezia-wg переносятся в wg-easy этого сервера
    log INFO "Найдена установка amnezia-wg — будет перенесена с сохранением клиентов"
  fi
  validate_params
  if local_vpn; then
    log INFO "VPN-нода на сервере панели: да (UDP ${WG_PORT})"
  else
    log INFO "VPN-нода на сервере панели: нет — VPN-серверы добавляются в панели (Ноды)"
  fi

  mkdir -p "${BASE_DIR}"
  save_config
  install_release
  prepare_config
  create_compose
  prepare_images          # пока amnezia-wg работает — простой VPN только на время переключения
  configure_firewall

  if [[ $legacy == 1 ]]; then
    migrate_prepare
    trap 'rollback_legacy' EXIT   # любой выход до подтверждения новой установки возвращает amnezia-wg
  fi

  deploy_stack
  wait_healthy 240 || die "Нода или панель не поднялись — см. ${INSTALL_LOG} и tunnelwright logs"

  if [[ $legacy == 1 ]]; then
    legacy_import_done || die "Данные amnezia-wg не импортировались в панель — см. docker logs tunnelwright-api"
    trap - EXIT
    migrate_cleanup
  fi

  setup_host
  print_summary
}

main "$@"
