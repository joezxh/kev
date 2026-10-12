---
kind: build_system
name: KEV 构建与部署体系：setuptools + uv + Docker Compose + GitHub Actions
category: build_system
scope:
    - '**'
source_files:
    - pyproject.toml
    - .github/workflows/ci.yml
    - deploy/Dockerfile.4B
    - deploy/Dockerfile.0.8B
    - deploy/Dockerfile.playground
    - deploy/docker-compose.yml
    - deploy/docker-compose-0.8B.yml
    - deploy/docker-compose-4B.yml
    - deploy/deploy-linux.sh
    - deploy/deploy-windows.ps1
    - deploy/up.sh
    - deploy/up.ps1
---

## 1. 使用的构建系统

仓库采用多工具组合的 Python 项目构建方案：

- **Python 包构建**：`pyproject.toml` 使用 `setuptools.build_meta`（要求 `setuptools>=77`），通过 `pip install .[serve]` 安装，依赖声明在 `[project.dependencies]` 与 `[project.optional-dependencies]` 中。
- **依赖解析/环境管理**：CI 与本地开发统一使用 `uv`（astral-sh/setup-uv@v5），命令为 `uv sync --extra serve`；根目录存在 `uv.lock` 锁定版本。
- **Python 版本约束**：`requires-python = ">=3.12,<3.14"`，Docker 镜像基于 `python:3.13-slim-bookworm`。
- **前端 Playground**：Next.js App Router 项目，位于 `playground/`，使用 npm + Node 22，构建入口为 `package.json` 中的脚本（`npm ci`、`npm run lint`、`npx next typegen && npx tsc --noEmit -p .`）。
- **容器化**：每个可运行组件一个独立 Dockerfile（见 `deploy/Dockerfile.*`），编排由 `docker-compose.yml` 及模型变体 compose 文件完成。
- **CI**：GitHub Actions（`.github/workflows/ci.yml`），push main 与 PR 触发。

## 2. 关键文件

- `pyproject.toml` — 包元数据、依赖、可选依赖 (`serve`、`mlx`)、pytest 配置、setuptools 打包范围。
- `.github/workflows/ci.yml` — CI 流水线定义。
- `deploy/Dockerfile.0.8B` / `deploy/Dockerfile.4B` — Kev-0.8B/Kev-4B 推理镜像。
- `deploy/Dockerfile.kev-server-local` / `deploy/Dockerfile.playground` / `deploy/Dockerfile.python-torch` — 辅助镜像。
- `deploy/docker-compose.yml` — 默认单栈编排（kev-server + playground）。
- `deploy/docker-compose-0.8B.yml` / `deploy/docker-compose-4B.yml` — 按模型尺寸区分的 compose。
- `deploy/deploy-linux.sh` — Linux 一键部署脚本（含模型选择、预检、健康检查）。
- `deploy/deploy-windows.ps1` / `deploy/up.ps1` / `deploy/start-console.ps1` — Windows 对应脚本。
- `deploy/up.sh` — 通用 up 包装器。
- `deploy/.env` — 环境变量模板。

## 3. 架构与约定

### 3.1 Python 包结构
`pyproject.toml` 显式声明 `packages = ["kev", "kev.console", "kev.console.stages"]`，仅打包这三个子包。`kev.serve` 作为 FastAPI 服务暴露 `/v1/systemone` API；`mlx-lm` 仅在 `sys_platform == 'darwin' and platform_machine == 'arm64'` 时安装（Apple Silicon 后端）。

### 3.2 Docker 镜像分层策略
- `Dockerfile.4B` / `Dockerfile.0.8B`：从 `python:3.13-slim-bookworm` 构建，`COPY pyproject.toml README.md LICENSE ./` 后 `pip install --no-cache-dir ".[serve]"`，再 `COPY kev ./kev`。模型 checkpoint **不**打入镜像，运行时通过 `--run` 参数指定本地路径或 HuggingFace Hub id（如 `jaredpalmer/kev-4b`）。
- 镜像暴露端口 `8008`，并通过 `HEALTHCHECK` 调用 `http://127.0.0.1:8008/v1/models` 做存活探测。
- 环境变量驱动行为：`KEV_RUN`（checkpoint）、`KEV_DTYPE`（默认 `bf16`）、`KEV_PREFIX_CACHE`、`KEV_CUDA_GRAPHS`、`KEV_FUSED`、`KEV_DATE_FACTS`、`KEV_TRUNCATE_STATES`、`KEV_API_KEY`、`HF_ENDPOINT`、`HF_HUB_OFFLINE` 等。

