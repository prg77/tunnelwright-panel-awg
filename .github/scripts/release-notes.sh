#!/usr/bin/env bash
# Описание релиза GitHub из шаблона .github/release-notes.md ({{VERSION}} — номер версии).
#   .github/scripts/release-notes.sh v1.0.0 > notes.md
set -euo pipefail
v="${1#v}"
sed "s/{{VERSION}}/${v}/g" .github/release-notes.md
