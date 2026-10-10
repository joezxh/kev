# Kev Docker 部署（Kev-4B / Kev-0.8B）

用 Docker 部署 `kev.serve`（FastAPI 推理服务，端口 8008，TypeSafe 兼容的
`POST /v1/systemone` / `GET /v1/models`），并附带 **Playground** 演示 UI
（Next.js，端口 3000）。Windows Docker Desktop 与 Linux 共用同一套文件。

提供 **一个部署脚本即可选择模型**：`deploy-windows.ps1` / `deploy-linux.sh`
通过 `-Model` / `--model` 在 `4B` 与 `0.8B` 之间切换，会自动选用对应的
`docker-compose-*.yml`、`Dockerfile.*`、默认 checkpoint 目录与 Hub id。

| 模型 | 默认本地目录 | 默认 Hub id | 基座 | 显存（bf16） |
|------|--------------|-------------|------|--------------|
| Kev-4B  | `./deploy/runs/kev-4b-local`   | `jaredpalmer/kev-4b`   | `Qwen/Qwen3.5-4B-Base`   | ~10–12 GB |
| Kev-0.8B| `./deploy/runs/kev-0.8b-local` | `jaredpalmer/kev-0.8b` | `Qwen/Qwen3.5-0.8B-Base` | ~2–3 GB  |

> 模型权重**不打进镜像**。`kev.serve --run` 接受本地 run 目录或 HuggingFace
> Hub ID（如 `jaredpalmer/kev-0.8b`，下载到 HF 缓存卷）。

## 目录结构

```
deploy/
├── deploy-windows.ps1     # Windows 一键部署（PowerShell），-Model 选 4B / 0.8B
├── deploy-linux.sh        # Linux 一键部署（Bash），--model 选 4B / 0.8B
├── docker-compose-4B.yml  # Kev-4B compose（server + playground）
├── docker-compose-0.8B.yml# Kev-0.8B compose（server + playground）
├── Dockerfile.4B          # 从本地源码构建 kev-server（4B 默认 KEV_RUN）
├── Dockerfile.0.8B        # 从本地源码构建 kev-server（0.8B 默认 KEV_RUN）
├── Dockerfile.playground  # 构建 playground（Next.js）镜像（两模型共用）
├── runs/                  # 本地 checkpoint（kev-4b-local / kev-0.8b-local）
└── README.md              # 本文档
```

> 两个 compose 文件共用服务名 `kev-server` / `playground` 与网络 `kev-net`
> （因为 `Dockerfile.playground` 在构建期把代理目标 `http://kev-server:8008`
> 烤进了 Next.js rewrite，服务名不能改）。所以**同一时刻只跑一个模型栈**——
> 部署脚本在启动前会自动 `down` 掉另一个模型的栈以释放同名容器。

## 快速开始

### Windows（Docker Desktop，WSL2 后端）

```powershell
cd d:\projects\github\kev

.\deploy\deploy-windows.ps1                       # 默认 Kev-4B，本地模式
.\deploy\deploy-windows.ps1 -Model 0.8B           # 改为 Kev-0.8B
.\deploy\deploy-windows.ps1 -NoBuild              # 跳过构建（复用已存在镜像）
.\deploy\deploy-windows.ps1 -Model 4B  -Run kev-4b-local   -ApiKey <key>  # 指定本地目录 + Bearer 认证
.\deploy\deploy-windows.ps1 -Model 0.8B -Hub jaredpalmer/kev-0.8b -ApiKey <key>  # 从 Hub 下载
```

### Linux（Ubuntu/Debian）

```bash
cd /path/to/kev
chmod +x deploy/deploy-linux.sh

./deploy/deploy-linux.sh                          # 默认 Kev-4B，本地模式
./deploy/deploy-linux.sh --model 0.8B             # 改为 Kev-0.8B
./deploy/deploy-linux.sh --no-build               # 跳过构建
./deploy/deploy-linux.sh --model 4B  --run kev-4b-local   --api-key <key>
./deploy/deploy-linux.sh --model 0.8B --hub jaredpalmer/kev-0.8b --api-key <key>
```

默认走**本地运行模式**：不传 `-Run`/`--run` 时脚本使用模型对应的默认本地目录
（4B → `./deploy/runs/kev-4b-local`，0.8B → `./deploy/runs/kev-0.8b-local`），
容器内路径为 `/kev/runs/<name>`。该目录需先放好 checkpoint，否则脚本报错退出。
本地模式复用已缓存的基座（`kev-hf-cache` 卷），无需联网下载。

