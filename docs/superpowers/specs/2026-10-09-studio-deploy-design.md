# Studio 控制台 · 第 5 章：部署与发布

> 第 7 章中的第 5 章。承接 `docs/pipeline.md` §2.4 + §2.5，覆盖 5 个 stage：image / deploy / smoke / publish / modal，加统一的端点列表视图。

## 5.1 入口

`#endpoints` 页面，5 个子标签：

- **概览**：所有 `endpoint:*` 产物（本地 + Modal），含 1 个「+ 新建部署」按钮
- **镜像**：image stage 入口 + 已构建镜像列表
- **部署**：deploy stage 入口 + 端点表
- **冒烟**：smoke stage 入口 + 5 场景结果
- **发布**：publish / modal stage 入口 + HF Hub / Modal 状态

## 5.2 image（构建镜像）

| 字段 | 默认 | 说明 |
|---|---|---|
| run | （必填，选 `run:{name}`） | 训练产物 |
| temperature | （必填） | **L4 修复后自动带出**最近 calibrate 产物的 `workload_temperature`，标注来源 run；无产物时给引导 |

闸门 G4-G7 全部通过才能提交（`app.py:356-362` 硬拦）。

提交后产物 `image:kev-{run}:{temp}`（docker tag）。

## 5.3 deploy（启动端点）

| 字段 | 默认 | 说明 |
|---|---|---|
| run | （必填） | 必是已 build 的 image |
| temperature | （必填） | 同 image 规则 |
| port | `8008` | **L8 修复后可配**；默认不变 |
| persist | `start` | 长驻（spawn 后即注册端点） |

`busy_port` 预检（`deploy.py:18, 105-108`），冲突 → 409 提示换端口。

提交后产物 `endpoint:{port}`，元数据含 `modal=False`、run 名。

## 5.4 smoke（5 场景冒烟）

| 字段 | 默认 | 说明 |
|---|---|---|
| base_url | `http://127.0.0.1:8008` | 也可选 `endpoint:8008` 产物 |

提交后跑 5 场景各 1 例，返回 p 分布与 argmax 形状；产物 `smoke:{run}`。

## 5.5 publish（发布 HF Hub）

| 字段 | 默认 | 说明 |
|---|---|---|
| run | （必填） | |
| repo | `jaredpalmer/kev-{size}` | 命名按 base 尺寸 |
| card | `docs/model-cards/{name}.md` | |
| message | commit message | |
| private | 开关 | 默认 on（`--private` 创建缺失的 repo 私有） |
| replace | 开关 | 现有 tag 替换；警告：会删上传不携带的文件 |
| tag | `vX.Y` | |
| revision | （可选） | 分支名 |

凭据 `HF_TOKEN` spawn 注入，不下发浏览器（已在 `app.py:43-47` 显式列举）。

## 5.6 modal（远端 Modal 部署）

| 字段 | 默认 | 说明 |
|---|---|---|
| run（→ `KEV_SERVE_RUN`） | （必填） | |
| gpu | `L4` | 也可选 `L40S` / `H100` / `H200` / `B200`（按 kev-deploy skill 列表） |
| app_name | （来自 `KEV_APP_NAME`） | 多部署隔离 |
| ref | （git ref） | 锁定镜像源 |

**全 env 驱动无 argparse**（`modal.py:52-54`）—— UI 字段只写 env overlay，后端组装为 spawn env。

**L6 修复**：modal 部署注册 `endpoint:modal-{run}` 产物，meta 含 `modal=True` 与 run 名；端点表以「Modal」徽标区分。

## 5.7 端点列表（统一视图）

单表，列：

- 端点 id（`endpoint:8008` / `endpoint:modal-{run}`）
- 模式（本端 / Modal）
- run 名
- 端口 / 远端 URL
- 温度（来自 calibrate）
- 状态（在线 / 离线 / 未知）
- 操作：`探测` / `冒烟` / `日志` / `下线`