### 3.3 Compose 编排
`docker-compose.yml` 定义两个服务：
- `kev-server`：构建自 `deploy/Dockerfile.0.8B`，映射 `8008:8008`，挂载 `./runs:/kev/runs` 与 `kev-console-data:/kev/data`，声明 NVIDIA GPU 资源预留（`driver: nvidia, count: all`）。
- `playground`：构建自 `deploy/Dockerfile.playground`，映射 `3030:3000`，通过内网 `http://kev-server:8008` 访问服务端（无 CORS、无 host 端口暴露）。
- 共享网络 `kev-net`，共享 volume `kev-hf-cache`（HuggingFace 缓存）。

### 3.4 部署脚本约定
`deploy-linux.sh` 提供 `--model {4B|0.8B}`、`--no-build`、`--run <name>`、`--hub <id>`、`--api-key <key>` 参数：
- 自动检测 `docker compose` 或 `docker-compose`。
- 校验 Docker daemon、GPU、NVIDIA Container Toolkit。
- 本地模式要求 `head.pt` 存在以区分 Hub id。
- 启动后轮询 `http://localhost:8008/v1/models` 最多 600s，再等待 playground UI 就绪。
- 同时运行不同模型时会先 `down` 另一个模型的 stack（二者共用容器名 `kev-server`/`kev-playground`）。

### 3.5 CI 流水线
两个 job：
- `python`：Ubuntu runner，`uv sync --extra serve` 后运行一组 pytest（明确列出 `tests/test_unit.py`、`test_compare.py`、`test_device.py`、`test_research.py`、`test_generators.py`、`test_conventions.py`、`test_documents_tools.py`、`test_hard_v1.py`、`test_devtools_v1.py`、`test_breadth_v1.py`、`test_rounds.py`、`test_skill_scripts.py`），注释说明“no model weights, no server”，tokenizer 从 Hub 下载。
- `playground`：Node 22，`npm ci` → `npm run lint` → `npx next typegen && npx tsc --noEmit -p .`。

## 4. 约定与约束

- **Python 版本**：`requires-python = ">=3.12,<3.14"`，Docker 镜像固定 `python:3.13-slim-bookworm`（`Dockerfile.4B` 第 12 行）。
- **依赖锁定**：使用 `uv.lock`，CI 通过 `uv sync` 而非 `pip` 安装依赖。
- **可选依赖隔离**：`serve` 额外依赖（FastAPI、uvicorn、typesafe-sdk、SQLAlchemy、psycopg[binary]、requests）仅在 `--extra serve` 时安装；`mlx` 额外依赖仅在 Apple Silicon 上安装（`pyproject.toml` 中 `sys_platform == 'darwin' and platform_machine == 'arm64'` 条件）。
- **模型权重不入镜像**：所有 Dockerfile 注释明确说明 checkpoint 不在镜像中，运行时通过 `KEV_RUN` 环境变量加载本地路径或 Hub id。
- **Compose 端口契约**：server 固定 `8008`，playground 固定 `3030:3000`，console 与 server 同端口挂载（`/console/api`）。
- **GPU 资源声明**：compose 中 `deploy.resources.reservations.devices` 要求 `driver: nvidia, count: all`，Linux 部署脚本在无 `nvidia-smi` 时降级到 CPU 并给出警告。
- **健康检查**：Dockerfile 与 compose 均对 `/v1/models` 端点执行 HTTP 200 探测，支持 `Authorization: Bearer $KEV_API_KEY`。
- **HF 镜像**：默认 `HF_ENDPOINT=https://hf-mirror.com`，`HF_HUB_OFFLINE=1`（首次拉取后离线运行）。
- **Playground 构建**：CI 中 `working-directory: playground`，缓存 `playground/package-lock.json`，执行 lint + TypeScript 类型检查（`tsc --noEmit`）。
- **测试标记**：pytest 配置 `markers = ["server: needs a running kev.serve instance (KEV_BASE_URL)"]`，但 CI 未运行带 `server` marker 的用例。
- **版本编号**：包版本硬编码在 `pyproject.toml` 中 `version = "0.1.0"`，未见自动化版本号管理脚本。
- **Windows 支持**：`deploy/deploy-windows.ps1`、`deploy/up.ps1`、`deploy/start-console.ps1` 提供与 Linux 脚本对应的 PowerShell 实现。