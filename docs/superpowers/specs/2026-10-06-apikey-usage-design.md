# API Key 管理与用量统计（Kev Console）设计文档

- 日期：2026-10-06
- 状态：待评审
- 作者：brainstorming 会话产出

---

## 1. 背景与目标

`kev.serve`（端口 8008）是 kev 的核心推理接口：`POST /v1/systemone`、`/v1/systemone/separate`、`/v1/systemone/permute`、`GET /v1/models`。当前 playground 通过 `next.config.ts` 的 `/kev/*` rewrite 直接打它，且只用一个管理 key（`NEXT_PUBLIC_KEV_API_KEY`）—— 这个 key 经 `NEXT_PUBLIC_` 下发给浏览器，等于公开（上一版控制台 spec §11.5 已要求删除）。

本设计要在控制台补两件事：

1. **API Key 管理**：管理员在控制台创建 key、列出、撤销；用户（含 playground 自己）用各自的 key 访问 kev 核心接口。
2. **用量统计**：按 apikey 记录每次核心接口调用的 token 消耗（输入/输出）、耗时、端点、时间，控制台按 key 汇总并给出按天时间序列。

### 1.1 目标（可判定）

| 目标 | 判据 |
| --- | --- |
| key 管理闭环 | 控制台能创建/列出/撤销 key；撤销后该 key 立即 401 |
| 调用走 key 鉴权 | playground 与任意外部调用方打 kev 核心接口都经 `/api/console/kev/*` 且必须带有效 key |
| 用量可归因 | 每次核心调用在 `usage_log` 落一行；按 key 能查到调用数、token、耗时 |
| 统计可读 | 用量页每个 key 一行汇总 + 点开看按天时间序列 |
| kev.serve 零改动 | `kev/serve.py` 的 `git diff` 为空；代理在控制台后端，复用其单 key 鉴权 |
| 凭据不落地 | key 明文只在创建时返回一次；库里只存 sha256；管理 key 仍只从进程环境变量读 |

### 1.2 非目标

- 不做多用户登录 / 角色 / 控制台自身鉴权（控制台仍是本地单用户，只绑 127.0.0.1，见上一版 §12）。
- 不做 key 的速率限制 / 额度上限 / 过期时间 / 端点范围（本期只做基础 CRUD，已与用户确认）。
- 不做 key 的轮换 / 多 key 轮换（YAGNI）。
- 不改变 kev.serve 的鉴权模型（它仍只认一个 `KEV_API_KEY`，代理转发时由控制台注入）。

---

## 2. 范围与决策

### 2.1 澄清问题的答案

| 问题 | 决策 | 理由 |
| --- | --- | --- |
| 鉴权与记录落在哪一层 | **控制台后端做代理** | `kev.console`（FastAPI）已有 SQLite `Store` 与 `/api/console/*` 代理；不改推理服务、复用现有持久化与 playground 代理链路 |
| playground 是否也走 key | **是** | playground 调用 kev 时带一个选中的 apikey（存 localStorage），试用调用也计入该 key 用量 |
| key 管理能力 | **基础 CRUD** | 名称 + 密钥(哈希) + 启用/撤销 + 创建时间；无速率/额度/过期/范围 |
| 统计维度 | **按 key 汇总 + 时间序列** | 每 key 一行（调用数、输入/输出 token、平均耗时、p99 耗时、最后调用时间）；点开看按天序列；含时间范围筛选 |

### 2.2 架构方案选型

考察了三个落点（§1.1 已定 A）：

| 方案 | 描述 | 结论 |
| --- | --- | --- |
| A 控制台后端代理 | `kev.console` 新增 `/console/api/kev/{path}`：校验 key → 转发 kev.serve（注入管理 key）→ 记录用量 → 透传响应 | **采纳** |
| B 改 kev.serve 本体 | 在推理服务里支持多 key + 自记用量 | 否决：动到 `kev.serve.py`（契约冻结），且与单 key 鉴权/CORS/standalone 耦合 |
| C Next.js 中间件 | 在 `next.config` 拦截 `/kev/*` 校验+记录 | 否决：边缘/节点运行时读写 SQLite 不便，且仍要调后端读库，多一层 |

