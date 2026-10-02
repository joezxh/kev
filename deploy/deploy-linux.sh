#!/bin/bash
# ============================================================================
# Kev-4B Linux Docker deploy script (bash)
# Run from anywhere: ./deploy/deploy-linux.sh [--no-build] [--run <local-dir>] [--api-key <key>] [--hub <hub-id>]
# ============================================================================

set -e

NO_BUILD=0
RUN_NAME="kev-4b-local"
API_KEY="${KEV_API_KEY:-}"
HUB=""
while [ $# -gt 0 ]; do
    case "$1" in
        --no-build) NO_BUILD=1 ;;
        --run)      shift; RUN_NAME="$1" ;;
        --api-key)  shift; API_KEY="$1" ;;
        --hub)      shift; HUB="$1" ;;
        *) echo "unknown option: $1"; exit 1 ;;
    esac
    shift
done

# Resolve paths relative to this script so the cwd does not matter
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"

# Pick the compose command
if docker compose version > /dev/null 2>&1; then
    COMPOSE="docker compose"
elif docker-compose version > /dev/null 2>&1; then
    COMPOSE="docker-compose"
else
    echo "ERROR: docker compose (or docker-compose) not installed"
    exit 1
fi

echo "=============================================="
echo "Kev-4B Linux Docker deploy"
echo "=============================================="

# ===== 1. Preconditions =====
echo ""
echo "[1/6] Checking environment..."

if ! command -v docker > /dev/null 2>&1; then
    echo "ERROR: docker not installed (Ubuntu/Debian: sudo apt install docker.io docker-compose-plugin)"
    exit 1
fi
echo "OK Docker: $(docker --version)"

if ! docker info > /dev/null 2>&1; then
    echo "ERROR: docker daemon not running (sudo systemctl start docker)"
    exit 1
fi
echo "OK Docker daemon is up"

if [ ! -f "$COMPOSE_FILE" ]; then
    echo "ERROR: missing $COMPOSE_FILE"
    exit 1
fi
echo "OK Compose file: $COMPOSE_FILE"

if command -v nvidia-smi > /dev/null 2>&1; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n 1)
    echo "OK NVIDIA GPU: $GPU_NAME (Kev-4B bf16 needs ~10-12 GB VRAM)"
    if command -v nvidia-ctk > /dev/null 2>&1 || [ -f /usr/bin/nvidia-container-cli ]; then
        echo "OK NVIDIA Container Toolkit present"
    else
        echo "WARN: NVIDIA Container Toolkit missing — server will run on CPU"
        echo "      https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
    fi
else
    echo "WARN: no NVIDIA GPU visible — server will run on CPU (slow)"
fi

# ===== 2. Build =====
echo ""
echo "[2/6] Building image..."

if [ "$NO_BUILD" -eq 0 ]; then
    $COMPOSE -f "$COMPOSE_FILE" build
else
    echo "Skipped (--no-build)"
fi

# ===== 3. (Re)start =====
echo ""
echo "[3/6] Resolving model source, API key & starting service..."

if [ -n "$HUB" ]; then
    export KEV_RUN="$HUB"
    echo "Mode: Hub  -> KEV_RUN=$HUB"
else
    LOCAL_DIR="$SCRIPT_DIR/runs/$RUN_NAME"
    if [ ! -d "$LOCAL_DIR" ]; then
        echo "ERROR: local run directory not found: $LOCAL_DIR"
        echo "       Place the checkpoint (base model + kev adapter, or a full checkpoint) there,"
        echo "       or deploy from a Hub id:  ./deploy/deploy-linux.sh --hub jaredpalmer/kev-4b"
        exit 1
    fi
    export KEV_RUN="/kev/runs/$RUN_NAME"
    echo "Mode: local -> KEV_RUN=$KEV_RUN  (host: $LOCAL_DIR)"
fi

export KEV_API_KEY="$API_KEY"
if [ -n "$API_KEY" ]; then
    echo "API key: set (clients must send 'Authorization: Bearer <key>')"
else
    echo "API key: NONE -> server is OPEN (no auth). Set --api-key or \$KEV_API_KEY."
fi

$COMPOSE -f "$COMPOSE_FILE" up -d

# ===== 4. Wait for readiness =====
echo ""
echo "[4/6] Waiting for http://localhost:8008/v1/models (first start downloads the checkpoint)..."

MAX_WAIT=600
ELAPSED=0
READY=0
while [ "$ELAPSED" -lt "$MAX_WAIT" ]; do
    sleep 5
    if [ -n "$API_KEY" ]; then
        curl -sf -H "Authorization: Bearer $API_KEY" http://localhost:8008/v1/models > /dev/null 2>&1 && { READY=1; break; }
    else
        curl -sf http://localhost:8008/v1/models > /dev/null 2>&1 && { READY=1; break; }
    fi
    ELAPSED=$((ELAPSED + 5))
    if [ $((ELAPSED % 30)) -eq 0 ]; then echo "  waiting... ${ELAPSED}s"; fi
done

if [ "$READY" -eq 1 ]; then
    echo "OK Service is ready"
else
    echo "WARN: not ready after ${MAX_WAIT}s — check logs:"
    echo "      docker logs -f kev-server"
fi

# ===== 5. Status =====
echo ""
echo "[5/6] Status:"
$COMPOSE -f "$COMPOSE_FILE" ps

# ===== 6. Tips =====
echo ""
echo "=============================================="
echo "Deploy done. API: http://localhost:8008  (docs: /docs)"
echo "=============================================="

echo ""
echo "Quick start:"
echo "  curl http://localhost:8008/v1/models"
echo "  python scripts/test-api.py            # from the repo root"
echo "  docker logs -f kev-server"
echo "  $COMPOSE -f deploy/docker-compose.yml down"

echo ""
echo "Local run (default): put the checkpoint in ./deploy/runs/<name>/"
echo "  ./deploy/deploy-linux.sh --run kev-4b-local --api-key <your-key>"
echo "Hub run:"
echo "  ./deploy/deploy-linux.sh --hub jaredpalmer/kev-4b --api-key <your-key>"
echo "Change API key / checkpoint on a running stack:"
echo "  KEV_API_KEY='<key>' KEV_RUN='/kev/runs/kev-4b-local' $COMPOSE -f deploy/docker-compose.yml up -d"

echo ""
echo "See deploy/README.md for the full guide."
