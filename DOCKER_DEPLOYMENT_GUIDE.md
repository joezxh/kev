# Kev-4B Docker 部署完整方案

本文档提供在 GPU 服务器上部署 Kev-4B 决策模型的完整 Docker 解决方案。

## 目录
1. [快速开始](#1-快速开始)
2. [Dockerfile](#2-dockerfile)
3. [Docker Compose 配置](#3-docker-compose-配置)
4. [镜像构建与依赖](#4-镜像构建与依赖)
5. [容器启动参数](#5-容器启动参数)
6. [API 服务访问](#6-api-服务访问)
7. [健康检查与监控](#7-健康检查与监控)
8. [生产环境最佳实践](#8-生产环境最佳实践)
9. [故障排查](#9-故障排查)

---

## 1. 快速开始

### 1.1 前置条件
- **GPU 服务器**：NVIDIA GPU（推荐 H100/L40S，最低 L4）
- **显存要求**：
  - Kev-4B（bf16）：约 10-12 GB VRAM
  - Kev-4B（fp16）：约 8-10 GB VRAM
  - Kev-4B（fp32）：约 16-20 GB VRAM
- **系统要求**：CUDA 11.8+ / 12.x，Docker 20.10+
- **NVIDIA Container Toolkit**：启用 GPU 直通

### 1.2 一键部署（推荐）

```bash
# 克隆项目
git clone https://github.com/jaredpalmer/kev.git
cd kev

# 构建并启动（使用 docker-compose）
docker-compose --profile production up -d --build

# 查看日志
docker-compose logs -f kev-server

# 测试 API
curl -s http://localhost:8008/v1/models | jq
```

### 1.3 直接测试（无缓存状态）

```bash
curl -X POST http://localhost:8008/v1/systemone \
  -H "Content-Type: application/json" \
  -d '{
    "state": "Shoes arrived two weeks late and in the wrong size.",
    "model": "kev-latest",
    "questions": {
      "returns": {"type": "choice", "instructions": "Which team?", 
                  "criteria": {"returns": null, "shipping": null, "billing": null}},
      "late": {"type": "noul", "instructions": "Is this urgent?", "criteria": {"true": null, "false": null}}
    }
  }' | jq
```

---

## 2. Dockerfile

以下是专为 Kev-4B 优化的多阶段构建 Dockerfile：

```dockerfile
# ============================================================================
# Kev Decision Model Serving Dockerfile
# Multi-stage build for optimized image size and reproducibility
# ============================================================================

# ==================== Build Stage 1: Dependencies ====================
FROM python:3.13-slim-bookworm AS builder

# 设置工作目录
WORKDIR /app

# 安装系统依赖（用于编译部分 Python 包）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 使用 uv 加速 Python 依赖安装
RUN pip install --no-cache-dir uv

# 复制依赖文件
COPY pyproject.toml .python-version ./

# 安装 Python 依赖（仅 serve extra）
RUN uv sync --extra serve --no-dev --no-self-installs

# ==================== Build Stage 2: Full Environment ====================
FROM builder AS full-env

# 克隆 kev 仓库（包含训练脚本和模型加载逻辑）
RUN git clone --depth 1 https://github.com/jaredpalmer/kev.git /kev-src || true

# 将依赖复制到最终环境
COPY --from=builder /app/.venv /usr/local/python/venv


# ==================== Production Stage: Minimal Runtime ====================
FROM python:3.13-slim-bookworm AS production

# 标注元数据
LABEL maintainer="kev-deploy"
LABEL description="Kev-4B Decision Model Server with GPU Support"
LABEL version="1.0"

# 安装运行时系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcuda1 \
    libcudnn8 \
    cuda-compat \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /usr/local/cuda/lib64/stubs

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# 创建工作目录
WORKDIR /kev

# 从 builder 阶段复制虚拟环境
COPY --from=builder /app/.venv /usr/local/python/venv

# 添加 venv 到 PATH
ENV PATH=/usr/local/python/venv/bin:$PATH

# 克隆轻量级源码仓库（只保留必要文件）
RUN git clone --depth 1 --branch main https://github.com/jaredpalmer/kev.git . 2>/dev/null || true

# 创建模型缓存目录（避免每次重新下载）
RUN mkdir -p /kev/checkpoints /kev/runs

# 暴露服务端口
EXPOSE 8008

# 健康检查（每 30 秒执行一次）
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8008/v1/models || exit 1

# 入口点脚本（带优雅关闭）
COPY scripts/docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 健康检查脚本
COPY scripts/health-check.sh /usr/local/bin/health-check.sh
RUN chmod +x /usr/local/bin/health-check.sh

# 设置默认环境变量
ENV KEV_MODEL="jaredpalmer/kev-4b" \
    CUDA_VISIBLE_DEVICES="0" \
    KEV_PREFIX_CACHE="4" \
    KEV_DTYPE="bf16" \
    MAX_BATCH="64"

# 运行入口点
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# 默认命令
CMD ["python", "-m", "kev.serve", "--host", "0.0.0.0", "--port", "8008"]


# ==================== Development Stage (可选) ====================
FROM production AS dev

# 安装开发依赖
RUN pip install --no-cache-dir \
    pytest>=9.1.1 \
    httpx>=0.28.1 \
    matplotlib>=3.9

# 挂载源码热重载
VOLUME ["/kev/src"]

# 开发模式命令
CMD ["pytest", "tests/", "-q"]
```

---

## 3. Docker Compose 配置

### 3.1 生产环境配置

```yaml
version: "3.9"

services:
  kev-server:
    build:
      context: .
      dockerfile: Dockerfile
      target: production
    
    image: kev-decision-model:latest
    container_name: kev-server
    
    # GPU 支持（必需）
    runtime: nvidia
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    
    # 资源限制
    deploy:
      resources:
        limits:
          memory: 16G
          nvidia.com/gpu.count: 1
        reservations:
          memory: 8G
          nvidia.com/gpu.count: 1
    
    # 端口映射
    ports:
      - "8008:8008"
    
    # 环境变量
    environment:
      - KEV_MODEL=jaredpalmer/kev-4b
      - KEV_PREFIX_CACHE=4
      - KEV_DTYPE=bf16
      - CUDA_VISIBLE_DEVICES=0
      - MAX_BATCH=64
      - KEV_CUDA_GRAPHS=1
    
    # 卷挂载（持久化模型权重）
    volumes:
      - kev-model-cache:/kev/checkpoints
    
    # 健康检查
    healthcheck:
      test: ["CMD", "/usr/local/bin/health-check.sh"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s
    
    # 重启策略
    restart: unless-stopped
    
    # 日志配置
    logging:
      driver: json-file
      options:
        max-size: 100m
        max-file: "3"

volumes:
  kev-model-cache:
```

### 3.2 开发环境配置

```bash
# 启动开发模式（源码热重载）
docker-compose --profile development up -d

# 停止开发模式
docker-compose --profile development down
```

---

## 4. 镜像构建与依赖

### 4.1 核心依赖

```toml
[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"

[project]
name = "kev"
version = "0.1.0"
requires-python = ">=3.12,<3.14"
dependencies = [
    "accelerate>=1.15.0",
    "datasets>=3.0",
    "numpy>=2.5.3",
    "peft>=0.21",
    "pydantic>=2.9",
    "scikit-learn>=1.9.1",
    "torch>=2.6,<2.9",
    "transformers>=5.17,<6",
]

[project.optional-dependencies]
serve = [
    "fastapi>=0.115",
    "typesafe-sdk>=0.6.0",
    "uvicorn>=0.30",
]
```

### 4.2 系统级依赖

- **Python**: 3.13 (slim bookworm)
- **CUDA**: 12.1+（推荐）或 11.8
- **cuDNN**: 8.x
- **GPU Drivers**: NVIDIA Driver 535+

### 4.3 构建步骤

```bash
# 方式 1：直接构建（推荐）
docker-compose build --no-cache

# 方式 2：手动构建
docker build -t kev-decision-model:latest .

# 验证 GPU 可用性
docker run --rm --gpus all kev-decision-model nvidia-smi
```

### 4.4 优化构建速度

```dockerfile
# 使用国内镜像源加速下载
RUN echo 'deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm main contrib non-free non-free-firmware' > /etc/apt/sources.list

# 缓存 HuggingFace 模型
RUN huggingface-cli download --do-not-download jaredpalmer/kev-4b 2>/dev/null || true
```

---

## 5. 容器启动参数

### 5.1 GPU 直通配置

#### 基本配置
```bash
# 指定单个 GPU
CUDA_VISIBLE_DEVICES=0

# 指定多个 GPU
CUDA_VISIBLE_DEVICES=0,1

# 自动选择所有可用 GPU
CUDA_VISIBLE_DEVICES=""  # 或省略此变量
```

#### 资源限制建议

| 场景 | 内存限制 | GPU 数量 | 适用模型 |
|------|---------|---------|---------|
| 单卡低配 | 8G | 1 | Kev-0.8B (L4) |
| 单卡标准 | 16G | 1 | Kev-4B (L40S) |
| 单卡高配 | 32G | 1 | Kev-9B (H100) |
| 多卡推理 | 64G+ | 2+ | Kev-27B 分片 |

### 5.2 性能优化参数

```yaml
environment:
  # 精度优化（按速度排序）
  - KEV_DTYPE=bf16        # 推荐：速度快且精度高
  - KEV_DTYPE=fp16        # 显存节省 30%
  - KEV_DTYPE=fp32        # 精确但慢
  
  # CUDA Graphs 优化
  - KEV_CUDA_GRAPHS=1     # 减少内核启动开销
  
  # 融合算子优化
  - KEV_FUSED=1           # Qwen3.5 专用融合内核
  
  # 批处理优化
  - MAX_BATCH=64          # 并发请求数
  
  # 前缀缓存优化
  - KEV_PREFIX_CACHE=4    # 缓存状态数（减少重复文本计算）
```

### 5.3 完整启动命令示例

```bash
# 生产环境标准启动
docker run -d \
  --name kev-server \
  --runtime nvidia \
  --gpus all \
  -p 8008:8008 \
  -e KEV_MODEL=jaredpalmer/kev-4b \
  -e KEV_DTYPE=bf16 \
  -e MAX_BATCH=64 \
  -v kev-model-cache:/kev/checkpoints \
  -m 16g \
  kev-decision-model:latest

# 带 API 密钥的安全启动
docker run -d \
  --name kev-server-auth \
  --gpus all \
  -e KEV_API_KEY=your-secret-key-here \
  kev-decision-model:latest
```

---

## 6. API 服务访问

### 6.1 本地测试

```bash
# 1. 检查服务状态
curl http://localhost:8008/v1/models | jq

# 2. 发送决策请求
curl -X POST http://localhost:8008/v1/systemone \
  -H "Content-Type: application/json" \
  -d '{
    "state": "鞋子晚到了两周而且尺码不对。另外我的信用卡被 charged 了两次。",
    "model": "kev-latest",
    "questions": {
      "department": {
        "type": "choice",
        "instructions": "Which team should handle this ticket?",
        "criteria": {
          "returns": "Exchanges, refunds, wrong or damaged items",
          "shipping": "Delivery status, delays, lost packages",
          "billing": "Charges, invoices, payment problems"
        }
      },
      "escalate": {
        "type": "noul",
        "instructions": "Does this need urgent human attention?",
        "criteria": {"true": null, "false": null}
      },
      "frustration": {
        "type": "score",
        "instructions": "How frustrated is the customer?",
        "criteria": ["Calm", "Frustrated", "Very angry"]
      }
    }
  }' | jq
```

### 6.2 生产环境 URL

```
基础 URL:     http://your-server-ip:8008
模型信息：   GET /v1/models
决策接口：    POST /v1/systemone
选项排列：    POST /v1/systemone/permute
分开提问：    POST /v1/systemone/separate
```

### 6.3 Python SDK 集成

```python
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

# 初始化客户端
client = TypeSafeClient(
    api_key="local",  # 如果启用了 KEV_API_KEY 则使用对应 key
    base_url="http://127.0.0.1:8008",
    model="kev-latest",
)

# 发送请求
response = client.system_one(
    state="我收到了错误的商品且被 charges 了两次",
    questions={
        "team": Choice(
            instructions="哪个团队负责？",
            criteria={"billing": "支付问题", "support": "技术支持"}
        ),
        "urgent": Noul(
            instructions="是否需要紧急处理？",
            criteria={"yes": True, "no": False}
        )
    }
)

# 访问结果
print(f"团队选择：{response.choices['team'].choice}")
print(f"紧急程度：{response.nouls['urgent'].noul}")
print(f"置信度：{response.choices['team'].confidence:.2%}")
```

### 6.4 TypeScript 集成

```typescript
import { TypeSafeClient, Choice, Noul, Score } from 'typesafe-sdk';

const client = new TypeSafeClient({
  baseUrl: 'http://localhost:8008',
  apiKey: 'local',
  model: 'kev-latest'
});

async function makeDecision() {
  const response = await client.systemOne({
    state: '订单延误且商品错误',
    questions: {
      department: new Choice({
        instructions: '应该由哪个团队处理？',
        criteria: {
          shipping: { description: '物流问题' },
          billing: { description: '支付问题' },
          returns: { description: '退换货' }
        }
      }),
      escalations: new Noul({
        instructions: '需要升级吗？',
        criteria: {
          yes: true,
          no: false
        }
      })
    }
  });

  console.log('Department:', response.choices.department.choice);
  console.log('Confidence:', response.choices.department.confidence);
}

makeDecision();
```

---

## 7. 健康检查与监控

### 7.1 Docker 内置健康检查

已在 `docker-compose.yml` 中配置：

```yaml
healthcheck:
  test: ["CMD", "/usr/local/bin/health-check.sh"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 120s
```

### 7.2 检查容器健康状态

```bash
# 查看容器状态
docker inspect kev-server --format '{{.State.Health.Status}}'

# 查看详细健康日志
docker inspect kev-server --format '{{json .State.Health.Log}}' | jq

# 手动触发生命周期检查
docker exec kev-server /usr/local/bin/health-check.sh
```

### 7.3 Prometheus 监控指标

```yaml
# prometheus.yml 配置示例
scrape_configs:
  - job_name: 'kev-server'
    static_configs:
      - targets: ['kev-server:8008']
    metrics_path: '/metrics'
    scrape_interval: 15s

# 暴露端点（需要在 serve.py 中添加）
@app.get("/metrics")
async def metrics():
    return Response(
        content=str(prometheus_metrics.get_metrics()),
        media_type='text/plain'
    )
```

### 7.4 Grafana 仪表板模板

```json
{
  "dashboard": {
    "title": "Kev-4B Serving Performance",
    "panels": [
      {
        "title": "Request Latency (ms)",
        "targets": [{
          "expr": "histogram_quantile(0.95, rate(kev_request_latency_bucket[5m]))"
        }]
      },
      {
        "title": "Prefix Cache Hit Rate",
        "targets": [{
          "expr": "rate(kev_prefix_cache_hits[5m]) / (rate(kev_prefix_cache_hits[5m]) + rate(kev_prefix_cache_misses[5m]))"
        }]
      },
      {
        "title": "Requests per Second",
        "targets": [{
          "expr": "rate(kev_batches_total[1m])"
        }]
      }
    ]
  }
}
```

---

## 8. 生产环境最佳实践

### 8.1 反向代理配置（Nginx）

```nginx
upstream kev_backend {
    server kev-server:8008;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name api.your-domain.com;

    # SSL 证书配置
    ssl_certificate /etc/nginx/ssl/server.crt;
    ssl_certificate_key /etc/nginx/ssl/server.key;

    # 客户端认证（如果启用 KEV_API_KEY）
    if ($http_authorization = "") {
        return 401 "Authorization required";
    }

    location / {
        proxy_pass http://kev_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        
        # 超时设置（AI 推理可能需要较长时间）
        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
        
        # WebSocket 支持（如需 SSE）
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection upgrade;
        
        # 限流
        limit_req zone=kev_limit burst=20 nodelay;
    }
}

# 限流配置
limit_req_zone $binary_remote_addr zone=kev_limit:10m rate=100r/s;
```

### 8.2 Kubernetes 部署

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kev-server
spec:
  replicas: 2
  selector:
    matchLabels:
      app: kev-server
  template:
    metadata:
      labels:
        app: kev-server
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                - key: nvidia.com/gpu.present
                  operator: In
                  values:
                    - "true"
      
      containers:
        - name: kev
          image: kev-decision-model:latest
          ports:
            - containerPort: 8008
          env:
            - name: KEV_MODEL
              value: "jaredpalmer/kev-4b"
            - name: KEV_DTYPE
              value: "bf16"
          resources:
            requests:
              memory: "8Gi"
              cpu: "2000m"
              nvidia.com/gpu: "1"
            limits:
              memory: "16Gi"
              nvidia.com/gpu: "1"
          livenessProbe:
            httpGet:
              path: /v1/models
              port: 8008
            initialDelaySeconds: 120
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /v1/models
              port: 8008
            initialDelaySeconds: 30
            periodSeconds: 10
      
      volumes:
        - name: model-cache
          persistentVolumeClaim:
            claimName: kev-model-pvc
```

### 8.3 自动扩缩容配置（KEDA）

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: kev-server-scaler
spec:
  scaleTargetRef:
    name: kev-server
  minReplicaCount: 1
  maxReplicaCount: 5
  triggers:
    - type: http
      metadata:
        endpoint: http://kev-server:8008/v1/models
        averageValue: '5'  # 平均活跃请求数
```

### 8.4 安全加固

```bash
# 1. 启用 API 密钥认证
KEV_API_KEY=$(openssl rand -hex 32)
docker run -e KEV_API_KEY=$KEV_API_KEY ...

# 2. 只暴露必要端口
docker run -p 127.0.0.1:8008:8008 ...  # 仅限 localhost

# 3. 禁用不必要的功能
ENV KEV_DATE_FACTS=0 \
    KEV_TRUNCATE_STATES=0

# 4. 定期更新镜像
docker pull kev-decision-model:latest
docker-compose pull
```

---

## 9. 故障排查

### 9.1 OOM（Out of Memory）问题

**症状**：容器被 Kill 或报错 "CUDA out of memory"

**解决方案**：

```bash
# 方案 1：降低精度
KEV_DTYPE=fp16

# 方案 2：减小批处理
MAX_BATCH=32

# 方案 3：减少缓存大小
KEV_PREFIX_CACHE=2

# 方案 4：增加系统内存
deploy:
  resources:
    limits:
      memory: 32G
```

### 9.2 模型加载缓慢

**症状**：启动后超过 60 秒仍未响应

**解决方案**：

```bash
# 延长健康检查等待时间
healthcheck:
  start_period: 180s  # 原为 120s

# 预下载模型并挂载
docker volume create kev-model-cache
huggingface-cli download jaredpalmer/kev-4b --local-dir ./downloads
docker run -v $(pwd)/downloads:/kev/checkpoints ...
```

### 9.3 GPU 未被识别

**症状**：容器内无法运行 `nvidia-smi`

**检查清单**：

```bash
# 宿主机验证
nvidia-smi
docker info | grep -i runtime

# 容器内验证
docker run --rm --gpus all nvcr.io/nvidia/cuda:12.1-base nvidia-smi

# 检查驱动版本
cat /proc/driver/nvidia/version

# 重启 Docker
sudo systemctl restart docker
```

### 9.4 API 返回 422 错误

**症状**：超长状态被拒绝

**原因**：默认拒绝超过 65,536 tokens 的状态

**解决**：

```bash
# 允许截断（不推荐生产环境）
KEV_TRUNCATE_STATES=1

# 或在客户端缩短输入
state: truncate_long_text(state, max_tokens=32768)
```

### 9.5 并发性能不足

**症状**：QPS 低，延迟高

**优化方案**：

```bash
# 1. 启用 CUDA Graphs
KEV_CUDA_GRAPHS=1

# 2. 增大批处理
MAX_BATCH=128

# 3. 启用融合算子（需安装 flash-linear-attention）
KEV_FUSED=1

# 4. 调整 worker 线程数
uvicorn --workers 4 ...
```

### 9.6 常见错误码对照表

| HTTP 码 | 含义 | 解决方案 |
|---------|------|----------|
| 401 | 缺少或无效 API Key | 检查 Authorization header |
| 422 | 状态过长或格式错误 | 检查 token 数，调整输入 |
| 503 | 服务停止中 | 等待容器完全启动 |
| 500 | 内部错误 | 查看容器日志 `docker logs` |

---

## 附录 A：环境变量速查表

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `KEV_MODEL` | `jaredpalmer/kev-4b` | 模型路径或 ID |
| `KEV_DTYPE` | `bf16` | 计算精度 |
| `KEV_PREFIX_CACHE` | `4` | 前缀缓存数量 |
| `KEV_API_KEY` | 空 | API 密钥（启用认证） |
| `CUDA_VISIBLE_DEVICES` | `0` | GPU 设备可见性 |
| `MAX_BATCH` | `64` | 最大批处理大小 |
| `KEV_CUDA_GRAPHS` | `1` | 是否启用 CUDA Graphs |
| `KEV_FUSED` | `1` | 是否启用融合算子 |
| `KEV_DATE_FACTS` | `0` | 是否添加日期事实预处理 |
| `KEV_TRUNCATE_STATES` | `0` | 是否截断超长状态 |

---

## 附录 B：性能基准参考

基于官方文档的测试数据：

| GPU | 模型 | 6 个问题（短文本） | 并发 64 客户端 |
|-----|------|-----------------|------------|
| L40S | Kev-4B | 41.5 / 27.7 ms | 51.4 req/s |
| H100 | Kev-4B | 18.1 / 12.9 ms | 100.8 req/s |

*注：第一次询问 vs 相同内容缓存命中*

---

**版本历史**：
- v1.0 (2026-10-01): 初始版本，完整 Docker 部署方案

**作者**: Kev Team  
**License**: Apache-2.0
