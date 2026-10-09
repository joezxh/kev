"""编排层的持久化：作业状态机、产物、血缘、事件、场景 spec 配置。

三条设计约定（spec §5 / §9）：
- 跨方言：用 SQLAlchemy Core 的 Engine/Connection 管理连接与事务（非 ORM），SQL 文本仍由
  本项目掌控。sqlite 与 postgresql 由环境变量 KEV_CONSOLE_DB_BACKEND 切换（见 backend_url）。
- 日志文件是真相源，events 表只是给 UI 的可分页尾巴（首屏回填 + Last-Event-ID 续传）
- 状态机集中校验：succeeded -> running 这类转移必须被拒

配置持久化（改进 1）：场景 spec 的当前内容存 scenarios.spec_json 列，历史版本存
scenario_spec_history 表，运行时不再依赖 docs/medical/specs/*.json 本地文件。
"""
from __future__ import annotations

import contextlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import text

from . import paths

SCHEMA_VERSION = 4

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


# ---------------------------------------------------------------------------
# 后端选择：通过环境变量在 sqlite / postgresql 之间切换（改进 2）
# ---------------------------------------------------------------------------
def backend_url() -> sa.URL:
    """按环境变量产出 SQLAlchemy URL。

    KEV_CONSOLE_DB_BACKEND = sqlite（默认） | postgres
      sqlite : KEV_CONSOLE_DB_PATH（缺省 paths.DB_PATH），兼容旧变量 KEV_CONSOLE_DB
      postgres: KEV_CONSOLE_DB_HOST/PORT/USER/PASSWORD/NAME（可选 SCHEMA）
    """
    backend = os.environ.get("KEV_CONSOLE_DB_BACKEND", "sqlite").lower()
    if backend in ("postgres", "postgresql"):
        host = os.environ.get("KEV_CONSOLE_DB_HOST", "localhost")
        port = int(os.environ.get("KEV_CONSOLE_DB_PORT", "5432"))
        user = os.environ.get("KEV_CONSOLE_DB_USER", "postgres")
        password = os.environ.get("KEV_CONSOLE_DB_PASSWORD", "")
        name = os.environ.get("KEV_CONSOLE_DB_NAME", "kev_console")
        schema = os.environ.get("KEV_CONSOLE_DB_SCHEMA", "")
        query = {}
        if schema:
            query["options"] = f"-csearch_path={schema}"
        return sa.URL.create(
            "postgresql+psycopg", username=user, password=password,
            host=host, port=port, database=name, query=query,
        )
    # sqlite
    raw = (os.environ.get("KEV_CONSOLE_DB_PATH")
           or os.environ.get("KEV_CONSOLE_DB")   # 兼容旧变量
           or str(paths.DB_PATH))
    return sa.URL.create("sqlite", database=str(Path(raw)))


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


