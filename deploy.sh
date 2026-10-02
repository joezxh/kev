#!/bin/bash
# ============================================================================
# Kev-4B Docker 快速部署脚本
# 一键完成构建和启动流程
# ============================================================================

set -e

echo "=============================================="
echo "Kev-4B Docker 部署脚本"
echo "=============================================="

# 配置变量
IMAGE_NAME="kev-decision-model"
CONTAINER_NAME="kev-server"
HOST_PORT=8008

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查命令是否存在
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo -e "${RED}错误：未找到 $1${NC}"
        exit 1
    fi
}

# 检查 GPU 可用性
check_gpu() {
    echo -e "\n${YELLOW}检查 GPU 环境...${NC}"
    
    if command -v nvidia-smi &> /dev/null; then
        local gpu_info=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader)
        local count=$(echo "$gpu_info" | wc -l)
        
        if [ "$count" -eq 0 ]; then
            echo -e "${RED}警告：检测到 NVIDIA GPU，但无法读取信息${NC}"
        else
            echo -e "${GREEN}✓ 发现 $count 个 GPU:${NC}"
            echo "$gpu_info" | while read line; do echo "  - $line"; done
        fi
        
        # 检查 Nsight Systems
        if command -v nvidia-ctk &> /dev/null; then
            echo -e "${GREEN}✓ NVIDIA Container Toolkit 已安装${NC}"
        else
            echo -e "${RED}✗ NVIDIA Container Toolkit 未安装${NC}"
            echo -e "请运行：$ curl -s -L https://nvidia.github.io/libnvidia-container/gpgkey | sudo apt-key add -"
            echo "     $ curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list"
            echo "     $ sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit"
            exit 1
        fi
    else
        echo -e "${YELLOW}未检测到 NVIDIA GPU，将在 CPU 模式下运行（速度较慢）${NC}"
    fi
}

# 构建镜像
build_image() {
    echo -e "\n${YELLOW}构建 Docker 镜像...${NC}"
    
    if docker build -t ${IMAGE_NAME}:latest . --no-cache; then
        echo -e "${GREEN}✓ 镜像构建成功${NC}"
    else
        echo -e "${RED}✗ 镜像构建失败${NC}"
        exit 1
    fi
    
    # 显示镜像大小
    local size=$(docker images ${IMAGE_NAME}:latest --format "{{.Size}}" | head -1)
    echo -e "${GREEN}镜像大小：${size}${NC}"
}

# 清理旧容器
cleanup() {
    echo -e "\n${YELLOW}清理旧容器...${NC}"
    
    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo -e "${YELLOW}停止并移除旧容器...${NC}"
        docker stop ${CONTAINER_NAME} || true
        docker rm ${CONTAINER_NAME} || true
    fi
}

# 启动容器
start_container() {
    echo -e "\n${YELLOW}启动容器...${NC}"
    
    # 准备参数
    local EXTRA_ARGS=""
    local MODEL_PATH="${KEV_MODEL:-jaredpalmer/kev-4b}"
    
    # GPU 支持检查
    if command -v nvidia-smi &> /dev/null; then
        EXTRA_ARGS="--gpus all"
    fi
    
    # 构建启动命令
    local cmd="docker run -d \\
      $EXTRA_ARGS \\
      --name ${CONTAINER_NAME} \\
      --runtime nvidia \\
      --memory 16g \\
      --memory-reservation 8g \\
      -p ${HOST_PORT}:8008 \\
      -e KEV_MODEL=${MODEL_PATH} \\
      -e KEV_DTYPE=bf16 \\
      -e MAX_BATCH=64 \\
      -e KEV_PREFIX_CACHE=4 \\
      -v kev-model-cache:/kev/checkpoints \\
      --restart unless-stopped \\
      ${IMAGE_NAME}:latest"
    
    # 添加 API 密钥（如果设置）
    if [ -n "${KEV_API_KEY:-}" ]; then
        cmd="$cmd \\
      -e KEV_API_KEY=${KEV_API_KEY}"
    fi
    
    # 执行启动
    eval $cmd
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ 容器启动成功${NC}"
    else
        echo -e "${RED}✗ 容器启动失败${NC}"
        exit 1
    fi
}

