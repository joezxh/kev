# Kev-4B Docker 部署完整方案 - 使用指南

## ✅ 已生成的文件清单

```
d:\projects\github\kev\
├── Dockerfile                              # 多阶段构建配置文件 ✨
├── docker-compose.yml                      # 生产/开发环境编排配置 ✨
├── .dockerignore                           # Docker 构建忽略规则 ✨
├── DEPLOYMENT_README.md                    # 用户级快速参考指南 ✨
├── DOCKER_DEPLOYMENT_GUIDE.md              # **完整技术文档**（超详细）⭐
├── deploy.sh                               # Linux/Mac一键部署脚本 ✨
├── deploy-windows.ps1                      # Windows PowerShell部署脚本 ✨
└── scripts/
    ├── docker-entrypoint.sh                # 容器入口点脚本（GPU 验证）✨
    └── health-check.sh                     # Docker 健康检查脚本 ✨
```

## 🎯 立即开始

### 方式 1：一键自动部署（推荐）

**Linux/Mac:**
```bash
cd d:\projects\github\kev
chmod +x deploy.sh
./deploy.sh deploy
```

**Windows (PowerShell):**
```powershell
cd d:\projects\github\kev
.\deploy-windows.ps1
```

### 方式 2：手动逐步执行

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

# 3. 验证服务
curl http://localhost:8008/v1/models | jq
```

## 📚 必读文档

### 优先级 1：`DOCKER_DEPLOYMENT_GUIDE.md` ⭐⭐⭐
这是你需要的**完整技术文档**，包含：
- ✅ 详细的 Dockerfile 解析
- ✅ GPU 直通配置详解
- ✅ API 访问方式和 Python/TypeScript 示例代码
- ✅ 环境变量完整列表和说明
- ✅ 生产环境最佳实践（Nginx/Kubernetes）
- ✅ 故障排查手册（OOM/慢加载/并发问题）

### 优先级 2：`DEPLOYMENT_README.md` ⭐⭐
简洁的快速参考指南：
- ✅ 常用命令速查
- ✅ 核心参数表
- ✅ 性能基准数据
- ✅ 安全加固建议

## 🔑 核心配置参数

| 参数 | 默认值 | 作用 | 调整场景 |
|------|--------|------|----------|
| `KEV_DTYPE` | `bf16` | 计算精度 | 显存不足→`fp16` |
| `MAX_BATCH` | `64` | 并发批处理 | QPS 低→增大到 128 |
| `KEV_PREFIX_CACHE` | `4` | 状态缓存数 | OOM→减小到 2 |
| `CUDA_VISIBLE_DEVICES` | `0` | GPU 选择 | 多卡推理→`"0,1"` |

📖 完整参数表请查阅 [DOCKER_DEPLOYMENT_GUIDE.md](DOCKER_DEPLOYMENT_GUIDE.md)

## 🌐 API 使用示例

### Curl 测试
```bash
curl -X POST http://localhost:8008/v1/systemone \
  -H "Content-Type: application/json" \
  -d '{
    "state": "订单延误且商品错误",
    "model": "kev-latest",
    "questions": {
      "department": {"type": "choice", 
          "instructions": "哪个团队？",
          "criteria": {"billing": null, "support": null}},
      "urgent": {"type": "noul",
          "instructions": "需要升级？",
          "criteria": {"true": null, "false": null}}
    }
  }'
```

### Python SDK
```python
from typesafe_sdk import TypeSafeClient, Choice, Noul

client = TypeSafeClient(
    api_key="local",
    base_url="http://localhost:8008",
    model="kev-latest"
)

response = client.system_one(
    state="客户投诉物流延误",
    questions={
        "team": Choice(
            instructions="处理团队",
            criteria={"logistics": "物流部", "returns": "退货部"}
        ),
        "escalations": Noul(
            instructions="需要紧急处理？",
            criteria={"yes": True, "no": False}
        )
    }
)