选 A 的关键收益：playground 与 `next.config` 的 `/kev` rewrite 可整体退场，所有 kev 流量统一经 `/api/console/kev` —— 既统一鉴权，也去掉了 `NEXT_PUBLIC_KEV_API_KEY` 泄露（§12）。

---

## 3. 架构与进程拓扑

```
浏览器
└── playground (Next.js)                         ← 控制台 UI + kev 试用
      │  HTTP /api/console/**   （同源，规避 CORS）
      ▼
kev-console (FastAPI, :8790)                     ← 编排服务（既有）+ 本次新增
      ├── SQLite kev-console.db                   ← jobs/artifacts/lineage/events
      │                                            + 本次新增 api_keys / usage_log
      └── 新增代理 POST /console/api/kev/{path}
            │  校验 Authorization: Bearer <userkey>（按 key_hash 查 api_keys）
            │  注入管理 key：Authorization: Bearer <KEV_API_KEY>（若设置）
            ▼
kev.serve (FastAPI, :8008)                       ← 推理服务，零改动
      GET  /v1/models
      POST /v1/systemone  | /v1/systemone/separate | /v1/systemone/permute
```

- 代理目标由新环境变量 `KEV_SERVE_URL` 控制，默认 `http://127.0.0.1:8008`；compose 里指向 `http://kev-server:8008`。
- 管理 key `KEV_API_KEY` 复用既有 `SECRET_NAMES`（已不落库、只回布尔态）。
- playground 的 `/kev/*` rewrite 保留为兜底（管理直连调试用），但 playground 主路径改为 `/api/console/kev/*`。

---

## 4. 数据模型

### 4.1 SQLite 两张新表（`SCHEMA_VERSION` → 2）

沿用既有约定：单文件、WAL、每线程一个连接、`PRAGMA user_version` 做版本迁移、不引 ORM。迁移用 `executescript` 在 `Store.__init__` 里 `CREATE TABLE IF NOT EXISTS` + 版本号提升，等价于既有做法（db.py:139-141）。

```sql
CREATE TABLE IF NOT EXISTS api_keys (
  id         TEXT PRIMARY KEY,          -- uuid hex
  name       TEXT NOT NULL,             -- 展示名，可重复
  key_hash   TEXT NOT NULL UNIQUE,      -- sha256(plaintext)，永不存明文
  prefix     TEXT NOT NULL,             -- 明文前 8 位，如 kev_a1b2c3d4，列表展示用
  active     INTEGER NOT NULL DEFAULT 1,-- 1=启用 0=已撤销
  created_at TEXT NOT NULL,
  revoked_at TEXT                        -- NULL=未撤销
);
CREATE INDEX IF NOT EXISTS api_keys_hash_idx ON api_keys(key_hash);

CREATE TABLE IF NOT EXISTS usage_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  key_id       TEXT NOT NULL REFERENCES api_keys(id),
  endpoint     TEXT NOT NULL,           -- systemone | separate | permute | models
  method       TEXT NOT NULL,           -- POST | GET
  status       INTEGER NOT NULL,       -- 上游 HTTP 状态（代理侧错误记 0/502）
  input_tokens  INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  latency_ms   REAL NOT NULL,           -- 代理侧墙钟耗时（毫秒）
  ts           TEXT NOT NULL            -- UTC ISO
);
CREATE INDEX IF NOT EXISTS usage_log_key_ts_idx ON usage_log(key_id, ts);
CREATE INDEX IF NOT EXISTS usage_log_ts_idx     ON usage_log(ts);
```

设计取舍：
- **key 明文只在创建时返回一次**：`create_api_key` 生成 `kev_` + 32 hex 随机串，库里只存 `sha256` 与 `prefix`，列表页用 `prefix` 让人能辨认是哪个 key。撤销不可恢复（重新创建）。
- **`usage_log` 细粒度落行**：每次调用一行，汇总与时间序列都由 SQL 聚合，避免冗余字段；`key_id` 外键保证 key 删除/撤销后用量仍可追溯（撤销只置 `active=0`，不删行）。
- **`latency_ms` 由代理侧统一测量**：kev.serve 返回的 `latency_ms` 是模型批内时间（serve.py:186），与网络/代理开销不同；统计以代理墙钟为准，更贴近用户体感。`input_tokens`/`output_tokens` 优先取响应体 `usage`（serve 在 body 里给，serve.py:216），缺失（permute/models）记 0。

