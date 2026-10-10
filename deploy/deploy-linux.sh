#!/bin/bash
# ============================================================================
# Kev Linux Docker deploy script (bash) — model chooser
# Run from anywhere:
#   ./deploy/deploy-linux.sh                       # default: Kev-4B
#   ./deploy/deploy-linux.sh --model 0.8B          # deploy Kev-0.8B instead
#   ./deploy/deploy-linux.sh --model 4B --run kev-4b-local --api-key <key>
#   ./deploy/deploy-linux.sh --model 0.8B --hub jaredpalmer/kev-0.8b --api-key <key>
# ============================================================================

set -e

MODEL="4B"
NO_BUILD=0
RUN_NAME=""
API_KEY="${KEV_API_KEY:-}"
HUB=""
while [ $# -gt 0 ]; do
    case "$1" in
        --model)    shift; MODEL="$1" ;;
        --no-build) NO_BUILD=1 ;;
        --run)      shift; RUN_NAME="$1" ;;
        --api-key)  shift; API_KEY="$1" ;;
        --hub)      shift; HUB="$1" ;;
        *) echo "unknown option: $1"; exit 1 ;;
    esac
    shift
done

# ----- model-specific defaults -----
case "$MODEL" in
    4B)   COMPOSE_NAME="docker-compose-4B.yml";  DEFAULT_RUN="kev-4b-local";  DEFAULT_HUB="jaredpalmer/kev-4b";  VRAM_NOTE="Kev-4B bf16 needs ~10-12 GB VRAM" ;;
    0.8B) COMPOSE_NAME="docker-compose-0.8B.yml"; DEFAULT_RUN="kev-0.8b-local"; DEFAULT_HUB="jaredpalmer/kev-0.8b"; VRAM_NOTE="Kev-0.8B bf16 needs only ~2-3 GB VRAM" ;;
    *) echo "ERROR: --model must be '4B' or '0.8B' (got '$MODEL')"; exit 1 ;;
esac

# Resolve paths relative to this script so the cwd does not matter
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/$COMPOSE_NAME"

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
echo "Kev-$MODEL Linux Docker deploy"
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
    echo "OK NVIDIA GPU: $GPU_NAME ($VRAM_NOTE)"
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

if [ -z "$RUN_NAME" ]; then RUN_NAME="$DEFAULT_RUN"; fi
if [ -n "$HUB" ]; then
    export KEV_RUN="$HUB"
    echo "Mode: Hub  -> KEV_RUN=$HUB"
else
    LOCAL_DIR="$SCRIPT_DIR/runs/$RUN_NAME"
    if [ ! -d "$LOCAL_DIR" ]; then
        echo "ERROR: local run directory not found: $LOCAL_DIR"
        echo "       Place the checkpoint (base model + kev adapter, or a full checkpoint) there,"
        echo "       or deploy from a Hub id:  ./deploy/deploy-linux.sh --model $MODEL --hub $DEFAULT_HUB"
        exit 1
    fi
    # The checkpoint must contain at least head.pt (the pointer head); otherwise
    # kev.serve treats the path as a Hub id and fails obscurely at runtime.
    if [ ! -f "$LOCAL_DIR/head.pt" ]; then
        echo "ERROR: checkpoint 'head.pt' not found in $LOCAL_DIR"
        echo "       Put the full Kev-$MODEL checkpoint there (head.pt + adapter_config.json"
        echo "       + adapter_model.safetensors + tokenizer files), or deploy from a Hub id:"
        echo "         ./deploy/deploy-linux.sh --model $MODEL --hub $DEFAULT_HUB"
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

# ----- stop the other model's stack (both share container names `kev-server`/`kev-playground`) -----
OTHER_MODEL=$([ "$MODEL" = "4B" ] && echo "0.8B" || echo "4B")
OTHER_COMPOSE="$SCRIPT_DIR/docker-compose-$OTHER_MODEL.yml"
if [ -f "$OTHER_COMPOSE" ]; then
    echo "Stopping the other Kev-$OTHER_MODEL stack (if running) to free shared container names..."
    $COMPOSE -f "$OTHER_COMPOSE" down > /dev/null 2>&1 || true
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

# ===== 4b. Wait for playground UI =====
echo ""
echo "[4b/6] Waiting for http://localhost:3000/ (playground UI)..."
PREADY=0; PELAPSED=0
while [ "$PELAPSED" -lt 120 ]; do
    sleep 3
    curl -sf http://localhost:3000/ > /dev/null 2>&1 && { PREADY=1; break; }
    PELAPSED=$((PELAPSED + 3))
done
if [ "$PREADY" -eq 1 ]; then
    echo "OK Playground UI is ready"
else
    echo "WARN: playground not ready after 120s — check: docker logs kev-playground"
fi

# ===== 5. Status =====
echo ""
echo "[5/6] Status:"
$COMPOSE -f "$COMPOSE_FILE" ps

# ===== 6. Tips =====
echo ""
echo "=============================================="
echo "Deploy done."
echo "  API:          http://localhost:8008  (docs: /docs)"
echo "  Playground UI: http://localhost:3000  (proxies /kev to kev-server)"
echo "=============================================="

echo ""
echo "Quick start:"
echo "  curl http://localhost:8008/v1/models"
echo "  open http://localhost:3000          # playground UI (kev / chess tabs)"
echo "  python scripts/test-api.py            # from the repo root"
echo "  docker logs -f kev-server"
echo "  docker logs -f kev-playground"
echo "  $COMPOSE -f deploy/$COMPOSE_NAME down"

echo ""
echo "Local run (default): put the checkpoint in ./deploy/runs/<name>/"
echo "  ./deploy/deploy-linux.sh --model $MODEL --run $DEFAULT_RUN --api-key <your-key>"
echo "Hub run:"
echo "  ./deploy/deploy-linux.sh --model $MODEL --hub $DEFAULT_HUB --api-key <your-key>"
echo "Switch models (stops the other stack first):"
echo "  ./deploy/deploy-linux.sh --model 0.8B --api-key <your-key>"
echo "Change API key / checkpoint on a running stack:"
echo "  KEV_API_KEY='<key>' KEV_RUN='/kev/runs/$DEFAULT_RUN' $COMPOSE -f deploy/$COMPOSE_NAME up -d"

echo ""
echo "See deploy/README.md for the full guide."
