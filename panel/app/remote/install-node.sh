#!/usr/bin/env bash
# Tunnelwright Panel AWG: установка или обновление удалённой VPN-ноды (wg-easy + node-agent).
# Запускает panel-api по SSH от root. Параметры приходят переменными окружения (см. nodeinstall.py),
# токен ноды — файлом NODE_TOKEN_FILE (не в командной строке).
# Повторный запуск — обновление: токен, сертификат и данные ноды сохраняются.
set -euo pipefail

: "${NODE_DIR:=/opt/tunnelwright-node}" "${WG_HOST:?}" "${WG_PORT:?}" "${AGENT_PORT:?}" "${WG_DNS:=1.1.1.1}"
: "${APP_VERSION:?}" "${NODE_IMAGE:?}" "${WG_EASY_IMAGE:?}" "${BUNDLE:=}" "${NODE_TOKEN_FILE:=}" "${PANEL_IP:=}" "${RESTORE_DIR:=}"

step() { echo "▶ $*"; }
die()  { echo "✗ $*" >&2; exit 1; }
apt_install() {
  [[ -n "${_apt_updated:-}" ]] || { apt-get update -qq >/dev/null; _apt_updated=1; }
  apt-get install -y -qq "$@" >/dev/null 2>&1
}

[[ $EUID -eq 0 ]] || die "нужен root"
[[ -f /etc/os-release ]] && . /etc/os-release
[[ "${ID:-}" =~ ^(debian|ubuntu)$ || "${ID_LIKE:-}" =~ (debian|ubuntu) ]] \
  || die "поддерживаются Debian и Ubuntu (найдено: ${PRETTY_NAME:-неизвестно})"
[[ -e /dev/net/tun ]] || die "нет /dev/net/tun — включите TUN в настройках VPS"
PANEL_IP="${PANEL_IP:-${SSH_CLIENT%% *}}"
[[ -n "$PANEL_IP" ]] || die "не удалось определить IP панели"
# any — панель с меняющимся IP (NAS дома): агент принимает запросы с любого адреса, защита — токен и TLS
ALLOWED_IPS="$PANEL_IP"; [[ "$PANEL_IP" == any ]] && ALLOWED_IPS=""

export DEBIAN_FRONTEND=noninteractive
if ! command -v docker >/dev/null 2>&1; then
  step "Установка Docker"
  apt_install docker.io || die "не удалось установить Docker"
  systemctl enable --now docker >/dev/null 2>&1 || true
fi
if ! docker compose version >/dev/null 2>&1; then
  step "Установка docker compose"
  apt_install docker-compose-plugin || apt_install docker-compose-v2 || die "не удалось установить docker compose"
fi
command -v openssl >/dev/null 2>&1 || apt_install openssl || die "не удалось установить openssl"

step "Каталоги и секреты"
mkdir -p "$NODE_DIR"/{secrets,tls}
chmod 700 "$NODE_DIR/secrets" "$NODE_DIR/tls"
umask 077
if [[ -n "$NODE_TOKEN_FILE" && -s "$NODE_TOKEN_FILE" ]]; then
  cat "$NODE_TOKEN_FILE" > "$NODE_DIR/secrets/node.token"
  rm -f "$NODE_TOKEN_FILE"
fi
[[ -s "$NODE_DIR/secrets/node.token" ]] || die "нет токена ноды"
if [[ ! -s "$NODE_DIR/tls/cert.pem" ]]; then
  step "Сертификат агента"
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 3650 \
    -subj "/CN=tunnelwright-node/O=Tunnelwright Panel AWG" -keyout "$NODE_DIR/tls/key.pem" -out "$NODE_DIR/tls/cert.pem" 2>/dev/null
fi
chmod 644 "$NODE_DIR/tls/cert.pem" "$NODE_DIR/secrets/node.token"
chmod 600 "$NODE_DIR/tls/key.pem"
umask 022

step "Образ агента ноды"
if docker pull -q "$NODE_IMAGE" >/dev/null 2>&1; then
  echo "  загружен из GHCR"
elif [[ -n "$BUNDLE" && -f "$BUNDLE" ]]; then
  rm -rf "$NODE_DIR/build" && mkdir -p "$NODE_DIR/build"
  tar xzf "$BUNDLE" -C "$NODE_DIR/build"
  # вывод сборки (в том числе предупреждение о legacy builder) — только при ошибке
  if ! out=$(docker build -q --build-arg APP_VERSION="$APP_VERSION" -t "$NODE_IMAGE" "$NODE_DIR/build" 2>&1); then
    echo "$out" | tail -20
    die "сборка образа агента не удалась"
  fi
  rm -f "$BUNDLE"
  echo "  собран на ноде"
else
  die "образ $NODE_IMAGE недоступен и исходники не переданы"
fi

step "docker-compose.yml"
cat > "$NODE_DIR/docker-compose.yml" <<EOF
# Tunnelwright Panel AWG node ${APP_VERSION} — создано панелью, не редактируйте вручную
name: tunnelwright-node

