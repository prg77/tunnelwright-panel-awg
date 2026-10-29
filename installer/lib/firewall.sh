# shellcheck shell=bash
# ─────────────────────── Firewall ────────────────────────────
# Наружу нужны только HTTPS панели и (если VPN стоит на этом сервере) UDP WireGuard.
# Остальное общается внутри Docker.
configure_firewall() {
  local ports="${WEB_PORT}/tcp"
  local_vpn && ports+=" и ${WG_PORT}/udp"
  if command -v ufw &>/dev/null; then
    ufw allow "${WEB_PORT}/tcp" comment "Tunnelwright HTTPS" >> "${INSTALL_LOG}" 2>&1 || true
    if local_vpn; then
      ufw allow "${WG_PORT}/udp" comment "Tunnelwright WireGuard" >> "${INSTALL_LOG}" 2>&1 || true
    else
      ufw delete allow "${WG_PORT}/udp" >> "${INSTALL_LOG}" 2>&1 || true   # VPN с этого сервера убран
    fi
    # SSH разрешаем ДО включения ufw — иначе можно потерять доступ к серверу
    local ssh_port
    ssh_port=$(ss -tlnpH 2>/dev/null | awk '/sshd/ {n=split($4,a,":"); print a[n]; exit}')
    ufw allow "${ssh_port:-22}/tcp" comment "SSH" >> "${INSTALL_LOG}" 2>&1 || true
    ufw --force enable >> "${INSTALL_LOG}" 2>&1 || true
    log OK "UFW: открыты ${ports} и SSH ${ssh_port:-22}/tcp"
  elif command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-port="${WEB_PORT}/tcp" >> "${INSTALL_LOG}" 2>&1 || true
    if local_vpn; then
      firewall-cmd --permanent --add-port="${WG_PORT}/udp" >> "${INSTALL_LOG}" 2>&1 || true
    fi
    firewall-cmd --reload >> "${INSTALL_LOG}" 2>&1 || true
    log OK "firewalld: открыты ${ports}"
  else
    log INFO "Файрвол не найден — ${ports} доступны без ограничений"
  fi
}
