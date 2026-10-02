#!/bin/bash
# Kev-4B Docker 快速部署脚本（Windows PowerShell 兼容版本）
# 运行方式：bash deploy-windows.sh

echo "=============================================="
echo "Kev-4B Docker 部署脚本 (Windows 兼容版)"
echo "=============================================="

# 配置变量
IMAGE_NAME="kev-decision-model"
CONTAINER_NAME="kev-server"
HOST_PORT=8008

# 检查 Docker
if ! docker --version &> /dev/null; then
    echo "错误：未找到 Docker"
    exit 1
fi

# GPU 检查
if nvidia-smi &> $null; then
    Write-Host "✓ NVIDIA GPU detected" -ForegroundColor Green
else
    Write-Host "⚠ Running in CPU mode (slow)" -ForegroundColor Yellow
fi

# 构建镜像
Write-Host "Building Docker image..." -ForegroundColor Cyan
docker build -t ${IMAGE_NAME}:latest . --no-cache

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed!" -ForegroundColor Red
    exit 1
}

# 清理旧容器
docker stop $CONTAINER_NAME 2>$null
docker rm $CONTAINER_NAME 2>$null

# 启动容器
Write-Host "Starting container..." -ForegroundColor Cyan

$gpu_flag = ""
if (nvidia-smi) {
    $gpu_flag = "--gpus all"
}

& docker run -d `
    $gpu_flag `
    --name $CONTAINER_NAME `
    --runtime nvidia `
    --memory 16g `
    -p ${HOST_PORT}:8008 `
    -e KEV_MODEL=${env:KEV_MODEL:-"jaredpalmer/kev-4b"} `
    -e KEV_DTYPE=bf16 `
    -e MAX_BATCH=64 `
    -e KEV_PREFIX_CACHE=4 `
    -v kev-model-cache:/kev/checkpoints `
    --restart unless-stopped `
    ${IMAGE_NAME}:latest

if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to start container!" -ForegroundColor Red
    exit 1
}

Write-Host "Container started!" -ForegroundColor Green

# 等待就绪
Write-Host "Waiting for service ready..." -ForegroundColor Cyan
for ($i = 0; $i -lt 12; $i++) {
    Start-Sleep -Seconds 10
    
    try {
        curl http://localhost:${HOST_PORT}/v1/models -ErrorAction Stop | Out-Null
        Write-Host "Service is ready!" -ForegroundColor Green
        break
    } catch {
        Write-Host "Attempt $($i+1)/12..." -ForegroundColor Yellow
    }
}

# 测试 API
Write-Host "`nTesting API..." -ForegroundColor Cyan

# 获取模型信息
$response = Invoke-RestMethod -Uri "http://localhost:${HOST_PORT}/v1/models" -Method Get
Write-Host "`nModel Info:" -ForegroundColor Cyan
$response | ConvertTo-Json -Depth 10

# 发送测试请求
$test_body = @{
    state = "Test message";
    model = "kev-latest";
    questions = @{
        test = @{
            type = "noul";
            instructions = "This is a test";
            criteria = @{
                true = $null;
                false = $null
            }
        }
    }
} | ConvertTo-Json

try {
    $response = Invoke-RestMethod `
        -Uri "http://localhost:${HOST_PORT}/v1/systemone" `
        -Method Post `
        -Body $test_body `
        -ContentType "application/json"
    
    Write-Host "`nDecision Result:" -ForegroundColor Cyan
    $response | ConvertTo-Json -Depth 10
} catch {
    Write-Host "API test failed: $_" -ForegroundColor Yellow
}

Write-Host "`n==============================================" -ForegroundColor Green
Write-Host "Deployment completed!" -ForegroundColor Green
Write-Host "==============================================${NC}" -ForegroundColor Green

Write-Host "`nNext steps:" -ForegroundColor Cyan
Write-Host "1. Check status: docker ps"
Write-Host "2. View logs: docker logs -f $CONTAINER_NAME"
Write-Host "3. API endpoint: http://localhost:${HOST_PORT}/v1/models"
Write-Host "4. Stop service: docker stop $CONTAINER_NAME"
Write-Host "5. Start service: docker start $CONTAINER_NAME"

# 显示资源使用
Write-Host "`nResource usage:" -ForegroundColor Cyan
docker stats --no-stream $CONTAINER_NAME
