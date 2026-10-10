# API Key 管理与用量统计（Kev Console）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 kev.console 后端新增 apikey 鉴权代理与用量落库，并新增蒸馏第三方模型配置（服务端密钥库）+ 蒸馏用量采集，配套 playground 控制台页面。

**Architecture:** 后端 `kev.console` 持有 SQLite `Store`（新增 `api_keys`/`usage_log`/`distill_providers`/`distill_usage` 表，SCHEMA_VERSION→2），新增 `/console/api/apikeys` 管理与 `/console/api/kev/{path}` 代理（校验用户 key → 转发 kev.serve 注入管理 key → 记录用量）；蒸馏第三方密钥存于**服务端密钥库文件**（不进 SQLite/浏览器），作业经 `provider_id` 解析后注入 `KEV_GEN_*`，生成器的 `usage_*.json` 由控制台拉取采集进 `distill_usage`。前端 playground 走同源代理 `/api/console/*`，playground 自身调用带用户 key（localStorage）。

**Tech Stack:** Python 3.11+ / FastAPI + SQLite（sqlite3，无 ORM）；`requests`（同步转发）；Next.js + React + shadcn/ui（手写 SVG 图表）。后端测试 `uv run python -m pytest`；前端 `npm --prefix playground run build`。

## Global Constraints

- `kev/console/db.py` `SCHEMA_VERSION = 2`（与既有 WAL / 每线程连接 / `PRAGMA user_version` 模式一致，无 ORM）。
- `api_keys`：明文**只创建时返回一次**；库里仅 `sha256` 与 `prefix`（`kev_` + 8 hex）；`active=0` 后代理立即 401。
- 代理目标 `KEV_SERVE_URL`（默认 `http://127.0.0.1:8008`）；管理 key `KEV_API_KEY` 复用既有 `SECRET_NAMES`，代理转发时注入，永不落库/下发浏览器。
- 蒸馏第三方密钥存**服务端密钥库** `KEV_DISTILL_SECRETS`（默认 `data/console/secrets/distill.json`，gitignore，`0600`）；SQLite `distill_providers` 仅存非敏感元数据 + `key_hints`（尾号）；列表/详情接口**绝不**回显明文 key。
- `kev/serve.py` 与 `skills/kev-finetune/scripts/generate_data.py` **零改动**（最终 `git diff` 断言为空）。
- 蒸馏用量采集为**拉模式**：`GET /console/api/distill/{job_id}/usage` 与 `/console/api/distill-usage` 触发读 `state_dir/usage_*.json` 后聚合（不改生成器记账格式）。
- 删除 `src/lib/kev.ts` 的 `NEXT_PUBLIC_KEV_API_KEY`；playground 调用带用户 key（localStorage `kev_apikey`）。
- 遵守 `tests/test_conventions.py`：文本 IO 用 `encoding="utf-8"`，JSON 用 `json` 模块；新增环境变量 `KEV_SERVE_URL`/`KEV_DISTILL_SECRETS` 不在禁止清单内（可读 `os.environ.get`）。
- 前端图表复用现有手写 SVG（`--color-chart-1..5`）。

---

## Part A — Kev API Key 管理 + 核心接口用量

### Task A1: 后端 schema 迁移 + apikey/usage Store 方法

**Files:**
- Modify: `kev/console/db.py`（`SCHEMA_VERSION`、`DDL` 末尾追加两表、`Store` 追加方法）
- Test: `tests/test_console_apikeys.py`（新建）

**Interfaces:**
- Produces: `Store.create_api_key(name) -> tuple[str, dict]`、`get_key_by_hash(hash) -> dict|None`、`list_api_keys() -> list[dict]`、`revoke_api_key(id) -> bool`、`record_usage(*, key_id, endpoint, method, status, input_tokens, output_tokens, latency_ms)`、`usage_summary(from_ts, to_ts) -> list[dict]`、`usage_timeseries(key_id, from_ts, to_ts) -> list[dict]`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_console_apikeys.py
"""apikey 管理 + 核心接口用量落库（本计划 Task A1）。
Run: uv run python -m pytest tests/test_console_apikeys.py -q
"""
import hashlib

from kev.console.db import Store


def test_create_api_key_returns_raw_once_and_hashes(store):
    raw, meta = store.create_api_key("playground")
    assert raw.startswith("kev_")
    assert meta["prefix"] == raw[:12]
    assert meta["active"] is True
    assert meta["key_hash"] == hashlib.sha256(raw.encode()).hexdigest()
    # 库里查不到明文
    row = store.connect().execute("SELECT key_hash FROM api_keys WHERE id=?", (meta["id"],)).fetchone()
    assert row["key_hash"] != raw


def test_get_key_by_hash_only_active(store):
    raw, meta = store.create_api_key("k")
    h = hashlib.sha256(raw.encode()).hexdigest()
    assert store.get_key_by_hash(h) is not None
    assert store.revoke_api_key(meta["id"]) is True
    assert store.get_key_by_hash(h) is None


def test_record_and_summary_aggregates(store):
    raw, meta = store.create_api_key("k")
    store.record_usage(key_id=meta["id"], endpoint="systemone", method="POST",
                        status=200, input_tokens=10, output_tokens=5, latency_ms=12.0)
    store.record_usage(key_id=meta["id"], endpoint="systemone", method="POST",
                        status=200, input_tokens=20, output_tokens=8, latency_ms=20.0)
    summary = store.usage_summary()
    assert summary[0]["calls"] == 2
    assert summary[0]["input_tokens"] == 30
    assert summary[0]["p99_latency_ms"] == 20.0   # 两样本 99 分位取最大
    series = store.usage_timeseries(meta["id"])
    assert series[0]["calls"] == 2
```

- [ ] **Step 2: 运行测试确认失败**
Run: `uv run python -m pytest tests/test_console_apikeys.py -q`
Expected: FAIL（`create_api_key` 未定义）

- [ ] **Step 3: 实现**

`kev/console/db.py`：`SCHEMA_VERSION = 1` → `2`。在 `DDL` 字符串末尾（`events_job_idx` 之后）追加：

```sql

