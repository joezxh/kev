"""编排层的持久化：作业状态机、产物、血缘、事件。

三条设计约定（spec §5 / §9）：
- SQLite 单文件，PRAGMA user_version 做 schema 版本，不引 ORM
- 日志文件是真相源，events 表只是给 UI 的可分页尾巴（首屏回填 + Last-Event-ID 续传）
- 状态机集中校验：succeeded -> running 这类转移必须被拒
"""
from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import paths

SCHEMA_VERSION = 3

# 运行时共享的编排库单例：create_app 启动时写入，stage 模块（data.py 等）借此解析
# 场景 spec_path。未初始化时返回 None，调用方应回退到 docs/medical/specs 目录。
_STORE: "Store | None" = None


def set_store(store: "Store") -> None:
    global _STORE
    _STORE = store


def store() -> "Store":
    if _STORE is None:
        raise RuntimeError("console store not initialized")
    return _STORE

TERMINAL = frozenset({"succeeded", "failed", "canceled", "interrupted"})
LIVE = frozenset({"pending", "queued", "running"})

ALLOWED: dict[str, frozenset[str]] = {
    # pending 也收 interrupted：interrupt_stale_jobs() 是一条直接 SQL，会把全部 LIVE（含 pending）
    # 标成 interrupted。状态机不许这条边，就等于「恢复路径造得出、状态机自己造不出」的状态。
    "pending": frozenset({"queued", "running", "canceled", "failed", "interrupted"}),
    "queued": frozenset({"running", "canceled", "failed", "interrupted"}),
    "running": TERMINAL,
    "succeeded": frozenset(),
    "failed": frozenset(),
    "canceled": frozenset(),
    "interrupted": frozenset(),
}

# to_status -> 全局上能到达它的来源状态集合，由 ALLOWED 反推（不是读出来的当前状态）。
# transition 把这份集合放进 WHERE，于是「校验」与「写入」落在同一条语句上。
SOURCES: dict[str, frozenset[str]] = {
    target: frozenset(source for source, allowed in ALLOWED.items() if target in allowed)
    for target in ALLOWED
}

DDL = """
CREATE TABLE IF NOT EXISTS jobs (
  id            TEXT PRIMARY KEY,
  kind          TEXT NOT NULL,
  stage         TEXT NOT NULL,
  scenario      TEXT NOT NULL,
  title         TEXT NOT NULL,
  status        TEXT NOT NULL,
  request       TEXT NOT NULL,
  argv          TEXT NOT NULL,
  env_overlay   TEXT NOT NULL,
  cwd           TEXT NOT NULL,
  log_path      TEXT NOT NULL,
  artifacts_in  TEXT NOT NULL,
  artifacts_out TEXT NOT NULL,
  parent_id     TEXT REFERENCES jobs(id),
  attempt       INTEGER NOT NULL DEFAULT 1,
  exit_code     INTEGER,
  error         TEXT,
  created_at    TEXT NOT NULL,
  started_at    TEXT,
  finished_at   TEXT
);
CREATE INDEX IF NOT EXISTS jobs_status_idx   ON jobs(status);
CREATE INDEX IF NOT EXISTS jobs_scenario_idx ON jobs(scenario, created_at DESC);

CREATE TABLE IF NOT EXISTS artifacts (
  id         TEXT PRIMARY KEY,
  kind       TEXT NOT NULL,
  name       TEXT NOT NULL,
  path       TEXT NOT NULL,
  meta       TEXT NOT NULL,
  bytes      INTEGER,
  created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS artifacts_kind_name ON artifacts(kind, name);

CREATE TABLE IF NOT EXISTS lineage (
  -- parent/child 不加 REFERENCES artifacts(id)：artifacts_in 里可以出现尚未登记的 id
  -- （用户手放的数据集目录、重试、artifacts 表被清空后的历史作业），血缘是给 UI 的索引，
  -- 不是真相源 —— job 行的 artifacts_in 才是。写成外键会让 register 在这种情况下整条作业炸掉。
  parent   TEXT NOT NULL,
  child    TEXT NOT NULL,
  relation TEXT NOT NULL,
  job_id   TEXT REFERENCES jobs(id),
  PRIMARY KEY (parent, child, relation)
);

CREATE TABLE IF NOT EXISTS events (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  ts     TEXT NOT NULL,
  stream TEXT NOT NULL,
  line   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_job_idx ON events(job_id, id);

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

CREATE TABLE IF NOT EXISTS scenario_domains (
  id         TEXT PRIMARY KEY,
  slug       TEXT NOT NULL UNIQUE,
  label_zh   TEXT NOT NULL,
  label_en   TEXT NOT NULL,
  sort       INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scenarios (
  id         TEXT PRIMARY KEY,
  domain_id  TEXT NOT NULL REFERENCES scenario_domains(id),
  slug       TEXT NOT NULL UNIQUE,
  label_zh   TEXT NOT NULL,
  label_en   TEXT NOT NULL,
  spec_path  TEXT NOT NULL,
  category   TEXT NOT NULL DEFAULT 'medical',
  sort       INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS scenarios_slug_idx   ON scenarios(slug);
CREATE INDEX IF NOT EXISTS scenarios_domain_idx ON scenarios(domain_id);
"""