如需临时从 Hub 下载，传 `-Hub <id>` / `--hub <id>`
（4B → `jaredpalmer/kev-4b`，0.8B → `jaredpalmer/kev-0.8b`），
首次启动会下载到 `kev-hf-cache` 卷，需几分钟。

### 手动 compose

```bash
# 4B
docker compose -f deploy/docker-compose-4B.yml up -d --build
# 0.8B
docker compose -f deploy/docker-compose-0.8B.yml up -d --build
```

## Playground（演示 UI 容器）

每个 compose 里都有一个 `playground` 服务，把 `playground/`（Next.js 应用，
kev / chess 两个 tab）打包成镜像并对外暴露 **3000** 端口。它**不直接连
kev-server 的 8008 端口**，而是走 Next.js 的服务端代理：`/kev/*` 由
`next.config.ts` 的 rewrite 转发到 `KEV_API` 指向的地址。在 compose 网络中，
这个值被设为 `http://kev-server:8008`，即 kev-server 的**服务名**——Docker 的
user-defined 网络 `kev-net` 提供按服务名的 DNS 解析，无需暴露端口、也无需处理 CORS。

- `playground` 通过 `depends_on: kev-server: service_healthy` 启动，确保模型服务先就绪。
- 浏览器只访问 `http://localhost:3000`，所有 `/kev` 请求由 Next 服务端转发给 kev-server。
- 若想把 playground 接别的 kev-server 实例，改 `KEV_API` 环境变量即可。

> 安全：kev-server 默认 `KEV_API_KEY` 为空（开放服务），playground 直接可用；
> 若给 kev-server 设了 key，需要让 playground 转发同样的 `Authorization` 头
> （playground 前端 `lib/kev.ts` 已内置一个兜底 key，与部署脚本传入的
> `--api-key` / `-ApiKey` 保持一致即可）。

## 本地 checkpoint 目录（deploy/runs/&lt;name&gt;）

本地运行模式（脚本默认）把 `KEV_RUN` 指向 `./deploy/runs/<name>`
（容器内 `/kev/runs/<name>`）。该目录只需放 **kev 的 LoRA 适配器快照**；
基座（如 `Qwen/Qwen3.5-4B-Base`）由 `head.pt` 里的 `meta.base` 经 HF 缓存卷
`kev-hf-cache` 解析（`kev.checkpoint` 的逻辑），卷里已缓存，可离线。

### 目录结构

以 `deploy/runs/kev-4b-local/` 为例（LoRA 适配器布局，`kev.serve` 凭
`adapter_config.json` 识别为适配器）：