### 4.2 `Store` 新增方法

```python
# kev/console/db.py（新增）
def create_api_key(self, name: str) -> tuple[str, dict]:
    """生成 kev_<32hex>，返回 (明文 key, 行 dict)。明文只此一次可见。"""
def get_key_by_hash(self, key_hash: str) -> dict | None:
    """active=1 才返回；被撤销的返回 None（代理据此 401）。"""
def list_api_keys(self) -> list[dict]:
    """每行含累计：calls, input_tokens, output_tokens, last_used（来自 usage_log 聚合）。"""
def revoke_api_key(self, key_id: str) -> bool:
    """置 active=0, revoked_at=now；返回是否真改了一行。"""
def record_usage(self, *, key_id, endpoint, method, status, input_tokens, output_tokens, latency_ms) -> None:
    """INSERT usage_log 一行；独立 commit，不进调用方事务。"""
def usage_summary(self, from_ts: str | None, to_ts: str | None) -> list[dict]:
    """按 key 聚合：calls, input_tokens, output_tokens, avg_latency_ms, p99_latency_ms, last_used。"""
def usage_timeseries(self, key_id: str, from_ts: str | None, to_ts: str | None) -> list[dict]:
    """按天(date(ts)) 聚合：date, calls, input_tokens, output_tokens, avg_latency_ms。"""
```

- 密钥生成用 `secrets.token_hex(32)`；哈希用 `hashlib.sha256(key.encode()).hexdigest()`。
- p99 用 SQLite 近似：`PERCENTILE` 不存在，改用子查询取排序后第 `ceil(0.99*n)` 行（`ORDER BY latency_ms LIMIT 1 OFFSET n-1`），n 为分组计数。
- 聚合 SQL 用 `LEFT JOIN usage_log` 或 `WHERE key_id IN (...)` + `GROUP BY`，时间过滤用 `ts >= ? AND ts <= ?`（`from_ts`/`to_ts` 为 `None` 时跳过该条件）。

---

## 5. 后端 API 契约

在 `kev/console/app.py` 的 `create_app` 内新增，复用既有 `store()`、`_error`、项 `_now`/`_dumps`（来自 db 模块）与 `SECRET_NAMES`/`KEV_API_KEY` 读取。

```
管理
POST   /console/api/apikeys              创建 key（body: {name}）→ 返回 {id, name, key, prefix, created_at}
GET    /console/api/apikeys              列出（含累计用量）
DELETE /console/api/apikeys/{id}         撤销（404 若未知；409 若已撤销）

代理（核心接口）
POST   /console/api/kev/{path:path}      校验 key → 转发 kev.serve → 记录用量 → 透传
GET    /console/api/kev/{path:path}      同上（覆盖 /v1/models）

统计
GET    /console/api/usage?from=&to=      按 key 汇总（usage_summary）
GET    /console/api/usage/{key_id}?from=&to=  某 key 按天时间序列（usage_timeseries）
```

代理实现要点（`POST /console/api/kev/{path}`）。沿用现有 `app.py` 的**同步路由**风格（FastAPI 线程池执行），用 `requests` 同步转发；不引入 `httpx`/`async`：