def _ddl(backend: str) -> str:
    """建表 DDL（建表 + 初始数据里除 seed 之外的结构）。两种方言仅自增列与浮点类型不同。"""
    # NOTE: self.backend is "postgresql" (from URL.get_backend_name()); use startswith
    # so both "postgres" and "postgresql" select the Postgres dialect, not sqlite.
    autoinc = "BIGSERIAL PRIMARY KEY" if backend.startswith("postgres") else "INTEGER PRIMARY KEY AUTOINCREMENT"
    real = "DOUBLE PRECISION" if backend.startswith("postgres") else "REAL"
    return f"""
CREATE TABLE IF NOT EXISTS console_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

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
  parent   TEXT NOT NULL,
  child    TEXT NOT NULL,
  relation TEXT NOT NULL,
  job_id   TEXT REFERENCES jobs(id),
  PRIMARY KEY (parent, child, relation)
);

CREATE TABLE IF NOT EXISTS events (
  id     {autoinc},
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
  id {autoinc},
  key_id TEXT NOT NULL REFERENCES api_keys(id),
  endpoint TEXT NOT NULL,
  method TEXT NOT NULL,
  status INTEGER NOT NULL,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  latency_ms {real} NOT NULL,
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
  id {autoinc},
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
  spec_json  TEXT,
  category   TEXT NOT NULL DEFAULT 'medical',
  sort       INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS scenarios_slug_idx   ON scenarios(slug);
CREATE INDEX IF NOT EXISTS scenarios_domain_idx ON scenarios(domain_id);

CREATE TABLE IF NOT EXISTS scenario_spec_history (
  id          TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL REFERENCES scenarios(id),
  spec_json   TEXT NOT NULL,
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS spec_history_scenario_idx ON scenario_spec_history(scenario_id, created_at DESC);
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


class _Conn:
    """连接代理：把 SQLAlchemy 2.0「不自动提交」补齐成「写语句在显式事务外自动提交」。

    SQLAlchemy 2.0 的 Connection 在任意语句后都会 autobegin 一个事务，且不会自动提交；
    原本基于 sqlite3（每条语句后手动 commit）的代码若直接平移会丢失写入。这里在代理层：
    - 读语句（SELECT / PRAGMA 探测）不提交；
    - 写语句（INSERT/UPDATE/DELETE/...）且当前不在 self.tx() 显式事务内时，执行后提交。

    在 self.tx() 内（store._in_tx 为 True）一律不提交，交给事务统一收尾。
    """

    _WRITE_PREFIXES = (
        "INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "REPLACE", "PRAGMA",
    )

    def __init__(self, conn: "sa.Connection", store: "Store"):
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_store", store)

    def execute(self, stmt, params=None):
        proxy = self._store._conn()
        try:
            result = proxy._conn.execute(stmt, params)
        except sa.exc.InternalError:
            # 事务被服务端中止（常见：连接以 idle-in-transaction 挂起被超时中止，
            # 或本连接上一条语句失败）。回滚并换新连接重试一次，避免毒连接一直 500。
            if getattr(self._store._local, "in_tx", False):
                raise  # 在显式事务里由 tx() 负责回滚，不要脱离事务自作主张
            try:
                proxy._conn.rollback()
            except Exception:
                pass
            self._reset_conn()
            proxy = self._store._conn()
            result = proxy._conn.execute(stmt, params)
        if getattr(self._store._local, "in_tx", False):
            return result
        head = str(stmt).strip().upper()
        if head.startswith(self._WRITE_PREFIXES):
            if proxy._conn.in_transaction:
                proxy._conn.commit()
        else:
            # 读语句执行完显式结束事务：否则连接以 idle-in-transaction 挂起，
            # Postgres 会因 idle_in_transaction_session_timeout 中止它，下次用就 500。
            if proxy._conn.in_transaction:
                proxy._conn.rollback()
        return result

    def _reset_conn(self):
        """丢弃本线程缓存的连接（出错/中止后恢复用），下次 _conn() 取新连接。"""
        proxy = getattr(self._store._local, "proxy", None)
        if proxy is not None:
            try:
                proxy._conn.close()
            except Exception:
                pass
            self._store._local.proxy = None

    def exec_driver_sql(self, *args, **kwargs):
        return self._conn.exec_driver_sql(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._conn, name)


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

    def __init__(self, db_path: "Path | str | None" = None, *, url: "sa.URL | str | None" = None):
        if url is None:
            if db_path is not None:
                # 单测直传路径：固定走 sqlite
                url = sa.URL.create("sqlite", database=str(Path(db_path)))
            else:
                url = backend_url()
        self.url = sa.make_url(url) if not isinstance(url, sa.URL) else url
        self.backend = "postgresql" if self.url.get_backend_name().startswith("postgres") else "sqlite"
        connect_args = {"check_same_thread": False} if self.backend == "sqlite" else {}
        self.engine = sa.create_engine(self.url, connect_args=connect_args, pool_pre_ping=True)
        self._local = threading.local()
        self._in_tx = False
        self._init_schema()
        self._migrate()
        # 幂等播种：把 run_matrix 已知的医疗场景落库（INSERT OR IGNORE 按 slug 去重，
        # 不覆盖用户后续编辑）。建库即播种，保证 fresh DB 也能开箱即用。
        self.seed_scenarios()

    # ---- connection / transaction ---------------------------------------

    def _conn(self) -> "_Conn":
        proxy = getattr(self._local, "proxy", None)
        if proxy is None or proxy._conn.closed:
            real = self.engine.connect()
            if self.backend == "sqlite":
                # 显式开启并立即提交，避免 PRAGMA 在非 DML 下触发 autobegin 留下悬挂事务
                with real.begin():
                    real.exec_driver_sql("PRAGMA journal_mode=WAL")
                    real.exec_driver_sql("PRAGMA foreign_keys=ON")
            proxy = _Conn(real, self)
            self._local.proxy = proxy
            self._local.conn = real
        return proxy

    @contextlib.contextmanager
    def tx(self):
        """一个写事务：BEGIN IMMEDIATE 当场拿写锁，让「读-改-写」整体串行化。

        连接是每线程一个（FastAPI 的同步路由跑在线程池里），所以这里只能锁住**本线程**的连接：
        事务里不要把连接交出去给别的线程，也不要调会自己 commit 的方法
        （put_artifact / add_lineage 的 commit=True 会提前结束事务）。

        SQLite 专有写法（PRAGMA、SELECT）会触发 SQLAlchemy 的 autobegin 留下悬挂事务，
        这里在开新事务前先回滚它（仅含已自动提交的读/PRAGMA，无未提交写入）。
        """
        self._local.in_tx = True
        conn = self._conn()
        if conn.in_transaction:
            conn.rollback()
        trans = conn.begin()
        try:
            yield conn
        except BaseException:
            trans.rollback()
            raise
        else:
            trans.commit()
        finally:
            self._local.in_tx = False

    def _upsert_ignore_sql(self, table: str, columns: list[str], conflict_cols: list[str]) -> "sa.TextClause":
        """按后端产出「冲突则忽略」的 INSERT：sqlite 用 INSERT OR IGNORE，postgres 用 ON CONFLICT DO NOTHING。"""
        cols = ", ".join(columns)
        ph = ", ".join(f":{c}" for c in columns)
        if self.backend == "sqlite":
            return text(f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({ph})")
        return text(
            f"INSERT INTO {table} ({cols}) VALUES ({ph}) "
            f"ON CONFLICT ({', '.join(conflict_cols)}) DO NOTHING"
        )

    # ---- schema version (console_meta，两端通用) ------------------------

    def schema_version(self) -> int:
        try:
            row = self._conn().execute(
                text("SELECT value FROM console_meta WHERE key='schema_version'")).mappings().fetchone()
        except Exception:
            return 0
        return int(row["value"]) if row else 0

    def _init_schema(self) -> None:
        with self.engine.begin() as conn:
            for stmt in _ddl(self.backend).split(";"):
                stripped = stmt.strip()
                if stripped:
                    conn.execute(text(stripped))
        # 新库：写入当前 schema 版本
        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT value FROM console_meta WHERE key='schema_version'")).mappings().fetchone()
            if row is None:
                version = 0
                if self.backend == "sqlite":
                    version = conn.exec_driver_sql("PRAGMA user_version").fetchone()[0]
                conn.execute(
                    text("INSERT INTO console_meta(key, value) VALUES('schema_version', :v)"),
                    {"v": str(version)},
                )

    def _column_exists(self, table: str, column: str) -> bool:
        if self.backend == "sqlite":
            rows = self._conn().execute(text(f"PRAGMA table_info({table})")).mappings().fetchall()
            # PRAGMA table_info 列：cid, name, type, notnull, dflt_value, pk（name 在第 2 列）
            return any(r["name"] == column for r in rows)
        rows = self._conn().execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name=:t"),
            {"t": table}).mappings().fetchall()
        return any(r["column_name"] == column for r in rows)

    def _migrate(self) -> None:
        """一次性、幂等迁移（旧 sqlite 库：补 spec_json 列 + 回填 spec 内容）。"""
        version = self.schema_version()
        if version >= SCHEMA_VERSION:
            return
        if version < 4:
            if not self._column_exists("scenarios", "spec_json"):
                with self.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE scenarios ADD COLUMN spec_json TEXT"))
            self._backfill_specs()
            with self.engine.begin() as conn:
                conn.execute(
                    text("UPDATE console_meta SET value=:v WHERE key='schema_version'"),
                    {"v": str(SCHEMA_VERSION)},
                )

    # ---- jobs -------------------------------------------------------------

    def create_job(self, *, kind, stage, scenario, title, request, argv, env_overlay,
                   cwd, log_path, artifacts_in, artifacts_out, parent_id=None,
                   attempt=1) -> str:
        """attempt 是「第几次尝试」：重试（换名续跑）时由调用方递增，jobs 表据此区分
        首次执行与重试。parent_id 指向被重试的那个作业。
        """
        job_id = uuid.uuid4().hex
        self._conn().execute(
            text("INSERT INTO jobs (id, kind, stage, scenario, title, status, request, argv, env_overlay, cwd,"
                 " log_path, artifacts_in, artifacts_out, parent_id, attempt, created_at)"
                 " VALUES (:id,:kind,:stage,:scenario,:title,'pending',:request,:argv,:env_overlay,:cwd,"
                 " :log_path,:artifacts_in,:artifacts_out,:parent_id,:attempt,:created_at)"),
            dict(id=job_id, kind=kind, stage=stage, scenario=scenario, title=title,
                 request=_dumps(request), argv=_dumps(argv), env_overlay=_dumps(env_overlay),
                 cwd=str(cwd), log_path=str(log_path), artifacts_in=_dumps(artifacts_in),
                 artifacts_out=_dumps(artifacts_out), parent_id=parent_id, attempt=int(attempt),
                 created_at=_now()),
        )
        return job_id

    def get_job(self, job_id) -> dict | None:
        row = self._conn().execute(text("SELECT * FROM jobs WHERE id = :id"), {"id": job_id}).mappings().fetchone()
        return _job(row) if row else None

    def list_jobs(self, *, status=None, stage=None, scenario=None, limit=200) -> list[dict]:
        clauses, params = [], {}
        for column, value in (("status", status), ("stage", stage), ("scenario", scenario)):
            if value is not None:
                clauses.append(f"{column} = :{column}")
                params[column] = value
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params["limit"] = limit
        rows = self._conn().execute(
            text(f"SELECT * FROM jobs{where} ORDER BY created_at DESC, rowid DESC LIMIT :limit"), params
        ).mappings().fetchall()
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
        params: dict = {"to": to_status, "job_id": job_id}
        assignments = ["status = :to"]
        if to_status == "running":
            # COALESCE：started_at 只在第一次进 running 时落时间，重跑不会覆盖它。
            assignments.append("started_at = COALESCE(started_at, :started)")
            params["started"] = _now()
        if to_status in TERMINAL:
            assignments.append("finished_at = :finished")
            params["finished"] = _now()
        if error is not None:
            assignments.append("error = :error")
            params["error"] = error
        if exit_code is not None:
            assignments.append("exit_code = :exit_code")
            params["exit_code"] = exit_code

        with self.tx() as conn:
            changed = 0
            if sources:
                in_clause = ", ".join(f":s{i}" for i in range(len(sources)))
                for i, s in enumerate(sources):
                    params[f"s{i}"] = s
                sql = ("UPDATE jobs SET " + ", ".join(assignments)
                       + " WHERE id = :job_id AND status IN (" + in_clause + ")")
                changed = conn.execute(text(sql), params).rowcount
            if not changed:
                row = conn.execute(
                    text("SELECT status FROM jobs WHERE id = :job_id"), {"job_id": job_id}).mappings().fetchone()
        if changed:
            return
        if row is None:
            raise KeyError(job_id)
        raise ValueError(f"illegal transition {row['status']} -> {to_status} for job {job_id}")

    def active_job_of_kind(self, kind) -> dict | None:
        placeholders = ", ".join(f":s{i}" for i in range(len(LIVE)))
        params = {f"s{i}": s for i, s in enumerate(sorted(LIVE))}
        params["kind"] = kind
        row = self._conn().execute(
            text(f"SELECT * FROM jobs WHERE kind = :kind AND status IN ({placeholders})"
                 " ORDER BY created_at DESC LIMIT 1"), params
        ).mappings().fetchone()
        return _job(row) if row else None

    def interrupt_stale_jobs(self) -> int:
        """编排服务启动时调用：WSL2 会自动回收内存，重启后残留的 running 一律算 interrupted。"""
        placeholders = ", ".join(f":s{i}" for i in range(len(LIVE)))
        params = {f"s{i}": s for i, s in enumerate(sorted(LIVE))}
        cursor = self._conn().execute(
            text(f"UPDATE jobs SET status = 'interrupted', error = :err, finished_at = :fin"
                 f" WHERE status IN ({placeholders})"),
            {"err": "编排服务重启", "fin": _now(), **params},
        )
        return cursor.rowcount

    # ---- artifacts --------------------------------------------------------

    def put_artifact(self, *, kind, name, path, meta, bytes_=None, commit: bool = True) -> str:
        """登记/更新一个产物。commit=False 让它留在调用方的事务里（见 Store.tx）。"""
        artifact_id = f"{kind}:{name}"
        self._conn().execute(
            text("INSERT INTO artifacts (id, kind, name, path, meta, bytes, created_at) VALUES "
                 "(:id,:kind,:name,:path,:meta,:bytes,:created_at) "
                 "ON CONFLICT(id) DO UPDATE SET path = excluded.path, meta = excluded.meta,"
                 " bytes = excluded.bytes"),
            dict(id=artifact_id, kind=kind, name=name, path=str(path), meta=_dumps(meta),
                 bytes=bytes_, created_at=_now()),
        )
        return artifact_id

    def get_artifact(self, artifact_id) -> dict | None:
        row = self._conn().execute(
            text("SELECT * FROM artifacts WHERE id = :id"), {"id": artifact_id}).mappings().fetchone()
        if row is None:
            return None
        out = dict(row)
        out["meta"] = _loads(out["meta"])
        return out

    def list_artifacts(self, kind=None) -> list[dict]:
        if kind is None:
            rows = self._conn().execute(
                text("SELECT * FROM artifacts ORDER BY created_at DESC")).mappings().fetchall()
        else:
            rows = self._conn().execute(
                text("SELECT * FROM artifacts WHERE kind = :kind ORDER BY created_at DESC"),
                {"kind": kind}).mappings().fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["meta"] = _loads(item["meta"])
            out.append(item)
        return out

    # ---- lineage ----------------------------------------------------------

    def add_lineage(self, parent, child, relation, job_id=None, *, commit: bool = True) -> None:
        """记一条产物血缘。commit=False 让它留在调用方的事务里（见 Store.tx）。"""
        self._conn().execute(
            self._upsert_ignore_sql(
                "lineage", ["parent", "child", "relation", "job_id"], ["parent", "child", "relation"]),
            dict(parent=parent, child=child, relation=relation, job_id=job_id),
        )

    def lineage_of(self, artifact_id) -> list[dict]:
        """出边（这个产物派生了什么）。入边查 child 那一侧。"""
        rows = self._conn().execute(
            text("SELECT * FROM lineage WHERE parent = :p"), {"p": artifact_id}).mappings().fetchall()
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

        跨方言：sqlite / postgres 都支持 INSERT ... RETURNING id（executemany 时
        inserted_primary_key_rows 给出全部生成的主键，取最后一条）。
        """
        rows = list(rows)
        if not rows:
            return 0
        stamp = _now()
        payload = [dict(job_id=job_id, ts=stamp, stream=stream, line=line) for stream, line in rows]
        # 走真实连接 + 显式事务：逐行 INSERT 并取 RETURNING id。
        # 注意：sqlite 的 executemany 不支持 RETURNING（bad parameter），故逐行插入；
        # 事件量不大，逐行开销可接受，且跨方言统一（postgres 同样可用 RETURNING id）。
        real = self._conn()._conn
        if real.in_transaction:
            real.rollback()
        ids: list[int] = []
        with real.begin():
            for stream, line in rows:
                r = real.execute(
                    text("INSERT INTO events (job_id, ts, stream, line) VALUES "
                         "(:job_id,:ts,:stream,:line) RETURNING id"),
                    dict(job_id=job_id, ts=stamp, stream=stream, line=line),
                )
                ids.append(r.mappings().fetchone()["id"])
        return ids[-1] if ids else 0

    def read_events(self, job_id, after_id=0, limit=500) -> list[dict]:
        rows = self._conn().execute(
            text("SELECT * FROM events WHERE job_id = :job_id AND id > :after_id ORDER BY id LIMIT :limit"),
            dict(job_id=job_id, after_id=after_id, limit=limit),
        ).mappings().fetchall()
        return [dict(row) for row in rows]

    def tail_text(self, job_id, lines=30) -> str:
        """子进程非零退出时给错误体的 stderr_tail（spec §10.2）。"""
        rows = self._conn().execute(
            text("SELECT stream, line FROM events WHERE job_id = :job_id ORDER BY id DESC LIMIT :lines"),
            dict(job_id=job_id, lines=lines),
        ).mappings().fetchall()
        return "\n".join(f"[{row['stream']}] {row['line']}" for row in reversed(rows))

    # ---- api keys ---------------------------------------------------------

    def create_api_key(self, name: str) -> tuple[str, dict]:
        import hashlib
        import secrets as _secrets
        raw = "kev_" + _secrets.token_hex(32)
        key_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        key_id = uuid.uuid4().hex
        self._conn().execute(
            text("INSERT INTO api_keys (id, name, key_hash, prefix, active, created_at) "
                 "VALUES (:id,:name,:key_hash,:prefix,1,:created_at)"),
            dict(id=key_id, name=name, key_hash=key_hash, prefix=raw[:12], created_at=_now()),
        )
        row = self._conn().execute(
            text("SELECT * FROM api_keys WHERE id=:id"), {"id": key_id}).mappings().fetchone()
        # 凭据即 key 的 id：前端从服务端列表拿到 id，选中后原样提交，
        # 后端按 id 校验「存在且 active」即可用（见 app.proxy_kev），无需前端持有任何密钥。
        return key_id, dict(row)

    def get_key_by_hash(self, key_hash: str) -> dict | None:
        row = self._conn().execute(
            text("SELECT * FROM api_keys WHERE key_hash=:h AND active=1"), {"h": key_hash}).mappings().fetchone()
        return dict(row) if row else None

    def get_key_by_id(self, key_id: str) -> dict | None:
        row = self._conn().execute(
            text("SELECT * FROM api_keys WHERE id=:id AND active=1"), {"id": key_id}).mappings().fetchone()
        return dict(row) if row else None

    def list_api_keys(self, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
        page = max(1, int(page))
        page_size = max(1, min(int(page_size), 100000))
        offset = (page - 1) * page_size
        total = self._conn().execute(text("SELECT COUNT(*) AS n FROM api_keys")).scalar() or 0
        rows = self._conn().execute(
            text("SELECT a.id, a.name, a.prefix, a.active, a.created_at, a.revoked_at, "
                 "COALESCE(u.calls,0) AS calls, "
                 "COALESCE(u.input_tokens,0) AS input_tokens, "
                 "COALESCE(u.output_tokens,0) AS output_tokens, u.last_used "
                 "FROM api_keys a LEFT JOIN ("
                 "  SELECT key_id, COUNT(*) AS calls, SUM(input_tokens) AS input_tokens, "
                 "  SUM(output_tokens) AS output_tokens, MAX(ts) AS last_used "
                 "  FROM usage_log GROUP BY key_id) u ON u.key_id=a.id "
                 "ORDER BY a.created_at DESC "
                 "LIMIT :limit OFFSET :offset"),
            dict(limit=page_size, offset=offset),
        ).mappings().fetchall()
        items = [{**dict(r), "active": bool(r["active"])} for r in rows]
        return items, total

    def revoke_api_key(self, key_id: str) -> bool:
        cursor = self._conn().execute(
            text("UPDATE api_keys SET active=0, revoked_at=:rev WHERE id=:id AND active=1"),
            dict(rev=_now(), id=key_id),
        )
        return cursor.rowcount == 1

    def reactivate_api_key(self, key_id: str) -> bool:
        cursor = self._conn().execute(
            text("UPDATE api_keys SET active=1, revoked_at=NULL WHERE id=:id AND active=0"),
            dict(id=key_id),
        )
        return cursor.rowcount == 1

    def record_usage(self, *, key_id, endpoint, method, status,
                      input_tokens, output_tokens, latency_ms) -> None:
        self._conn().execute(
            text("INSERT INTO usage_log (key_id, endpoint, method, status, input_tokens, "
                 "output_tokens, latency_ms, ts) VALUES (:key_id,:endpoint,:method,:status,"
                 ":input_tokens,:output_tokens,:latency_ms,:ts)"),
            dict(key_id=key_id, endpoint=endpoint, method=method, status=int(status),
                 input_tokens=int(input_tokens), output_tokens=int(output_tokens),
                 latency_ms=float(latency_ms), ts=_now()),
        )

    def _usage_pred(self, from_ts, to_ts) -> tuple[str, dict]:
        clauses, params = [], {}
        if from_ts:
            clauses.append("ts >= :from")
            params["from"] = from_ts
        if to_ts:
            clauses.append("ts <= :to")
            params["to"] = to_ts
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
        keys = self._conn().execute(
            text("SELECT id, name, prefix, active FROM api_keys ORDER BY created_at DESC")
        ).mappings().fetchall()
        out = []
        for k in keys:
            row = dict(k)
            stat_params = {"key_id": k["id"], **p}
            stats = self._conn().execute(text(
                f"SELECT COUNT(*) c, COALESCE(SUM(input_tokens),0) i, "
                f"COALESCE(SUM(output_tokens),0) o, MAX(ts) last FROM usage_log l "
                f"WHERE l.key_id=:key_id{pred}"), stat_params).mappings().fetchone()
            lats = [r["latency_ms"] for r in self._conn().execute(text(
                f"SELECT latency_ms FROM usage_log l WHERE l.key_id=:key_id{pred}"),
                stat_params).mappings().fetchall()]
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
        params = {"key_id": key_id, **p}
        stmt = (f"SELECT substr(l.ts,1,10) AS date, COUNT(*) AS calls, "
                f"SUM(l.input_tokens) AS input_tokens, SUM(l.output_tokens) AS output_tokens, "
                f"AVG(l.latency_ms) AS avg_latency_ms FROM usage_log l WHERE l.key_id=:key_id{pred} "
                f"GROUP BY date ORDER BY date")
        rows = self._conn().execute(text(stmt), params).mappings().fetchall()
        return [dict(r) for r in rows]

    # ---- distill providers ------------------------------------------------

    def create_distill_provider(self, name, base_url, model, daily_limit, keys) -> dict:
        import json as _json
        provider_id = uuid.uuid4().hex
        hints = _json.dumps([(k[:3] + "..." + k[-4:]) for k in keys], ensure_ascii=False)
        self._conn().execute(
            text("INSERT INTO distill_providers (id, name, base_url, model, daily_limit, "
                 "key_count, key_hints, active, created_at) VALUES "
                 "(:id,:name,:base_url,:model,:daily_limit,:key_count,:key_hints,1,:created_at)"),
            dict(id=provider_id, name=name, base_url=base_url, model=model, daily_limit=int(daily_limit),
                 key_count=len(keys), key_hints=hints, created_at=_now()))
        return self.get_distill_provider(provider_id)

    def list_distill_providers(self) -> list[dict]:
        rows = self._conn().execute(
            text("SELECT * FROM distill_providers WHERE active=1 ORDER BY created_at DESC")).mappings().fetchall()
        return [self._distill_row(r) for r in rows]

    def get_distill_provider(self, provider_id) -> dict | None:
        row = self._conn().execute(
            text("SELECT * FROM distill_providers WHERE id=:id"), {"id": provider_id}).mappings().fetchone()
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
        cursor = self._conn().execute(
            text("UPDATE distill_providers SET active=0 WHERE id=:id AND active=1"),
            {"id": provider_id})
        return cursor.rowcount == 1

    def update_distill_provider(self, provider_id, name=None, base_url=None, model=None,
                                daily_limit=None, keys=None):
        """部分更新蒸馏 provider。keys 仅当为非空列表时才替换（空列表表示保留现有密钥）。"""
        import json as _json
        updates, params = [], {"id": provider_id}
        if name is not None:
            updates.append("name=:name"); params["name"] = name
        if base_url is not None:
            updates.append("base_url=:base_url"); params["base_url"] = base_url
        if model is not None:
            updates.append("model=:model"); params["model"] = model
        if daily_limit is not None:
            updates.append("daily_limit=:daily_limit"); params["daily_limit"] = int(daily_limit)
        if keys is not None and len(keys) > 0:
            hints = _json.dumps([(k[:3] + "..." + k[-4:]) for k in keys], ensure_ascii=False)
            updates.append("key_count=:key_count"); params["key_count"] = len(keys)
            updates.append("key_hints=:key_hints"); params["key_hints"] = hints
        if updates:
            self._conn().execute(
                text(f"UPDATE distill_providers SET {', '.join(updates)} WHERE id=:id AND active=1"),
                params)
        return self.get_distill_provider(provider_id)

    def upsert_distill_usage(self, *, job_id, provider_id, key_hash, key_hint,
                             model, base_url, day, tokens) -> None:
        # 两种方言都支持 ON CONFLICT ... DO UPDATE（sqlite 需 3.24+，环境满足）
        self._conn().execute(
            text("INSERT INTO distill_usage (job_id, provider_id, key_hash, key_hint, model, "
                 "base_url, day, tokens, ts) VALUES (:job_id,:provider_id,:key_hash,:key_hint,"
                 ":model,:base_url,:day,:tokens,:ts) "
                 "ON CONFLICT(provider_id, key_hash, day) DO UPDATE SET tokens=excluded.tokens, "
                 "job_id=excluded.job_id, model=excluded.model, base_url=excluded.base_url, ts=excluded.ts"),
            dict(job_id=job_id, provider_id=provider_id, key_hash=key_hash, key_hint=key_hint,
                 model=model, base_url=base_url, day=day, tokens=int(tokens), ts=_now()),
        )

    def distill_usage_by_provider(self, provider_id=None, from_day=None, to_day=None) -> list[dict]:
        where, params = [], {}
        if provider_id:
            where.append("provider_id=:provider_id"); params["provider_id"] = provider_id
        if from_day:
            where.append("day >= :from_day"); params["from_day"] = from_day
        if to_day:
            where.append("day <= :to_day"); params["to_day"] = to_day
        w = (" WHERE " + " AND ".join(where)) if where else ""
        rows = self._conn().execute(
            text("SELECT provider_id, key_hint, model, SUM(tokens) AS tokens, "
                 "COUNT(DISTINCT day) AS days, MAX(day) AS last_day FROM distill_usage" + w +
                 " GROUP BY provider_id, key_hint, model ORDER BY tokens DESC"), params).mappings().fetchall()
        return [dict(r) for r in rows]

    def distill_usage_totals(self, from_day=None, to_day=None) -> list[dict]:
        where, params = [], {}
        if from_day:
            where.append("day >= :from_day"); params["from_day"] = from_day
        if to_day:
            where.append("day <= :to_day"); params["to_day"] = to_day
        w = (" WHERE " + " AND ".join(where)) if where else ""
        rows = self._conn().execute(
            text("SELECT day, SUM(tokens) AS tokens FROM distill_usage" + w +
                 " GROUP BY day ORDER BY day DESC"), params).mappings().fetchall()
        return [dict(r) for r in rows]

    def distill_usage_by_job(self, job_id, from_day=None, to_day=None) -> list[dict]:
        where, params = ["job_id=:job_id"], {"job_id": job_id}
        if from_day:
            where.append("day >= :from_day"); params["from_day"] = from_day
        if to_day:
            where.append("day <= :to_day"); params["to_day"] = to_day
        rows = self._conn().execute(
            text("SELECT key_hint, model, SUM(tokens) AS tokens, COUNT(DISTINCT day) AS days, "
                 "MAX(day) AS last_day FROM distill_usage WHERE " + " AND ".join(where) +
                 " GROUP BY key_hint, model"), params).mappings().fetchall()
        out = [dict(r) for r in rows]
        job = self.get_job(job_id)
        prov = self.get_distill_provider((job["request"].get("provider_id") if job else "") or "")
        for r in out:
            r["daily_limit"] = prov["daily_limit"] if prov else 0
        return out

    # ---- scenario domains & scenarios ------------------------------------

    def seed_scenarios(self) -> None:
        """幂等播种：把 run_matrix 已知的医疗场景落库。

        INSERT OR IGNORE / ON CONFLICT 按 slug 去重，所以重复初始化不会插脏数据，也不会覆盖用户
        后续对标签/ spec_path 的编辑。spec 内容（spec_json）由 _backfill_specs 在库内补全，
        使空库自包含、运行时不再强制要求 docs/medical/specs/*.json 存在。
        """
        paths.ensure_generators_on_path()
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
        now = _now()
        with self.tx() as conn:
            conn.execute(
                self._upsert_ignore_sql(
                    "scenario_domains",
                    ["id", "slug", "label_zh", "label_en", "sort", "created_at"],
                    ["slug"]),
                dict(id="medical", slug="medical", label_zh="医疗", label_en="Medical",
                     sort=0, created_at=now),
            )
            for idx, name in enumerate(_RM_SCENARIOS):
                zh, en = labels.get(name, (name, name))
                conn.execute(
                    self._upsert_ignore_sql(
                        "scenarios",
                        ["id", "domain_id", "slug", "label_zh", "label_en", "spec_path",
                         "category", "sort", "created_at", "updated_at"],
                        ["slug"]),
                    dict(id=uuid.uuid4().hex, domain_id="medical", slug=name, zh=zh, en=en,
                         label_zh=zh, label_en=en, spec_path=f"docs/medical/specs/{name}.json",
                         category="medical", sort=idx, created_at=now, updated_at=now),
                )
        self._backfill_specs()

    def _backfill_specs(self) -> None:
        """把 docs/medical/specs/*.json 的本地内容回填进 scenarios.spec_json（仅填空行）。

        空库经此即自包含；旧库（迁移路径）也借由此把文件内容搬进 DB。文件缺失的行保持
        spec_json 为 NULL（运行时回退到文件，不影响启动）。
        """
        paths.ensure_generators_on_path()
        from run_matrix import SCENARIOS as _RM_SCENARIOS
        for name in _RM_SCENARIOS:
            row = self.get_scenario_by_slug(name)
            if row is None or row.get("spec_json"):
                continue
            spec_file = paths.SPECS / f"{name}.json"
            if spec_file.is_file():
                self._conn().execute(
                    text("UPDATE scenarios SET spec_json=:s, updated_at=:t WHERE id=:id"),
                    dict(s=spec_file.read_text(encoding="utf-8"), t=_now(), id=row["id"]),
                )

    def list_scenario_slugs(self) -> list[str]:
        rows = self._conn().execute(
            text("SELECT slug FROM scenarios ORDER BY sort, slug")).mappings().fetchall()
        return [r["slug"] for r in rows]

    def list_scenario_tree(self, lang: str = "zh") -> list[dict]:
        """两级树：域下挂场景。label 按 lang 取中/英；spec_json 非空即视为已配置（exists=True）。"""
        label = "label_en" if lang == "en" else "label_zh"
        domains = self._conn().execute(
            text("SELECT * FROM scenario_domains ORDER BY sort, slug")).mappings().fetchall()
        scenes = self._conn().execute(
            text("SELECT * FROM scenarios ORDER BY sort, slug")).mappings().fetchall()
        by_domain: dict[str, list[dict]] = {}
        for s in scenes:
            s = dict(s)
            spec_path = s.get("spec_path")
            file_exists = bool(s.get("spec_json")) or (
                (paths.ROOT / spec_path).resolve().is_file() if spec_path else False)
            by_domain.setdefault(s["domain_id"], []).append({
                "id": s["id"], "slug": s["slug"], "label": s[label],
                "label_zh": s["label_zh"], "label_en": s["label_en"],
                "spec_path": s.get("spec_path"), "spec_json": s.get("spec_json"),
                "category": s["category"], "sort": s["sort"], "exists": file_exists})
        tree = []
        for d in domains:
            d = dict(d)
            tree.append({
                "id": d["id"], "slug": d["slug"], "label": d[label],
                "label_zh": d["label_zh"], "label_en": d["label_en"],
                "sort": d["sort"], "scenarios": by_domain.get(d["id"], [])})
        return tree

    def get_scenario_by_slug(self, slug: str) -> dict | None:
        row = self._conn().execute(
            text("SELECT * FROM scenarios WHERE slug=:slug"), {"slug": slug}).mappings().fetchone()
        return dict(row) if row else None

    def get_scenario_by_id(self, scenario_id: str) -> dict | None:
        row = self._conn().execute(
            text("SELECT * FROM scenarios WHERE id=:id"), {"id": scenario_id}).mappings().fetchone()
        return dict(row) if row else None

    def get_domain(self, domain_id: str) -> dict | None:
        row = self._conn().execute(
            text("SELECT * FROM scenario_domains WHERE id=:id"), {"id": domain_id}).mappings().fetchone()
        return dict(row) if row else None

    def resolve_spec_path(self, slug: str) -> Path:
        """返回场景 spec_path 指向的文件绝对路径（相对仓库根解析）。仅作回退/存在性检查用，
        不再作为 spec 内容的真相源（真相源是 scenarios.spec_json）。场景不存在抛 KeyError。"""
        row = self.get_scenario_by_slug(slug)
        if row is None:
            raise KeyError(slug)
        spec_path = row.get("spec_path")
        if not spec_path:
            raise KeyError(slug)
        return (paths.ROOT / spec_path).resolve()

    def spec_file_path(self, slug: str) -> "Path | None":
        """返回可供生成器（generate_data.py / plan_size.py）直接按路径读取的 spec 文件。

        优先用 DB 的 spec_json 物化到 data/console/specs/<slug>.json（运行时投影，不依赖仓库内
        原始文件）；DB 为空时回退到仓库内 docs/medical/specs/<slug>.json；都没有返回 None。
        """
        row = self.get_scenario_by_slug(slug)
        if row is None:
            return None
        content = row.get("spec_json")
        if content:
            directory = paths.CONSOLE_SPECS
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{slug}.json"
            path.write_text(content, encoding="utf-8")
            return path
        # 回退到仓库内原始 spec 文件（旧库 / 测试）
        spec_path = row.get("spec_path")
        fallback = (paths.ROOT / spec_path).resolve() if spec_path else None
        if fallback and fallback.is_file():
            return fallback
        repo = paths.SPECS / f"{slug}.json"
        return repo if repo.is_file() else None

    # ---- domain CRUD ------------------------------------------------------

    def create_domain(self, *, slug, label_zh, label_en, sort=0) -> str:
        domain_id = uuid.uuid4().hex
        self._conn().execute(
            text("INSERT INTO scenario_domains (id, slug, label_zh, label_en, sort, created_at)"
                 " VALUES (:id,:slug,:label_zh,:label_en,:sort,:created_at)"),
            dict(id=domain_id, slug=slug, label_zh=label_zh, label_en=label_en,
                 sort=int(sort), created_at=_now()))
        return domain_id

    def update_domain(self, domain_id, *, label_zh=None, label_en=None, sort=None) -> bool:
        fields, params = {}, {}
        if label_zh is not None:
            fields["label_zh"] = ":label_zh"; params["label_zh"] = label_zh
        if label_en is not None:
            fields["label_en"] = ":label_en"; params["label_en"] = label_en
        if sort is not None:
            fields["sort"] = ":sort"; params["sort"] = int(sort)
        if not fields:
            return True
        params["domain_id"] = domain_id
        cursor = self._conn().execute(
            text(f"UPDATE scenario_domains SET {', '.join(f'{k}={v}' for k, v in fields.items())} "
                 f"WHERE id=:domain_id"), params)
        return cursor.rowcount == 1

    def delete_domain(self, domain_id) -> bool:
        with self.tx() as conn:
            conn.execute(
                text("DELETE FROM scenarios WHERE domain_id=:id"), {"id": domain_id})
            cursor = conn.execute(
                text("DELETE FROM scenario_domains WHERE id=:id"), {"id": domain_id})
        return cursor.rowcount == 1

    # ---- scenario CRUD ----------------------------------------------------

    def create_scenario(self, *, domain_id, slug, label_zh, label_en, spec_path,
                        category="medical", sort=0) -> str:
        scenario_id = uuid.uuid4().hex
        now = _now()
        self._conn().execute(
            text("INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path,"
                 " spec_json, category, sort, created_at, updated_at)"
                 " VALUES (:id,:domain_id,:slug,:label_zh,:label_en,:spec_path,"
                 " :spec_json,:category,:sort,:created_at,:updated_at)"),
            dict(id=scenario_id, domain_id=domain_id, slug=slug, label_zh=label_zh,
                 label_en=label_en, spec_path=spec_path, spec_json=None, category=category,
                 sort=int(sort), created_at=now, updated_at=now))
        return scenario_id

    def update_scenario(self, scenario_id, *, domain_id=None, label_zh=None, label_en=None,
                        spec_path=None, category=None, sort=None) -> bool:
        fields, params = {}, {}
        if domain_id is not None:
            fields["domain_id"] = ":domain_id"; params["domain_id"] = domain_id
        if label_zh is not None:
            fields["label_zh"] = ":label_zh"; params["label_zh"] = label_zh
        if label_en is not None:
            fields["label_en"] = ":label_en"; params["label_en"] = label_en
        if spec_path is not None:
            fields["spec_path"] = ":spec_path"; params["spec_path"] = spec_path
        if category is not None:
            fields["category"] = ":category"; params["category"] = category
        if sort is not None:
            fields["sort"] = ":sort"; params["sort"] = int(sort)
        if not fields:
            return True
        fields["updated_at"] = ":updated_at"; params["updated_at"] = _now()
        params["scenario_id"] = scenario_id
        cursor = self._conn().execute(
            text(f"UPDATE scenarios SET {', '.join(f'{k}={v}' for k, v in fields.items())} "
                 f"WHERE id=:scenario_id"), params)
        return cursor.rowcount == 1

    def delete_scenario(self, scenario_id) -> bool:
        with self.tx() as conn:
            conn.execute(
                text("DELETE FROM scenario_spec_history WHERE scenario_id=:id"), {"id": scenario_id})
            cursor = conn.execute(
                text("DELETE FROM scenarios WHERE id=:id"), {"id": scenario_id})
        return cursor.rowcount == 1

    # ---- spec 配置持久化（不再依赖本地文件） ------------------------------

    def read_spec_file(self, slug: str) -> str:
        """读取场景 spec 内容：优先 DB 的 spec_json，缺失时回退到本地 spec_path 文件。"""
        row = self.get_scenario_by_slug(slug)
        if row is None:
            raise KeyError(slug)
        content = row.get("spec_json")
        if content:
            return content
        path = self.resolve_spec_path(slug)
        if path.is_file():
            return path.read_text(encoding="utf-8")
        raise FileNotFoundError(
            f"spec 内容缺失：场景 {slug} 在数据库中无 spec_json 且无本地 spec 文件")

    def write_spec_file(self, slug: str, content: str) -> None:
        """把 spec 内容写入 DB（不再回写本地文件）。校验 JSON 合法性与必要字段，
        并落一条历史版本（最近 20 版，超出清理）。
        """
        row = self.get_scenario_by_slug(slug)
        if row is None:
            raise KeyError(slug)
        try:
            data = json.loads(content)
        except ValueError as error:
            raise ValueError(f"spec 不是合法 JSON：{error}") from error
        for field in ("name", "domain", "state", "questions"):
            if not data.get(field):
                raise ValueError(f"spec 缺少必要字段 {field!r}")
        if not isinstance(data.get("questions"), dict) or not data["questions"]:
            raise ValueError("spec.questions 必须是非空对象")
        now = _now()
        previous = row.get("spec_json")
        if previous:
            # 把覆盖前的旧内容归档一条历史（历史只存「上一版」，当前内容不重复入历史）。
            self._conn().execute(
                text("INSERT INTO scenario_spec_history (id, scenario_id, spec_json, created_at) "
                     "VALUES (:id, :sid, :spec, :ts)"),
                dict(id=uuid.uuid4().hex, sid=row["id"], spec=previous, ts=now))
        self._conn().execute(
            text("UPDATE scenarios SET spec_json=:spec, updated_at=:ts WHERE id=:id"),
            dict(spec=content, ts=now, id=row["id"]))
        self._prune_spec_history(row["id"])

    SPEC_HISTORY_LIMIT = 20

    def _prune_spec_history(self, scenario_id, limit: int = SPEC_HISTORY_LIMIT) -> None:
        """保留每个场景最近 limit 版历史，删除更早的（按 created_at, id 倒序取前 limit 之外的）。"""
        self._conn().execute(
            text("DELETE FROM scenario_spec_history WHERE scenario_id=:sid AND id NOT IN ("
                 "SELECT id FROM scenario_spec_history WHERE scenario_id=:sid "
                 "ORDER BY created_at DESC, id DESC LIMIT :limit)"),
            dict(sid=scenario_id, limit=limit))

    def list_spec_history(self, slug: str) -> list[dict]:
        """历史版本列表，新的在前。用历史行 id 作为版本标识（ts 字段返回，前端按它取内容）。"""
        row = self.get_scenario_by_slug(slug)
        if row is None:
            return []
        rows = self._conn().execute(
            text("SELECT id, created_at FROM scenario_spec_history WHERE scenario_id=:sid "
                 "ORDER BY created_at DESC, id DESC LIMIT :limit"),
            dict(sid=row["id"], limit=self.SPEC_HISTORY_LIMIT)).mappings().fetchall()
        return [{"ts": r["id"], "created_at": r["created_at"]} for r in rows]

    def read_spec_history(self, slug: str, ts: str) -> str:
        row = self.get_scenario_by_slug(slug)
        if row is None:
            raise FileNotFoundError(f"没有这个场景：{slug}")
        r = self._conn().execute(
            text("SELECT spec_json FROM scenario_spec_history WHERE scenario_id=:sid AND id=:ts"),
            dict(sid=row["id"], ts=ts)).mappings().fetchone()
        if r is None:
            raise FileNotFoundError(f"没有这个历史版本：{ts}")
        return r["spec_json"]