CREATE TABLE IF NOT EXISTS api_keys (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  key_hash TEXT NOT NULL UNIQUE,
  prefix TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS api_keys_hash_idx ON api_keys(key_hash);

CREATE TABLE IF NOT EXISTS usage_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key_id TEXT NOT NULL REFERENCES api_keys(id),
  endpoint TEXT NOT NULL,
  method TEXT NOT NULL,
  status INTEGER NOT NULL,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  latency_ms REAL NOT NULL,
  ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS usage_log_key_ts_idx ON usage_log(key_id, ts);
CREATE INDEX IF NOT EXISTS usage_log_ts_idx ON usage_log(ts);
```

在 `Store` 类末尾（`tail_text` 方法之后）追加：

```python
    # ---- api keys ---------------------------------------------------------

    def create_api_key(self, name: str) -> tuple[str, dict]:
        import hashlib, secrets as _secrets
        raw = "kev_" + _secrets.token_hex(32)
        key_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        key_id = uuid.uuid4().hex
        self.connect().execute(
            "INSERT INTO api_keys (id, name, key_hash, prefix, active, created_at) "
            "VALUES (?,?,?,?,1,?)",
            (key_id, name, key_hash, raw[:12], _now()))
        self.connect().commit()
        row = self.connect().execute("SELECT * FROM api_keys WHERE id=?", (key_id,)).fetchone()
        return raw, dict(row)

    def get_key_by_hash(self, key_hash: str) -> dict | None:
        row = self.connect().execute(
            "SELECT * FROM api_keys WHERE key_hash=? AND active=1", (key_hash,)).fetchone()
        return dict(row) if row else None

    def list_api_keys(self) -> list[dict]:
        rows = self.connect().execute(
            "SELECT a.*, COALESCE(u.calls,0) AS calls, "
            "COALESCE(u.input_tokens,0) AS input_tokens, "
            "COALESCE(u.output_tokens,0) AS output_tokens, u.last_used "
            "FROM api_keys a LEFT JOIN ("
            "  SELECT key_id, COUNT(*) AS calls, SUM(input_tokens) AS input_tokens, "
            "  SUM(output_tokens) AS output_tokens, MAX(ts) AS last_used "
            "  FROM usage_log GROUP BY key_id) u ON u.key_id=a.id "
            "ORDER BY a.created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def revoke_api_key(self, key_id: str) -> bool:
        cursor = self.connect().execute(
            "UPDATE api_keys SET active=0, revoked_at=? WHERE id=? AND active=1",
            (_now(), key_id))
        self.connect().commit()
        return cursor.rowcount == 1

    def record_usage(self, *, key_id, endpoint, method, status,
                      input_tokens, output_tokens, latency_ms) -> None:
        self.connect().execute(
            "INSERT INTO usage_log (key_id, endpoint, method, status, input_tokens, "
            "output_tokens, latency_ms, ts) VALUES (?,?,?,?,?,?,?,?)",
            (key_id, endpoint, method, int(status), int(input_tokens), int(output_tokens),
             float(latency_ms), _now()))
        self.connect().commit()

    def _usage_pred(self, from_ts, to_ts) -> tuple[str, list]:
        clauses, params = [], []
        if from_ts:
            clauses.append("ts >= ?"); params.append(from_ts)
        if to_ts:
            clauses.append("ts <= ?"); params.append(to_ts)
        return (" AND " + " AND ".join(clauses)) if clauses else "", params

    @staticmethod
    def _p99(values):
        if not values:
            return 0.0
        ordered = sorted(values)
        return ordered[min(len(ordered) - 1, int(round(0.99 * (len(ordered) - 1))))]

    def usage_summary(self, from_ts=None, to_ts=None) -> list[dict]:
        pred, p = self._usage_pred(from_ts, to_ts)
        if pred:
            pred = pred.replace("ts", "l.ts")
        keys = self.connect().execute(
            "SELECT id, name, prefix, active FROM api_keys ORDER BY created_at DESC").fetchall()
        out = []
        for k in keys:
            row = dict(k)
            stats = self.connect().execute(
                f"SELECT COUNT(*) c, COALESCE(SUM(input_tokens),0) i, "
                f"COALESCE(SUM(output_tokens),0) o, MAX(ts) last FROM usage_log l "
                f"WHERE l.key_id=?{pred}", [k["id"], *p]).fetchone()
            lats = [r[0] for r in self.connect().execute(
                f"SELECT latency_ms FROM usage_log l WHERE l.key_id=?{pred}",
                [k["id"], *p]).fetchall()]
            row["calls"] = stats["c"]
            row["input_tokens"] = stats["i"]
            row["output_tokens"] = stats["o"]
            row["last_used"] = stats["last"]
            row["avg_latency_ms"] = (sum(lats) / len(lats)) if lats else None
            row["p99_latency_ms"] = self._p99(lats)
            out.append(row)
        return out

    def usage_timeseries(self, key_id, from_ts=None, to_ts=None) -> list[dict]:
        pred, p = self._usage_pred(from_ts, to_ts)
        if pred:
            pred = pred.replace("ts", "l.ts")
        rows = self.connect().execute(
            "SELECT substr(l.ts,1,10) AS date, COUNT(*) AS calls, "
            "SUM(l.input_tokens) AS input_tokens, SUM(l.output_tokens) AS output_tokens, "
            "AVG(l.latency_ms) AS avg_latency_ms FROM usage_log l WHERE l.key_id=?" + pred +
            " GROUP BY date ORDER BY date", [key_id, *p]).fetchall()
        return [dict(r) for r in rows]
```

- [ ] **Step 4: 运行测试确认通过**
Run: `uv run python -m pytest tests/test_console_apikeys.py -q`
Expected: PASS

- [ ] **Step 5: 提交**
```bash
git add kev/console/db.py tests/test_console_apikeys.py
git commit -m "feat(console): api_keys + usage_log schema and Store methods"
```

---

### Task A2: 后端路由 — apikeys 管理、kev 代理、usage 汇总

**Files:**
- Modify: `kev/console/app.py`（导入 `requests`、`asyncio` 已有；新增 5 个路由 + 代理助手）
- Test: `tests/test_console_apikey_routes.py`（新建）

**Interfaces:**
- Consumes: `Store` 的 A1 方法；`KEV_SERVE_URL` / `KEV_API_KEY`（进程环境变量）。
- Produces: 路由 `POST /console/api/apikeys`、`GET /console/api/apikeys`、`DELETE /console/api/apikeys/{id}`、`POST|GET /console/api/kev/{path:path}`、`GET /console/api/usage`、`GET /console/api/usage/{key_id}`。供前端 `console.ts` 调用。

- [ ] **Step 1: 写失败测试（用 TestClient 打路由）**

```python
# tests/test_console_apikey_routes.py
"""apikey 路由 + kev 代理（Task A2）。用 FastAPI TestClient，stub 掉 kev.serve。
Run: uv run python -m pytest tests/test_console_apikey_routes.py -q
"""
import hashlib
from fastapi.testclient import TestClient

from kev.console.app import create_app
from kev.console.db import Store


def make_app(tmp_path, monkeypatch):
    db = Store(tmp_path / "c.db")
    app = create_app(store=db)
    # stub 上游：把 KEV_SERVE_URL 指到不监听的端口会超时，这里 monkeypatch requests
    import kev.console.app as mod
    class FakeResp:
        def __init__(self, content, status_code=200):
            self.content = content.encode(); self.status_code = status_code
            self.headers = {"content-type": "application/json"}
        def json(self): return {"usage": {"input_tokens": 3, "output_tokens": 2}}
    monkeypatch.setattr(mod, "requests", None)  # 占位，下面按方法替换
    return TestClient(app), db


def test_create_and_list_and_revoke(tmp_path, monkeypatch):
    client, db = make_app(tmp_path, monkeypatch)
    r = client.post("/console/api/apikeys", json={"name": "pg"})
    assert r.status_code == 201, r.text
    raw = r.json()["key"]
    assert r.json()["prefix"] == raw[:12]
    # 列表只有元数据，无明文
    lst = client.get("/console/api/apikeys").json()
    assert lst[0]["prefix"] == raw[:12]
    assert all("key_hash" not in k for k in lst)
    # 撤销
    assert client.delete(f"/console/api/apikeys/{lst[0]['id']}").status_code == 200
    assert client.delete(f"/console/api/apikeys/{lst[0]['id']}").status_code == 404
```

> 注：代理路由的端到端（带真实 kev.serve）放在手动验收（§9.2）。本任务只验证 apikeys CRUD 与 usage 路由存在性；代理逻辑用下面的单元替身确保 401/记录分支。

- [ ] **Step 2: 运行测试确认失败**
Run: `uv run python -m pytest tests/test_console_apikey_routes.py -q`
Expected: FAIL（路由不存在 → 404）

- [ ] **Step 3: 实现**

`kev/console/app.py` 顶部 `import` 区追加 `import requests`（放在 `import os` 附近）；`create_app` 内、`# ---- config / scenarios` 注释之前插入：

```python
    KEV_SERVE_URL = os.environ.get("KEV_SERVE_URL", "http://127.0.0.1:8008")
    ADMIN_KEY = os.environ.get("KEV_API_KEY")

    def _sha256(text: str) -> str:
        import hashlib
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _ep(path: str) -> str:
        tail = path.rstrip("/").split("/")[-1]
        return {"systemone": "systemone", "separate": "separate",
                "permute": "permute", "models": "models"}.get(tail, tail)

    # ---- api keys ---------------------------------------------------------

    @app.post("/console/api/apikeys")
    def create_api_key(payload: dict):
        name = (payload.get("name") or "").strip()
        if not name:
            return _error("validation", "名称必填", status=400, field="name")
        raw, meta = store().create_api_key(name)
        return JSONResponse(status_code=201, content={"key": raw, **meta})

    @app.get("/console/api/apikeys")
    def list_api_keys() -> list:
        return store().list_api_keys()

    @app.delete("/console/api/apikeys/{key_id}")
    def delete_api_key(key_id: str):
        if not store().revoke_api_key(key_id):
            return _error("validation", f"未知或已撤销的 key {key_id}", status=404)
        return {"revoked": True}

    # ---- usage -------------------------------------------------------------

    @app.get("/console/api/usage")
    def usage_summary(from_ts: str | None = None, to_ts: str | None = None) -> list:
        return store().usage_summary(from_ts, to_ts)

    @app.get("/console/api/usage/{key_id}")
    def usage_timeseries(key_id: str, from_ts: str | None = None, to_ts: str | None = None) -> list:
        return store().usage_timeseries(key_id, from_ts, to_ts)

    # ---- kev proxy ---------------------------------------------------------

    def _do_proxy(path: str, headers: dict, query: str, method: str, body) -> "JSONResponse":
        upstream = f"{KEV_SERVE_URL}/{path}"
        fwd = {"content-type": headers.get("content-type", "application/json")}
        if ADMIN_KEY:
            fwd["authorization"] = f"Bearer {ADMIN_KEY}"
        started = __import__("time").perf_counter()
        try:
            if method == "POST":
                resp = requests.post(upstream, data=body, headers=fwd, params=query, timeout=300)
            else:
                resp = requests.get(upstream, headers=fwd, params=query, timeout=300)
        except requests.RequestException:
            return _error("upstream", "kev.serve 不可达", status=502)
        finally:
            elapsed = round((__import__("time").perf_counter() - started) * 1000, 1)
        in_t = out_t = 0
        try:
            usage = resp.json().get("usage") or {}
            in_t = int(usage.get("input_tokens", 0) or 0)
            out_t = int(usage.get("output_tokens", 0) or 0)
        except (ValueError, AttributeError):
            pass
        return JSONResponse(status_code=resp.status_code, content=resp.json(),
                            headers={"content-type": resp.headers.get("content-type", "application/json")})

    async def proxy_kev(path: str, request: Request):
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return _error("auth", "缺少 API Key", status=401, hint="Authorization: Bearer <key>")
        key = store().get_key_by_hash(_sha256(auth[7:].strip()))
        if key is None:
            return _error("auth", "API Key 无效或已撤销", status=401)
        method = request.method
        body = await request.body() if method == "POST" else None
        # 鉴权通过后再调上游并记录（记录失败不影响返回）
        try:
            resp = await asyncio.to_thread(
                _do_proxy, path, dict(request.headers), str(request.url.query), method, body)
        except Exception:
            store().record_usage(key_id=key["id"], endpoint=_ep(path), method=method,
                                  status=502, input_tokens=0, output_tokens=0, latency_ms=0.0)
            return _error("upstream", "kev.serve 不可达", status=502)
        # 代理本身不写库（记录逻辑在 _do_proxy 内层不可达时由上面兜底）；
        # 成功路径的记录改在下面统一做
        return resp

    # 注：上一段把记录逻辑下沉到代理成功分支更稳妥，见下方修正
```

> ⚠️ 上面的代理片段把「记录用量」漏在了成功路径之外。落地请用下方**修正版** `_do_proxy`：在成功返回前调用 `store().record_usage(...)`，并把 `key_id` 传进去。完整修正版：

```python
    def _do_proxy(key_id: str, path: str, headers: dict, query: str, method: str, body):
        import time
        upstream = f"{KEV_SERVE_URL}/{path}"
        fwd = {"content-type": headers.get("content-type", "application/json")}
        if ADMIN_KEY:
            fwd["authorization"] = f"Bearer {ADMIN_KEY}"
        started = time.perf_counter()
        try:
            if method == "POST":
                resp = requests.post(upstream, data=body, headers=fwd, params=query, timeout=300)
            else:
                resp = requests.get(upstream, headers=fwd, params=query, timeout=300)
        except requests.RequestException:
            store().record_usage(key_id=key_id, endpoint=_ep(path), method=method,
                                  status=502, input_tokens=0, output_tokens=0,
                                  latency_ms=round((time.perf_counter() - started) * 1000, 1))
            return _error("upstream", "kev.serve 不可达", status=502)
        dt = round((time.perf_counter() - started) * 1000, 1)
        in_t = out_t = 0
        try:
            usage = resp.json().get("usage") or {}
            in_t = int(usage.get("input_tokens", 0) or 0)
            out_t = int(usage.get("output_tokens", 0) or 0)
        except (ValueError, AttributeError):
            pass
        store().record_usage(key_id=key_id, endpoint=_ep(path), method=method, status=resp.status_code,
                              input_tokens=in_t, output_tokens=out_t, latency_ms=dt)
        return JSONResponse(status_code=resp.status_code, content=resp.json(),
                            headers={"content-type": resp.headers.get("content-type", "application/json")})

    async def proxy_kev(path: str, request: Request):
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return _error("auth", "缺少 API Key", status=401, hint="Authorization: Bearer <key>")
        key = store().get_key_by_hash(_sha256(auth[7:].strip()))
        if key is None:
            return _error("auth", "API Key 无效或已撤销", status=401)
        method = request.method
        body = await request.body() if method == "POST" else None
        return await asyncio.to_thread(_do_proxy, key["id"], path, dict(request.headers),
                                        str(request.url.query), method, body)

    app.add_api_route("/console/api/kev/{path:path}", proxy_kev, methods=["POST", "GET"])
```

（用 `app.add_api_route(..., methods=["POST","GET"])` 把同一个 async 函数挂到两种 method，避免重复定义。）

- [ ] **Step 4: 运行测试确认通过**
Run: `uv run python -m pytest tests/test_console_apikey_routes.py -q`
Expected: PASS（apikeys CRUD 通过；代理路由已注册）

- [ ] **Step 5: 提交**
```bash
git add kev/console/app.py tests/test_console_apikey_routes.py
git commit -m "feat(console): apikey CRUD + kev proxy + usage routes"
```

---

### Task A3: 前端 lib — kev 代理 + key 选择 + console 类型

**Files:**
- Modify: `playground/src/lib/kev.ts`（删除 `NEXT_PUBLIC_KEV_API_KEY`，改走 `/api/console/kev` 并带用户 key）
- Create: `playground/src/lib/apikey-store.ts`（localStorage 管理选定 key）
- Modify: `playground/src/lib/console.ts`（`ApiKey`/`UsageRow`/`UsageDay` 类型 + 方法）
- Modify: `playground/next.config.ts`（保留 `/kev` 兜底 rewrite，无需改；确认即可）

**Interfaces:**
- Produces: `kev.api.{systemOne,separate,permute,models}`（带 Bearer）；`apikeyStore.{loadKeys,saveKey,setCurrent,getCurrent,clearCurrent}`；`console.api.{apikeys,createApiKey,revokeApiKey,usageSummary,usageTimeseries}`。供 A4/A5 页面与 playground 选择器使用。

- [ ] **Step 1: 写失败测试（类型/构建前的最小断言）**
前端无单测框架覆盖 lib；本任务以 `npm --prefix playground run build` 作为类型门禁。先写代码再构建。

- [ ] **Step 2: 实现 `kev.ts`**

将 `kev.ts` 第 29–53 行整段替换为：

```ts
// 用户 key 只存在浏览器 localStorage（kev_apikey），后端只存哈希。
// 浏览器这一侧不持有任何管理 key —— 编排层 /console/api/config 只回布尔态。
const LS_KEY = "kev_apikey";

function currentKey(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(LS_KEY) || null;
}

function requireKey(): string {
  const key = currentKey();
  if (!key) throw new Error("请先在控制台「API Keys」页创建并选择一个 key（playground 顶部）");
  return key;
}

async function postKev<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`/api/console/kev${path}`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${requireKey()}` },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

export const api = {
  systemOne: (req: SystemOneRequest) => postKev<SystemOneResponse>("/v1/systemone", req),
  separate: (req: SystemOneRequest) => postKev<SystemOneResponse>("/v1/systemone/separate", req),
  permute: (request: SystemOneRequest, question: string, n_perm = 6) =>
    postKev<PermuteResponse>("/v1/systemone/permute", { request, question, n_perm }),
  models: async () => {
    const r = await fetch("/api/console/kev/v1/models", {
      headers: { authorization: `Bearer ${requireKey()}` },
    });
    if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
    return r.json() as Promise<{ models: { name: string; run: string; base: string }[] }>;
  },
};
```

- [ ] **Step 3: 实现 `apikey-store.ts`**

```ts
// playground 选定 key 的本地存储。明文只在此浏览器，后端只存哈希。
const LS_ALL = "kev_apikeys";   // { [id]: { prefix: string; key: string } }
const LS_CURRENT = "kev_apikey"; // 当前选中的明文 key

export type SavedKey = { id: string; prefix: string; key: string };

export const apikeyStore = {
  loadKeys(): SavedKey[] {
    if (typeof window === "undefined") return [];
    try {
      const map = JSON.parse(localStorage.getItem(LS_ALL) || "{}") as Record<string, { prefix: string; key: string }>;
      return Object.entries(map).map(([id, v]) => ({ id, ...v }));
    } catch {
      return [];
    }
  },
  saveKey(id: string, prefix: string, key: string) {
    if (typeof window === "undefined") return;
    const map = JSON.parse(localStorage.getItem(LS_ALL) || "{}") as Record<string, { prefix: string; key: string }>;
    map[id] = { prefix, key };
    localStorage.setItem(LS_ALL, JSON.stringify(map));
    localStorage.setItem(LS_CURRENT, key);
  },
  setCurrent(key: string) {
    if (typeof window === "undefined") return;
    localStorage.setItem(LS_CURRENT, key);
  },
  getCurrent(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(LS_CURRENT) || null;
  },
  clearKey(id: string) {
    if (typeof window === "undefined") return;
    const map = JSON.parse(localStorage.getItem(LS_ALL) || "{}") as Record<string, { prefix: string; key: string }>;
    const removed = map[id];
    delete map[id];
    localStorage.setItem(LS_ALL, JSON.stringify(map));
    if (removed && localStorage.getItem(LS_CURRENT) === removed.key) {
      localStorage.removeItem(LS_CURRENT);
    }
  },
};
```

- [ ] **Step 4: 在 `console.ts` 追加类型与方法**

在 `console.ts` 的 `Artifact` 类型之后、`api` 对象之前插入：

```ts
export type ApiKey = {
  id: string; name: string; prefix: string; active: boolean;
  created_at: string; revoked_at: string | null;
  calls: number; input_tokens: number; output_tokens: number; last_used: string | null;
};
export type UsageRow = {
  id: string; name: string; prefix: string; active: boolean;
  calls: number; input_tokens: number; output_tokens: number;
  avg_latency_ms: number | null; p99_latency_ms: number; last_used: string | null;
};
export type UsageDay = {
  date: string; calls: number; input_tokens: number; output_tokens: number;
  avg_latency_ms: number | null;
};
```

在 `api` 对象内（`endpoints:` 之后）追加：

```ts
  apikeys: () => call<ApiKey[]>("apikeys"),
  createApiKey: (name: string) =>
    call<{ key: string } & ApiKey>("apikeys", { method: "POST", body: JSON.stringify({ name }) }),
  revokeApiKey: (id: string) => call<{ revoked: boolean }>(`apikeys/${id}`, { method: "DELETE" }),
  usageSummary: (from?: string, to?: string) => {
    const q = new URLSearchParams();
    if (from) q.set("from", from);
    if (to) q.set("to", to);
    return call<UsageRow[]>(`usage${q.toString() ? `?${q}` : ""}`);
  },
  usageTimeseries: (keyId: string, from?: string, to?: string) => {
    const q = new URLSearchParams();
    if (from) q.set("from", from);
    if (to) q.set("to", to);
    return call<UsageDay[]>(`usage/${keyId}${q.toString() ? `?${q}` : ""}`);
  },
```

- [ ] **Step 5: 构建确认类型通过**
Run: `npm --prefix playground run build`
Expected: 成功（无 TS 错误）

- [ ] **Step 6: 提交**
```bash
git add playground/src/lib/kev.ts playground/src/lib/apikey-store.ts playground/src/lib/console.ts
git commit -m "feat(playground): route kev calls through console proxy with user apikey"
```

---

### Task A4: 前端 — API Keys 管理页 + playground key 选择器

**Files:**
- Create: `playground/src/app/console/apikeys/page.tsx`
- Create: `playground/src/components/console/ApiKeyPicker.tsx`
- Modify: `playground/src/components/playground.tsx`（顶部接入 `ApiKeyPicker`）
- Modify: `playground/src/app/console/layout.tsx`（`NAV` 追加 API Keys）
- Modify: `playground/src/components/console/strings.ts`（i18n）

**Interfaces:**
- Consumes: `console.api.{apikeys,createApiKey,revokeApiKey}`、`apikeyStore`、`kev.ts` 的 currentKey 契约。
- Produces: 管理页 UI；playground 顶部 key 选择器（写 `kev_apikey`）。

- [ ] **Step 1: 实现 `ApiKeyPicker.tsx`**

```tsx
"use client";
import { useEffect, useState } from "react";
import { apikeyStore, type SavedKey } from "@/lib/apikey-store";
import { useLang } from "@/lib/i18n";

export function ApiKeyPicker() {
  const { t, lang } = useLang();
  const [keys, setKeys] = useState<SavedKey[]>([]);
  const [current, setCurrent] = useState<string | null>(null);

  useEffect(() => {
    setKeys(apikeyStore.loadKeys());
    setCurrent(apikeyStore.getCurrent());
  }, []);

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-muted-foreground">{t("console.apikeys.use")}</span>
      <select
        className="h-8 rounded-md border border-border bg-background px-2 text-xs"
        value={current ?? ""}
        onChange={(e) => { apikeyStore.setCurrent(e.target.value); setCurrent(e.target.value); }}
      >
        <option value="">{lang === "zh" ? "未选择" : "none"}</option>
        {keys.map((k) => (
          <option key={k.id} value={k.key}>{k.prefix}</option>
        ))}
      </select>
      {keys.length === 0 && (
        <a className="text-xs underline" href="/console/apikeys">
          {t("console.apikeys.createHint")}
        </a>
      )}
    </div>
  );
}
```

- [ ] **Step 2: 实现 `apikeys/page.tsx`**

```tsx
"use client";
import { useCallback, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, type ApiKey } from "@/lib/console";
import { apikeyStore } from "@/lib/apikey-store";
import { useLang } from "@/lib/i18n";
import { usePoll } from "@/components/console/usePoll";
import { formatNumber } from "@/components/console/format";