```python
import hashlib, time
import requests
from fastapi import Request, Response

KEV_SERVE_URL = os.environ.get("KEV_SERVE_URL", "http://127.0.0.1:8008")
ADMIN_KEY = os.environ.get("KEV_API_KEY")   # 既有 SECRET_NAMES 之一

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def _ep(path: str) -> str:
    tail = path.rstrip("/").split("/")[-1]
    return {"systemone": "systemone", "separate": "separate",
            "permute": "permute", "models": "models"}.get(tail, tail)

@app.post("/console/api/kev/{path:path}")
def proxy_kev(path: str, request: Request):
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return _error("auth", "缺少 API Key", status=401, hint="Authorization: Bearer <key>")
    key = store().get_key_by_hash(_sha256(auth[7:].strip()))
    if key is None:
        return _error("auth", "API Key 无效或已撤销", status=401)
    body = request.body.read() if request.method == "POST" else None
    upstream = f"{KEV_SERVE_URL}/{path}"
    headers = {"content-type": request.headers.get("content-type", "application/json")}
    if ADMIN_KEY:
        headers["authorization"] = f"Bearer {ADMIN_KEY}"
    started = time.perf_counter()
    try:
        resp = requests.post(upstream, data=body, headers=headers,
                             params=request.url.query, timeout=300)
    except requests.RequestException:
        store().record_usage(key_id=key["id"], endpoint=_ep(path), method="POST",
                              status=502, input_tokens=0, output_tokens=0,
                              latency_ms=round((time.perf_counter() - started) * 1000, 1))
        return _error("upstream", "kev.serve 不可达", status=502)
    dt = round((time.perf_counter() - started) * 1000, 1)
    in_t, out_t = 0, 0
    try:
        payload = resp.json()
        usage = payload.get("usage") or {}
        in_t = int(usage.get("input_tokens", 0) or 0)
        out_t = int(usage.get("output_tokens", 0) or 0)
    except (ValueError, AttributeError):
        pass
    store().record_usage(key_id=key["id"], endpoint=_ep(path), method="POST",
                          status=resp.status_code, input_tokens=in_t, output_tokens=out_t, latency_ms=dt)
    return Response(content=resp.content, status_code=resp.status_code,
                    headers={"content-type": resp.headers.get("content-type", "application/json")})
```

- `_ep(path)`：`v1/systemone`→`systemone`，`v1/systemone/separate`→`separate`，`v1/systemone/permute`→`permute`，`v1/models`→`models`，其余取最后一段。
- 代理用 `requests` 同步转发（现有 `app.py` 路由是同步函数，跑在线程池里），不引入 `httpx`/`async`。`kev.console` 的 `pyproject`/依赖需含 `requests`（FastAPI 侧已常备，实施期确认）。
- **透传 body 而非重解析**：代理不校验 kev.serve 的请求体，直接转发原始字节，避免与 `kev/api.py` 的 `SystemOneRequest` 模型重复。kev.serve 自身做校验。
- 撤销的 key：`get_key_by_hash` 只返回 `active=1`，故立即 401，无需额外判断。
- 复用既有统一错误体（`_error`）与前端 `ApiError` 分派。
- GET 代理（`/console/api/kev/v1/models`）同理：转发 query、按 `_ep` 记 `models`，无 `usage` 故 token 记 0。

---

## 6. 前端

### 6.1 库与代理

- `src/lib/console.ts`：新增 `api.apikeys()`、`api.createApiKey(name)`、`api.revokeApiKey(id)`、`api.usageSummary(from,to)`、`api.usageTimeseries(keyId, from, to)`。复用现有 `call<T>` 与错误分派。
- `src/lib/kev.ts`：
  - `post` / `models` 改为打 `/api/console/kev/v1/...`（而非 `/kev/v1/...`）。
  - 每次请求从 `localStorage["kev_apikey"]` 读当前 key，注入 `Authorization: Bearer <key>`。
  - 若 localStorage 无 key：`systemOne`/`separate`/`permute`/`models` 抛一个清晰错误（提示「请先在控制台 API Keys 页创建并选择 key」），不静默失败。
  - 删除 `NEXT_PUBLIC_KEV_API_KEY` 相关行（kev.ts:32,36,48）：playground 不再持有管理 key（§12）。
- `next.config.ts`：`/kev/*` rewrite 保留作兜底，但 playground 主路径已切到 `/api/console/kev`（代理 route.ts 已通用转发 `/api/console/*`，无需改）。

### 6.2 路由与导航

```
playground/src/app/console/
├── layout.tsx              sidebar 新增两项
├── apikeys/page.tsx        ① API Key 管理
└── usage/page.tsx          ② 用量统计
```

`NAV`（`layout.tsx:10-17`）追加：
```ts
{ href: "/console/apikeys", key: "console.nav.apikeys" },
{ href: "/console/usage",    key: "console.nav.usage" },
```

