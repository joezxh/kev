# Kev-4B 本地部署完整指南

本文档提供在 Windows 系统上部署 Kev-4B 决策模型的三种方案：

1. **WSL2 + Docker**（推荐）✅ 
2. **纯 Python 环境**（轻量）
3. **Docker Desktop 原生**（完整）

---

## 🚀 方案一：WSL2 + Docker（推荐）

### 前置条件检查

```bash
# 1. 检查 WSL2
wsl --list --verbose

# 2. 检查 Docker Desktop
docker --version
docker compose version

# 3. 检查 NVIDIA 驱动（如有 GPU）
nvidia-smi
```

### 部署步骤

#### 步骤 1: 运行部署脚本

在 **PowerShell** 或 **CMD** 中执行：

```powershell
# 进入项目目录
cd d:\projects\github\kev

# 使用 WSL 执行部署脚本
wsl bash deploy-wsl2.sh
```

脚本将自动：
- ✅ 创建项目目录 `~/kev-deploy`
- ✅ 克隆 kev 仓库
- ✅ 生成环境变量配置文件
- ✅ 创建 Docker Compose 配置
- ✅ 准备数据持久化卷

#### 步骤 2: 启动服务

```bash
# 进入部署目录（在 WSL 中）
cd ~/kev-deploy

# 构建并启动容器
docker compose up -d --build

# 查看日志
docker compose logs -f kev-server
```

**预期输出**：
```
✓ 服务已就绪
正在加载模型：jaredpalmer/kev-4b...
🌐 API 地址：http://localhost:8008
```

#### 步骤 3: 测试 API

##### 方式 A: 使用 Python 测试脚本（推荐）

```bash
# 在 WSL 中安装依赖
pip install httpx

# 运行测试
python scripts/test-api.py
```

##### 方式 B: 使用 curl

```bash
# 1. 健康检查
curl http://localhost:8008/v1/models | jq

# 2. 发送决策请求
curl -X POST http://localhost:8008/v1/systemone \
  -H "Content-Type: application/json" \
  -d '{
    "state": "鞋子晚到了两周而且尺码不对",
    "model": "kev-latest",
    "questions": {
      "team": {
        "type": "choice",
        "instructions": "哪个团队负责？",
        "criteria": {
          "returns": "退换货问题",
          "shipping": "物流问题",
          "billing": "支付问题"
        }
      }
    }
  }' | jq
```

---

## 💻 方案二：纯 Python 环境（轻量）

### 适用场景
- 没有 Docker 环境
- 快速验证或开发测试
- CPU 推理（较慢）

### 部署步骤

#### 步骤 1: 安装依赖

```powershell
# PowerShell
cd d:\projects\github\kev

# 使用 uv（推荐）或者 pip
uv sync --extra serve
# 或
pip install fastapi uvicorn typesafe-sdk torch transformers peft accelerate datasets pydantic scikit-learn
```

#### 步骤 2: 下载模型

```powershell
# 方法 1: 使用 HuggingFace CLI
huggingface-cli download jaredpalmer/kev-4b --local-dir .\models\kev-4b

# 方法 2: 在代码中自动下载
$env:KEV_MODEL="jaredpalmer/kev-4b"
```

#### 步骤 3: 启动服务

```powershell
# 直接运行 Python 模块
python -m kev.serve --host 0.0.0.0 --port 8008
```

或者使用 uvicorn：

```powershell
uvicorn kev.serve:app --host 0.0.0.0 --port 8008 --workers 1
```

#### 步骤 4: 测试 API

```powershell
# PowerShell
Invoke-RestMethod -Uri "http://localhost:8008/v1/models" -Method GET | ConvertTo-Json
```

或者使用 Python 测试脚本：

```powershell
python scripts\test-api.py
```

---

## 🐳 方案三：Docker Desktop 原生（Windows）

### 前置条件
- Docker Desktop for Windows 启用
- WSL2 后端开启
- NVIDIA Container Toolkit（GPU 支持）

### 部署步骤

#### 步骤 1: 准备部署目录

```powershell
# 创建部署目录
New-Item -ItemType Directory -Path "C:\kev-deploy" -Force
Set-Location "C:\kev-deploy"

# 复制必要的配置文件
Copy-Item "d:\projects\github\kev\Dockerfile" -Destination "C:\kev-deploy\"
Copy-Item "d:\projects\github\kev\docker-compose.yml" -Destination "C:\kev-deploy\"
```

