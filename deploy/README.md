# Kev-4B Docker 部署

用 Docker 部署 `kev.serve`（FastAPI 推理服务，端口 8008，TypeSafe 兼容的
`POST /v1/systemone` / `GET /v1/models`）。Windows Docker Desktop 与 Linux
共用同一套文件。

## 目录结构

```
deploy/
├── deploy-windows.ps1     # Windows 一键部署（PowerShell）
├── deploy-linux.sh        # Linux 一键部署（Bash）
├── docker-compose.yml     # 唯一的 compose 配置（两平台通用）
├── Dockerfile             # 从本地源码构建，安装 .[serve]
└── README.md              # 本文档
```

> 模型权重**不打进镜像**。`kev.serve --run` 接受本地 run 目录或 HuggingFace
> Hub ID（如 `jaredpalmer/kev-4b`，下载到 HF 缓存卷）。

## 快速开始

### Windows（Docker Desktop，WSL2 后端）

```powershell
cd d:\projects\github\kev
.\deploy\deploy-windows.ps1                                       # 默认本地模式：加载 ./deploy/runs/kev-4b-local
.\deploy\deploy-windows.ps1 -NoBuild                              # 跳过构建
.\deploy\deploy-windows.ps1 -Run kev-4b-local -ApiKey <key>       # 指定本地目录并启用 Bearer 认证
.\deploy\deploy-windows.ps1 -Hub jaredpalmer/kev-4b -ApiKey <key> # 回退到 Hub 模式
```

### Linux（Ubuntu/Debian）

```bash
cd /path/to/kev
chmod +x deploy/deploy-linux.sh
./deploy/deploy-linux.sh                                     # 默认本地模式：加载 ./deploy/runs/kev-4b-local
./deploy/deploy-linux.sh --no-build                          # 跳过构建
./deploy/deploy-linux.sh --run kev-4b-local --api-key <key>  # 指定本地目录并启用 Bearer 认证
./deploy/deploy-linux.sh --hub jaredpalmer/kev-4b --api-key <key>  # 回退到 Hub 模式
```

默认走**本地运行模式**：不传 `-Run`/`--run` 时脚本使用 `./deploy/runs/kev-4b-local`
（容器内 `/kev/runs/kev-4b-local`）。该目录需先放好 checkpoint，否则脚本会报错退出。
本地模式复用已缓存的基座（`kev-hf-cache` 卷里的 `Qwen/Qwen3.5-4B-Base`），无需联网下载。

如需临时从 Hub 下载，传 `-Hub <id>` / `--hub <id>`（如 `jaredpalmer/kev-4b`，
首次启动会下载到 `kev-hf-cache` 卷，需几分钟）。

### 手动 compose

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

## 本地 checkpoint 目录（deploy/runs/&lt;name&gt;）

本地运行模式（脚本默认）把 `KEV_RUN` 指向 `./deploy/runs/<name>`（容器内 `/kev/runs/<name>`）。
该目录只需放 **kev 的 LoRA 适配器快照**；基座 `Qwen/Qwen3.5-4B-Base` 由 `head.pt` 里的 `meta.base`
经 HF 缓存卷 `kev-hf-cache` 解析（`kev.checkpoint` 的逻辑），卷里已缓存，可离线。

### 目录结构

以 `deploy/runs/kev-4b-local/` 为例（LoRA 适配器布局，`kev.serve` 凭 `adapter_config.json` 识别为适配器）：

```
deploy/runs/kev-4b-local/
├── head.pt                    # 指针头 + 元数据（base / temperature / lora rank ...）
├── adapter_config.json        # peft LoRA 配置（存在它 = 适配器，而非完整权重）
├── adapter_model.safetensors  # LoRA 权重
├── tokenizer.json             # tokenizer 副本（始终随 checkpoint 提供）
├── tokenizer_config.json
├── special_tokens_map.json
├── vocab.json / merges.txt    # BPE 词表
├── added_tokens.json
├── config.json                # 可选：tokenizer / 发布元数据
├── training_config.json / provenance.json / result.json / training_metrics.json
└── （若适配器带训练得到的 token 嵌入，还会有对应权重）
```

> 若是 `kev.train --full_ft` 的完整权重 run，则没有 `adapter_*` 文件，改为 `config.json` +
> `model*.safetensors`（`kev.checkpoint` 据此判定 `weights="full"`，从目录本身加载基座）。

### 放置清单（checklist）

1. 在 `deploy/runs/` 下新建子目录，名称即 `<name>`（脚本默认 `kev-4b-local`）
2. 放入上述文件（**至少** `head.pt` + `adapter_config.json` + `adapter_model.safetensors`）
3. 确认基座可用：基座 `Qwen/Qwen3.5-4B-Base` 需已在 `kev-hf-cache` 卷缓存；
   换机器或要纯离线时设 `HF_HUB_OFFLINE=1`（见下方配置表）
