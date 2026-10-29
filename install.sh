#!/usr/bin/env bash
# =============================================================================
#  Tunnelwright Panel AWG — загрузчик
#  Скачивает релиз с GitHub, проверяет sha256,
#  раскладывает в /opt/tunnelwright/releases/<версия> и запускает установщик.
#
#  Использование:
#    sudo bash install.sh                      # последний релиз
#    sudo bash install.sh --version v1.0.0     # конкретный релиз
#    sudo bash install.sh --channel main       # ветка без релиза (для тестов)
#  Остальные параметры передаются в installer/setup.sh
#  (--reuse, --build-local, --update-ui).
#
#  Токен GitHub не нужен (репозиторий публичный); если задан — $GITHUB_TOKEN или GITHUB_TOKEN=
#  в install.env, или сохранён прежней установкой в /opt/tunnelwright/.github_token — используется.
# =============================================================================
set -euo pipefail

REPO="prg77/tunnelwright-panel-awg"
BASE_DIR="/opt/tunnelwright"
RELEASES_DIR="${BASE_DIR}/releases"
TOKEN_FILE="${BASE_DIR}/.github_token"
KEEP_RELEASES=3

VERSION=""
CHANNEL=""
SETUP_ARGS=()

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; DIM='\033[2m'; RESET='\033[0m'
info() { echo -e "  ${DIM}→ $*${RESET}"; }
ok()   { echo -e "  ${GREEN}✓ $*${RESET}"; }
warn() { echo -e "  ${YELLOW}⚠ $*${RESET}"; }
die()  { echo -e "  ${RED}✗ $*${RESET}" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) VERSION="${2:-}"; [[ -n "$VERSION" ]] || die "--version требует значение"; shift ;;
    --channel) CHANNEL="${2:-}"; [[ -n "$CHANNEL" ]] || die "--channel требует значение"; shift ;;
    -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) SETUP_ARGS+=("$1") ;;
  esac
  shift
done

[[ $EUID -eq 0 ]] || die "Запустите от root: sudo bash $0"

# ── Зависимости загрузчика ───────────────────────────────────
missing=()
for bin in curl tar sha256sum python3; do
  command -v "$bin" &>/dev/null || missing+=("$bin")
done
if [[ ${#missing[@]} -gt 0 ]]; then
  command -v apt-get &>/dev/null || die "Не хватает: ${missing[*]}. Установите вручную."
  info "Устанавливаем: ${missing[*]}"
  pkgs=()
  for bin in "${missing[@]}"; do
    case "$bin" in sha256sum) pkgs+=(coreutils) ;; *) pkgs+=("$bin") ;; esac
  done
  DEBIAN_FRONTEND=noninteractive apt-get update -qq >/dev/null
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends "${pkgs[@]}" ca-certificates >/dev/null
fi

# ── install.env (non-interactive режим) ──────────────────────
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || pwd)"
INSTALL_ENV=""
for p in "${SELF_DIR}/install.env" "$(pwd)/install.env"; do
  [[ -f "$p" ]] && { INSTALL_ENV="$p"; break; }
done

# ── Токен GitHub (необязательный) ────────────────────────────
# Репозиторий публичный: релизы скачиваются без токена. Если токен есть (сохранён прежней
# установкой или задан), он используется — у анонимных запросов к API лимит 60 в час.
TOKEN="${GITHUB_TOKEN:-}"
if [[ -z "$TOKEN" && -n "$INSTALL_ENV" ]]; then
  TOKEN=$(sed -n 's/^GITHUB_TOKEN=//p' "$INSTALL_ENV" | tail -1 | tr -d "\"' \r")
fi
if [[ -z "$TOKEN" && -f "$TOKEN_FILE" ]]; then
  TOKEN=$(tr -d '[:space:]' < "$TOKEN_FILE")
fi
AUTH=()
[[ -n "$TOKEN" ]] && AUTH=(-H "Authorization: Bearer ${TOKEN}")