# 等待服务就绪
wait_for_ready() {
    echo -e "\n${YELLOW}等待服务就绪（最多 120 秒）...${NC}"
    
    local max_attempts=12
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        sleep 10
        
        if curl -f http://localhost:${HOST_PORT}/v1/models > /dev/null 2>&1; then
            echo -e "${GREEN}✓ 服务已就绪！${NC}"
            return 0
        fi
        
        echo -e "${YELLOW}尝试 $attempt/$max_attempts...${NC}"
        ((attempt++))
    done
    
    echo -e "${RED}✗ 服务未在预期时间内启动${NC}"
    echo "查看详细日志："
    docker logs --tail 50 ${CONTAINER_NAME}
    exit 1
}

# 测试 API
test_api() {
    echo -e "\n${YELLOW}测试 API 连接...${NC}"
    
    # 测试模型端点
    echo -e "\n测试 GET /v1/models:"
    curl -s http://localhost:${HOST_PORT}/v1/models | jq '.' | head -20
    
    # 测试决策端点
    echo -e "\n测试 POST /v1/systemone:"
    local response=$(curl -s -X POST http://localhost:${HOST_PORT}/v1/systemone \
        -H "Content-Type: application/json" \
        -d '{
            "state": "测试消息",
            "model": "kev-latest",
            "questions": {
                "test": {"type": "noul", "instructions": "This is a test", "criteria": {"true": null, "false": null}}
            }
        }')
    
    echo "$response" | jq '.'
    
    echo -e "\n${GREEN}✓ API 测试通过${NC}"
}

# 显示状态
show_status() {
    echo -e "\n${YELLOW}容器状态:${NC}"
    docker inspect ${CONTAINER_NAME} --format '
名称：{{.Name}}
状态：{{.State.Status}}
端口：{{(index .NetworkSettings.Ports "8008/tcp")[0].HostPort}}
创建时间：{{.Created}}
'
    
    echo -e "\n${YELLOW}资源使用:${NC}"
    docker stats ${CONTAINER_NAME} --no-stream
    
    echo -e "\n${YELLOW}健康检查:${NC}"
    docker inspect ${CONTAINER_NAME} --format '{{.State.Health.Status}}'
}

# 主流程
main() {
    echo "=============================================="
    echo "开始部署..."
    echo "=============================================="
    
    # 前置检查
    check_command docker
    check_command curl
    
    # GPU 环境检查
    check_gpu
    
    # 构建镜像
    build_image
    
    # 清理旧容器
    cleanup
    
    # 启动容器
    start_container
    
    # 等待就绪
    wait_for_ready
    
    # 测试 API
    test_api
    
    echo -e "\n${GREEN}=============================================="
    echo "部署完成！"
    echo "==============================================${NC}"
    
    echo -e "\n${YELLOW}下一步操作:${NC}"
    echo "1. 查看容器状态：docker ps"
    echo "2. 查看实时日志：docker logs -f ${CONTAINER_NAME}"
    echo "3. 访问 API：http://localhost:${HOST_PORT}/v1/models"
    echo "4. 停止服务：docker stop ${CONTAINER_NAME}"
    echo "5. 启动服务：docker start ${CONTAINER_NAME}"
    
    # 自动显示状态（可选）
    show_status
}

# 解析命令行参数
case "${1:-deploy}" in
    deploy|up)
        main
        ;;
    status)
        check_command docker
        show_status
        ;;
    stop)
        check_command docker
        docker stop ${CONTAINER_NAME}
        docker rm ${CONTAINER_NAME}
        echo -e "${GREEN}✓ 容器已停止并移除${NC}"
        ;;
    restart)
        check_command docker
        docker restart ${CONTAINER_NAME}
        echo -e "${GREEN}✓ 容器已重启${NC}"
        ;;
    logs)
        check_command docker
        docker logs -f ${CONTAINER_NAME}
        ;;
    clean)
        check_command docker
        echo -e "${YELLOW}删除镜像和卷...${NC}"
        docker rmi ${IMAGE_NAME}:latest || true
        docker volume remove kev-model-cache || true
        echo -e "${GREEN}✓ 清理完成${NC}"
        ;;
    *)
        echo "用法：$0 {deploy|status|stop|restart|logs|clean}"
        echo ""
        echo "子命令:"
        echo "  deploy   完整部署流程（默认行为）"
        echo "  status   查看容器状态和资源使用"
        echo "  stop     停止并移除容器"
        echo "  restart  重启容器"
        echo "  logs     查看实时日志"
        echo "  clean    删除镜像和持久化卷"
        ;;
esac
