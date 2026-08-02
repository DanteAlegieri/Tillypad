#!/usr/bin/env bash
set -euo pipefail

cd /opt/restaurantos/gateway
docker compose up -d --build
docker compose ps
curl --fail http://127.0.0.1:8020/health
echo
echo "Gateway обновлён."