volumes:
  wg:   { name: tunnelwright_node_wg }
  node: { name: tunnelwright_node_data }

services:
  wg-easy:
    image: ${WG_EASY_IMAGE}
    container_name: tunnelwright-node-wg
    restart: unless-stopped
    environment:
      EXPERIMENTAL_AWG: "true"
      OVERRIDE_AUTO_AWG: "awg"
      DISABLE_IPV6: "true"
      INSECURE: "true"
      HOST: "127.0.0.1"
      PORT: "51821"
    volumes: [ "wg:/etc/wireguard" ]
    devices: [ "/dev/net/tun:/dev/net/tun" ]
    cap_add: [NET_ADMIN, SYS_MODULE]
    sysctls:
      - net.ipv4.ip_forward=1
      - net.ipv4.conf.all.src_valid_mark=1
    ports:
      - "${WG_PORT}:${WG_PORT}/udp"
      - "${AGENT_PORT}:8711/tcp"
    healthcheck:
      test: ["CMD-SHELL", "awg show | grep -q interface"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s
    logging: { driver: json-file, options: { max-size: "10m", max-file: "3" } }

  node-agent:
    image: ${NODE_IMAGE}
    container_name: tunnelwright-node-agent
    restart: unless-stopped
    network_mode: "service:wg-easy"
    cap_add: [NET_ADMIN]
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8711", "--no-access-log",
              "--ssl-certfile", "/run/tunnelwright/tls/cert.pem", "--ssl-keyfile", "/run/tunnelwright/tls/key.pem"]
    environment:
      WG_HOST: "${WG_HOST}"
      WG_PORT: "${WG_PORT}"
      WG_DNS: "${WG_DNS}"
      NODE_ALLOWED_IPS: "${ALLOWED_IPS}"   # опубликованный порт обходит ufw — фильтрует сам агент
    volumes:
      - node:/data
      - wg:/wg:ro
      - ${NODE_DIR}/secrets/node.token:/run/tunnelwright/node.token:ro
      - ${NODE_DIR}/tls:/run/tunnelwright/tls:ro
      - ${NODE_DIR}/update:/update          # запросы автообновления (см. update.sh)
    depends_on:
      wg-easy: { condition: service_started, restart: true }
    logging: { driver: json-file, options: { max-size: "10m", max-file: "3" } }
EOF

# Автообновление агента: панель передаёт агенту версию (и исходники), агент кладёт запрос
# в $NODE_DIR/update, systemd-юнит на хосте подхватывает его и меняет только образ агента.
# Агенту не нужен доступ к Docker — его права остаются прежними.
step "Автообновление агента"
mkdir -p "$NODE_DIR/update" && chmod 700 "$NODE_DIR/update"
echo "NODE_IMAGE_REPO=${NODE_IMAGE%:*}" > "$NODE_DIR/update.env"
cat > "$NODE_DIR/update.sh" <<'EOF'
#!/usr/bin/env bash
# Tunnelwright Panel AWG: обновление агента ноды по запросу панели (запускает tunnelwright-node-update.path)
set -uo pipefail
NODE_DIR=/opt/tunnelwright-node; U="$NODE_DIR/update"
# shellcheck disable=SC1091
. "$NODE_DIR/update.env"
[[ -f "$U/request" ]] || exit 0
ver=$(head -c 32 "$U/request" | tr -d '[:space:]'); rm -f "$U/request"
status() { printf '{"version":"%s","ok":%s,"message":"%s","ts":%s}\n' "$ver" "$1" "$2" "$(date +%s)" > "$U/status.tmp"
           mv "$U/status.tmp" "$U/status"; }
