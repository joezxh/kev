---
kind: configuration_system
name: KEV 配置系统：环境变量 + .env 分层加载与密钥文件管理
category: configuration_system
scope:
    - '**'
source_files:
    - .env.example
    - deploy/.env
    - playground/.env.local
    - deploy/docker-compose.yml
    - pyproject.toml
    - kev/checkpoint.py
    - kev/console/db.py
    - kev/console/__main__.py
    - kev/console/secrets.py
    - examples/kev_example.py
---

## 1. 采用的方案

KEV 没有引入第三方配置库（如 pydantic-settings、dynaconf），而是以 **`os.environ` 直接读取** 作为唯一运行时配置来源，配合 `.env*` 文件由 Docker / Next.js 等宿主环境注入。关键约定：
- Python 侧统一使用 `os.environ.get("KEY", default)` 或 `os.environ.setdefault(...)`。
- 所有面向用户的开关以 `KEV_` 前缀命名（见 `kev/checkpoint.py`、`deploy/docker-compose.yml`、`.env.example`）。
- 部署层通过 `docker compose` 的 `environment:` 字段集中声明默认值，本地覆盖放在 `deploy/.env`。
- Playground 前端通过 Next.js 自动加载 `playground/.env.local`（已被 `.gitignore` 忽略）。
- 敏感凭据不放入数据库，而是落盘到 `data/console/secrets/distill.json`，路径由 `KEV_DISTILL_SECRETS` 控制，写入时强制 `chmod 0o600`。

## 2. 关键文件

| 文件 | 作用 |
|---|---|
| `.env.example` | KEV Console 数据库后端（sqlite/postgres）、端口等变量的模板 |
| `deploy/.env` | docker compose 本地覆盖（HF 镜像、CUDA graphs/fused 开关等） |
| `playground/.env.local` | Next.js 前端开发端口与 API 地址 |
| `deploy/docker-compose.yml` | 服务级环境变量清单与默认值（`KEV_RUN`、`KEV_DTYPE`、`KEV_API_KEY`、`KEV_CONSOLE_DB` 等） |
| `pyproject.toml` | 项目元数据、可选依赖 `serve`/`mlx`、pytest markers（`server: needs a running kev.serve instance (KEV_BASE_URL)`） |
| `kev/checkpoint.py` | `CheckpointOptions.from_env()` 解析 `KEV_DTYPE`/`KEV_MERGE`/`KEV_ATTN`/`KEV_LORA_SCALE`/`KEV_TEMPERATURE`/`KEV_BACKEND`/`KEV_CUDA_GRAPHS`/`KEV_FUSED` |
| `kev/console/db.py` | `backend_url()` 根据 `KEV_CONSOLE_DB_BACKEND` 切换 sqlite/postgres，并读取 `KEV_CONSOLE_DB_PATH`/`KEV_CONSOLE_DB_HOST`/`PORT`/`USER`/`PASSWORD`/`NAME`/`SCHEMA` |
| `kev/console/__main__.py` | 控制台 CLI 入口，读取 `KEV_CONSOLE_PORT`、`KEV_CONSOLE_ALLOW_SERVE_PORT`、`KEV_SERVE_URL` |
| `kev/console/secrets.py` | 蒸馏 provider 密钥文件的读写，默认路径 `data/console/secrets/distill.json`，可被 `KEV_DISTILL_SECRETS` 覆盖 |
| `examples/kev_example.py` | 示例脚本通过 `KEV_BASE_URL` 指定远程推理端点 |

## 3. 架构与约定

### 3.1 变量命名空间
- `KEV_*`：应用运行时开关（dtype、merge、attn、lora_scale、temperature、backend、cuda_graphs、fused、date_facts、truncate_states、api_key、run、base_url、remote_api_key 等）。
- `KEV_CONSOLE_*`：编排控制台专用（DB backend/host/port/user/password/name/schema/path、port、allow_serve_port、base_url、serve_url）。
- `KEV_DISTILL_SECRETS`：密钥文件路径。
- `HF_*`：HuggingFace Hub 代理与离线模式（`HF_ENDPOINT`、`HF_HUB_OFFLINE`、`HF_HUB_DISABLE_XET`）。
- `WORLD_SIZE`/`LOCAL_RANK`：分布式训练（`full_ft.py`）。