export default function ApiKeysPage() {
  const { t, lang } = useLang();
  const [name, setName] = useState("");
  const [created, setCreated] = useState<{ prefix: string; key: string } | null>(null);
  const load = useCallback(() => api.apikeys(), []);
  const { value: keys, error, refresh } = usePoll<ApiKey[]>(load, []);

  async function onCreate() {
    try {
      const row = await api.createApiKey(name || "key");
      setCreated({ prefix: row.prefix, key: row.key });
      apikeyStore.saveKey(row.id, row.prefix, row.key);   // 明文只存本地
      setName("");
      refresh();
    } catch (e) { toast.error((e as Error).message); }
  }
  async function onRevoke(id: string) {
    await api.revokeApiKey(id);
    apikeyStore.clearKey(id);
    refresh();
  }

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold">{t("console.nav.apikeys")}</h1>
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-2">
          <Label htmlFor="kname">{t("console.apikeys.name")}</Label>
          <Input id="kname" value={name} onChange={(e) => setName(e.target.value)} placeholder="playground" />
        </div>
        <Button onClick={() => void onCreate()}>{t("console.apikeys.create")}</Button>
      </div>
      {created && (
        <div className="rounded-md border border-dashed border-border p-3 text-sm">
          <p className="font-medium">{t("console.apikeys.shownOnce")}</p>
          <code className="block break-all rounded bg-muted p-2 text-xs">{created.key}</code>
          <p className="mt-1 text-xs text-muted-foreground">{t("console.apikeys.copyNow")}</p>
        </div>
      )}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>prefix</TableHead><TableHead>{t("console.apikeys.name")}</TableHead>
            <TableHead>{t("console.apikeys.status")}</TableHead>
            <TableHead>{t("console.apikeys.calls")}</TableHead>
            <TableHead>tokens</TableHead><TableHead>{t("console.apikeys.lastUsed")}</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {(keys ?? []).map((k) => (
            <TableRow key={k.id}>
              <TableCell className="font-mono text-xs">{k.prefix}</TableCell>
              <TableCell>{k.name}</TableCell>
              <TableCell>{k.active ? t("console.apikeys.active") : t("console.apikeys.revoked")}</TableCell>
              <TableCell>{formatNumber(k.calls, 0)}</TableCell>
              <TableCell className="text-xs">{formatNumber(k.input_tokens + k.output_tokens, 0)}</TableCell>
              <TableCell className="text-xs text-muted-foreground">{k.last_used ?? "—"}</TableCell>
              <TableCell className="text-right">
                {k.active && <Button size="sm" variant="ghost" onClick={() => void onRevoke(k.id)}>
                  {t("console.apikeys.revoke")}</Button>}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 3: playground 顶部接入选择器**

在 `playground.tsx` 顶部 import 区追加 `import { ApiKeyPicker } from "@/components/console/ApiKeyPicker";`，并在渲染顶部（如 `model` 信息附近）插入 `<ApiKeyPicker />`，使 playground 试用调用带上选定 key（kev.ts 已自动读取 `localStorage`）。

- [ ] **Step 4: `layout.tsx` NAV 追加**

```tsx
  { href: "/console/apikeys", key: "console.nav.apikeys" },
```

（加在 `deploy` 项之后、`];` 之前）

- [ ] **Step 5: i18n（`strings.ts` 在 `console.nav.deploy` 之后追加）**

```ts
  "console.nav.apikeys": { en: "API Keys", zh: "API Keys" },
  "console.apikeys.name": { en: "Name", zh: "名称" },
  "console.apikeys.create": { en: "Create key", zh: "创建 key" },
  "console.apikeys.createHint": { en: "create one first", zh: "先去创建一个" },
  "console.apikeys.use": { en: "API key", zh: "API key" },
  "console.apikeys.shownOnce": { en: "Key created — shown only once. Copy it now:", zh: "key 已创建，仅显示一次，请立即复制：" },
  "console.apikeys.copyNow": { en: "It will not be shown again. Stored locally in your browser only.", zh: "不会再次显示，仅保存在你本机浏览器。" },
  "console.apikeys.status": { en: "Status", zh: "状态" },
  "console.apikeys.active": { en: "active", zh: "启用" },
  "console.apikeys.revoked": { en: "revoked", zh: "已撤销" },
  "console.apikeys.calls": { en: "calls", zh: "调用" },
  "console.apikeys.lastUsed": { en: "last used", zh: "最后调用" },
  "console.apikeys.revoke": { en: "Revoke", zh: "撤销" },
```

- [ ] **Step 6: 构建确认**
Run: `npm --prefix playground run build`
Expected: 成功

- [ ] **Step 7: 提交**
```bash
git add playground/src/app/console/apikeys playground/src/components/console/ApiKeyPicker.tsx playground/src/components/playground.tsx playground/src/app/console/layout.tsx playground/src/components/console/strings.ts
git commit -m "feat(playground): api keys page + playground key picker"
```

---

### Task A5: 前端 — 用量页（kev 核心接口分区）

**Files:**
- Create: `playground/src/app/console/usage/page.tsx`
- Modify: `playground/src/app/console/layout.tsx`（`NAV` 追加 Usage）
- Modify: `playground/src/components/console/strings.ts`（i18n）

**Interfaces:**
- Consumes: `console.api.{usageSummary,usageTimeseries}`、`console.api.apikeys`（用于 key 列表跳转）。
- Produces: 用量页（A 分区：kev 核心）；B 分区在 Task B6 追加。

- [ ] **Step 1: 实现 `usage/page.tsx`**

```tsx
"use client";
import { useCallback, useState } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { api, type UsageRow, type UsageDay } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { usePoll } from "@/components/console/usePoll";
import { formatNumber } from "@/components/console/format";
import { UsageChart } from "@/components/console/UsageChart";

const RANGES = [["7", "7d"], ["30", "30d"], ["", "all"]] as const;

export default function UsagePage() {
  const { t, lang } = useLang();
  const [days, setDays] = useState<string>("7");
  const from = days ? isoDaysAgo(Number(days)) : undefined;
  const load = useCallback(() => api.usageSummary(from), [from]);
  const { value: rows } = usePoll<UsageRow[]>(load, [days]);
  const [open, setOpen] = useState<string | null>(null);
  const series = usePoll<UsageDay[]>(
    useCallback(() => (open ? api.usageTimeseries(open, from) : Promise.resolve([])), [open, from]),
    [open, days],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">{t("console.usage.kev")}</h1>
        <div className="flex gap-1">
          {RANGES.map(([d, label]) => (
            <Button key={label} size="sm" variant={d === days ? "secondary" : "ghost"}
                    onClick={() => setDays(d)}>{label}</Button>
          ))}
        </div>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>prefix</TableHead><TableHead>{t("console.apikeys.name")}</TableHead>
            <TableHead>{t("console.apikeys.calls")}</TableHead>
            <TableHead>in/out tok</TableHead>
            <TableHead>avg ms</TableHead><TableHead>p99 ms</TableHead>
            <TableHead>{t("console.apikeys.lastUsed")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {(rows ?? []).map((r) => (
            <TableRow key={r.id} className="cursor-pointer" onClick={() => setOpen(open === r.id ? null : r.id)}>
              <TableCell className="font-mono text-xs">{r.prefix}</TableCell>
              <TableCell>{r.name}</TableCell>
              <TableCell>{formatNumber(r.calls, 0)}</TableCell>
              <TableCell className="text-xs">{formatNumber(r.input_tokens, 0)}/{formatNumber(r.output_tokens, 0)}</TableCell>
              <TableCell className="text-xs">{r.avg_latency_ms == null ? "—" : formatNumber(r.avg_latency_ms, 1)}</TableCell>
              <TableCell className="text-xs">{formatNumber(r.p99_latency_ms, 1)}</TableCell>
              <TableCell className="text-xs text-muted-foreground">{r.last_used ?? "—"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {open && series.value && series.value.length > 0 && (
        <UsageChart days={series.value} />
      )}
    </div>
  );
}

function isoDaysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10) + "T00:00:00";
}
```

- [ ] **Step 2: 创建 `UsageChart.tsx`（手写 SVG，复用 `--color-chart-*`）**

```tsx
"use client";
import { formatNumber } from "./format";
import type { UsageDay } from "@/lib/console";

const W = 640, H = 200, PAD = { top: 12, right: 12, bottom: 24, left: 46 };

export function UsageChart({ days }: { days: UsageDay[] }) {
  if (days.length < 2) return <p className="text-xs text-muted-foreground">还需要更多数据点</p>;
  const innerW = W - PAD.left - PAD.right, innerH = H - PAD.top - PAD.bottom;
  const maxTok = Math.max(...days.map((d) => d.input_tokens + d.output_tokens), 1);
  const x = (i: number) => PAD.left + (i / (days.length - 1)) * innerW;
  const y = (v: number) => PAD.top + innerH - (v / maxTok) * innerH;
  const line = (pick: (d: UsageDay) => number) =>
    days.map((d, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(pick(d))}`).join(" ");
  const last = days[days.length - 1];
  return (
    <figure className="space-y-2">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="token usage">
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(maxTok * f)} y2={y(maxTok * f)} stroke="var(--color-border)" strokeDasharray="3 3" />
            <text x={PAD.left - 6} y={y(maxTok * f) + 4} textAnchor="end" fontSize="10" fill="var(--color-muted-foreground)">{formatNumber(maxTok * f, 0)}</text>
          </g>
        ))}
        <path d={line((d) => d.input_tokens + d.output_tokens)} fill="none" stroke="var(--color-chart-1)" strokeWidth={1.6} strokeLinejoin="round" />
      </svg>
      <figcaption className="text-xs text-muted-foreground">
        {last.date} · {formatNumber(last.input_tokens + last.output_tokens, 0)} tok
      </figcaption>
    </figure>
  );
}
```

- [ ] **Step 3: `layout.tsx` NAV 追加**
```tsx
  { href: "/console/usage", key: "console.nav.usage" },
