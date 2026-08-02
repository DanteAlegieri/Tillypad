#!/usr/bin/env bash
set -euo pipefail

AGENT_ID="${1:-gastrodom3}"
ADMIN_TOKEN="${GATEWAY_ADMIN_TOKEN:?Не задан GATEWAY_ADMIN_TOKEN}"

curl -sS \
  -H "X-Admin-Token: ${ADMIN_TOKEN}" \
  "http://127.0.0.1:8020/api/cloud/${AGENT_ID}/sales/latest"
echo
