#!/bin/bash
# ============================================================================
# Kev Server Entrypoint Script
# Handles graceful shutdown and pre-start checks
# ============================================================================

set -e

echo "=============================================="
echo "Kev Decision Model Server Startup"
echo "=============================================="

# 显示当前配置
echo "Model: ${KEV_MODEL:-jaredpalmer/kev-4b}"
echo "Precision: ${KEV_DTYPE:-bf16}"
echo "GPU Devices: ${CUDA_VISIBLE_DEVICES:-0}"
echo "Host: ${HOST:-0.0.0.0}:${PORT:-8008}"
echo "Prefix Cache Size: ${KEV_PREFIX_CACHE:-4}"

# GPU 验证
if command -v nvidia-smi &> /dev/null; then
    echo "GPU Status:"
    nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader
else
    echo "Warning: nvidia-smi not found, running in CPU mode (slow)"
fi

# 检查模型缓存（可选）
if [ -n "$MODEL_CACHE_PATH" ] && [ ! -d "$MODEL_CACHE_PATH" ]; then
    mkdir -p "$MODEL_CACHE_PATH"
    echo "Creating model cache directory: $MODEL_CACHE_PATH"
fi

# 等待启动完成超时设置
TIMEOUT=${STARTUP_TIMEOUT:-120}
START_TIME=$(date +%s)

echo ""
echo "Starting uvicorn server..."
echo ""

# 执行实际服务启动
exec python -m kev.serve \
    --host "${HOST:-0.0.0.0}" \
    --port "${PORT:-8008}" \
    --run "${KEV_MODEL:-jaredpalmer/kev-4b}" || {
    echo "Server exited with error code: $?"
    exit 1
}