### 3.2 分层加载顺序
1. **容器/进程环境**：Docker Compose `environment:` 为每个变量提供默认值（例如 `KEV_RUN=${KEV_RUN:-jaredpalmer/kev-0.8b}`），允许外部 shell 变量覆盖。
2. **`.env` 文件**：`deploy/.env` 用于本地复现（关闭 Xet、禁用 CUDA graphs 等）。Playground 的 `playground/.env.local` 由 Next.js 自动加载。
3. **代码内 `default`**：`os.environ.get("KEY", "default")` 在缺少环境变量时回退到硬编码默认值（如 sqlite 路径、端口 8790、`http://127.0.0.1:8008`）。
4. **命令行参数**：少数入口（如 `examples/kev_example.py`）同时支持 `--base-url` 参数，但默认仍从 `KEV_BASE_URL` 读取。

### 3.3 数据库后端切换
`kev/console/db.py::backend_url()` 是唯一的数据库 URL 构造点：
- `KEV_CONSOLE_DB_BACKEND=sqlite`（默认）→ 使用 `KEV_CONSOLE_DB_PATH` 或兼容旧变量 `KEV_CONSOLE_DB`，最终落到 `paths.DB_PATH`。
- `KEV_CONSOLE_DB_BACKEND=postgres` → 使用 `KEV_CONSOLE_DB_HOST/PORT/USER/PASSWORD/NAME/SCHEMA`，连接串为 `postgresql+psycopg://...`，schema 通过 `-csearch_path=` 传入。
- DDL 中自增列与浮点类型按后端分支生成（`BIGSERIAL` vs `INTEGER AUTOINCREMENT`、`DOUBLE PRECISION` vs `REAL`）。

### 3.4 密钥管理
`kev/console/secrets.py` 是蒸馏第三方模型凭据的唯一落盘处：
- 明文 key 只存在于该 JSON 文件中，SQLite 仅存哈希和掩码（`mask()` 返回 sha256 + `xxx...yyy`）。
- 文件权限在 `_atomic_write` 中强制设为 `0o600`。
- 默认路径 `data/console/secrets/distill.json`，可通过 `KEV_DISTILL_SECRETS` 环境变量覆盖。

### 3.5 配置即文档
`.env.example` 中的注释把每个变量与其用途、默认行为、以及关联文档（`docs/medical/runbook-train_cn.md §7.0`）绑定在一起，形成“配置即文档”的约定。

## 4. 约定与约束

- **环境变量命名规范**：所有用户可配置的运行时开关均以 `KEV_` 前缀开头（见 `checkpoint.py`、`db.py`、`__main__.py`、`docker-compose.yml` 的一致性用法）。
- **数据库后端选择**：通过 `KEV_CONSOLE_DB_BACKEND` 在 sqlite 与 postgresql 之间切换；sqlite 路径优先取 `KEV_CONSOLE_DB_PATH`，其次兼容旧变量 `KEV_CONSOLE_DB`，最后回退到 `paths.DB_PATH`（`kev/console/db.py` 第 55–74 行）。
- **密钥文件安全**：`KEV_DISTILL_SECRETS` 指向的文件会被 `chmod 0o600`（`secrets.py` 第 61 行），且 gitignore 排除 `.env*` 与 `data/console/secrets/*`。
- **Compose 默认值**：`deploy/docker-compose.yml` 中每个 `KEV_*` 变量都通过 `${VAR:-default}` 语法给出默认值，确保无 `.env` 也能启动（第 43–65 行）。
- **Playground 前端 API 地址**：`playground/.env.local` 必须显式设置 `KEV_CONSOLE_API` 与 `KEV_API` 指向 `http://127.0.0.1:8008`（注释明确说明默认 route.ts 指向 8790，必须改成 8008）。
- **测试标记约束**：`pyproject.toml` 定义 pytest marker `server: needs a running kev.serve instance (KEV_BASE_URL)`，要求运行服务器类测试时必须设置 `KEV_BASE_URL`。
- **分布式训练环境变量**：`full_ft.py` 通过 `WORLD_SIZE` 与 `LOCAL_RANK` 感知 torchrun 环境，并将 `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` 写回 `os.environ`（第 162–165 行）。
- **向后兼容**：`KEV_CONSOLE_DB` 作为旧变量名被保留，仅用于 sqlite 路径兜底（`db.py` 第 71–72 行），新代码应使用 `KEV_CONSOLE_DB_PATH`。