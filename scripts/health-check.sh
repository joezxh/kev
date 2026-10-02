#!/bin/bash
# ============================================================================
# Kev Server Health Check Script
# Used by Docker HEALTHCHECK directive
# Returns 0 if healthy, 1 otherwise
# ============================================================================

set -e

# 配置超时时间
TIMEOUT=5
BASE_URL=${KEV_API_URL:-http://localhost:8008}
ENDPOINT="/v1/models"

echo "Running health check on $BASE_URL$ENDPOINT (timeout: ${TIMEOUT}s)..."

# 发送 HTTP GET 请求并设置超时
if timeout $TIMEOUT curl -f -s "$BASE_URL$ENDPOINT" > /dev/null 2>&1; then
    echo "✓ Health check passed"
    exit 0
else
    echo "✗ Health check failed" >&2
    exit 1
fi
