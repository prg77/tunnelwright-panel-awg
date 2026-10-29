# shellcheck shell=bash
# ─────────────────────── Команды и службы хоста ──────────────
setup_host() {
  install -m 755 "${REPO_ROOT}/host/tunnelwright"       /usr/local/bin/tunnelwright
  install -m 755 "${REPO_ROOT}/host/tunnelwright-cert"     /usr/local/bin/tunnelwright-cert
  install -m 755 "${REPO_ROOT}/host/tunnelwright-watchdog" /usr/local/bin/tunnelwright-watchdog
  ln -sfn /usr/local/bin/tunnelwright /usr/local/bin/amnezia-ctl  # имя команды amnezia-wg

  # Продление TLS-сертификата: раз в сутки, перевыпуск за 30 дней до истечения
  cat > /etc/systemd/system/tunnelwright-cert.service <<'EOF'
[Unit]
Description=Tunnelwright Panel AWG: продление TLS-сертификата панели

[Service]
Type=oneshot
ExecStart=/usr/local/bin/tunnelwright-cert
EOF
  cat > /etc/systemd/system/tunnelwright-cert.timer <<'EOF'
[Unit]
Description=Tunnelwright Panel AWG: ежедневная проверка TLS-сертификата

[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  systemctl enable --now tunnelwright-cert.timer >> "${INSTALL_LOG}" 2>&1 || log WARN "Не удалось включить таймер сертификата"

  cat > /etc/cron.d/tunnelwright <<'EOF'
# Tunnelwright Panel AWG: подъём упавших контейнеров
*/5 * * * * root /usr/local/bin/tunnelwright-watchdog
EOF
  chmod 644 /etc/cron.d/tunnelwright

  cat > /etc/logrotate.d/tunnelwright <<'EOF'
/var/log/tunnelwright/*.log {
    weekly
    rotate 4
    compress
    missingok
    notifempty
    copytruncate
}
EOF
  log OK "Команда tunnelwright, продление сертификата и watchdog установлены"
}

# ─────────────────────── Код релиза в /opt/tunnelwright ─────────
# Загрузчик amnezia-wg кладёт релиз в /opt/amnezia-wg/releases — переносим в /opt/tunnelwright/releases
install_release() {
  local label
  label=$(basename "${REPO_ROOT}")
  mkdir -p "${BASE_DIR}/releases"
  if [[ "$(readlink -f "${REPO_ROOT}")" != "$(readlink -f "${BASE_DIR}/releases/${label}")" ]]; then
    rm -rf "${BASE_DIR}/releases/${label}"
    cp -a "${REPO_ROOT}" "${BASE_DIR}/releases/${label}"
  fi
  if [[ -L "${BASE_DIR}/current" ]]; then
    local prev
    prev=$(basename "$(readlink -f "${BASE_DIR}/current")")
    [[ "$prev" != "$label" ]] && echo "$prev" > "${BASE_DIR}/.previous"
  fi
  ln -sfn "${BASE_DIR}/releases/${label}" "${BASE_DIR}/current"
  # Токен GitHub для обновлений, сохранённый установкой amnezia-wg
  if [[ -f "${LEGACY_BASE}/.github_token" && ! -f "${BASE_DIR}/.github_token" ]]; then
    install -m 600 "${LEGACY_BASE}/.github_token" "${BASE_DIR}/.github_token"
  fi
}