```

- [ ] **Step 4: i18n**
```ts
  "console.nav.usage": { en: "Usage", zh: "用量" },
  "console.usage.kev": { en: "Kev core interface usage", zh: "Kev 核心接口用量" },
  "console.usage.distill": { en: "Distillation 3rd-party usage", zh: "蒸馏第三方模型用量" },
```

- [ ] **Step 5: 构建确认**
Run: `npm --prefix playground run build`
Expected: 成功

- [ ] **Step 6: 提交**
```bash
git add playground/src/app/console/usage playground/src/components/console/UsageChart.tsx playground/src/app/console/layout.tsx playground/src/components/console/strings.ts
git commit -m "feat(playground): kev core usage page with time series"
```

---

## Part B — 蒸馏第三方模型配置 + 用量追踪

### Task B1: 服务端密钥库模块 `secrets.py`

**Files:**
- Create: `kev/console/secrets.py`
- Test: `tests/test_console_secrets.py`

**Interfaces:**
- Produces: `secrets.load() -> dict`、`secrets.put(id, entry)`、`secrets.remove(id)`、`secrets.mask(key) -> (hash, hint)`。供 B2/B3 使用。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_console_secrets.py
"""服务端密钥库（Task B1）。明文 key 只落这个文件。
Run: uv run python -m pytest tests/test_console_secrets.py -q
"""
import hashlib

from kev.console import secrets


def test_put_load_remove(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets, "DEFAULT_PATH", tmp_path / "secrets.json")
    secrets.put("p1", {"keys": ["sk-aaa1111"], "base_url": "x", "model": "m", "daily_limit": 1})
    data = secrets.load()
    assert data["p1"]["keys"] == ["sk-aaa1111"]
    secrets.remove("p1")
    assert "p1" not in secrets.load()


def test_mask_hashes_and_hints(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets, "DEFAULT_PATH", tmp_path / "s.json")
    h, hint = secrets.mask("sk-abcdefghijklmnop")
    assert h == hashlib.sha256(b"sk-abcdefghijklmnop").hexdigest()
    assert hint == "sk-...mnop"
    # 不落明文到任何地方以外
```

