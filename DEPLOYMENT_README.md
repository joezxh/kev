# Kev-4B Docker 部署包

本目录提供完整的 Kev-4B 决策模型 Docker 部署方案。

## 🚀 快速开始

### Linux/Mac 一键部署

```bash
# 赋予执行权限
chmod +x deploy.sh

# 一键部署（构建 + 启动 + 测试）
./deploy.sh deploy

# 查看状态
./deploy.sh status

# 停止服务
./deploy.sh stop
```

### Windows 部署

#### PowerShell 方式
```powershell
# 以管理员身份运行 PowerShell
.\deploy-windows.ps1
```

#### Git Bash 方式
```bash
git bash deploy.sh deploy
```

## 📦 部署内容

| 文件 | 说明 |
|------|------|
| `Dockerfile` | 多阶段构建配置，优化镜像大小和性能 |
| `docker-compose.yml` | 生产/开发环境编排配置 |
| `scripts/docker-entrypoint.sh` | 容器入口点脚本（GPU 验证、优雅关闭） |
| `scripts/health-check.sh` | Docker 健康检查脚本 |
| `.dockerignore` | 忽略不必要的文件，加速构建 |
| `deploy.sh` | Linux/Mac 自动部署脚本 |
| `deploy-windows.ps1` | Windows PowerShell 部署脚本 |
| `DOCKER_DEPLOYMENT_GUIDE.md` | **完整部署文档**（重要！） |

## 📖 详细文档

请阅读 **[DOCKER_DEPLOYMENT_GUIDE.md](DOCKER_DEPLOYMENT_GUIDE.md)** 获取：

- ✅ Dockerfile 深度解析
- ✅ GPU 直通配置详解
- ✅ API 访问方式和示例代码
- ✅ 环境变量完整列表
- ✅ 生产环境最佳实践
- ✅ 故障排查指南

## 🔧 常用操作

### 手动构建和启动

```bash
# 1. 构建镜像
docker build -t kev-decision-model:latest .

# 2. 启动容器
docker run -d \
  --name kev-server \
  --gpus all \
  -p 8008:8008 \
  -e KEV_MODEL=jaredpalmer/kev-4b \
  -e KEV_DTYPE=bf16 \
  -v kev-model-cache:/kev/checkpoints \
  kev-decision-model:latest

# 3. 验证 API
curl http://localhost:8008/v1/models
```

### 使用 docker-compose

```bash
# 生产模式
docker-compose up -d --build

# 开发模式（源码热重载）
docker-compose --profile development up -d

# 查看所有日志
docker-compose logs -f
```

## 🌐 API 使用示例

### 基础请求

```bash
curl -X POST http://localhost:8008/v1/systemone \
  -H "Content-Type: application/json" \
  -d '{
    "state": "订单延误且商品错误",
    "model": "kev-latest",
    "questions": {
      "department": {"type": "choice", "instructions": "Which team?", 
                     "criteria": {"billing": null, "support": null}},
      "urgent": {"type": "noul", "instructions": "Is it urgent?", 
                 "criteria": {"true": null, "false": null}}
    }
  }' | jq
```

### Python SDK

```python
from typesafe_sdk import Choice, Noul, TypeSafeClient

client = TypeSafeClient(
    api_key="local",
    base_url="http://127.0.0.1:8008",
    model="kev-latest"
)

response = client.system_one(
    state="客户收到错误商品",
    questions={
        "team": Choice(
            instructions="哪个团队负责？",
            criteria={"billing": "支付问题", "logistics": "物流问题"}
        )
    }
)

print(f"选择：{response.choices['team'].choice}")
print(f"置信度：{response.choices['team'].confidence:.2%}")
```

## ⚙️ 核心环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `KEV_MODEL` | `jaredpalmer/kev-4b` | 模型路径 |
| `KEV_DTYPE` | `bf16` | 精度 (`bf16`/`fp16`/`fp32`) |
| `MAX_BATCH` | `64` | 批处理大小 |
| `KEV_PREFIX_CACHE` | `4` | 前缀缓存数量 |
| `CUDA_VISIBLE_DEVICES` | `0` | GPU 设备可见性 |
| `KEV_API_KEY` | (空) | API 密钥（启用认证） |

📖 完整参数表见 [DOCKER_DEPLOYMENT_GUIDE.md](DOCKER_DEPLOYMENT_GUIDE.md)

## 🎯 性能基准

基于官方测试数据：

| GPU | Kev-4B 延迟 (短文本) | 并发吞吐量 |
|-----|-------------------|-----------|
| H100 | 18.1 ms | 100.8 req/s |
| L40S | 41.5 ms | 51.4 req/s |
| L4 | ~120 ms | ~20 req/s |

## 🔍 故障排查

### OOM (显存不足)

```bash
# 降低精度
-e KEV_DTYPE=fp16

# 减小批处理
-e MAX_BATCH=32

# 减少缓存
-e KEV_PREFIX_CACHE=2
```

### 服务无法启动

```bash
# 查看详细日志
docker logs kev-server

# 检查 GPU 挂载
docker exec kev-server nvidia-smi

# 验证端口占用
netstat -tlnp | grep 8008
```

### 模型加载慢

首次启动可能需要 60-120 秒（下载模型权重），可通过挂载本地缓存加速：

```bash
-v ~/huggingface/jaredpalmer/kev-4b:/kev/checkpoints
```

## 🛡️ 安全加固

```bash
# 启用 API 密钥认证
docker run -e KEV_API_KEY=$(openssl rand -hex 32) ...

# 仅暴露 localhost
docker run -p 127.0.0.1:8008:8008 ...

# 只读文件系统（高级）
--read-only --tmpfs /tmp --tmpfs /root/.cache
```

## 📊 监控指标

```bash
# 健康检查状态
docker inspect kev-server --format '{{.State.Health.Status}}'

# 实时资源使用
docker stats kev-server

# Prometheus 端点（需自行实现）
http://localhost:8008/metrics
```

## 🔄 更新维护

```bash
# 拉取最新镜像
docker pull kev-decision-model:latest

# 重启容器
docker restart kev-server

# 清理无用镜像
docker image prune -a
```

## 💡 更多支持

- 📖 **完整文档**: [DOCKER_DEPLOYMENT_GUIDE.md](DOCKER_DEPLOYMENT_GUIDE.md)
- 🐛 **Issue**: https://github.com/jaredpalmer/kev/issues
- 🌐 **HuggingFace**: https://huggingface.co/jaredpalmer/kev-4b

## 📜 License

Apache-2.0 (与 Kev 项目保持一致)

---

**Happy Deploying! 🚀**
