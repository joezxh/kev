#!/usr/bin/env bash
# One-click deploy for the Kev stack (kev-server + kev-playground).
# Builds both images and starts the two containers.
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE="${1:-$(dirname "$0")/docker-compose.yml}"

echo "Building and starting Kev stack (kev-server + kev-playground)..."
docker compose -f "$COMPOSE" up -d --build

echo
echo "Stack is up:"
echo "  Playground:  http://localhost:3030"
echo "  Server API:  http://localhost:8008  (docs: /docs)"
echo "  Console API: http://localhost:8008/console/api"
echo
echo "Stop it with:  docker compose -f \"$COMPOSE\" down"
