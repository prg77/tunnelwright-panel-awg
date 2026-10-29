# shellcheck shell=bash
# ─────────────────────── Итоговый вывод ──────────────────────
print_summary() {
  local url="https://${WG_HOST}:${WEB_PORT}" c s color fp
  echo ""
  echo -e "${BOLD}${CYAN}  ╔══════════════════════════════════════════════════════════════╗"
  printf  "  ║  🔒  Tunnelwright Panel AWG v%-7s ·  установка завершена  ║\n" "${APP_VERSION}"
  echo -e "  ╚══════════════════════════════════════════════════════════════╝${RESET}"
  echo ""
  echo -e "  ${BOLD}🌐  Панель:${RESET}  ${BOLD}${GREEN}${url}${RESET}"
  echo -e "      ${DIM}Логин: admin · пароль — заданный при установке (при переносе с amnezia-wg — прежний пароль)${RESET}"
  fp=$(openssl x509 -noout -fingerprint -sha256 -in "${TLS_DIR}/cert.pem" 2>/dev/null | cut -d= -f2)
  echo -e "      ${DIM}Сертификат самоподписанный — браузер покажет предупреждение.${RESET}"
  echo -e "      ${DIM}Отпечаток SHA-256 для проверки: ${fp}${RESET}"
  echo ""
  echo -e "  ${BOLD}${CYAN}┌─ Компоненты ─────────────────────────────────────────────────┐${RESET}"
  local comps=("tunnelwright-api:panel-api · бэкенд панели" "tunnelwright-web:web · HTTPS ${WEB_PORT}")
  if local_vpn; then
    comps=("tunnelwright-wg:wg-easy 15.5 · VPN UDP ${WG_PORT}" "tunnelwright-node:node-agent · лимиты, метрики" "${comps[@]}")
  fi
  for c in "${comps[@]}"; do
    s=$(docker inspect -f '{{.State.Status}}' "${c%%:*}" 2>/dev/null || echo missing)
    color="${GREEN}"; [[ "$s" == "running" ]] || color="${RED}"
    printf "  ${CYAN}│${RESET}  ${color}●${RESET} %-16s %-9s %s\n" "${c%%:*}" "$s" "${c#*:}"
  done
  echo -e "  ${CYAN}└──────────────────────────────────────────────────────────────┘${RESET}"
  echo ""
  local_vpn || echo -e "  ${BOLD}VPN-серверы:${RESET} добавьте ноду в панели — раздел «Ноды» → «Добавить ноду»\n"
  echo -e "  ${BOLD}Управление:${RESET} tunnelwright status | logs | update | rollback | reset-admin"
  echo -e "  ${DIM}Данные: тома tunnelwright_wg (ключи VPN), tunnelwright_data (панель); бэкапы: ${BACKUP_DIR}${RESET}"
  echo ""
}
