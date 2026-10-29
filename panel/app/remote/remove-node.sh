#!/usr/bin/env bash
# Tunnelwright Panel AWG: удаление VPN-ноды с сервера (wg-easy + node-agent, их данные и правило ufw).
# Запускает panel-api по SSH от root, когда ноду удаляют из панели с отметкой «удалить с сервера».
# Docker и остальное содержимое сервера не трогаются.
set -uo pipefail

: "${NODE_DIR:=/opt/tunnelwright-node}" "${WG_PORT:=}"

step() { echo "▶ $*"; }

if [[ -f "$NODE_DIR/docker-compose.yml" ]]; then
  step "Остановка контейнеров и удаление данных VPN"
  docker compose -f "$NODE_DIR/docker-compose.yml" down -v --remove-orphans 2>&1 | tail -3
else
  echo "  $NODE_DIR/docker-compose.yml не найден — контейнеры удаляем по имени"
  docker rm -f tunnelwright-node-wg tunnelwright-node-agent >/dev/null 2>&1 || true
  docker volume rm tunnelwright_node_wg tunnelwright_node_data >/dev/null 2>&1 || true
fi

step "Удаление образов ноды"
docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '(^|/)(tunnelwright-node|vpn-panel-node|wg-easy)(:|$)' \
  | xargs -r docker rmi >/dev/null 2>&1 || true

if [[ -n "$WG_PORT" ]] && command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  step "Брандмауэр ufw: закрываем ${WG_PORT}/udp"
  ufw delete allow "${WG_PORT}/udp" >/dev/null 2>&1 || true
fi

if command -v systemctl >/dev/null 2>&1 && [[ -f /etc/systemd/system/tunnelwright-node-update.path ]]; then
  step "Автообновление агента: отключение"
  systemctl disable --now tunnelwright-node-update.path >/dev/null 2>&1 || true
  rm -f /etc/systemd/system/tunnelwright-node-update.path /etc/systemd/system/tunnelwright-node-update.service
  systemctl daemon-reload || true
fi

step "Удаление ${NODE_DIR}"
rm -rf "$NODE_DIR"

# Нода в /opt/vpn-node, если осталась
if [[ -d /opt/vpn-node ]] || docker volume inspect vpn_node_wg >/dev/null 2>&1; then
  step "Удаление ноды из /opt/vpn-node"
  docker rm -f vpn-node-wg vpn-node-agent >/dev/null 2>&1 || true
  docker volume rm vpn_node_wg vpn_node_data >/dev/null 2>&1 || true
  if command -v systemctl >/dev/null 2>&1 && [[ -f /etc/systemd/system/vpn-node-update.path ]]; then
    systemctl disable --now vpn-node-update.path >/dev/null 2>&1 || true
    rm -f /etc/systemd/system/vpn-node-update.path /etc/systemd/system/vpn-node-update.service
    systemctl daemon-reload || true
  fi
  rm -rf /opt/vpn-node
fi

echo "✓ VPN-нода удалена с сервера"