4. 部署：`.\deploy\deploy-windows.ps1 -Run kev-4b-local -ApiKey <key>`

### 从 kev-hf-cache 卷导出（本仓库已执行）

当前 `deploy/runs/kev-4b-local` 即由运行中的 `kev-hf-cache` 卷里的 Hub 快照
`models--jaredpalmer--kev-4b` 实体化导出（软链展开为真实文件，约 152 MB）：

```bash
# 临时容器把卷内快照拷到 host 的 deploy/runs/<name>（cp -rL 展开软链为实体文件）
docker run --rm -v kev-hf-cache:/hf -v "$PWD/deploy/runs":/out busybox sh -c \
  "mkdir -p /out/<name> && cp -rL /hf/hub/models--<org>--<repo>/snapshots/*/. /out/<name>/"
```

> 不要直接复制 `models--*--*` 缓存目录本身（含 `blobs/refs/snapshots` 软链层级）；
> `kev.serve` 要的是 **快照内的扁平文件**，即 `snapshot_download` 返回的那一层。

## 前置条件

- Docker 20.10+ 与 Docker Compose v2（Windows 需启用 WSL2 后端）
- GPU（推荐）：NVIDIA Container Toolkit（Linux）或 Docker Desktop 自动直通；
  Kev-4B bf16 约需 10–12 GB 显存。无 GPU 时服务以 CPU 模式启动（慢）
- Linux GPU 安装 Toolkit：<https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html>

## 验证

```bash
docker ps                                   # kev-server 应为 healthy
curl http://localhost:8008/v1/models
python scripts/test-api.py                  # 在仓库根目录执行
# Swagger UI: http://localhost:8008/docs
```

## 常用命令

```bash
docker logs -f kev-server                                   # 日志
docker compose -f deploy/docker-compose.yml ps              # 状态
docker compose -f deploy/docker-compose.yml restart         # 重启
docker compose -f deploy/docker-compose.yml down            # 停止
docker compose -f deploy/docker-compose.yml up -d --build   # 重建并启动
```

## 配置（环境变量）

compose 里全部以 `${VAR:-默认值}` 形式透传，可在 shell 或 `.env` 中覆盖。
以下均为 `kev.serve` 实际读取的变量：

| 变量 | 默认 | 说明 |
|------|------|------|
| `KEV_RUN` | `/kev/runs/kev-4b-local` | checkpoint：本地目录 `/kev/runs/<name>`（`./runs` 已挂载，脚本默认）；或 Hub ID（可 `@<rev>` 固定版本，下载到 `kev-hf-cache` 卷） |
| `KEV_DTYPE` | `bf16` | 计算精度（`fp32` 为精确路径） |
| `KEV_PREFIX_CACHE` | `4` | 状态前缀缓存条数，`0` 关闭 |
| `KEV_API_KEY` | 空 | 设置后启用 Bearer 认证；空 = 开放服务 |
| `KEV_DATE_FACTS` | `0` | `1` 启用日期预处理 |
| `KEV_TRUNCATE_STATES` | `0` | `1` 截断超长状态（默认 422 拒绝） |
| `KEV_CUDA_GRAPHS` | 自动 | `0` 关闭 CUDA Graphs |
| `KEV_FUSED` | 自动 | `0` 关闭融合 Qwen3.5 内核（需 fla） |
| `KEV_BACKEND` | 自动 | `torch` 强制 PyTorch（Apple Silicon 默认 MLX，与容器无关） |
| `HF_HUB_OFFLINE` | `0` | `1` 只用已下载的缓存 |

注意：`MAX_BATCH` 是 `kev/serve.py` 中的硬编码常量（64），**不是**环境变量。

## 故障排查

| 症状 | 处理 |
|------|------|
| 容器 unhealthy / 启动失败 | `docker logs kev-server`；确认 8008 未被占用 |
| GPU 未生效（推理极慢） | `docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi`；Linux 检查 `nvidia-ctk cdi generate` |
| 首次启动超过 5 分钟 | Hub 权重下载中，看日志；或提前挂载本地 run 并设 `KEV_RUN` |
| 422 超长状态 | 默认拒绝 > `SERVE_MAX_STATE` 的状态；临时用 `KEV_TRUNCATE_STATES=1` |
| 认证 401 | 服务端设了 `KEV_API_KEY`，请求带 `Authorization: Bearer <key>` |

## 安全（生产环境建议）

- 设置 `KEV_API_KEY` 启用 Bearer 认证（部署脚本用 `-ApiKey <key>` / `--api-key <key>` 传入，等价于设置该环境变量；也可通过 shell 环境变量或 `.env` 提供）
- 前置 Nginx/TLS 反向代理，勿直接暴露 8008
