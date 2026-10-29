#!/bin/sh
# Tunnelwright Panel AWG web: выбор режима при старте контейнера (запускается docker-entrypoint.sh образа nginx).
#   PANEL_TLS=on (по умолчанию) — HTTPS. Сертификат в /etc/tunnelwright/tls: при установке на сервер его
#     выпускает и продлевает хост (tunnelwright cert). Если сертификата нет (стек Portainer на NAS) —
#     контейнер выпускает самоподписанный сам и продлевает его, пока работает.
#   PANEL_TLS=off — обычный HTTP за обратным прокси NAS (Synology/QNAP с Let's Encrypt).
set -eu
TLS_DIR=/etc/tunnelwright/tls
CONF=/etc/nginx/tunnelwright/listen.conf
VALID_DAYS=365
RENEW_DAYS=30
mkdir -p /etc/nginx/tunnelwright

if [ "${PANEL_TLS:-on}" = "off" ]; then
  cat > "$CONF" <<'EOF'
listen 443;
# Обратный прокси NAS в локальной сети: реальный IP клиента — из X-Forwarded-For
set_real_ip_from 10.0.0.0/8;
set_real_ip_from 172.16.0.0/12;
set_real_ip_from 192.168.0.0/16;
real_ip_header   X-Forwarded-For;
real_ip_recursive on;
EOF
  echo "tunnelwright: HTTP без TLS (PANEL_TLS=off) — откройте панель через обратный прокси с HTTPS"
  exit 0
fi

cat > "$CONF" <<'EOF'
listen 443 ssl;
http2 on;
ssl_certificate     /etc/tunnelwright/tls/cert.pem;
ssl_certificate_key /etc/tunnelwright/tls/key.pem;
ssl_protocols       TLSv1.2 TLSv1.3;
ssl_session_cache   shared:SSL:5m;
ssl_session_timeout 1d;
# Обычный HTTP на этот же порт → 497 → редирект на https ($http_host — адрес с внешним портом)
error_page 497 =301 https://$http_host$request_uri;
EOF

# Сертификат выпускал контейнер (а не хост) — значит, продлевает тоже он
AUTO="$TLS_DIR/.auto"
issue() {
  host="${PANEL_HOST:-tunnelwright}"
  case "$host" in
    *[!0-9.]*) san="DNS:$host" ;;
    *)         san="IP:$host" ;;
  esac
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days "$VALID_DAYS" \
    -subj "/CN=$host" -addext "subjectAltName=$san" \
    -keyout "$TLS_DIR/key.pem.new" -out "$TLS_DIR/cert.pem.new" 2>/dev/null
  chmod 600 "$TLS_DIR/key.pem.new"
  mv "$TLS_DIR/key.pem.new" "$TLS_DIR/key.pem"
  mv "$TLS_DIR/cert.pem.new" "$TLS_DIR/cert.pem"
  echo "$host" > "$AUTO"
  echo "tunnelwright: выпущен самоподписанный сертификат для $host на $VALID_DAYS дней"
}

if [ ! -s "$TLS_DIR/cert.pem" ] || [ ! -s "$TLS_DIR/key.pem" ]; then
  [ -w "$TLS_DIR" ] || { echo "tunnelwright: нет сертификата в $TLS_DIR, а каталог только для чтения" >&2; exit 1; }
  issue
elif [ -f "$AUTO" ] && { [ "$(cat "$AUTO")" != "${PANEL_HOST:-tunnelwright}" ] \
     || ! openssl x509 -checkend $((RENEW_DAYS * 86400)) -noout -in "$TLS_DIR/cert.pem" >/dev/null 2>&1; }; then
  issue   # сменили PANEL_HOST в стеке или срок подходит к концу
fi

if [ -f "$AUTO" ]; then
  # Раз в сутки: продление за RENEW_DAYS дней до конца срока и перезагрузка nginx
  ( while sleep 86400; do
      if ! openssl x509 -checkend $((RENEW_DAYS * 86400)) -noout -in "$TLS_DIR/cert.pem" >/dev/null 2>&1; then
        issue && nginx -s reload
      fi
    done ) &
fi