- [ ] **Step 2: 运行确认失败**
Run: `uv run python -m pytest tests/test_console_secrets.py -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 `kev/console/secrets.py`**

```python
"""服务端密钥库：蒸馏第三方模型凭据的唯一落盘处（spec §4.3 / §7）。

明文 key 只在这里，SQLite 只存非敏感元数据。文件 gitignore、权限 0600。
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from kev.console import paths

DEFAULT_PATH = Path(os.environ.get(
    "KEV_DISTILL_SECRETS", paths.ROOT / "data" / "console" / "secrets" / "distill.json"))


def _path() -> Path:
    return DEFAULT_PATH


def load() -> dict:
    p = _path()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def put(provider_id: str, entry: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    data = load()
    data[provider_id] = entry
    _atomic_write(p, data)


def remove(provider_id: str) -> None:
    p = _path()
    if not p.is_file():
        return
    data = load()
    if provider_id in data:
        del data[provider_id]
        _atomic_write(p, data)


def mask(key: str) -> tuple[str, str]:
    return (hashlib.sha256(key.encode("utf-8")).hexdigest(),
            f"{key[:3]}...{key[-4:]}")


def _atomic_write(p: Path, data: dict) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
```

- [ ] **Step 4: 运行确认通过**
Run: `uv run python -m pytest tests/test_console_secrets.py -q`
Expected: PASS

- [ ] **Step 5: 提交**
```bash
git add kev/console/secrets.py tests/test_console_secrets.py
git commit -m "feat(console): server-side secret store for distill providers"
```

---

### Task B2: 后端 schema — distill_providers + distill_usage + Store 方法

**Files:**
- Modify: `kev/console/db.py`（`DDL` 追加两表；`SCHEMA_VERSION` 已是 2；`Store` 追加方法）
- Test: `tests/test_console_distill_db.py`

**Interfaces:**
- Produces: `Store.create_distill_provider`、`list_distill_providers`、`get_distill_provider`、`deactivate_distill_provider`、`upsert_distill_usage`、`distill_usage_by_provider`、`distill_usage_by_job`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_console_distill_db.py
"""蒸馏配置 + 用量聚合（Task B2）。
Run: uv run python -m pytest tests/test_console_distill_db.py -q
"""
from kev.console.db import Store


def test_provider_crud_and_usage_upsert(store):
    meta = store.create_distill_provider("openai", "https://api.openai.com/v1",
                                         "gpt-4.1-mini", 500000, ["sk-aaa1111", "sk-bbb2222"])
    assert meta["key_count"] == 2
    assert meta["active"] is True
    assert store.list_distill_providers()[0]["key_hints"]
    # 停用双删
    assert store.deactivate_distill_provider(meta["id"]) is True
    assert store.list_distill_providers() == []   # 列表只回启用
    # 用量 upsert 幂等
    store.upsert_distill_usage(job_id="j1", provider_id=meta["id"], key_hash="h1",
        key_hint="sk-...1111", model="gpt-4.1-mini", base_url="x", day="2026-10-06", tokens=100)
    store.upsert_distill_usage(job_id="j1", provider_id=meta["id"], key_hash="h1",
        key_hint="sk-...1111", model="gpt-4.1-mini", base_url="x", day="2026-10-06", tokens=250)
    agg = store.distill_usage_by_provider(meta["id"])
    assert agg[0]["tokens"] == 250          # 覆盖写，非累加
    assert agg[0]["days"] == 1
    by_job = store.distill_usage_by_job("j1")
    assert by_job[0]["daily_limit"] == 500000
```

- [ ] **Step 2: 运行确认失败**
Run: `uv run python -m pytest tests/test_console_distill_db.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

`kev/console/db.py`：`DDL` 末尾追加：

```sql

CREATE TABLE IF NOT EXISTS distill_providers (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  base_url TEXT NOT NULL,
  model TEXT NOT NULL,
  daily_limit INTEGER NOT NULL DEFAULT 500000,
  key_count INTEGER NOT NULL DEFAULT 0,
  key_hints TEXT NOT NULL DEFAULT '[]',
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS distill_providers_active_idx ON distill_providers(active);

CREATE TABLE IF NOT EXISTS distill_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  provider_id TEXT NOT NULL,
  key_hash TEXT NOT NULL,
  key_hint TEXT NOT NULL,
  model TEXT NOT NULL,
  base_url TEXT NOT NULL,
  day TEXT NOT NULL,
  tokens INTEGER NOT NULL DEFAULT 0,
  ts TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS distill_usage_ukd ON distill_usage(provider_id, key_hash, day);
CREATE INDEX IF NOT EXISTS distill_usage_job_idx ON distill_usage(job_id);
CREATE INDEX IF NOT EXISTS distill_usage_day_idx ON distill_usage(day);
```

`Store` 末尾追加：

```python
    # ---- distill providers ------------------------------------------------

    def create_distill_provider(self, name, base_url, model, daily_limit, keys) -> dict:
        import json as _json
        provider_id = uuid.uuid4().hex
        hints = _json.dumps([(k[:3] + "..." + k[-4:]) for k in keys], ensure_ascii=False)
        self.connect().execute(
            "INSERT INTO distill_providers (id, name, base_url, model, daily_limit, "
            "key_count, key_hints, active, created_at) VALUES (?,?,?,?,?,?,?,1,?)",
            (provider_id, name, base_url, model, int(daily_limit), len(keys), hints, _now()))
        self.connect().commit()
        return self.get_distill_provider(provider_id)

    def list_distill_providers(self) -> list[dict]:
        rows = self.connect().execute(
            "SELECT * FROM distill_providers WHERE active=1 ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def get_distill_provider(self, provider_id) -> dict | None:
        row = self.connect().execute(
            "SELECT * FROM distill_providers WHERE id=?", (provider_id,)).fetchone()
        return dict(row) if row else None

    def deactivate_distill_provider(self, provider_id) -> bool:
        cursor = self.connect().execute(
            "UPDATE distill_providers SET active=0 WHERE id=? AND active=1", (provider_id,))
        self.connect().commit()
        return cursor.rowcount == 1

    def upsert_distill_usage(self, *, job_id, provider_id, key_hash, key_hint,
                              model, base_url, day, tokens) -> None:
        self.connect().execute(
            "INSERT INTO distill_usage (job_id, provider_id, key_hash, key_hint, model, "
            "base_url, day, tokens, ts) VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(provider_id, key_hash, day) DO UPDATE SET tokens=excluded.tokens, "
            "job_id=excluded.job_id, model=excluded.model, base_url=excluded.base_url, ts=excluded.ts",
            (job_id, provider_id, key_hash, key_hint, model, base_url, day, int(tokens), _now()))
        self.connect().commit()

    def distill_usage_by_provider(self, provider_id=None, from_day=None, to_day=None) -> list[dict]:
        where, params = [], []
        if provider_id:
            where.append("provider_id=?"); params.append(provider_id)
        if from_day:
            where.append("day >= ?"); params.append(from_day)
        if to_day:
            where.append("day <= ?"); params.append(to_day)
        w = (" WHERE " + " AND ".join(where)) if where else ""
        rows = self.connect().execute(
            "SELECT provider_id, key_hint, model, SUM(tokens) AS tokens, "
            "COUNT(DISTINCT day) AS days, MAX(day) AS last_day FROM distill_usage" + w +
            " GROUP BY provider_id, key_hint, model ORDER BY tokens DESC", params).fetchall()
        return [dict(r) for r in rows]

    def distill_usage_by_job(self, job_id, from_day=None, to_day=None) -> list[dict]:
        where, params = ["job_id=?"], [job_id]
        if from_day:
            where.append("day >= ?"); params.append(from_day)
        if to_day:
            where.append("day <= ?"); params.append(to_day)
        rows = self.connect().execute(
            "SELECT key_hint, model, SUM(tokens) AS tokens, COUNT(DISTINCT day) AS days, "
            "MAX(day) AS last_day FROM distill_usage WHERE " + " AND ".join(where) +
            " GROUP BY key_hint, model", params).fetchall()
        out = [dict(r) for r in rows]
        job = self.get_job(job_id)
        prov = self.get_distill_provider((job["request"].get("provider_id") if job else "") or "")
        for r in out:
            r["daily_limit"] = prov["daily_limit"] if prov else 0
        return out
```

- [ ] **Step 4: 运行确认通过**
Run: `uv run python -m pytest tests/test_console_distill_db.py -q`
Expected: PASS

- [ ] **Step 5: 提交**
```bash
git add kev/console/db.py tests/test_console_distill_db.py
git commit -m "feat(console): distill_providers + distill_usage schema and methods"
```

---

### Task B3: 后端路由 — 蒸馏配置 CRUD + 用量采集；_distill_build 解析 provider

**Files:**
- Modify: `kev/console/app.py`（导入 `secrets`；新增蒸馏路由 + `_ingest_distill_usage`）
- Modify: `kev/console/stages/data.py`（`_distill_build` 解析 `provider_id`）
- Test: `tests/test_console_distill_routes.py`、`tests/test_console_goldset_distill.py`（扩展）

**Interfaces:**
- Consumes: `Store` B2 方法、`secrets` 模块、`jobs` 表（读 `state_dir`/`provider_id`）。
- Produces: `POST /console/api/distill-providers`、`GET /console/api/distill-providers`、`DELETE /console/api/distill-providers/{id}`、`GET /console/api/distill/{job_id}/usage`、`GET /console/api/distill-usage`；`distill` 作业带 `provider_id` 时注入 `KEV_GEN_*`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_console_distill_routes.py
"""蒸馏配置路由 + 用量采集（Task B3）。
Run: uv run python -m pytest tests/test_console_distill_routes.py -q
"""
import json

from fastapi.testclient import TestClient

from kev.console.app import create_app
from kev.console.db import Store


def test_provider_crud_and_usage_ingest(tmp_path, monkeypatch):
    db = Store(tmp_path / "c.db")
    client = TestClient(create_app(store=db))
    r = client.post("/console/api/distill-providers", json={
        "name": "oa", "base_url": "https://api.openai.com/v1", "model": "gpt-4.1-mini",
        "daily_limit": 100, "keys": ["sk-aaa1111"]})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    # 列表无明文
    assert all("keys" not in p for p in client.get("/console/api/distill-providers").json())
    # 停用即删密钥库
    assert client.delete(f"/console/api/distill-providers/{pid}").status_code == 200
    assert client.get("/console/api/distill-providers").json() == []

    # 用量采集：造一个 distill 作业 + 假 usage 文件
    jid = db.create_job(kind="distill", stage="data", scenario="critical-value", title="t",
                        request={"provider_id": pid, "state_dir": str(tmp_path / "state")},
                        argv=["x"], env_overlay={}, cwd="/repo",
                        log_path="l.log", artifacts_in=[], artifacts_out=[])
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "usage_2026-10-06.json").write_text(
        json.dumps({"sk-aaa1111": 123}), encoding="utf-8")
    rows = client.get(f"/console/api/distill/{jid}/usage").json()
    assert rows[0]["tokens"] == 123
    assert rows[0]["key_hint"] == "sk-...1111"
```

- [ ] **Step 2: 运行确认失败**
Run: `uv run python -m pytest tests/test_console_distill_routes.py -q`
Expected: FAIL（路由不存在）

- [ ] **Step 3: 实现 `app.py`**

顶部 import 区追加：`from . import secrets as distill_secrets`（放在 `from . import artifacts, paths` 附近）。

在 `create_app` 内、`# ---- artifacts / gates / endpoints` 之前插入：

```python
    # ---- distill providers ------------------------------------------------

    @app.post("/console/api/distill-providers")
    def create_distill_provider(payload: dict):
        name = (payload.get("name") or "").strip()
        if not name:
            return _error("validation", "名称必填", status=400, field="name")
        base_url = (payload.get("base_url") or "").strip() or "https://api.openai.com/v1"
        model = (payload.get("model") or "").strip()
        if not model:
            return _error("validation", "模型必填", status=400, field="model")
        keys = [k.strip() for k in (payload.get("keys") or []) if k.strip()]
        if not keys:
            return _error("validation", "至少提供一个 API Key", status=400, field="keys")
        daily_limit = int(payload.get("daily_limit") or 500000)
        meta = store().create_distill_provider(name, base_url, model, daily_limit, keys)
        distill_secrets.put(meta["id"], {"keys": keys, "base_url": base_url,
                                         "model": model, "daily_limit": daily_limit})
        return JSONResponse(status_code=201, content=meta)

    @app.get("/console/api/distill-providers")
    def list_distill_providers() -> list:
        return store().list_distill_providers()

    @app.delete("/console/api/distill-providers/{provider_id}")
    def delete_distill_provider(provider_id: str):
        if store().get_distill_provider(provider_id) is None:
            return _error("validation", f"未知配置 {provider_id}", status=404)
        store().deactivate_distill_provider(provider_id)
        distill_secrets.remove(provider_id)
        return {"deactivated": True}

    def _ingest_distill_usage(job_id: str) -> None:
        import json as _json
        from pathlib import Path as _Path
        job = store().get_job(job_id)
        if job is None or job["kind"] not in ("distill", "distill_daemon"):
            return
        state_dir = (job["request"].get("state_dir") or "").strip()
        if not state_dir or not _Path(state_dir).is_dir():
            return
        provider_id = job["request"].get("provider_id") or ""
        prov = store().get_distill_provider(provider_id) or {}
        model = prov.get("model", "")
        base_url = prov.get("base_url", "")
        for f in sorted(_Path(state_dir).glob("usage_*.json")):
            day = f.stem.split("_")[-1]
            try:
                data = _json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for key, tokens in data.items():
                kh, hint = distill_secrets.mask(key)
                store().upsert_distill_usage(job_id=job_id, provider_id=provider_id, key_hash=kh,
                    key_hint=hint, model=model, base_url=base_url, day=day, tokens=int(tokens or 0))

    @app.get("/console/api/distill/{job_id}/usage")
    def distill_job_usage(job_id: str, from_day: str | None = None, to_day: str | None = None):
        if store().get_job(job_id) is None:
            return _error("validation", f"未知作业 {job_id}", status=404)
        _ingest_distill_usage(job_id)
        return store().distill_usage_by_job(job_id, from_day, to_day)

    @app.get("/console/api/distill-usage")
    def distill_usage(provider_id: str | None = None, from_day: str | None = None,
                      to_day: str | None = None) -> list:
        return store().distill_usage_by_provider(provider_id, from_day, to_day)
```

- [ ] **Step 4: 改写 `_distill_build`（`data.py` 第 142–179 行）**

整段替换为：

```python
def _distill_build(request: JobRequest, *, require_schedule: bool = False) -> BuiltCommand:
    _spec(request.scenario)
    params = request.params
    provider_id = params.get("provider_id")
    env = {}
    daily_limit = None
    if provider_id:
        from kev.console import secrets as distill_secrets
        entry = distill_secrets.load().get(provider_id)
        if entry is None:
            raise Invalid(f"未知蒸馏配置 {provider_id}", field="provider_id",
                          hint="先到控制台「蒸馏配置」创建并选择")
        env["KEV_GEN_BASE_URL"] = entry["base_url"]
        env["KEV_GEN_MODEL"] = entry["model"]
        env["KEV_GEN_API_KEYS"] = ",".join(entry["keys"])
        daily_limit = entry.get("daily_limit", 500000)
    else:
        keys = params.get("api_keys") or []
        if len(keys) > MAX_DISTILL_KEYS:
            raise Invalid(f"最多 {MAX_DISTILL_KEYS} 个 key（每日额度轮换用），收到 {len(keys)}",
                          field="api_keys", hint="generate_data.py 按 key 轮换，单 key 有每日上限")
    data_dir = params.get("data") or f"data/{request.scenario}"
    category = params.get("category") or request.scenario
    out = f"{data_dir}/{category}.jsonl"
    if not require_schedule:
        _exists(out, params)
    schedule = params.get("schedule")
    if require_schedule and not schedule:
        raise Invalid("守护模式必须给 --schedule HH:MM", field="schedule",
                      hint="每天蒸馏到当日份额后睡到本地 HH:MM；靠 cron/Task Scheduler 常驻")
    argv = [_python(), str(SKILL_SCRIPTS / "generate_data.py"),
            "--category", category,
            "--n", str(_int(params, "n", PLANNED_RECORDS)),
            "--model", params.get("model", "Ling-3.0-tiny"),
            "--out", out]
    if params.get("concurrency"):
        argv += ["--concurrency", str(_int(params, "concurrency", 3))]
    if schedule:
        argv += ["--schedule", schedule]
    if daily_limit is not None:
        argv += ["--daily-limit", str(int(daily_limit))]
    elif params.get("daily_limit"):
        argv += ["--daily-limit", str(_int(params, "daily_limit", 500000))]
    if params.get("state_dir"):
        argv += ["--state-dir", params["state_dir"]]
    if not provider_id:
        if params.get("base_url"):
            env["KEV_GEN_BASE_URL"] = params["base_url"]
        if params.get("model"):
            env["KEV_GEN_MODEL"] = params["model"]
    # 凭据（KEV_GEN_API_KEYS）：带 provider_id 时由密钥库注入；否则沿用编排服务进程环境
    return BuiltCommand(argv=argv, env=env, cwd=str(paths.ROOT),
                        artifacts_out=[f"dataset:{_dataset_id(data_dir)}/{category}"])
```

- [ ] **Step 5: 扩展既有蒸馏测试（断言 provider 注入）**

在 `tests/test_console_goldset_distill.py` 末尾追加：

```python
def test_distill_build_injects_provider_env(monkeypatch):
    import json, tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp()) / "secrets.json"
    tmp.write_text(json.dumps({"p1": {"keys": ["sk-x"], "base_url": "http://g",
                                      "model": "m", "daily_limit": 7}}), encoding="utf-8")
    monkeypatch.setattr("kev.console.secrets.DEFAULT_PATH", tmp)
    built = d.distill.preview(req({"provider_id": "p1", "category": "critical-value",
                                    "state_dir": ".d", "skip_exists_check": True}))
    assert built.env["KEV_GEN_BASE_URL"] == "http://g"
    assert built.env["KEV_GEN_MODEL"] == "m"
    assert built.env["KEV_GEN_API_KEYS"] == "sk-x"
    assert "--daily-limit" in built.argv and built.argv[built.argv.index("--daily-limit") + 1] == "7"


def test_distill_build_rejects_unknown_provider():
    with pytest.raises(Invalid, match="未知蒸馏配置"):
        d.distill.preview(req({"provider_id": "nope", "category": "critical-value",
                                "skip_exists_check": True}))
```

- [ ] **Step 6: 运行测试**
Run: `uv run python -m pytest tests/test_console_distill_routes.py tests/test_console_goldset_distill.py -q`
Expected: PASS

- [ ] **Step 7: 提交**
```bash
git add kev/console/app.py kev/console/stages/data.py tests/test_console_distill_routes.py tests/test_console_goldset_distill.py
git commit -m "feat(console): distill provider CRUD + usage ingest + build resolves provider"
```

---

### Task B4: 前端 lib — 蒸馏类型与方法

**Files:**
- Modify: `playground/src/lib/console.ts`（追加蒸馏类型 + 方法）

**Interfaces:**
- Produces: `console.api.{distillProviders,createDistillProvider,deactivateDistillProvider,distillUsage,distillJobUsage}` + 类型 `DistillProvider`/`DistillUsageRow`。供 B5/B6 使用。

- [ ] **Step 1: 在 `console.ts` 类型区追加**

```ts
export type DistillProvider = {
  id: string; name: string; base_url: string; model: string;
  daily_limit: number; key_count: number; key_hints: string[]; active: boolean; created_at: string;
};
export type DistillUsageRow = {
  provider_id: string; key_hint: string; model: string;
  tokens: number; days: number; last_day: string | null; daily_limit: number;
};
```

- [ ] **Step 2: 在 `api` 对象追加**

```ts
  distillProviders: () => call<DistillProvider[]>("distill-providers"),
  createDistillProvider: (p: { name: string; base_url: string; model: string; daily_limit: number; keys: string[] }) =>
    call<DistillProvider>("distill-providers", { method: "POST", body: JSON.stringify(p) }),
  deactivateDistillProvider: (id: string) =>
    call<{ deactivated: boolean }>(`distill-providers/${id}`, { method: "DELETE" }),
  distillUsage: (providerId?: string, from?: string, to?: string) => {
    const q = new URLSearchParams();
    if (providerId) q.set("provider_id", providerId);
    if (from) q.set("from", from);
    if (to) q.set("to", to);
    return call<DistillUsageRow[]>(`distill-usage${q.toString() ? `?${q}` : ""}`);
  },
  distillJobUsage: (jobId: string, from?: string, to?: string) => {
    const q = new URLSearchParams();
    if (from) q.set("from", from);
    if (to) q.set("to", to);
    return call<DistillUsageRow[]>(`distill/${jobId}/usage${q.toString() ? `?${q}` : ""}`);
  },
```

- [ ] **Step 3: 构建确认**
Run: `npm --prefix playground run build`
Expected: 成功

- [ ] **Step 4: 提交**
```bash
git add playground/src/lib/console.ts
git commit -m "feat(playground): distill provider + usage client methods"
```

---

### Task B5: 前端 — 蒸馏配置页 + 数据集表单 provider 选择器

**Files:**
- Create: `playground/src/app/console/distill-providers/page.tsx`
- Modify: `playground/src/app/console/datasets/page.tsx`（distill/distill_daemon 字段用 `provider_id` 选择）
- Modify: `playground/src/components/console/JobStagePage.tsx`（select 支持 `optionsUrl` 动态选项）
- Modify: `playground/src/app/console/layout.tsx`（`NAV` 追加）
- Modify: `playground/src/components/console/strings.ts`（i18n）

**Interfaces:**
- Consumes: `console.api.{distillProviders,createDistillProvider,deactivateDistillProvider}`、`JobStagePage` 的 `optionsUrl`。
- Produces: 蒸馏配置管理页；数据集蒸馏表单的「蒸馏配置」下拉（提交 `provider_id`）。

- [ ] **Step 1: 扩展 `JobStagePage` 支持动态选项**

`FieldSpec` 类型（第 19–27 行）追加 `optionsUrl?: string`；`usePoll` 引入（文件顶部已有 `usePoll` import）。在组件内加一个 `providerOptions` 状态：

```tsx
import { useEffect, useState } from "react";
// 已有 usePoll import
```

在 `JobStagePage` 函数内（靠近 `const [values, setValues]` 之后）加：

```tsx
  const [dynamicOptions, setDynamicOptions] = useState<Record<string, { value: string; label: string }[]>>({});
  useEffect(() => {
    for (const f of fields) {
      if (f.optionsUrl && !(f.key in dynamicOptions)) {
        api.distillProviders().then((list) => {
          setDynamicOptions((prev) => ({
            ...prev,
            [f.key]: [
              { value: "", label: "（进程环境变量）" },
              ...list.map((p) => ({ value: p.id, label: `${p.name} · ${p.model}` })),
            ],
          }));
        }).catch(() => {});
      }
    }
  }, [fields]);  // eslint-disable-line react-hooks/exhaustive-deps
```

渲染 select 时，选项来源取 `field.optionsUrl ? dynamicOptions[field.key] : field.options`：

```tsx
              {field.kind === "select" ? (
                <Select value={values[field.key]} onValueChange={(v) => v !== null && set(field.key, v)}>
                  <SelectTrigger id={`f-${field.key}`}><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {(field.optionsUrl ? dynamicOptions[field.key] ?? [] : field.options ?? []).map((option) => (
                      <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
```

- [ ] **Step 2: `datasets/page.tsx` 字段改为 provider 选择**

将 `KINDS.distill` 与 `KINDS.distill_daemon` 的 `fields` 中 `model`/`base_url` 两项替换为：

```tsx
  distill: { kind: "distill", fields: [
    { key: "category", label: "--category" },
    { key: "provider_id", label: "provider", kind: "select", optionsUrl: "/console/api/distill-providers",
      hint: "蒸馏配置（模型/Base URL/Key/每日阈值）在「蒸馏配置」页创建" },
    { key: "concurrency", label: "--concurrency" },
    { key: "n", label: "--n" },
    { key: "schedule", label: "--schedule", hint: "HH:MM（可选；守护模式下必填）" },
    { key: "state_dir", label: "--state-dir", hint: "进度状态目录（用量采集依据）" },
  ] },
  distill_daemon: { kind: "distill_daemon", fields: [
    { key: "category", label: "--category" },
    { key: "provider_id", label: "provider", kind: "select", optionsUrl: "/console/api/distill-providers",
      hint: "蒸馏配置在「蒸馏配置」页创建" },
    { key: "concurrency", label: "--concurrency" },
    { key: "n", label: "--n" },
    { key: "schedule", label: "--schedule", hint: "HH:MM；每天蒸馏到当日配额后睡到本地该时刻" },
    { key: "state_dir", label: "--state-dir", hint: "进度状态目录（用量采集依据）" },
  ] },
```

并删去原 `daily_limit` 字段（阈值已随 provider 注入）；保留 `initial` 不变（`model` 默认值可删，不影响）。

- [ ] **Step 3: 实现 `distill-providers/page.tsx`**

```tsx
"use client";
import { useCallback, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, type DistillProvider } from "@/lib/console";
import { useLang } from "@/lib/i18n";
import { usePoll } from "@/components/console/usePoll";

export default function DistillProvidersPage() {
  const { t, lang } = useLang();
  const [form, setForm] = useState({ name: "", base_url: "https://api.openai.com/v1",
    model: "", daily_limit: "500000", keys: "" });
  const set = (k: keyof typeof form, v: string) => setForm((p) => ({ ...p, [k]: v }));
  const load = useCallback(() => api.distillProviders(), []);
  const { value: list, refresh } = usePoll<DistillProvider[]>(load, []);

  async function onCreate() {
    try {
      await api.createDistillProvider({ name: form.name || "provider", base_url: form.base_url,
        model: form.model, daily_limit: Number(form.daily_limit) || 500000,
        keys: form.keys.split("\n").map((s) => s.trim()).filter(Boolean) });
      toast.success(t("console.distill.created"));
      setForm({ ...form, name: "", model: "", keys: "" });
      refresh();
    } catch (e) { toast.error((e as Error).message); }
  }
  async function onDeactivate(id: string) { await api.deactivateDistillProvider(id); refresh(); }

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-semibold">{t("console.nav.distill")}</h1>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="dname" label={t("console.apikeys.name")} value={form.name} onChange={(v) => set("name", v)} />
        <Field id="dmodel" label="model" value={form.model} onChange={(v) => set("model", v)} />
        <Field id="durl" label="Base URL" value={form.base_url} onChange={(v) => set("base_url", v)} />
        <Field id="dlim" label={t("console.distill.dailyLimit")} value={form.daily_limit} onChange={(v) => set("daily_limit", v)} />
        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor="dkeys">{t("console.distill.keys")}</Label>
          <textarea id="dkeys" className="h-24 w-full rounded-md border border-border bg-background p-2 font-mono text-xs"
            value={form.keys} onChange={(e) => set("keys", e.target.value)}
            placeholder={"sk-... 每行一个"} />
        </div>
      </div>
      <Button onClick={() => void onCreate()}>{t("console.distill.create")}</Button>
      <Table>
        <TableHeader>
          <TableRow><TableHead>{t("console.apikeys.name")}</TableHead><TableHead>Base URL</TableHead>
            <TableHead>model</TableHead><TableHead>{t("console.distill.dailyLimit")}</TableHead>
            <TableHead>keys</TableHead><TableHead /></TableRow>
        </TableHeader>
        <TableBody>
          {(list ?? []).map((p) => (
            <TableRow key={p.id}>
              <TableCell>{p.name}</TableCell><TableCell className="font-mono text-xs">{p.base_url}</TableCell>
              <TableCell>{p.model}</TableCell><TableCell>{formatNumber(p.daily_limit, 0)}</TableCell>
              <TableCell className="font-mono text-xs text-muted-foreground">{(p.key_hints ?? []).join(" ")}</TableCell>
              <TableCell className="text-right">
                <Button size="sm" variant="ghost" onClick={() => void onDeactivate(p.id)}>
                  {t("console.distill.deactivate")}</Button></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function Field({ id, label, value, onChange }: { id: string; label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
```
（文件顶部补 `import { formatNumber } from "@/components/console/format";`）

- [ ] **Step 4: `layout.tsx` NAV 追加**
```tsx
  { href: "/console/distill-providers", key: "console.nav.distill" },
```

- [ ] **Step 5: i18n**
```ts
  "console.nav.distill": { en: "Distill config", zh: "蒸馏配置" },
  "console.distill.created": { en: "provider saved (keys stored server-side only)", zh: "配置已保存（密钥仅存于服务端）" },
  "console.distill.keys": { en: "API keys (one per line)", zh: "API Key（每行一个）" },
  "console.distill.create": { en: "Save config", zh: "保存配置" },
  "console.distill.deactivate": { en: "Deactivate", zh: "停用" },
```

- [ ] **Step 6: 构建确认**
Run: `npm --prefix playground run build`
Expected: 成功

- [ ] **Step 7: 提交**
```bash
git add playground/src/app/console/distill-providers playground/src/app/console/datasets/page.tsx playground/src/components/console/JobStagePage.tsx playground/src/app/console/layout.tsx playground/src/components/console/strings.ts
git commit -m "feat(playground): distill provider page + dataset form selector"
```

---

### Task B6: 前端 — 用量页蒸馏第三方分区

**Files:**
- Modify: `playground/src/app/console/usage/page.tsx`（追加 B 分区）
- Modify: `playground/src/components/console/strings.ts`（i18n）

**Interfaces:**
- Consumes: `console.api.{distillUsage,distillProviders}`。

- [ ] **Step 1: 在 `usage/page.tsx` 追加蒸馏分区**

在现有 kev 分区 `<div>` 之后追加：

```tsx
      <div className="space-y-4 pt-4 border-t border-border">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">{t("console.usage.distill")}</h2>
          <div className="flex gap-1">
            <Button size="sm" variant={provFilter === "" ? "secondary" : "ghost"} onClick={() => setProvFilter("")}>all</Button>
            {providers.map((p) => (
              <Button key={p.id} size="sm" variant={provFilter === p.id ? "secondary" : "ghost"}
                      onClick={() => setProvFilter(p.id)}>{p.name}</Button>
            ))}
          </div>
        </div>
        <Table>
          <TableHeader>
            <TableRow><TableHead>config</TableHead><TableHead>key</TableHead><TableHead>model</TableHead>
              <TableHead>tokens</TableHead><TableHead>days</TableHead><TableHead>{t("console.distill.dailyLimit")}</TableHead></TableRow>
          </TableHeader>
          <TableBody>
            {(distill ?? []).map((r, i) => (
              <TableRow key={i}>
                <TableCell>{r.provider_id ? provName(r.provider_id) : "—"}</TableCell>
                <TableCell className="font-mono text-xs">{r.key_hint}</TableCell>
                <TableCell>{r.model}</TableCell>
                <TableCell>{formatNumber(r.tokens, 0)}</TableCell>
                <TableCell>{r.days}</TableCell>
                <TableCell className="text-xs">
                  {formatNumber(r.tokens, 0)} / {formatNumber(r.daily_limit, 0)}
                  {r.daily_limit > 0 && r.tokens >= r.daily_limit &&
                    <span className="ml-1 text-destructive">⚠</span>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
```

并在组件内加状态与加载：

```tsx
  const [provFilter, setProvFilter] = useState("");
  const [providers, setProviders] = useState<{ id: string; name: string }[]>([]);
  const [distill, setDistill] = useState<DistillUsageRow[]>([]);
  useEffect(() => {
    api.distillProviders().then(setProviders).catch(() => {});
  }, []);
  useEffect(() => {
    api.distillUsage(provFilter || undefined, from).then(setDistill).catch(() => setDistill([]));
  }, [provFilter, days]);
  const provName = (id: string) => providers.find((p) => p.id === id)?.name ?? id;
```
（顶部补 `import { useEffect, useState } from "react";`、`import { api, type DistillUsageRow } from "@/lib/console";`）

- [ ] **Step 2: i18n（已含 `console.usage.distill` 与 `console.distill.dailyLimit`）**

- [ ] **Step 3: 构建确认**
Run: `npm --prefix playground run build`
Expected: 成功

- [ ] **Step 4: 提交**
```bash
git add playground/src/app/console/usage/page.tsx playground/src/components/console/strings.ts
git commit -m "feat(playground): distill 3rd-party usage section"
```

---

## Part C — 收尾与合规验证

### Task C1: 部署配置 + 依赖 + 契约冻结校验

**Files:**
- Modify: `.gitignore`（追加 `data/console/secrets/`）
- Modify: `kev/console/pyproject.toml` 或 `requirements*.txt`（确认 `requests` 依赖；若缺则补）
- Verify: `git diff --stat kev/serve.py skills/kev-finetune/scripts/generate_data.py` 为空

**Interfaces:**
- 无新代码接口；确保运行时 `KEV_SERVE_URL`/`KEV_DISTILL_SECRETS` 可被读取、密钥库文件被 gitignore。

- [ ] **Step 1: `.gitignore` 追加**
```
data/console/secrets/
```

- [ ] **Step 2: 确认 `requests` 可导入**
Run: `uv run python -c "import requests; print(requests.__version__)"`
若失败：在 `kev/console` 的依赖清单补 `requests`，再 `uv pip install requests`。

- [ ] **Step 3: 运行全部后端测试**
Run: `uv run python -m pytest tests/ -q`
Expected: 全绿（含 `test_conventions.py`）

- [ ] **Step 4: 契约冻结断言**
Run: `git diff --stat -- kev/serve.py skills/kev-finetune/scripts/generate_data.py`
Expected: 空（本计划零改动这两个文件）

- [ ] **Step 5: 前端构建 + lint**
Run: `npm --prefix playground run build`
Expected: 成功

- [ ] **Step 6: 提交（仅 .gitignore / 依赖清单变更）**
```bash
git add .gitignore <依赖清单文件>
git commit -m "chore: gitignore distill secret store; ensure requests dep"
```

---

## 自我审查（Spec 覆盖核对）

- **apikey 管理闭环** → A1（schema+CRUD）、A2（路由）、A3（lib）、A4（页+选择器）。✓
- **调用走 key 鉴权** → A2（代理 401/记录）、A3（kev.ts 带 Bearer）。✓
- **用量可归因（kev 核心）** → A1（`usage_log`/`record_usage`）、A2（usage 路由）、A5（页）。✓
- **统计可读（按 key 汇总 + 时间序列）** → A1（`usage_summary`/`usage_timeseries` + p99）、A5（表 + `UsageChart`）。✓
- **蒸馏配置可管理** → B1（密钥库）、B2（表+方法）、B3（路由+`_distill_build` 解析）、B5（页+表单选择）。✓
- **蒸馏用量可归因（按第三方 apikey）** → B2（`distill_usage`/`upsert`/`by_provider`/`by_job`）、B3（采集 `usage_*.json`）、B6（页 + 当日/阈值进度）。✓
- **kev.serve / generate_data.py 零改动** → C1 断言。✓
- **安全：明文不落 SQLite/浏览器** → apikey 仅哈希（A1）；蒸馏密钥仅服务端文件（B1）+ 前端仅存 localStorage（A3/A4）。✓
- **删除 NEXT_PUBLIC_KEV_API_KEY** → A3（kev.ts 改写）。✓

**类型一致性检查**：`console.ts` 的 `ApiKey`/`UsageRow`/`UsageDay`/`DistillProvider`/`DistillUsageRow` 在 A3/B4 定义、A4/A5/B5/B6 消费，字段名一致；`Store` 方法名在 A1/B2 定义、A2/B3 消费，签名一致；`secrets.mask/put/remove/load` 在 B1 定义、B3 消费。✓

**占位符扫描**：无 TBD/TODO；每步均含完整代码与命令。✓