_JSON_COLUMNS = frozenset({"request", "env_overlay", "artifacts_in", "artifacts_out"})
_ROW_COLUMNS = (
    "id", "kind", "stage", "scenario", "title", "status", "request", "argv",
    "env_overlay", "cwd", "log_path", "artifacts_in", "artifacts_out",
    "parent_id", "attempt", "exit_code", "error", "created_at", "started_at", "finished_at",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dumps(value) -> str:
    # allow_nan=False mirrors kev.suite.write_json: a NaN metric must fail loudly here,
    # not silently produce a file no reader can parse.
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _loads(text):
    return json.loads(text)


def _job(row) -> dict:
    out = {}
    for column in _ROW_COLUMNS:
        out[column] = row[column]
    for column in _JSON_COLUMNS:
        out[column] = _loads(out[column])
    out["argv"] = _loads(out["argv"])
    return out


class Store:
    """每线程一个连接。WAL 让读不阻塞写，事件轮询与日志落库可以并发。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        with self.connect() as connection:
            connection.executescript(DDL)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        # 幂等播种：把 run_matrix 已知的医疗场景落库（INSERT OR IGNORE 按 slug 去重，
        # 不覆盖用户后续编辑）。建库即播种，保证 fresh DB 也能开箱即用。
        self.seed_scenarios()

    def connect(self) -> sqlite3.Connection:
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = sqlite3.connect(self.path, timeout=30.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA foreign_keys = ON")
            self._local.connection = connection
        return connection

    def schema_version(self) -> int:
        return self.connect().execute("PRAGMA user_version").fetchone()[0]

    @contextlib.contextmanager
    def tx(self):
        """一个写事务：BEGIN IMMEDIATE 当场拿写锁，让「读-改-写」整体串行化。

        连接是每线程一个（FastAPI 的同步路由跑在线程池里），所以这里只能锁住**本线程**的连接：
        事务里不要把连接交出去给别的线程，也不要调会自己 commit 的方法
        （put_artifact / add_lineage 的 commit=True 会提前结束事务）。
        """
        connection = self.connect()
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        else:
            if connection.in_transaction:
                connection.commit()

    # ---- jobs -------------------------------------------------------------

    def create_job(self, *, kind, stage, scenario, title, request, argv, env_overlay,
                   cwd, log_path, artifacts_in, artifacts_out, parent_id=None,
                   attempt=1) -> str:
        """attempt 是「第几次尝试」：重试（换名续跑）时由调用方递增，jobs 表据此区分
        首次执行与重试。parent_id 指向被重试的那个作业。
        """
        job_id = uuid.uuid4().hex
        self.connect().execute(
            "INSERT INTO jobs (id, kind, stage, scenario, title, status, request, argv, env_overlay, cwd,"
            " log_path, artifacts_in, artifacts_out, parent_id, attempt, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (job_id, kind, stage, scenario, title, "pending", _dumps(request), _dumps(argv),
             _dumps(env_overlay), str(cwd), str(log_path), _dumps(artifacts_in),
             _dumps(artifacts_out), parent_id, int(attempt), _now()),
        )
        self.connect().commit()
        return job_id

    def get_job(self, job_id) -> dict | None:
        row = self.connect().execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _job(row) if row else None

    def list_jobs(self, *, status=None, stage=None, scenario=None, limit=200) -> list[dict]:
        clauses, params = [], []
        for column, value in (("status", status), ("stage", stage), ("scenario", scenario)):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = self.connect().execute(
            f"SELECT * FROM jobs{where} ORDER BY created_at DESC, rowid DESC LIMIT ?", params
        ).fetchall()
        return [_job(row) for row in rows]

    def transition(self, job_id, to_status, *, error=None, exit_code=None) -> None:
        """把作业推到 to_status。校验与写入是同一条语句，中间没有窗口。

        旧的写法是「SELECT 读当前状态 → Python 里校验 → UPDATE」，两步之间任何线程都能改状态：
        Task 3 的 reader 线程标 succeeded 与请求线程标 canceled 会双双读到 running、双双通过校验，
        后写者赢 —— 已取消的作业最终是 succeeded，error 被冲掉，finished_at 被写两次。

        所以这里用 BEGIN IMMEDIATE 拿写锁，并把**全局上能到达 to_status 的来源集合**放进 WHERE：
        那个集合来自模块级的 SOURCES，不是读出来的当前状态（用当前状态推就等于又读了一遍）。
        rowcount == 0 时还在事务里（WAL 下没人能在这中间改状态），回查一次区分
        「作业不存在」(KeyError) 与「非法转移」(ValueError)。

        来源集合为空（没有任何状态能到 to_status，例如 terminal 之后的任意目标）就跳过 UPDATE，
        直接走回查分支 —— 两条异常的语义不变。
        """
        sources = sorted(SOURCES.get(to_status, ()))
        stamps, params = [], [to_status]
        if to_status == "running":
            # COALESCE：started_at 只在第一次进 running 时落时间，重跑不会覆盖它。
            stamps.append("started_at = COALESCE(started_at, ?)")
            params.append(_now())
        if to_status in TERMINAL:
            stamps.append("finished_at = ?")
            params.append(_now())
        if error is not None:
            stamps.append("error = ?")
            params.append(error)
        if exit_code is not None:
            stamps.append("exit_code = ?")
            params.append(exit_code)

        with self.tx() as connection:
            changed = 0
            if sources:
                sql = ("UPDATE jobs SET status = ?" + (", " + ", ".join(stamps) if stamps else "")
                       + " WHERE id = ? AND status IN (" + ", ".join("?" * len(sources)) + ")")
                changed = connection.execute(sql, (*params, job_id, *sources)).rowcount
            if not changed:
                row = connection.execute(
                    "SELECT status FROM jobs WHERE id = ?", (job_id,)
                ).fetchone()
        if changed:
            return
        if row is None:
            raise KeyError(job_id)
        raise ValueError(f"illegal transition {row['status']} -> {to_status} for job {job_id}")

    def active_job_of_kind(self, kind) -> dict | None:
        placeholders = ", ".join("?" * len(LIVE))
        row = self.connect().execute(
            f"SELECT * FROM jobs WHERE kind = ? AND status IN ({placeholders})"
            " ORDER BY created_at DESC LIMIT 1",
            (kind, *sorted(LIVE)),
        ).fetchone()
        return _job(row) if row else None

    def interrupt_stale_jobs(self) -> int:
        """编排服务启动时调用：WSL2 会自动回收内存，重启后残留的 running 一律算 interrupted。"""
        placeholders = ", ".join("?" * len(LIVE))
        cursor = self.connect().execute(
            f"UPDATE jobs SET status = 'interrupted', error = ?, finished_at = ?"
            f" WHERE status IN ({placeholders})",
            ("编排服务重启", _now(), *sorted(LIVE)),
        )
        self.connect().commit()
        return cursor.rowcount

    # ---- artifacts --------------------------------------------------------

    def put_artifact(self, *, kind, name, path, meta, bytes_=None, commit: bool = True) -> str:
        """登记/更新一个产物。commit=False 让它留在调用方的事务里（见 Store.tx）。"""
        artifact_id = f"{kind}:{name}"
        self.connect().execute(
            "INSERT INTO artifacts (id, kind, name, path, meta, bytes, created_at) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET path = excluded.path, meta = excluded.meta,"
            " bytes = excluded.bytes",
            (artifact_id, kind, name, str(path), _dumps(meta), bytes_, _now()),
        )
        if commit:
            self.connect().commit()
        return artifact_id

    def get_artifact(self, artifact_id) -> dict | None:
        row = self.connect().execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
        if row is None:
            return None
        out = dict(row)
        out["meta"] = _loads(out["meta"])
        return out

    def list_artifacts(self, kind=None) -> list[dict]:
        if kind is None:
            rows = self.connect().execute("SELECT * FROM artifacts ORDER BY created_at DESC").fetchall()
        else:
            rows = self.connect().execute(
                "SELECT * FROM artifacts WHERE kind = ? ORDER BY created_at DESC", (kind,)
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["meta"] = _loads(item["meta"])
            out.append(item)
        return out

    # ---- lineage ----------------------------------------------------------

    def add_lineage(self, parent, child, relation, job_id=None, *, commit: bool = True) -> None:
        """记一条产物血缘。commit=False 让它留在调用方的事务里（见 Store.tx）。"""
        self.connect().execute(
            "INSERT OR IGNORE INTO lineage (parent, child, relation, job_id) VALUES (?,?,?,?)",
            (parent, child, relation, job_id),
        )
        if commit:
            self.connect().commit()

    def lineage_of(self, artifact_id) -> list[dict]:
        """出边（这个产物派生了什么）。入边查 child 那一侧。"""
        rows = self.connect().execute(
            "SELECT * FROM lineage WHERE parent = ?", (artifact_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    # ---- events -----------------------------------------------------------

    def append_events(self, job_id, rows) -> int:
        """rows: [(stream, line), ...]。返回**本次写入**的最后一条 id，供 SSE 续传游标使用。

        游标取 last_insert_rowid()，不是 SELECT MAX(id) WHERE job_id = ?：同一个作业有第二个写入源
        （Task 3 里多个 reader 线程各写各的）时，MAX 会把别人写的行当成自己写的返回，
        调用方拿它当游标会静默跳过一段日志。last_insert_rowid 是连接私有的，其他连接插不进来；
        executemany 多行时它就是最后那行的 rowid。

        空批次返回 0，语义是「没有新增」：没有行可指，而返回该作业现有的最大 id 会把游标
        顶到当前末尾，等于谎报「日志到这里为止」。
        """
        rows = list(rows)
        if not rows:
            return 0
        stamp = _now()
        payload = [(job_id, stamp, stream, line) for stream, line in rows]
        connection = self.connect()
        connection.executemany(
            "INSERT INTO events (job_id, ts, stream, line) VALUES (?,?,?,?)", payload
        )
        connection.commit()
        return connection.execute("SELECT last_insert_rowid()").fetchone()[0]

    def read_events(self, job_id, after_id=0, limit=500) -> list[dict]:
        rows = self.connect().execute(
            "SELECT * FROM events WHERE job_id = ? AND id > ? ORDER BY id LIMIT ?",
            (job_id, after_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def tail_text(self, job_id, lines=30) -> str:
        """子进程非零退出时给错误体的 stderr_tail（spec §10.2）。"""
        rows = self.connect().execute(
            "SELECT stream, line FROM events WHERE job_id = ? ORDER BY id DESC LIMIT ?",
            (job_id, lines),
        ).fetchall()
        return "\n".join(f"[{row['stream']}] {row['line']}" for row in reversed(rows))

    # ---- api keys ---------------------------------------------------------

    def create_api_key(self, name: str) -> tuple[str, dict]:
        import hashlib
        import secrets as _secrets
        raw = "kev_" + _secrets.token_hex(32)
        key_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        key_id = uuid.uuid4().hex
        self.connect().execute(
            "INSERT INTO api_keys (id, name, key_hash, prefix, active, created_at) "
            "VALUES (?,?,?,?,1,?)",
            (key_id, name, key_hash, raw[:12], _now()),
        )
        self.connect().commit()
        row = self.connect().execute("SELECT * FROM api_keys WHERE id=?", (key_id,)).fetchone()
        return raw, dict(row)

    def get_key_by_hash(self, key_hash: str) -> dict | None:
        row = self.connect().execute(
            "SELECT * FROM api_keys WHERE key_hash=? AND active=1", (key_hash,)
        ).fetchone()
        return dict(row) if row else None

    def list_api_keys(self) -> list[dict]:
        rows = self.connect().execute(
            "SELECT a.id, a.name, a.prefix, a.active, a.created_at, a.revoked_at, "
            "COALESCE(u.calls,0) AS calls, "
            "COALESCE(u.input_tokens,0) AS input_tokens, "
            "COALESCE(u.output_tokens,0) AS output_tokens, u.last_used "
            "FROM api_keys a LEFT JOIN ("
            "  SELECT key_id, COUNT(*) AS calls, SUM(input_tokens) AS input_tokens, "
            "  SUM(output_tokens) AS output_tokens, MAX(ts) AS last_used "
            "  FROM usage_log GROUP BY key_id) u ON u.key_id=a.id "
            "ORDER BY a.created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def revoke_api_key(self, key_id: str) -> bool:
        cursor = self.connect().execute(
            "UPDATE api_keys SET active=0, revoked_at=? WHERE id=? AND active=1",
            (_now(), key_id),
        )
        self.connect().commit()
        return cursor.rowcount == 1

    def record_usage(self, *, key_id, endpoint, method, status,
                      input_tokens, output_tokens, latency_ms) -> None:
        self.connect().execute(
            "INSERT INTO usage_log (key_id, endpoint, method, status, input_tokens, "
            "output_tokens, latency_ms, ts) VALUES (?,?,?,?,?,?,?,?)",
            (key_id, endpoint, method, int(status), int(input_tokens), int(output_tokens),
             float(latency_ms), _now()),
        )
        self.connect().commit()

    def _usage_pred(self, from_ts, to_ts) -> tuple[str, list]:
        clauses, params = [], []
        if from_ts:
            clauses.append("ts >= ?")
            params.append(from_ts)
        if to_ts:
            clauses.append("ts <= ?")
            params.append(to_ts)
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
            "SELECT id, name, prefix, active FROM api_keys ORDER BY created_at DESC"
        ).fetchall()
        out = []
        for k in keys:
            row = dict(k)
            stats = self.connect().execute(
                f"SELECT COUNT(*) c, COALESCE(SUM(input_tokens),0) i, "
                f"COALESCE(SUM(output_tokens),0) o, MAX(ts) last FROM usage_log l "
                f"WHERE l.key_id=?{pred}", [k["id"], *p]
            ).fetchone()
            lats = [r[0] for r in self.connect().execute(
                f"SELECT latency_ms FROM usage_log l WHERE l.key_id=?{pred}",
                [k["id"], *p],
            ).fetchall()]
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
            " GROUP BY date ORDER BY date", [key_id, *p]
        ).fetchall()
        return [dict(r) for r in rows]

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
        return [self._distill_row(r) for r in rows]

    def get_distill_provider(self, provider_id) -> dict | None:
        row = self.connect().execute(
            "SELECT * FROM distill_providers WHERE id=?", (provider_id,)).fetchone()
        return self._distill_row(row) if row else None

    @staticmethod
    def _distill_row(row) -> dict:
        out = dict(row)
        try:
            out["key_hints"] = json.loads(out["key_hints"]) if out["key_hints"] else []
        except (ValueError, TypeError):
            out["key_hints"] = []
        return out

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

    def distill_usage_totals(self, from_day=None, to_day=None) -> list[dict]:
        """全 provider 按日 token 汇总 —— 预算告警的依据（P2-2）。"""
        where, params = [], []
        if from_day:
            where.append("day >= ?"); params.append(from_day)
        if to_day:
            where.append("day <= ?"); params.append(to_day)
        w = (" WHERE " + " AND ".join(where)) if where else ""
        rows = self.connect().execute(
            "SELECT day, SUM(tokens) AS tokens FROM distill_usage" + w +
            " GROUP BY day ORDER BY day DESC", params).fetchall()
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

    # ---- scenario domains & scenarios ------------------------------------

    def seed_scenarios(self) -> None:
        """幂等播种：把 run_matrix 已知的医疗场景落库。

        INSERT OR IGNORE 按 slug 去重，所以重复初始化不会插脏数据，也不会覆盖用户
        后续对标签/ spec_path 的编辑。仅当「域/场景表不存在或为空」时才需要，但放这里
        每次建库都跑一次、代价可忽略。
        """
        paths.ensure_medical_on_path()
        from run_matrix import SCENARIOS as _RM_SCENARIOS
        labels = {
            "critical-value": ("危急值", "Critical Value"),
            "diagnosis": ("诊断", "Diagnosis"),
            "icd-coding": ("ICD 编码", "ICD Coding"),
            "medication-review": ("用药审查", "Medication Review"),
            "nursing-quality": ("护理质量", "Nursing Quality"),
            "record-summary": ("病历摘要", "Record Summary"),
            "triage": ("分诊", "Triage"),
        }
        with self.tx() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO scenario_domains (id, slug, label_zh, label_en, sort, created_at)"
                " VALUES (?,?,?,?,?,?)",
                ("medical", "medical", "医疗", "Medical", 0, _now()))
            domain_id = "medical"
            for idx, name in enumerate(_RM_SCENARIOS):
                zh, en = labels.get(name, (name, name))
                connection.execute(
                    "INSERT OR IGNORE INTO scenarios"
                    " (id, domain_id, slug, label_zh, label_en, spec_path, category, sort, created_at, updated_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (uuid.uuid4().hex, domain_id, name, zh, en,
                     f"docs/medical/specs/{name}.json", "medical", idx, _now(), _now()))

    def list_scenario_slugs(self) -> list[str]:
        rows = self.connect().execute(
            "SELECT slug FROM scenarios ORDER BY sort, slug").fetchall()
        return [r["slug"] for r in rows]

    def list_scenario_tree(self, lang: str = "zh") -> list[dict]:
        """两级树：域下挂场景。label 按 lang 取中/英；spec 文件缺失仅标 exists=False。"""
        label = "label_en" if lang == "en" else "label_zh"
        domains = self.connect().execute(
            "SELECT * FROM scenario_domains ORDER BY sort, slug").fetchall()
        scenes = self.connect().execute("SELECT * FROM scenarios ORDER BY sort, slug").fetchall()
        by_domain: dict[str, list[dict]] = {}
        for s in scenes:
            spec = (paths.ROOT / s["spec_path"]).resolve()
            by_domain.setdefault(s["domain_id"], []).append({
                "id": s["id"], "slug": s["slug"], "label": s[label],
                "label_zh": s["label_zh"], "label_en": s["label_en"],
                "spec_path": s["spec_path"], "category": s["category"],
                "sort": s["sort"], "exists": spec.is_file()})
        tree = []
        for d in domains:
            tree.append({
                "id": d["id"], "slug": d["slug"], "label": d[label],
                "label_zh": d["label_zh"], "label_en": d["label_en"],
                "sort": d["sort"], "scenarios": by_domain.get(d["id"], [])})
        return tree

    def get_scenario_by_slug(self, slug: str) -> dict | None:
        row = self.connect().execute(
            "SELECT * FROM scenarios WHERE slug=?", (slug,)).fetchone()
        return dict(row) if row else None

    def get_scenario_by_id(self, scenario_id: str) -> dict | None:
        row = self.connect().execute(
            "SELECT * FROM scenarios WHERE id=?", (scenario_id,)).fetchone()
        return dict(row) if row else None

    def get_domain(self, domain_id: str) -> dict | None:
        row = self.connect().execute(
            "SELECT * FROM scenario_domains WHERE id=?", (domain_id,)).fetchone()
        return dict(row) if row else None

    def resolve_spec_path(self, slug: str) -> Path:
        """返回场景 spec 文件的绝对路径（先查 DB.spec_path，相对仓库根解析）。

        不校验文件是否存在——调用方（_spec / read_spec_file）按需判缺。场景不存在抛 KeyError。
        """
        row = self.get_scenario_by_slug(slug)
        if row is None:
            raise KeyError(slug)
        return (paths.ROOT / row["spec_path"]).resolve()

    # ---- domain CRUD ------------------------------------------------------

    def create_domain(self, *, slug, label_zh, label_en, sort=0) -> str:
        domain_id = uuid.uuid4().hex
        self.connect().execute(
            "INSERT INTO scenario_domains (id, slug, label_zh, label_en, sort, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (domain_id, slug, label_zh, label_en, int(sort), _now()))
        self.connect().commit()
        return domain_id

    def update_domain(self, domain_id, *, label_zh=None, label_en=None, sort=None) -> bool:
        fields, params = [], []
        if label_zh is not None:
            fields.append("label_zh=?"); params.append(label_zh)
        if label_en is not None:
            fields.append("label_en=?"); params.append(label_en)
        if sort is not None:
            fields.append("sort=?"); params.append(int(sort))
        if not fields:
            return True
        cursor = self.connect().execute(
            f"UPDATE scenario_domains SET {', '.join(fields)} WHERE id=?", (*params, domain_id))
        self.connect().commit()
        return cursor.rowcount == 1

    def delete_domain(self, domain_id) -> bool:
        with self.tx() as connection:
            connection.execute("DELETE FROM scenarios WHERE domain_id=?", (domain_id,))
            cursor = connection.execute(
                "DELETE FROM scenario_domains WHERE id=?", (domain_id,))
        return cursor.rowcount == 1

    # ---- scenario CRUD ----------------------------------------------------

    def create_scenario(self, *, domain_id, slug, label_zh, label_en, spec_path,
                        category="medical", sort=0) -> str:
        scenario_id = uuid.uuid4().hex
        now = _now()
        self.connect().execute(
            "INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path,"
            " category, sort, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (scenario_id, domain_id, slug, label_zh, label_en, spec_path, category,
             int(sort), now, now))
        self.connect().commit()
        return scenario_id

    def update_scenario(self, scenario_id, *, domain_id=None, label_zh=None, label_en=None,
                        spec_path=None, category=None, sort=None) -> bool:
        fields, params = [], []
        if domain_id is not None:
            fields.append("domain_id=?"); params.append(domain_id)
        if label_zh is not None:
            fields.append("label_zh=?"); params.append(label_zh)
        if label_en is not None:
            fields.append("label_en=?"); params.append(label_en)
        if spec_path is not None:
            fields.append("spec_path=?"); params.append(spec_path)
        if category is not None:
            fields.append("category=?"); params.append(category)
        if sort is not None:
            fields.append("sort=?"); params.append(int(sort))
        if not fields:
            return True
        fields.append("updated_at=?")
        params.append(_now())
        cursor = self.connect().execute(
            f"UPDATE scenarios SET {', '.join(fields)} WHERE id=?", (*params, scenario_id))
        self.connect().commit()
        return cursor.rowcount == 1

    def delete_scenario(self, scenario_id) -> bool:
        cursor = self.connect().execute("DELETE FROM scenarios WHERE id=?", (scenario_id,))
        self.connect().commit()
        return cursor.rowcount == 1

    # ---- spec file read/write (sandboxed under repo root) ----------------

    def read_spec_file(self, slug: str) -> str:
        path = self.resolve_spec_path(slug)
        if not path.is_file():
            raise FileNotFoundError(
                f"spec 文件不存在：{path}（场景 {slug} 的 spec_path 未指向有效文件）")
        return path.read_text(encoding="utf-8")

    def write_spec_file(self, slug: str, content: str) -> None:
        """写回场景 spec 文件。校验 JSON 合法性与必要字段，并限制路径在仓库根内。

        覆盖已存在文件前先留档到 data/console/spec-history/<slug>/（保留最近 20 版）——
        spec 在线编辑直接写回源文件，没有版本管理等于没有撤销。
        """
        path = self.resolve_spec_path(slug)
        root = paths.ROOT.resolve()
        if path != root and root not in path.parents:
            raise ValueError(f"spec_path 必须在仓库根内：{path}")
        if not str(path).endswith(".json"):
            raise ValueError("spec_path 必须是 .json 文件")
        try:
            data = json.loads(content)
        except ValueError as error:
            raise ValueError(f"spec 不是合法 JSON：{error}") from error
        for field in ("name", "domain", "state", "questions"):
            if not data.get(field):
                raise ValueError(f"spec 缺少必要字段 {field!r}")
        if not isinstance(data.get("questions"), dict) or not data["questions"]:
            raise ValueError("spec.questions 必须是非空对象")
        if path.is_file():
            self._snapshot_spec(slug, path.read_text(encoding="utf-8"))
        path.write_text(content, encoding="utf-8")

    SPEC_HISTORY_LIMIT = 20

    def _spec_history_dir(self, slug: str) -> Path:
        return Path(paths.ROOT) / paths.CONSOLE_REL / "spec-history" / slug

    def _snapshot_spec(self, slug: str, previous: str) -> None:
        directory = self._spec_history_dir(slug)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        (directory / f"{stamp}.json").write_text(previous, encoding="utf-8")
        versions = sorted(directory.glob("*.json"))
        for stale in versions[:-self.SPEC_HISTORY_LIMIT]:
            stale.unlink(missing_ok=True)

    def list_spec_history(self, slug: str) -> list[dict]:
        """历史版本列表，新的在前。只报版本号，内容按需拉取（spec 可能很大）。"""
        directory = self._spec_history_dir(slug)
        if not directory.is_dir():
            return []
        return [{"ts": item.stem} for item in sorted(directory.glob("*.json"), reverse=True)]

    def read_spec_history(self, slug: str, ts: str) -> str:
        target = self._spec_history_dir(slug) / f"{Path(ts).stem}.json"
        if not target.is_file():
            raise FileNotFoundError(f"没有这个历史版本：{ts}")
        return target.read_text(encoding="utf-8")