### 6.3 ① API Keys 页（`/console/apikeys`）

- 顶部「创建」表单：输入名称（必填）→ `createApiKey(name)`。
- 创建成功弹 `sonner` 提示，**一次性显示明文 key**（等宽字体 + 复制按钮），并提示「仅此一次可见，请妥善保存」。
- 列表（表格）：`prefix` / 名称 / 状态（启用·撤销，badge）/ 创建时间 / 累计调用数 / 累计 token（in+out）/ 最后调用时间。
- 每行「撤销」按钮：二次确认（`AlertDialog`/`confirm`）→ `revokeApiKey(id)`；撤销后该行状态变「已撤销」，调用方立即 401。
- 数据用轻量轮询（`usePoll`，沿用现有 `usePoll`）。

### 6.4 ② 用量页（`/console/usage`）

- 顶部时间范围筛选：`7天 / 30天 / 全部`（改 `from/to` 传给 `usageSummary`）。
- 汇总表（每 key 一行）：调用数 / 输入 token / 输出 token / 平均耗时 / **p99 耗时** / 最后调用时间。点击某行展开（或进 `/console/usage/{id}`）看该 key 的按天时间序列。
- 时间序列图：复用现有 `playground/src/components/console/` 的图表手法（手写 SVG，零新依赖，见上一版 §11.3）。日序列数据形态是几十个点，画「调用数」与「token」两条折线（或柱+线）。chart 配色用 `globals.css` 已定义的 `--chart-1..5`。
- 若无 key 或无用量，显示空态提示（先去 API Keys 创建 key 并调用一次）。

### 6.5 playground 的 key 选择器

- 在 playground 主界面（`src/components/playground.tsx` 或 `src/app/layout.tsx`）顶部加一个轻量 key 选择器：`Dropdown`/`Select` 列出 `apikeys()` 得到的可用 key（启用状态），选定项写入 `localStorage["kev_apikey"]`。
- 默认无选中；首次使用引导用户去控制台创建。
- 选择器只存 key 明文到 localStorage（浏览器本地，非跨域下发）；符合「凭据不落地到服务端/库」要求（§12）。

### 6.6 i18n

- 文案加进 `src/components/console/strings.ts`（沿用 `{en, zh}` 形状、`t()` 单一入口）。
- 新增 key：`console.nav.apikeys` / `console.nav.usage` / `console.apikeys.*` / `console.usage.*`。

---

## 7. 安全与合规

| 类别 | 处理 |
| --- | --- |
| 用户 apikey 明文 | 只在创建响应里返回一次；库里只存 `sha256`；列表只回 `prefix` |
| 管理 key `KEV_API_KEY` | 仍只从控制台进程环境变量读，代理转发时注入；**永不**写库、不下发浏览器 |
| 撤销即时性 | `active=0` 后 `get_key_by_hash` 直接返回 None → 下次调用即 401，无需缓存失效 |
| 监听地址 | 控制台只绑 `127.0.0.1`；playground 同源代理，浏览器不发跨域请求 |
| playground 端 key | 存 `localStorage`（本地），不进 SQLite、不进 Network 之外的服务端 |
| 删除 `NEXT_PUBLIC_KEV_API_KEY` | 与上一版 §11.5 一致，消除 key 经构建产物公开泄露 |

**删除泄露点**：`src/lib/kev.ts:32` 的 `const KEV_API_KEY = process.env.NEXT_PUBLIC_KEV_API_KEY ?? ""` 及所有 `headers["authorization"] = Bearer ${KEV_API_KEY}` 必须删除；playground 改为带用户 key 打 `/api/console/kev`。

---

## 8. 仓库约定合规清单

`tests/test_conventions.py` 扫描 `kev/`。本次新增均在 `kev/console/`，须遵守：