#### 步骤 2: 修改 docker-compose.yml

编辑 `docker-compose.yml`，移除或注释掉 GPU 相关配置（如果无 GPU）：

```yaml
services:
  kev-server:
    # 注释掉 GPU 配置
    # runtime: nvidia
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: 1
    #           capabilities: [gpu]
    
    environment:
      - KEV_DTYPE=fp32  # CPU 模式使用 fp32
```

#### 步骤 3: 构建并启动

```powershell
cd C:\kev-deploy

# 构建镜像
docker compose build

# 启动服务
docker compose up -d

# 查看日志
docker compose logs -f kev-server
```

#### 步骤 4: 测试 API

```powershell
# 健康检查
curl.exe http://localhost:8008/v1/models

# 或 PowerShell
Invoke-RestMethod -Uri "http://localhost:8008/v1/models"
```

---

## 🔧 故障排查

### 问题 1: OOM（内存不足）

**症状**: 容器被 Kill 或报错 "CUDA out of memory"

**解决方案**:

```yaml
# 降低精度
KEV_DTYPE=fp16

# 减小批处理
MAX_BATCH=32

# 减少缓存大小
KEV_PREFIX_CACHE=2
```

### 问题 2: 模型加载缓慢

**症状**: 启动后超过 2 分钟未响应

**解决方案**:

```bash
# 延长健康检查等待
docker compose logs -f --tail 100 kev-server

# 预下载模型
huggingface-cli download jaredpalmer/kev-4b --local-dir .\downloads
docker run -v .\downloads:/kev/checkpoints ...
```

### 问题 3: GPU 未被识别

**症状**: 容器内无法运行 `nvidia-smi`

**解决方案**:

```powershell
# 检查 Docker GPU 支持
docker info | grep -i runtime

# 重启 Docker Desktop
# 确保已启用 WSL2 后端和 GPU 加速
```

### 问题 4: 端口已被占用

**症状**: `Address already in use`

**解决方案**:

```bash
# Windows 查看占用端口的进程
netstat -ano | findstr :8008

# 修改端口
docker compose up -p 8009:8008
```

---

## 📊 性能基准参考

| GPU | 模型 | 6 个问题（短文本） | 并发 64 客户端 |
|-----|------|-----------------|------------|
| L40S | Kev-4B | 41.5 / 27.7 ms | 51.4 req/s |
| H100 | Kev-4B | 18.1 / 12.9 ms | 100.8 req/s |
| CPU  | Kev-4B | ~500 ms         | ~5 req/s   |

*注：第一次询问 vs 相同内容缓存命中*

---

## 🎯 下一步操作

### 1. API 集成

```python
from typesafe_sdk import TypeSafeClient, Choice, Noul

client = TypeSafeClient(
    base_url="http://localhost:8008",
    model="kev-latest"
)

response = client.system_one(
    state="订单延误且商品错误",
    questions={
        "team": Choice(...),
        "urgent": Noul(...)
    }
)
```

### 2. 反向代理配置

参考 [`DOCKER_DEPLOYMENT_GUIDE.md`](./DOCKER_DEPLOYMENT_GUIDE.md#81-反向代理配置nginx) 配置 Nginx。

### 3. Kubernetes 部署

参考 [`DOCKER_DEPLOYMENT_GUIDE.md`](./DOCKER_DEPLOYMENT_GUIDE.md#82-kubernetes-部署) 配置 K8s 生产环境。

---

## 📝 总结

**推荐使用流程**：

1. ✅ **首次部署**: 使用 `deploy-wsl2.sh` 脚本一键初始化
2. ✅ **启动服务**: `docker compose up -d --build`
3. ✅ **验证功能**: `python scripts/test-api.py`
4. ✅ **日常运维**: 查看日志、监控健康状态

**常见问题解决顺序**：

1. 检查 Docker 是否正常运行
2. 查看容器日志：`docker compose logs -f`
3. 验证 GPU 驱动（如有）
4. 调整资源限制参数

---

**维护者**: Kev Team  
**最后更新**: 2026-10-02  
**License**: Apache-2.0