[[ "$ver" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { status false "неверная версия"; exit 1; }
img="${NODE_IMAGE_REPO}:${ver}"
if docker pull -q "$img" >/dev/null 2>&1; then
  src="образ из GHCR"
elif [[ -s "$U/bundle.tgz" ]]; then
  rm -rf "$NODE_DIR/build" && mkdir -p "$NODE_DIR/build"
  if ! tar xzf "$U/bundle.tgz" -C "$NODE_DIR/build" \
     || ! out=$(docker build -q --build-arg APP_VERSION="$ver" -t "$img" "$NODE_DIR/build" 2>&1); then
    echo "${out:-}" | tail -20 > "$U/log"
    status false "сборка образа не удалась"; exit 1
  fi
  src="собран на ноде"
else
  status false "образ недоступен и исходники не переданы"; exit 1
fi
rm -f "$U/bundle.tgz"
sed -i -E "s#^(    image: )${NODE_IMAGE_REPO}:[^ ]+\$#\1${img}#" "$NODE_DIR/docker-compose.yml"
if ! docker compose -f "$NODE_DIR/docker-compose.yml" up -d node-agent > "$U/log" 2>&1; then
  status false "агент не запустился"; exit 1
fi
status true "обновлено до ${ver}: ${src}"
EOF
chmod 700 "$NODE_DIR/update.sh"
if command -v systemctl >/dev/null 2>&1; then
  cat > /etc/systemd/system/tunnelwright-node-update.service <<EOF
[Unit]
Description=Tunnelwright Panel AWG: обновление агента ноды по запросу панели
[Service]
Type=oneshot
ExecStart=$NODE_DIR/update.sh
EOF
  cat > /etc/systemd/system/tunnelwright-node-update.path <<EOF
[Unit]
Description=Tunnelwright Panel AWG: запрос обновления агента ноды
[Path]
PathExists=$NODE_DIR/update/request
[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload && systemctl enable --now tunnelwright-node-update.path >/dev/null 2>&1 \
    && echo "  включено" || echo "  ⚠ не удалось включить tunnelwright-node-update.path — обновляйте ноду по SSH"
else
  echo "  ⚠ нет systemd — автообновление недоступно, обновляйте ноду по SSH"
fi

# Нода, установленная ранее в /opt/vpn-node (тома vpn_node_*): ключи переносятся
# в новые тома — клиентам не нужно менять конфиги, — а старые контейнеры, тома и юнит удаляются
LEGACY_DIR=/opt/vpn-node
if [[ -d "$LEGACY_DIR" ]] || docker volume inspect vpn_node_wg >/dev/null 2>&1; then
  step "Перенос ноды из $LEGACY_DIR"
  if [[ -f "$LEGACY_DIR/docker-compose.yml" ]]; then
    docker compose -f "$LEGACY_DIR/docker-compose.yml" down --timeout 15 >/dev/null 2>&1 || true
  fi
  docker rm -f vpn-node-wg vpn-node-agent >/dev/null 2>&1 || true
  if docker volume inspect vpn_node_wg >/dev/null 2>&1 && ! docker volume inspect tunnelwright_node_wg >/dev/null 2>&1; then
    for v in wg data; do
      docker volume create "tunnelwright_node_$v" >/dev/null
      cp -a "$(docker volume inspect -f '{{.Mountpoint}}' "vpn_node_$v")/." \
            "$(docker volume inspect -f '{{.Mountpoint}}' "tunnelwright_node_$v")/" || die "не удалось перенести данные ноды"
    done
    echo "  ключи сервера и клиентов перенесены"
  fi
  docker volume rm vpn_node_wg vpn_node_data >/dev/null 2>&1 || true
  if command -v systemctl >/dev/null 2>&1 && [[ -f /etc/systemd/system/vpn-node-update.path ]]; then
    systemctl disable --now vpn-node-update.path >/dev/null 2>&1 || true
    rm -f /etc/systemd/system/vpn-node-update.path /etc/systemd/system/vpn-node-update.service
    systemctl daemon-reload || true
  fi
  rm -rf "$LEGACY_DIR"
fi

# Восстановление: данные ноды из бэкапа панели (переустановленный сервер получает прежние ключи)
if [[ -n "${RESTORE_DIR:-}" && -s "${RESTORE_DIR}/wg-easy.db" ]]; then
  step "Восстановление данных ноды из бэкапа панели"
  docker compose -f "$NODE_DIR/docker-compose.yml" down --timeout 15 >/dev/null 2>&1 || true
  docker volume create tunnelwright_node_wg >/dev/null && docker volume create tunnelwright_node_data >/dev/null
  W=$(docker volume inspect -f '{{.Mountpoint}}' tunnelwright_node_wg)
  N=$(docker volume inspect -f '{{.Mountpoint}}' tunnelwright_node_data)
  rm -f "$W"/wg0.conf "$W"/wg-easy.db-wal "$W"/wg-easy.db-shm
  install -m 644 "$RESTORE_DIR/wg-easy.db" "$W/wg-easy.db"
  for f in limits.json wg-easy-admin.json uids.json; do
    if [[ -f "$RESTORE_DIR/$f" ]]; then install -m 600 "$RESTORE_DIR/$f" "$N/$f"; fi
  done
  rm -rf "$N/import" "$RESTORE_DIR"
  echo "  ключи сервера и клиентов восстановлены"
fi

step "Запуск"
docker compose -f "$NODE_DIR/docker-compose.yml" up -d --remove-orphans 2>&1 | tail -3

if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  step "Брандмауэр ufw"
  ufw allow "${WG_PORT}/udp" >/dev/null
fi

step "Проверка агента"
for _ in $(seq 1 30); do
  if docker exec tunnelwright-node-agent python -c "import ssl,urllib.request as u;print(u.urlopen('https://127.0.0.1:8711/health',context=ssl._create_unverified_context(),timeout=3).read().decode())" 2>/dev/null | grep -q '"ok":true'; then
    echo "  агент отвечает"
    break
  fi
  sleep 3
done

echo "=====CERT====="
cat "$NODE_DIR/tls/cert.pem"
echo "=====END====="
