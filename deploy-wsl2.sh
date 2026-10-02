#!/bin/bash
# ============================================================================
# Kev-4B WSL2 本地部署脚本
# 适用于 Windows + WSL2 + Docker Desktop 环境
# ============================================================================

set -e

echo "=============================================="
echo "Kev-4B WSL2 部署初始化"
echo "=============================================="

# ===== 1. 检查前置条件 =====
echo ""
echo "🔍 检查系统环境..."

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装，请先安装 Docker Desktop for Windows"
    exit 1
fi
echo "✓ Docker 已安装：$(docker --version)"

# 检查 nvidia-container-cli
if command -v nvidia-smi &> /dev/null; then
    echo "✓ NVIDIA 驱动可用：$(nvidia-smi --query-gpu=name --format=csv,noheader | tr -d '\r')"
else
    echo "⚠️  NVIDIA GPU 未检测到，服务将以 CPU 模式运行（较慢）"
fi

# 检查 Docker Compose
if ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose 未启用，请使用旧版命令 docker-compose"
fi

# ===== 2. 创建必要的目录结构 =====
echo ""
echo "📁 创建项目目录..."

PROJECT_DIR="${HOME}/kev-deploy"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# 克隆 kev 仓库（如果还没有）
if [ ! -d "kev" ]; then
    echo "📥 克隆 Kev 仓库..."
    git clone --depth 1 https://github.com/jaredpalmer/kev.git kev || true
fi

# 复制 Dockerfile 到当前目录（关键！）
if [ -f "kev/Dockerfile" ] && [ ! -f "Dockerfile" ]; then
    echo "🔗 链接 Dockerfile..."
    cp kev/Dockerfile ./Dockerfile
else
    echo "⚠️  Dockerfile 已存在或无法复制"
fi

# 创建数据持久化目录
mkdir -p model-cache
mkdir -p runs

# ===== 3. 生成环境变量文件 =====
echo ""
echo "⚙️  生成环境变量配置..."

cat > .env << EOF
# ===== 核心配置 =====
KEV_MODEL=jaredpalmer/kev-4b
KEV_DTYPE=bf16
KEV_PREFIX_CACHE=4

# ===== GPU 配置 =====
CUDA_VISIBLE_DEVICES=0

# ===== 性能参数 =====
MAX_BATCH=64
KEV_CUDA_GRAPHS=1
KEV_FUSED=1

# ===== 网络配置 =====
HOST=0.0.0.0
PORT=8008

# ===== 安全选项（可选）=====
# KEV_API_KEY=your-secret-key-here

# ===== 调试选项（默认关闭）=====
# KEV_DATE_FACTS=0
# KEV_TRUNCATE_STATES=0
EOF

echo "✓ 配置文件已保存：$PROJECT_DIR/.env"

# ===== 4. 创建 Docker Compose 配置 =====
echo ""
echo "🐳 创建 Docker Compose 配置..."

cat > docker-compose.yml << 'COMPOSE_EOF'
version: "3.9"

services:
  kev-server:
    build:
      context: ./kev
      dockerfile: Dockerfile
    
    image: kev-decision-model:latest
    container_name: kev-server
    
    # GPU 支持
    runtime: nvidia
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    
    ports:
      - "8008:8008"
    
    environment:
      - KEV_MODEL=${KEV_MODEL}
      - KEV_DTYPE=${KEV_DTYPE}
      - KEV_PREFIX_CACHE=${KEV_PREFIX_CACHE}
      - CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES}
      - MAX_BATCH=${MAX_BATCH}
      - KEV_CUDA_GRAPHS=${KEV_CUDA_GRAPHS}
      - KEV_FUSED=${KEV_FUSED}
      - HOST=${HOST}
      - PORT=${PORT}
      - KEV_API_KEY=${KEV_API_KEY}
      - KEV_DATE_FACTS=${KEV_DATE_FACTS}
      - KEV_TRUNCATE_STATES=${KEV_TRUNCATE_STATES}
    
    volumes:
      - ./model-cache:/kev/checkpoints
      - ./runs:/kev/runs
    
    healthcheck:
      test: ["CMD", "/bin/bash", "-c", "curl -f http://localhost:8008/v1/models || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s
    
    restart: unless-stopped
    
    networks:
      - kev-network

networks:
  kev-network:
    driver: bridge

volumes:
  model-cache:
  runs:
COMPOSE_EOF

echo "✓ Docker Compose 配置已创建"

# ===== 5. 显示部署摘要 =====
echo ""
echo "=============================================="
echo "✅ 部署配置完成！"
echo "=============================================="
echo ""
echo "📂 项目目录：$PROJECT_DIR"
echo "📄 配置文件：$PROJECT_DIR/.env"
echo "🌐 API 地址：http://localhost:8008"
echo ""
echo "🚀 下一步操作："
echo "   1. cd $PROJECT_DIR"
echo "   2. docker compose up -d --build"
echo "   3. docker compose logs -f kev-server"
echo ""
echo "🧪 测试 API："
echo "   curl http://localhost:8008/v1/models"
echo ""
echo "📖 详细文档：https://github.com/jaredpalmer/kev"
echo ""