```
deploy/runs/kev-<4b|0.8b>-local/
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

> 若是 `kev.train --full_ft` 的完整权重 run，则没有 `adapter_*` 文件，改为
> `config.json` + `model*.safetensors`（`kev.checkpoint` 据此判定
> `weights="full"`，从目录本身加载基座）。

### 放置清单（checklist）

1. 在 `deploy/runs/` 下新建子目录，名称即 `<name>`（4B 默认 `kev-4b-local`，
   0.8B 默认 `kev-0.8b-local`）
2. 放入上述文件（**至少** `head.pt` + `adapter_config.json` + `adapter_model.safetensors`）
3. 确认基座可用：基座需已在 `kev-hf-cache` 卷缓存；换机器或要纯离线时设
   `HF_HUB_OFFLINE=1`（见下方配置表）
4. 部署：`.\deploy\deploy-windows.ps1 -Model 4B -Run kev-4b-local -ApiKey <key>`

### 从 kev-hf-cache 卷导出

当前 `deploy/runs/kev-4b-local` 即由运行中的 `kev-hf-cache` 卷里的 Hub 快照
`models--jaredpalmer--kev-4b` 实体化导出（软链展开为真实文件）。0.8B 同理：

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
  Kev-4B bf16 约需 10–12 GB 显存，Kev-0.8B bf16 仅需 ~2–3 GB。无 GPU 时服务以
  CPU 模式启动（慢，0.8B 在 CPU 上仍可用）
- Linux GPU 安装 Toolkit：<https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html>

## 验证

```bash
docker ps                                   # kev-server 应为 healthy；playground 应为 running/healthy
curl http://localhost:8008/v1/models
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/   # playground 首页应返回 200
curl -s http://localhost:3000/kev/v1/models                                # 经 playground 代理打到 kev-server
python scripts/test-api.py                  # 在仓库根目录执行
# Swagger UI: http://localhost:8008/docs
# Playground UI: http://localhost:3000
```

## 常用命令

```bash
docker logs -f kev-server                                   # 日志
docker compose -f deploy/docker-compose-4B.yml ps           # 状态（4B）
docker compose -f deploy/docker-compose-0.8B.yml ps         # 状态（0.8B）
docker compose -f deploy/docker-compose-4B.yml restart      # 重启（4B）
docker compose -f deploy/docker-compose-0.8B.yml restart    # 重启（0.8B）
docker compose -f deploy/docker-compose-4B.yml down         # 停止（4B）
docker compose -f deploy/docker-compose-0.8B.yml down       # 停止（0.8B）
docker compose -f deploy/docker-compose-4B.yml up -d --build   # 重建并启动（4B）
docker compose -f deploy/docker-compose-0.8B.yml up -d --build   # 重建并启动（0.8B）
```

## 配置（环境变量）

compose 里全部以 `${VAR:-默认值}` 形式透传，可在 shell 或 `.env` 中覆盖。
以下均为 `kev.serve` 实际读取的变量：

| 变量 | 默认 | 说明 |
|------|------|------|
| `KEV_RUN` | 4B: `/kev/runs/kev-4b-local`<br>0.8B: `/kev/runs/kev-0.8b-local` | checkpoint：本地目录 `/kev/runs/<name>`（`./runs` 已挂载，脚本默认）；或 Hub ID（可 `@<rev>` 固定版本，下载到 `kev-hf-cache` 卷） |
| `KEV_DTYPE` | `bf16` | 计算精度（`fp32` 为精确路径） |
| `KEV_PREFIX_CACHE` | `4` | 状态前缀缓存条数，`0` 关闭 |
| `KEV_API_KEY` | 空 | 设置后启用 Bearer 认证；空 = 开放服务 |
| `KEV_DATE_FACTS` | `0` | `1` 启用日期预处理 |
| `KEV_TRUNCATE_STATES` | `0` | `1` 截断超长状态（默认 422 拒绝） |
| `KEV_CUDA_GRAPHS` | 自动 | `0` 关闭 CUDA Graphs |
| `KEV_FUSED` | 自动 | `0` 关闭融合 Qwen3.5 内核（需 fla） |
| `KEV_BACKEND` | 自动 | `torch` 强制 PyTorch（Apple Silicon 默认 MLX，与容器无关） |
| `HF_HUB_OFFLINE` | `0` | `1` 只用已下载的缓存 |

### Playground 相关变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `KEV_API` | `http://kev-server:8008` | playground 的 Next.js 服务端代理目标；`kev-server` 是 compose 服务名，由 `kev-net` 网络解析。改名 kev-server 时需同步改这里 |
| `PORT` / `HOSTNAME` | `3000` / `0.0.0.0` | playground 容器监听地址 |
| `NODE_ENV` | `production` | 生产模式 |

注意：`MAX_BATCH` 是 `kev/serve.py` 中的硬编码常量（64），**不是**环境变量。

## 故障排查

| 症状 | 处理 |
|------|------|
| 容器 unhealthy / 启动失败 | `docker logs kev-server`；确认 8008 未被占用 |
| GPU 未生效（推理极慢） | `docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi`；Linux 检查 `nvidia-ctk cdi generate` |
| 首次启动超过 5 分钟 | Hub 权重下载中，看日志；或提前挂载本地 run 并设 `KEV_RUN` |
| 422 超长状态 | 默认拒绝 > `SERVE_MAX_STATE` 的状态；临时用 `KEV_TRUNCATE_STATES=1` |
| 认证 401 | 服务端设了 `KEV_API_KEY`，请求带 `Authorization: Bearer <key>` |
| 切换模型报容器名冲突 | 部署脚本会自动 `down` 另一模型栈；若仍冲突，手动 `docker compose -f deploy/docker-compose-<other>.yml down` |

## 安全（生产环境建议）

- 设置 `KEV_API_KEY` 启用 Bearer 认证（部署脚本用 `-ApiKey <key>` / `--api-key <key>` 传入，等价于设置该环境变量；也可通过 shell 环境变量或 `.env` 提供）
- 前置 Nginx/TLS 反向代理，勿直接暴露 8008