「探测」调 `GET /v1/models`（`KEV_SERVE_URL`），在线则拉取 `max_state_tokens` / `truncate_states` / 当前 temperature / prefix-cache stats（已有 `kev/serve` 实现）；离线则标灰。

「下线」对本地端点调 `executor.cancel`（标记 `endpoint:*` 产物的 `meta.offline` 字段），Modal 端点走 `modal app stop`。

## 5.8 闸门预检条

`#endpoints` 部署类 stage 顶部同样显示 G4-G7 状态（同 §4.7）。

## 5.9 前端位置

新增 `playground/src/app/kev.studio/endpoints/`：

- 5 个子标签对应 `image/`、`deploy/`、`smoke/`、`publish/`、`modal/` 5 个 page
- 共享 `components/EndpointTable.tsx`（含状态探测 + Modal 徽标 + 操作下拉）
- `components/DeployFormShell.tsx`（image/deploy/modal 三者字段差异在配置里驱动）

API 调用统一封装在 `playground/src/lib/console.ts`（沿用 §1–§4 的封装），URL 前缀 `/console/api`。

## 5.X Service 层重构 · 部署与发布

**目标**：把 `kev/console/stages/deploy.py` 与 `publish.py` 5 个 stage 改造为 service 同步调用。**但 `deploy` 与 `modal` 仍保留子进程**——它们的产品语义就是"长驻 / 外部 SaaS"，service 化是包装而非内联。

### Service 接口

新建 `kev/console/services/deploy.py` 与 `kev/console/services/publish.py`：

```python
class DeployService:
    def __init__(self, store: Store, cancel: threading.Event):
        ...

    def image(self, req: JobRequest, *, on_log) -> dict: ...       # 同步：打 docker tag
    def deploy(self, req: JobRequest, *, on_log) -> dict: ...     # 异步：spawn kev.serve Popen
    def smoke(self, req: JobRequest, *, on_log) -> dict: ...      # 同步：5 场景 HTTP 请求
    def cancel_endpoint(self, endpoint_id: str) -> None: ...      # 取消正在跑的 deploy

class PublishService:
    def publish(self, req: JobRequest, *, on_log) -> dict: ...    # 调 kev.publish.run
    def modal(self, req: JobRequest, *, on_log) -> dict: ...      # spawn modal CLI Popen
```

### 改造点

1. **`image`**：内部调 `kev.publish` 的镜像构建（已有 `scripts/release_checkpoint.py`）；同步
2. **`deploy`**：**保留长驻子进程**——kev.serve 仍需独立 Python 进程占 GPU；service 启动 `python -m kev.serve` Popen，但取消 / 健康探测 / 端口预检全在 service 内
3. **`smoke`**：内部调 `kev.predictors` + HTTP 5 场景；同步
4. **`publish`**：内部调 `kev.publish.run(...)`（**拆 CLI 块**，与 train/eval 同模式）
5. **`modal`**：**保留 Popen 调 `modal app deploy`**——这是真正的外部子进程依赖；service 包装 Popen 但不绕过产物注册

### 依赖新增

- `kev/console/services/deploy.py`（4 个 service 方法 + `cancel_endpoint`）
- `kev/console/services/publish.py`（2 个 service 方法）
- `kev/publish.py` 拆 CLI 块

### 不动

- 端点列表 `/console/api/endpoints`（已实现）
- 探测 / 下线 / 冒烟（产品语义不变）
- Modal `kev-deploy` skill（远端部署仍走 skill 提供的 `scripts/kev_serve.py`）

### 风险

- `deploy` 长驻子进程仍占独立 GPU，但 console 进程只是 watch 它的 stdout/health——service 化不增加 console 自身显存
- `modal` 走 Popen 调 modal CLI 是合理的（modal 是外部 SaaS），但**取消语义复杂**——service 杀 Popen，modal 那边未必同步停止

## 5.10 已知 / 不在本期

- 不做镜像层 / 容器层细节
- 不做 Modal 实时日志流（SSE 代理成本不划算，仅展示作业级日志）
- `replace` 开关是危险操作，提交时弹二次确认 + 输入 repo 名