gh_api() {
  curl -fsSL "${AUTH[@]}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/${REPO}/$1"
}
gh_download() {  # gh_download <api-path> <файл> [accept]
  curl -fsSL --retry 3 "${AUTH[@]}" \
    -H "Accept: ${3:-application/octet-stream}" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    -o "$2" "https://api.github.com/repos/${REPO}/$1"
}

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# ── Скачивание ───────────────────────────────────────────────
if [[ -n "$CHANNEL" ]]; then
  info "Скачиваем ветку ${CHANNEL}..."
  sha=$(gh_api "commits/${CHANNEL}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["sha"][:7])') \
    || die "Ветка ${CHANNEL} не найдена"
  LABEL="${CHANNEL}-${sha}"
  gh_download "tarball/${CHANNEL}" "$TMP/src.tar.gz" "application/vnd.github+json" \
    || die "Не удалось скачать ветку ${CHANNEL}"
  warn "Ветка без релиза: контрольная сумма не проверяется"
else
  if [[ -n "$VERSION" ]]; then
    [[ "$VERSION" == v* ]] || VERSION="v${VERSION}"
    meta=$(gh_api "releases/tags/${VERSION}") || die "Релиз ${VERSION} не найден"
  else
    meta=$(gh_api "releases/latest") || die "Релизы не найдены (или превышен лимит запросов GitHub — повторите позже)"
  fi
  # tag, id архива, id SHA256SUMS
  read -r LABEL archive_id sums_id < <(python3 -c '
import json, sys
r = json.load(sys.stdin)
tag = r["tag_name"]
assets = {a["name"]: a["id"] for a in r.get("assets", [])}
archive = assets.get("tunnelwright-panel-awg-%s.tar.gz" % tag, "")
print(tag, archive, assets.get("SHA256SUMS", ""))
' <<<"$meta")
  [[ -n "$archive_id" && -n "$sums_id" ]] || die "В релизе ${LABEL} нет архива или SHA256SUMS"
  info "Скачиваем релиз ${LABEL}..."
  gh_download "releases/assets/${archive_id}" "$TMP/src.tar.gz" || die "Не удалось скачать архив"
  gh_download "releases/assets/${sums_id}" "$TMP/SHA256SUMS" || die "Не удалось скачать SHA256SUMS"
  # SHA256SUMS содержит имя архива — проверяем по его хэшу, а не по имени файла
  want=$(awk 'NR==1 {print $1}' "$TMP/SHA256SUMS")
  [[ -n "$want" && "$(sha256sum "$TMP/src.tar.gz" | cut -d' ' -f1)" == "$want" ]] \
    || die "Контрольная сумма архива не совпадает"
  ok "Контрольная сумма совпадает"
fi

# ── Распаковка и переключение ────────────────────────────────
mkdir -p "$RELEASES_DIR"
DEST="${RELEASES_DIR}/${LABEL}"
rm -rf "${DEST}.new"
mkdir -p "${DEST}.new"
tar -xzf "$TMP/src.tar.gz" -C "${DEST}.new" --strip-components=1
[[ -f "${DEST}.new/installer/setup.sh" ]] || die "Архив повреждён: нет installer/setup.sh"
rm -rf "$DEST"
mv "${DEST}.new" "$DEST"

if [[ -L "${BASE_DIR}/current" ]]; then
  prev=$(basename "$(readlink -f "${BASE_DIR}/current")")
  [[ "$prev" != "$LABEL" ]] && echo "$prev" > "${BASE_DIR}/.previous"
fi
ln -sfn "$DEST" "${BASE_DIR}/current"
ok "Установлен код ${LABEL} → ${BASE_DIR}/current"

# Старые релизы: оставляем KEEP_RELEASES последних (+ текущий и предыдущий)
keep_prev=$(cat "${BASE_DIR}/.previous" 2>/dev/null || true)
mapfile -t old < <(ls -1t "$RELEASES_DIR" | tail -n +$((KEEP_RELEASES + 1)))
for d in "${old[@]}"; do
  [[ "$d" == "$LABEL" || "$d" == "$keep_prev" ]] && continue
  rm -rf "${RELEASES_DIR:?}/${d}"
done

export INSTALL_ENV
exec bash "${BASE_DIR}/current/installer/setup.sh" "${SETUP_ARGS[@]}"