print(f"团队：{response.choices['team'].choice}")
print(f"置信度：{response.choices['team'].confidence:.2%}")
```

## 🚨 常见问题解决

### 1️⃣ OOM (显存不足)
**症状**: 容器被 Kill，错误 "CUDA out of memory"

**解决方案**：
```bash
-e KEV_DTYPE=fp16 \          # 降低精度节省 30% 显存
-e MAX_BATCH=32 \             # 减少批处理大小
-e KEV_PREFIX_CACHE=2         # 减小前缀缓存
```

### 2️⃣ 服务启动慢
**症状**: 超过 60 秒未响应

**原因**: 首次下载模型权重 (~8GB)

**优化方案**：
```bash
# 方式 1：预下载并挂载
huggingface-cli download jaredpalmer/kev-4b --local-dir ./downloads
docker run -v $(pwd)/downloads:/kev/checkpoints ...

# 方式 2：延长健康检查等待时间
healthcheck:
  start_period: 180s
```

### 3️⃣ GPU 未被识别
**症状**: 容器内 `nvidia-smi` 失败

**检查步骤**：
```bash
# 宿主机验证
nvidia-smi
docker info | grep -i runtime

# 容器内验证
docker run --rm --gpus all nvidia/cuda:12.1-base nvidia-smi

# 安装 NVIDIA Container Toolkit
curl -s -L https://nvidia.github.io/libnvidia-container/gpgkey | sudo apt-key add -
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
```

### 4️⃣ 并发性能不足
**症状**: QPS 低，延迟高

**优化方案**：
```bash
# 启用 CUDA Graphs（减少内核启动开销）
-e KEV_CUDA_GRAPHS=1

# 增大批处理
-e MAX_BATCH=128

# 启用融合算子（需安装 flash-linear-attention）
-e KEV_FUSED=1
```

## 📊 硬件需求参考

### Kev-4B 最低要求
- **GPU**: NVIDIA L4 (8GB VRAM)
- **内存**: 16GB RAM
- **存储**: 20GB 可用空间（含模型权重）
- **精度**: bf16/fp16

### Kev-4B 推荐配置
- **GPU**: H100/L40S (24GB+ VRAM)
- **内存**: 32GB RAM
- **吞吐量**: ~50-100 req/s

### Kev-9B/27B 扩展
- **Kev-9B**: L40S/H100 (≥17GB VRAM)
- **Kev-27B**: H200/B200 (≥66GB VRAM)

## 🔄 日常维护

### 查看状态
```bash
docker ps -a | grep kev
docker inspect kev-server --format '{{.State.Health.Status}}'
docker stats kev-server --no-stream
```

### 日志管理
```bash
# 实时查看
docker logs -f kev-server

# 导出日志
docker logs kev-server > kev-$(date +%Y%m%d).log
```

### 备份模型
```bash
# 创建快照
docker run --volumes-from kev-server -v $(pwd):/backup alpine cp -r /kev/checkpoints /backup/

# 恢复模型
docker run -v $(pwd)/backup:/kev/checkpoints ...
```

## 💡 高级用法

### 多 GPU 分布式推理
```yaml
# docker-compose.yml
environment:
  - CUDA_VISIBLE_DEVICES=0,1
  # 需要在 serve.py 中配置 Multi-GPU 支持
```

### Kubernetes 部署
详见 [DOCKER_DEPLOYMENT_GUIDE.md](DOCKER_DEPLOYMENT_GUIDE.md) → 第 8 章

### Prometheus 监控集成
```python
@app.get("/metrics")
async def metrics():
    return Response(
        content=str(prometheus_metrics.get_metrics()),
        media_type='text/plain'
    )
```

## 📞 获取帮助

- 📖 **完整文档**: [DOCKER_DEPLOYMENT_GUIDE.md](DOCKER_DEPLOYMENT_GUIDE.md)
- 🐛 **Bug 报告**: https://github.com/jaredpalmer/kev/issues
- 💬 **社区支持**: Kev GitHub Discussions

---

## 下一步操作

1. ✅ **运行一键部署**: `./deploy.sh deploy`
2. 📖 **阅读完整文档**: 打开 `DOCKER_DEPLOYMENT_GUIDE.md`
3. 🧪 **测试 API**: 参考本文档中的 Curl/Python 示例
4. 🔧 **调优参数**: 根据实际性能调整环境变量
5. 📊 **建立监控**: 配置健康检查和日志收集

**祝您部署顺利！🚀**