| 规则 | 约束 |
| --- | --- |
| 文本 IO | 沿用 `kev.suite.read_json/write_json`；本功能无文件 IO，主要走 SQLite（现有 `db.py` 模式） |
| JSON 写 | 响应体用 `JSONResponse`，不手写 json 字符串；`api_keys.meta` 暂无 JSON 列（用标量列） |
| 环境变量 | 只读 `KEV_SERVE_URL`（新增）、`KEV_API_KEY`（既有 SECRET_NAMES）；不读 `KEV_DTYPE/...` 等受限变量 |
| 设备/指标 | 不涉及 |
| `kev/serve.py` 零改动 | **硬约束**：代理在 `kev.console`，`git diff --name-only` 断言 `kev/serve.py` 为空 |

---

## 9. 测试策略

| 层 | 覆盖 | 手法 |
| --- | --- | --- |
| 单元 | 密钥生成 + 哈希查询 | 造 key → 用明文能查到、明文前缀正确、撤销后查不到 |
| 单元 | 代理鉴权 | `TestClient` 打 `/console/api/kev/v1/systemone`：无 key→401、撤销 key→401、有效 key→转发并记录一行 usage_log |
| 单元 | 用量聚合 | 插若干 usage_log 行 → `usage_summary`/`usage_timeseries` 数值与 p99 正确 |
| 契约冻结 | `kev/serve.py` 零改动 | `git diff --name-only` 断言 |
| 前端 | kev.ts 路由 + key 注入 | 抽 `currentKey()` 纯函数；断言无 key 抛错、有 key 带 Bearer |
| 端到端 | 见下方人工清单 | 冒烟 |

**不写真跑推理的测试**：代理测试用假 kev.serve（monkeypatch `KEV_SERVE_URL` 到本地 stub，或 `TestClient` + 依赖覆写）。

### 9.1 人工验收清单

1. 控制台创建 key → 明文只显示一次、可复制；列表出现该 `prefix`。
2. playground 选该 key，发一次 `systemone` 调用成功；用量页该 key 出现 1 次调用 + 正确 token。
3. 撤销该 key → playground 再调用立即 401；用量历史仍在。
4. 外部 `curl -H "Authorization: Bearer <key>" POST /api/console/kev/v1/systemone` 成功并记录用量；带错误 key → 401。
5. 用量页切换 7天/30天/全部，时间序列图随筛选变化。
6. `git diff --name-only` 确认 `kev/serve.py` 为空；浏览器 Network 里无任何 key 明文落到服务端日志/库（仅 Authorization 头）。
7. 删除 `NEXT_PUBLIC_KEV_API_KEY` 后 `npm run build` 通过、`kev.ts` 调用走 `/api/console/kev`。

---

## 10. 主要风险

| 风险 | 严重度 | 缓解 |
| --- | --- | --- |
| 代理引入新依赖（httpx/requests）与现有同步路由风格冲突 | 低 | 用 `requests`（同步），贴合现有线程池路由；已在 executor 等用过同族 |
| 密钥哈希碰撞 / 前缀歧义 | 低 | 32 hex = 256 bit，`secrets.token_hex` 足够；`prefix` 仅展示不用于鉴权 |
| playground 改路径后旧 `/kev` 直连仍可用导致用量漏记 | 中 | 保留 `/kev` 仅作管理调试兜底；playground 主路径切 `/api/console/kev`，文档明确 |
| 用量表随时间膨胀 | 低 | 细粒度行；本期不做归档/聚合表（YAGNI），后续可加日聚合物化 |
| 撤销后 kev.serve 仍认管理 key | 无 | 代理转发的永远是管理 key；用户 key 仅在代理层校验，与 kev.serve 鉴权解耦 |

---

## 11. 开放问题（不阻塞实施，各带默认值）

1. **用量数据保留/归档**：是否按日聚合落物化表、是否设保留期？
   **默认**：本期不归档，细粒度行长期保留；后续若膨胀再加日聚合。
2. **key 选择器 UI 位置**：放 playground 顶部栏还是独立设置弹窗？
   **默认**：playground 顶栏 `Dropdown`，选项来自 `apikeys()`（仅启用项），选定写 `localStorage["kev_apikey"]`。
3. **代理是否同步转发 kev.serve 的流式/非 JSON 响应**：当前核心接口都是 JSON，无流式。
   **默认**：透传原始 `resp.content` + content-type；非 JSON（未来）也照透传，不解析。
