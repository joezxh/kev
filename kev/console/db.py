"""编排层的持久化：作业状态机、产物、血缘、事件、场景 spec 配置。

三条设计约定（spec §5 / §9）：
- 跨方言：用 SQLAlchemy Core 的 Engine/Connection 管理连接与事务（非 ORM），SQL 文本仍由
  本项目掌控。sqlite 与 postgresql 由环境变量 KEV_CONSOLE_DB_BACKEND 切换（见 backend_url）。
- 日志文件是真相源，events 表只是给 UI 的可分页尾巴（首屏回填 + Last-Event-ID 续传）
- 状态机集中校验：succeeded -> running 这类转移必须被拒

配置持久化（改进 1）：场景 spec 的当前内容存 scenarios.spec_json 列，历史版本存
scenario_spec_history 表，运行时不再依赖 docs/domains/medical/specs/*.json 本地文件。
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
import yaml
from sqlalchemy import text

from . import paths

SCHEMA_VERSION = 10

# 运行时共享的编排库单例：create_app 启动时写入，stage 模块（data.py 等）借此解析
# 场景 spec_path。未初始化时返回 None，调用方应回退到 docs/domains/medical/specs 目录。
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
  daemon_id     TEXT,
  template_id   TEXT,
  project_id    TEXT NOT NULL DEFAULT '',
  exit_code     INTEGER,
  error         TEXT,
  created_at    TEXT NOT NULL,
  started_at    TEXT,
  finished_at   TEXT
);
CREATE INDEX IF NOT EXISTS jobs_status_idx   ON jobs(status);
CREATE INDEX IF NOT EXISTS jobs_scenario_idx ON jobs(scenario, created_at DESC);
CREATE INDEX IF NOT EXISTS jobs_project_idx  ON jobs(project_id, created_at DESC);

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
  -- 该域由 docs/domains/<spec_dir>/specs 供数（seed_scenarios 按它认领/新建域行）；
  -- 空串 = 手工建的域，不参与导入。
  spec_dir   TEXT NOT NULL DEFAULT '',
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
  -- 轨制与派生事实（kev/console/scenario_specs.derive_track）：track = rule|distill|both|llm，
  -- generator_kind = engine（spec.generator 九件套）|script（legacy gen_<场景>.py）|''，
  -- distill_yaml = 该场景的 EasyDistill 配置（仓库相对路径）或 ''，
  -- distill_yaml_content = 该 yaml 的可编辑内容（DB 为编辑真相源；空 = 未导入/未编辑，
  --   read_distill_yaml 回退读 distill_yaml 路径文件），
  -- origin = 'domains' 表示行由 docs/domains 的种子导入维护（'' = 手工建）。
  track           TEXT NOT NULL DEFAULT '',
  generator_kind  TEXT NOT NULL DEFAULT '',
  distill_yaml    TEXT NOT NULL DEFAULT '',
  distill_yaml_content TEXT,
  origin          TEXT NOT NULL DEFAULT '',
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

-- 作业类型「提交表单」参数 schema：单一真相源，落库后可经 API 改（版本化）。
-- 结构与前端 JobStagePage 的 FieldSpec 对齐；default 与各 StageSpec.build() 默认值一致。
CREATE TABLE IF NOT EXISTS stage_param_specs (
  kind        TEXT PRIMARY KEY,
  schema_json TEXT NOT NULL,
  version     INTEGER NOT NULL DEFAULT 1,
  updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stage_param_spec_history (
  id          TEXT PRIMARY KEY,
  kind        TEXT NOT NULL,
  schema_json TEXT NOT NULL,
  version     INTEGER NOT NULL,
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS stage_param_history_kind_idx ON stage_param_spec_history(kind, created_at DESC);

-- 命名作业模板：跨会话复用/编辑某类任务的参数预设。
CREATE TABLE IF NOT EXISTS job_templates (
  id         TEXT PRIMARY KEY,
  kind       TEXT NOT NULL,
  name       TEXT NOT NULL,
  scenario   TEXT NOT NULL DEFAULT '',
  params     TEXT NOT NULL DEFAULT '{{}}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS job_templates_kind_idx ON job_templates(kind, updated_at DESC);

-- ch6 管理面：projects / members / quota / webhooks / invoices
CREATE TABLE IF NOT EXISTS projects (
  id          TEXT PRIMARY KEY,
  slug        TEXT NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  status      TEXT NOT NULL DEFAULT 'active',
  scenario    TEXT NOT NULL DEFAULT '',
  goal        TEXT NOT NULL DEFAULT '',
  archived_at TEXT,
  freeze_min_records      INTEGER NOT NULL DEFAULT 300,
  freeze_min_review_ratio {real}    NOT NULL DEFAULT 0.10,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_members (
  id         TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id),
  email      TEXT NOT NULL,
  name       TEXT NOT NULL DEFAULT '',
  role       TEXT NOT NULL DEFAULT 'member',
  status     TEXT NOT NULL DEFAULT 'invited',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS project_members_project_idx ON project_members(project_id);
CREATE UNIQUE INDEX IF NOT EXISTS project_members_email_idx ON project_members(project_id, email);

CREATE TABLE IF NOT EXISTS project_quota (
  project_id           TEXT PRIMARY KEY REFERENCES projects(id),
  training_hours_limit {real} NOT NULL DEFAULT 0,
  training_hours_used  {real} NOT NULL DEFAULT 0,
  gpu_limit            INTEGER NOT NULL DEFAULT 0,
  api_calls_limit      INTEGER NOT NULL DEFAULT 0,
  api_calls_used       INTEGER NOT NULL DEFAULT 0,
  storage_gb_limit     {real} NOT NULL DEFAULT 0,
  storage_gb_used      {real} NOT NULL DEFAULT 0,
  updated_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS webhooks (
  id                TEXT PRIMARY KEY,
  project_id        TEXT NOT NULL REFERENCES projects(id),
  url               TEXT NOT NULL,
  events            TEXT NOT NULL DEFAULT '[]',
  secret            TEXT NOT NULL DEFAULT '',
  active            INTEGER NOT NULL DEFAULT 1,
  last_status       INTEGER,
  last_delivered_at TEXT,
  created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS webhooks_project_idx ON webhooks(project_id);

CREATE TABLE IF NOT EXISTS invoices (
  id         TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id),
  period     TEXT NOT NULL,
  amount     {real} NOT NULL,
  currency   TEXT NOT NULL DEFAULT 'USD',
  status     TEXT NOT NULL DEFAULT 'open',
  due_at     TEXT,
  issued_at  TEXT NOT NULL,
  line_items TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS invoices_project_idx ON invoices(project_id, period DESC);

-- 数据策展（Project Hub v7 PR A，设计稿 §4.2-§4.5）：产物版本、冻结快照、
-- 逐条标注与结论发布。全是新表，fresh 与升级库都由这里的 CREATE IF NOT EXISTS 收敛到同一形状。
-- artifact_versions —— 产物的不可变版本快照（登记即算 sha256/records）。artifacts 是可变
-- 指针（D2），故 artifact_id 不建指向 artifacts 的 FK；job_id 记录是哪个作业产出的这一版。
CREATE TABLE IF NOT EXISTS artifact_versions (
  id          TEXT PRIMARY KEY,
  artifact_id TEXT NOT NULL,
  seq         INTEGER NOT NULL,
  job_id      TEXT NOT NULL REFERENCES jobs(id),
  path        TEXT NOT NULL,
  sha256      TEXT NOT NULL,
  records     INTEGER,
  bytes       INTEGER,
  meta        TEXT NOT NULL DEFAULT '{{}}',
  spec_sha256 TEXT,
  created_at  TEXT NOT NULL,
  UNIQUE (artifact_id, seq)
);
CREATE INDEX IF NOT EXISTS artifact_versions_job_idx ON artifact_versions(job_id);
CREATE INDEX IF NOT EXISTS artifact_versions_artifact_idx ON artifact_versions(artifact_id, seq DESC);

CREATE TABLE IF NOT EXISTS bundles (
  id                 TEXT PRIMARY KEY,
  project_id         TEXT NOT NULL REFERENCES projects(id),
  name               TEXT NOT NULL,
  artifact_id        TEXT NOT NULL,
  status             TEXT NOT NULL,
  sha256             TEXT,
  records            INTEGER,
  reviewed_records   INTEGER,
  reviewed_native    INTEGER,
  reviewed_inherited INTEGER,
  review_ratio       {real},
  freeze_checks      TEXT NOT NULL DEFAULT '[]',
  manifest_path      TEXT,
  manifest_sha256    TEXT,
  frozen_at          TEXT,
  note               TEXT NOT NULL DEFAULT '',
  created_at         TEXT NOT NULL,
  updated_at         TEXT NOT NULL,
  UNIQUE (project_id, name)
);

CREATE TABLE IF NOT EXISTS bundle_members (
  bundle_id       TEXT NOT NULL REFERENCES bundles(id),
  version_id      TEXT NOT NULL REFERENCES artifact_versions(id),
  op              TEXT NOT NULL,
  ord             INTEGER NOT NULL,
  records_in      INTEGER,
  records_kept    INTEGER,
  records_dropped INTEGER,
  drop_reasons    TEXT NOT NULL DEFAULT '{{}}',
  PRIMARY KEY (bundle_id, version_id)
);
CREATE INDEX IF NOT EXISTS bundle_members_ord_idx ON bundle_members(bundle_id, ord);

-- record_reviews —— 逐条标注。origin_project_id 有意不建 FK：删项目时按 D13 只把它清成 ''
-- （「来源已删」）而保留标注行（作用域是场景，供下一轮继承），FK 会阻止这次改写；这与
-- jobs.project_id 的 '' legacy 哨兵同理（D14）。
CREATE TABLE IF NOT EXISTS record_reviews (
  id                TEXT PRIMARY KEY,
  scenario          TEXT NOT NULL,
  origin_project_id TEXT NOT NULL DEFAULT '',
  fingerprint       TEXT NOT NULL,
  record_id         TEXT,
  verdict           TEXT NOT NULL,
  patch             TEXT,
  fingerprint_after TEXT,
  labels            TEXT NOT NULL DEFAULT '[]',
  note              TEXT NOT NULL DEFAULT '',
  reviewer          TEXT NOT NULL DEFAULT '',
  source_version_id TEXT REFERENCES artifact_versions(id),
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL,
  UNIQUE (scenario, fingerprint)
);
CREATE INDEX IF NOT EXISTS record_reviews_scenario_idx ON record_reviews(scenario, fingerprint);
CREATE INDEX IF NOT EXISTS record_reviews_project_idx ON record_reviews(origin_project_id);

-- 覆盖前归档（同 scenario_spec_history 的写法，限流在 PR D 的 record_review 里做）。
CREATE TABLE IF NOT EXISTS record_review_history (
  id         TEXT PRIMARY KEY,
  review_id  TEXT NOT NULL REFERENCES record_reviews(id),
  verdict    TEXT NOT NULL,
  patch      TEXT,
  labels     TEXT NOT NULL DEFAULT '[]',
  note       TEXT NOT NULL DEFAULT '',
  reviewer   TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS review_history_review_idx ON record_review_history(review_id, created_at DESC);

CREATE TABLE IF NOT EXISTS project_releases (
  id                   TEXT PRIMARY KEY,
  project_id           TEXT NOT NULL REFERENCES projects(id),
  name                 TEXT NOT NULL,
  bundle_id            TEXT REFERENCES bundles(id),
  bundle_sha256        TEXT,
  train_job_id         TEXT REFERENCES jobs(id),
  run_artifact         TEXT,
  eval_artifact        TEXT,
  comparison_artifact  TEXT,
  regression_artifact  TEXT,
  calibration_artifact TEXT,
  metrics              TEXT NOT NULL DEFAULT '{{}}',
  gates_snapshot       TEXT NOT NULL DEFAULT '[]',
  verdict              TEXT NOT NULL DEFAULT 'candidate',
  note                 TEXT NOT NULL DEFAULT '',
  created_at           TEXT NOT NULL,
  UNIQUE (project_id, name)
);
"""


_JSON_COLUMNS = frozenset({"request", "env_overlay", "artifacts_in", "artifacts_out"})
_ROW_COLUMNS = (
    "id", "kind", "stage", "scenario", "title", "status", "request", "argv",
    "env_overlay", "cwd", "log_path", "artifacts_in", "artifacts_out",
    "parent_id", "attempt", "daemon_id", "template_id", "project_id",
    "exit_code", "error", "created_at", "started_at", "finished_at",
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


def _artifact_version(row) -> dict:
    """artifact_versions 行 → dict；只有 meta 是 JSON，其余列原样透出（nullable 列保留 None）。"""
    out = dict(row)
    out["meta"] = _loads(out["meta"])
    return out


def _bundle(row) -> dict:
    """bundles 行 → dict；freeze_checks 是 JSON 列表，其余列原样透出（nullable 保留 None）。"""
    out = dict(row)
    out["freeze_checks"] = _loads(out["freeze_checks"])
    return out


def _bundle_member(row) -> dict:
    """bundle_members 行 → dict；drop_reasons 是 JSON 字典，其余列原样透出。"""
    out = dict(row)
    out["drop_reasons"] = _loads(out["drop_reasons"])
    return out


def _review(row) -> dict:
    """record_reviews 行 → dict；patch/labels 是 JSON（patch 可空），其余列原样透出（nullable 保留 None）。"""
    out = dict(row)
    out["patch"] = _loads(out["patch"]) if out.get("patch") else None
    out["labels"] = _loads(out["labels"]) if out.get("labels") is not None else []
    return out


def _release(row) -> dict:
    """project_releases 行 → dict；metrics（JSON 字典）与 gates_snapshot（JSON 列表）解出，
    其余列原样透出（nullable 产物指针保留 None）。snapshot 是落库时的判定快照，读时不再算。"""
    out = dict(row)
    out["metrics"] = _loads(out["metrics"]) if out.get("metrics") else {}
    out["gates_snapshot"] = _loads(out["gates_snapshot"]) if out.get("gates_snapshot") else []
    return out


class Store:
    """每线程一个连接。WAL 让读不阻塞写，事件轮询与日志落库可以并发。"""

    def __init__(self, db_path: "Path | str | None" = None, *, url: "sa.URL | str | None" = None,
                 seed: bool = True):
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
        # 幂等播种：把 docs/domains 五个领域的全量 spec 登记为域 + 场景（按 slug INSERT OR IGNORE，
        # 不覆盖用户后续编辑）。建库即播种，保证 fresh DB 也能开箱即用。
        # seed=False 跳过（scripts/import_domain_specs.py 自己按 --force/--domain 决定何时播种）。
        if seed:
            self.seed_scenarios()
        # 幂等播种：作业类型「提交表单」参数 schema（来自 kev/console/stage_params.py）。
        # 只在缺失时写入，用户经 API 改过的 schema 不会被覆盖；建库即播种，开箱即用。
        self.seed_stage_params()

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
        事务里不要把连接交出去给别的线程。

        关于 `commit` 形参（§4.6-1，更正旧措辞）：`put_artifact` / `add_lineage` 的 `commit=True`
        对 `_Conn` 没有作用——是否留在本事务由 `_local.in_tx` 决定，不是某个形参。在 tx() 内这些
        方法**不会**提前 commit，而是交给本事务统一收尾；新增的写方法照 `_Conn` 这一真实语义写。

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

    def _upsert_sql(self, table: str, columns: list[str], conflict_cols: list[str]) -> "sa.TextClause":
        """按后端产出「冲突则更新」的 INSERT（upsert）：sqlite 用 INSERT OR REPLACE；
        postgres 用 ON CONFLICT DO UPDATE SET（排除冲突键）。"""
        cols = ", ".join(columns)
        ph = ", ".join(f":{c}" for c in columns)
        if self.backend == "sqlite":
            return text(f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({ph})")
        updates = ", ".join(f"{c}=excluded.{c}" for c in columns if c not in conflict_cols)
        return text(
            f"INSERT INTO {table} ({cols}) VALUES ({ph}) "
            f"ON CONFLICT ({', '.join(conflict_cols)}) DO UPDATE SET {updates}"
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

    def _table_exists(self, table: str) -> bool:
        if self.backend == "sqlite":
            row = self._conn().execute(
                text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:t"),
                {"t": table}).fetchone()
            return row is not None
        row = self._conn().execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_name=:t"),
            {"t": table}).fetchone()
        return row is not None

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
        # v5: jobs.daemon_id for the distill_daemon Wave D refactor
        # (kev/console/data_daemon.py + app.py endpoints). 旧 sqlite 库需要 ALTER；
        # 新库已经由 DDL 自带。
        if version < 5:
            if not self._column_exists("jobs", "daemon_id"):
                with self.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE jobs ADD COLUMN daemon_id TEXT"))
        # v6: jobs.template_id 追溯作业来自哪个模板（新增列）。
        if version < 6:
            if not self._column_exists("jobs", "template_id"):
                with self.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE jobs ADD COLUMN template_id TEXT"))
        # v7: §4.1 —— jobs.project_id + projects 升级为流水线根（status/scenario/goal/
        # archived_at/freeze_*）。旧库逐列幂等 ALTER；新库由 _ddl 自带。'' 是 legacy 哨兵（D14）。
        if version < 7:
            real = "DOUBLE PRECISION" if self.backend.startswith("postgres") else "REAL"
            if not self._column_exists("jobs", "project_id"):
                with self.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE jobs ADD COLUMN project_id TEXT NOT NULL DEFAULT ''"))
            with self.engine.begin() as conn:
                conn.execute(text("CREATE INDEX IF NOT EXISTS jobs_project_idx ON jobs(project_id, created_at DESC)"))
            project_columns = {
                "status": "TEXT NOT NULL DEFAULT 'active'",
                "scenario": "TEXT NOT NULL DEFAULT ''",
                "goal": "TEXT NOT NULL DEFAULT ''",
                "archived_at": "TEXT",
                "freeze_min_records": "INTEGER NOT NULL DEFAULT 300",
                "freeze_min_review_ratio": f"{real} NOT NULL DEFAULT 0.10",
            }
            for column, ddl_type in project_columns.items():
                if not self._column_exists("projects", column):
                    with self.engine.begin() as conn:
                        conn.execute(text(f"ALTER TABLE projects ADD COLUMN {column} {ddl_type}"))
        # v8: 跨领域 spec 登记 —— scenario_domains.spec_dir（域由哪个 docs/domains 目录供数）+
        # scenarios 的 track / generator_kind / distill_yaml / origin（轨制派生与导入来源）。
        # 旧库逐列幂等 ALTER；新库由 _ddl 自带。补完后按 docs/domains 重新播种（见 __init__ 顺序）。
        if version < 8:
            for table, column in (("scenario_domains", "spec_dir"),
                                  ("scenarios", "track"),
                                  ("scenarios", "generator_kind"),
                                  ("scenarios", "distill_yaml"),
                                  ("scenarios", "origin")):
                if not self._column_exists(table, column):
                    with self.engine.begin() as conn:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"))
            self._backfill_domain_dirs()
        # v10: scenarios.distill_yaml_content —— distill yaml 的可编辑内容存库（DB 为编辑真相源，
        # distill_yaml 路径列保留做参考/回退）。旧库幂等 ALTER，再从路径指向的仓库文件回填内容。
        if version < 10:
            if not self._column_exists("scenarios", "distill_yaml_content"):
                with self.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE scenarios ADD COLUMN distill_yaml_content TEXT"))
            self._backfill_distill_yaml()
        # v9: 数据策展新表（artifact_versions / bundles / bundle_members /
        # record_reviews / record_review_history / project_releases）——全是新表，无列可 ALTER，
        # 由 _init_schema 的 CREATE TABLE IF NOT EXISTS 建出（fresh 与升级库同一形状），
        # 这里只声明版本边界；postgres 存量库的升级走 deploy/console/migration_project_hub_v9.postgres.sql。
        if version < SCHEMA_VERSION:
            with self.engine.begin() as conn:
                conn.execute(
                    text("UPDATE console_meta SET value=:v WHERE key='schema_version'"),
                    {"v": str(SCHEMA_VERSION)},
                )

    # ---- jobs -------------------------------------------------------------

    def create_job(self, *, project_id, kind, stage, scenario, title, request, argv, env_overlay,
                   cwd, log_path, artifacts_in, artifacts_out, parent_id=None,
                   attempt=1, daemon_id=None, template_id=None) -> str:
        """每个作业归属一个项目（D14）：project_id 是强制的关键字参数，无默认值。

        缺参数 → TypeError（签名没有默认值）；传空/None → ValueError（空串是具名 legacy
        哨兵，不是一个项目，调用方不能靠传空来满足「归属某个项目」）。

        attempt 是「第几次尝试」：重试（换名续跑）时由调用方递增，jobs 表据此区分
        首次执行与重试。parent_id 指向被重试的那个作业。

        daemon_id：仅 distill_daemon 阶段填，由 stages/data.py::_distill_daemon
        生成（uuid4().hex，32 字符），写库后 cancel_job 端点据此去设 loopback
        取消标志；其他阶段留 None。

        template_id：作业若由某个命名模板发起，记录其 id 以便追溯（可空）。
        """
        if not project_id:
            raise ValueError("project_id 必填")
        job_id = uuid.uuid4().hex
        self._conn().execute(
            text("INSERT INTO jobs (id, project_id, kind, stage, scenario, title, status, request, argv, env_overlay, cwd,"
                 " log_path, artifacts_in, artifacts_out, parent_id, attempt, daemon_id, template_id, created_at)"
                 " VALUES (:id,:project_id,:kind,:stage,:scenario,:title,'pending',:request,:argv,:env_overlay,:cwd,"
                 " :log_path,:artifacts_in,:artifacts_out,:parent_id,:attempt,:daemon_id,:template_id,:created_at)"),
            dict(id=job_id, project_id=project_id, kind=kind, stage=stage, scenario=scenario, title=title,
                 request=_dumps(request), argv=_dumps(argv), env_overlay=_dumps(env_overlay),
                 cwd=str(cwd), log_path=str(log_path), artifacts_in=_dumps(artifacts_in),
                 artifacts_out=_dumps(artifacts_out), parent_id=parent_id, attempt=int(attempt),
                 daemon_id=daemon_id, template_id=template_id, created_at=_now()),
        )
        return job_id

    def get_job(self, job_id) -> dict | None:
        row = self._conn().execute(text("SELECT * FROM jobs WHERE id = :id"), {"id": job_id}).mappings().fetchone()
        return _job(row) if row else None

    def list_jobs(self, *, status=None, stage=None, scenario=None, project=None, limit=200) -> list[dict]:
        clauses, params = [], {}
        for column, value in (("status", status), ("stage", stage), ("scenario", scenario)):
            if value is not None:
                clauses.append(f"{column} = :{column}")
                params[column] = value
        # project=legacy 落在空哨兵 '' 上；具体项目 id 只返回归属它的作业，
        # legacy 行永远不出现在某个具体项目的列表里（Review Focus：legacy invisibility）。
        if project is not None:
            clauses.append("project_id = :project")
            params["project"] = "" if project == "legacy" else project
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        # limit=None 取全部（项目汇总要跨全部作业统计阶段/产物）；sqlite/postgres 都不接受
        # 把 NULL 绑进 LIMIT，所以无上限时干脆不写 LIMIT 子句。
        tail = ""
        if limit is not None:
            params["limit"] = limit
            tail = " LIMIT :limit"
        # Postgres 没有 SQLite 的 rowid 伪列；jobs 表有 id 主键，用它做二级排序（确定性）。
        rows = self._conn().execute(
            text(f"SELECT * FROM jobs{where} ORDER BY created_at DESC, id DESC{tail}"), params
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

    # ---- artifact versions（不可变快照，PR B）--------------------------

    def record_artifact_version(self, *, artifact_id, job_id, path, sha256, records,
                                bytes=None, meta=None, spec_sha256=None) -> str:
        """登记产物的一个不可变版本：seq = 该 artifact 现有 MAX(seq)+1，只增不改（V3）。

        必须在调用方的 `store.tx()` 里执行：seq 的「读-改-写」要落在同一 BEGIN IMMEDIATE 事务内
        串行化，两个并发注册才不会撞 UNIQUE(artifact_id, seq)。这里不自行 commit，事务由调用方收尾
        （照 `_Conn` 的真实语义，见 §4.6-1：是否留事务由 in_tx 决定，而非某个 commit 形参）。
        """
        version_id = uuid.uuid4().hex
        conn = self._conn()
        nxt = conn.execute(
            text("SELECT COALESCE(MAX(seq), 0) + 1 AS next FROM artifact_versions WHERE artifact_id = :a"),
            {"a": artifact_id}).mappings().fetchone()["next"]
        conn.execute(
            text("INSERT INTO artifact_versions (id, artifact_id, seq, job_id, path, sha256, records,"
                 " bytes, meta, spec_sha256, created_at)"
                 " VALUES (:id,:artifact_id,:seq,:job_id,:path,:sha256,:records,:bytes,:meta,:spec_sha256,:created_at)"),
            dict(id=version_id, artifact_id=artifact_id, seq=int(nxt), job_id=job_id, path=str(path),
                 sha256=sha256, records=records, bytes=bytes, meta=_dumps(meta or {}),
                 spec_sha256=spec_sha256, created_at=_now()),
        )
        return version_id

    def list_artifact_versions(self, artifact_id) -> list[dict]:
        """某产物的版本列表，seq 从新到旧；历史无版本（旧产物）返回空列表而非报错。"""
        rows = self._conn().execute(
            text("SELECT * FROM artifact_versions WHERE artifact_id = :a ORDER BY seq DESC"),
            {"a": artifact_id}).mappings().fetchall()
        return [_artifact_version(row) for row in rows]

    def get_artifact_version(self, version_id) -> dict | None:
        row = self._conn().execute(
            text("SELECT * FROM artifact_versions WHERE id = :id"), {"id": version_id}).mappings().fetchone()
        return _artifact_version(row) if row else None

    def artifact_version_job(self, version_id) -> dict | None:
        """版本 → 产出它的作业（项目归属经 versions.job_id → jobs.project_id join，D2 不给 artifacts 加列）。"""
        row = self._conn().execute(
            text("SELECT jobs.* FROM jobs JOIN artifact_versions ON artifact_versions.job_id = jobs.id"
                 " WHERE artifact_versions.id = :id"), {"id": version_id}).mappings().fetchone()
        return _job(row) if row else None

    # ---- bundles（数据策展 / 冻结快照，PR C）--------------------------

    def create_bundle(self, *, project_id, name, artifact_id, note="") -> dict:
        """建一个 draft bundle。重名（同项目）由 UNIQUE(project_id, name) 拦，端点转 409。"""
        bundle_id = uuid.uuid4().hex
        now = _now()
        self._conn().execute(
            text("INSERT INTO bundles (id, project_id, name, artifact_id, status, freeze_checks,"
                 " note, created_at, updated_at)"
                 " VALUES (:id,:pid,:name,:aid,'draft','[]',:note,:created,:updated)"),
            dict(id=bundle_id, pid=project_id, name=name, aid=artifact_id, note=note or "",
                 created=now, updated=now))
        return self.get_bundle(bundle_id)

    def get_bundle(self, bundle_id) -> dict | None:
        row = self._conn().execute(
            text("SELECT * FROM bundles WHERE id = :id"), {"id": bundle_id}).mappings().fetchone()
        return _bundle(row) if row else None

    def get_bundle_by_name(self, project_id, name) -> dict | None:
        row = self._conn().execute(
            text("SELECT * FROM bundles WHERE project_id = :p AND name = :n"),
            {"p": project_id, "n": name}).mappings().fetchone()
        return _bundle(row) if row else None

    def list_bundles(self, project_id) -> list[dict]:
        rows = self._conn().execute(
            text("SELECT * FROM bundles WHERE project_id = :p ORDER BY created_at"),
            {"p": project_id}).mappings().fetchall()
        return [_bundle(row) for row in rows]

    def replace_bundle_members(self, bundle_id, members) -> None:
        """全量替换成员（只在 draft 调用，端点已拦状态）。members: [{version_id, op, ord}]。"""
        with self.tx() as conn:
            conn.execute(text("DELETE FROM bundle_members WHERE bundle_id = :b"), {"b": bundle_id})
            for m in members:
                conn.execute(
                    text("INSERT INTO bundle_members (bundle_id, version_id, op, ord,"
                         " records_in, records_kept, records_dropped, drop_reasons)"
                         " VALUES (:b,:v,:op,:ord,NULL,NULL,NULL,'{}')"),
                    dict(b=bundle_id, v=m["version_id"], op=m["op"], ord=int(m["ord"])))

    def get_bundle_members(self, bundle_id) -> list[dict]:
        """成员（按 ord）+ join 版本拿到 artifact_id/path/records（物化与 diff 都靠它）。"""
        rows = self._conn().execute(
            text("SELECT bundle_members.*, artifact_versions.artifact_id AS source_artifact,"
                 " artifact_versions.path AS source_path, artifact_versions.records AS version_records"
                 " FROM bundle_members JOIN artifact_versions"
                 " ON bundle_members.version_id = artifact_versions.id"
                 " WHERE bundle_id = :b ORDER BY bundle_members.ord"),
            {"b": bundle_id}).mappings().fetchall()
        return [_bundle_member(row) for row in rows]

    def set_bundle_members_stats(self, bundle_id, stats) -> None:
        """逐成员写回 records_in/kept/dropped + drop_reasons（物化后调用）。"""
        with self.tx() as conn:
            for s in stats:
                conn.execute(
                    text("UPDATE bundle_members SET records_in=:ri, records_kept=:rk,"
                         " records_dropped=:rd, drop_reasons=:dr WHERE bundle_id=:b AND version_id=:v"),
                    dict(ri=s.get("records_in"), rk=s.get("records_kept"),
                         rd=s.get("records_dropped"), dr=_dumps(s.get("drop_reasons") or {}),
                         b=bundle_id, v=s["version_id"]))

    def update_bundle_materialization(self, bundle_id, *, sha256, records, review_ratio,
                                      reviewed_records, reviewed_native, reviewed_inherited,
                                      manifest_path, manifest_sha256) -> None:
        """物化成功：落 sha/records/复核比 + manifest 指针，状态推 materialized（幂等重跑允许）。"""
        self._conn().execute(
            text("UPDATE bundles SET status='materialized', sha256=:sha, records=:rec,"
                 " review_ratio=:rr, reviewed_records=:rv, reviewed_native=:rn,"
                 " reviewed_inherited=:ri, manifest_path=:mp, manifest_sha256=:ms,"
                 " updated_at=:t WHERE id=:id"),
            dict(sha=sha256, rec=records, rr=float(review_ratio), rv=reviewed_records,
                 rn=reviewed_native, ri=reviewed_inherited, mp=manifest_path, ms=manifest_sha256,
                 t=_now(), id=bundle_id))

    def set_bundle_freeze_checks(self, bundle_id, freeze_checks) -> None:
        """只写四条 freeze_checks（硬拒路径用：不冻结，但把判定留痕）。"""
        self._conn().execute(
            text("UPDATE bundles SET freeze_checks=:fc, updated_at=:t WHERE id=:id"),
            dict(fc=_dumps(freeze_checks), t=_now(), id=bundle_id))

    def freeze_bundle(self, bundle_id, freeze_checks) -> None:
        """冻结：状态 → frozen、落 frozen_at + 四条 checks（软门槛不过也照冻，只带 warnings）。"""
        now = _now()
        self._conn().execute(
            text("UPDATE bundles SET status='frozen', freeze_checks=:fc, frozen_at=:t,"
                 " updated_at=:t WHERE id=:id"),
            dict(fc=_dumps(freeze_checks), t=now, id=bundle_id))

    # ---- record reviews 覆盖层（PR D：场景作用域 + 覆盖前归档 + queue/import）----

    REVIEW_HISTORY_LIMIT = 20

    def upsert_record_review(self, *, scenario, origin_project_id, fingerprint, verdict,
                             patch=None, labels=None, note="", reviewer="",
                             record_id=None, source_version_id=None,
                             fingerprint_after=None) -> str:
        """按 UNIQUE(scenario, fingerprint) upsert 一条标注决定；覆盖前把旧决定归档进
        record_review_history（抄 scenario_spec_history 的写法，限 REVIEW_HISTORY_LIMIT），
        整体一个事务。新建不归档、保留 created_at、刷新 updated_at。返回 review 行 id。

        注：不改源 JSONL（P7/D6），只写覆盖层；源文件指纹永不变，fingerprint_after 供
        edit/relabel 记「改后内容」的指纹（可空）。
        """
        now = _now()
        payload = dict(o=origin_project_id, v=verdict,
                       p=_dumps(patch) if patch is not None else None,
                       l=_dumps(labels if labels is not None else []), n=note or "",
                       r=reviewer or "", fa=fingerprint_after, ri=record_id,
                       sv=source_version_id, t=now)
        with self.tx() as conn:
            row = conn.execute(
                text("SELECT id, verdict, patch, labels, note, reviewer FROM record_reviews"
                     " WHERE scenario=:s AND fingerprint=:f"),
                {"s": scenario, "f": fingerprint}).mappings().fetchone()
            if row:
                review_id = row["id"]
                # 覆盖前把「上一版」决定归档（历史只存被覆盖的旧值，当前值不重复入历史）。
                conn.execute(
                    text("INSERT INTO record_review_history"
                         " (id, review_id, verdict, patch, labels, note, reviewer, created_at)"
                         " VALUES (:id,:rid,:v,:p,:l,:n,:r,:t)"),
                    dict(id=uuid.uuid4().hex, rid=review_id, v=row["verdict"], p=row["patch"],
                         l=row["labels"] if row["labels"] is not None else "[]",
                         n=row["note"] or "", r=row["reviewer"] or "", t=now))
                conn.execute(
                    text("UPDATE record_reviews SET origin_project_id=:o, verdict=:v, patch=:p,"
                         " fingerprint_after=:fa, labels=:l, note=:n, reviewer=:r, record_id=:ri,"
                         " source_version_id=:sv, updated_at=:t WHERE id=:id"),
                    {**payload, "id": review_id})
            else:
                review_id = uuid.uuid4().hex
                conn.execute(
                    text("INSERT INTO record_reviews (id, scenario, origin_project_id, fingerprint,"
                         " record_id, verdict, patch, fingerprint_after, labels, note, reviewer,"
                         " source_version_id, created_at, updated_at)"
                         " VALUES (:id,:s,:o,:f,:ri,:v,:p,:fa,:l,:n,:r,:sv,:t,:t)"),
                    {**payload, "id": review_id, "s": scenario, "f": fingerprint})
            conn.execute(
                text("DELETE FROM record_review_history WHERE review_id=:rid AND id NOT IN ("
                     "SELECT id FROM record_review_history WHERE review_id=:rid"
                     " ORDER BY created_at DESC, id DESC LIMIT :limit)"),
                dict(rid=review_id, limit=self.REVIEW_HISTORY_LIMIT))
        return review_id

    def list_record_review_history(self, review_id) -> list[dict]:
        """一条 review 的归档历史（新在前）：每次覆盖前的旧决定，最多 REVIEW_HISTORY_LIMIT 条。"""
        rows = self._conn().execute(
            text("SELECT id, review_id, verdict, patch, labels, note, reviewer, created_at"
                 " FROM record_review_history WHERE review_id=:rid"
                 " ORDER BY created_at DESC, id DESC LIMIT :limit"),
            dict(rid=review_id, limit=self.REVIEW_HISTORY_LIMIT)).mappings().fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["patch"] = _loads(item["patch"]) if item["patch"] else None
            item["labels"] = _loads(item["labels"]) if item["labels"] is not None else []
            out.append(item)
        return out

    def record_reviews_by_fingerprint(self, scenario) -> dict:
        """场景作用域的覆盖层：{fingerprint -> {verdict, patch, origin}}（跨轮继承靠它，D13）。

        origin = origin_project_id，供 materialize 把 reviewed 拆成 native/inherited（PR D）。
        """
        rows = self._conn().execute(
            text("SELECT fingerprint, verdict, patch, origin_project_id FROM record_reviews"
                 " WHERE scenario=:s"),
            {"s": scenario}).mappings().fetchall()
        return {row["fingerprint"]: {"verdict": row["verdict"],
                                     "patch": _loads(row["patch"]) if row["patch"] else None,
                                     "origin": row["origin_project_id"]}
                for row in rows}

    def record_review_for(self, scenario, fingerprint) -> dict | None:
        """单条决定查询（场景作用域）；无则 None。值形状同 record_reviews_by_fingerprint。"""
        row = self._conn().execute(
            text("SELECT verdict, patch, origin_project_id FROM record_reviews"
                 " WHERE scenario=:s AND fingerprint=:f"),
            {"s": scenario, "f": fingerprint}).mappings().fetchone()
        if row is None:
            return None
        return {"verdict": row["verdict"],
                "patch": _loads(row["patch"]) if row["patch"] else None,
                "origin": row["origin_project_id"]}

    def get_record_review(self, review_id) -> dict | None:
        """按 id 取一条完整标注行（PUT 后的回读）。"""
        row = self._conn().execute(
            text("SELECT * FROM record_reviews WHERE id=:id"),
            {"id": review_id}).mappings().fetchone()
        return _review(row) if row else None

    def list_record_reviews(self, scenario, *, verdict=None, labels=None, origin=None,
                            project_id=None, page=0, page_size=50) -> dict:
        """场景作用域列出标注行，带 origin_project_slug（继承来的能看出从哪轮来）。

        origin: self=本项目、inherited=别的项目、all/None=不限。verdict 精确过滤；
        labels（单个标签或多个）要求行内标签命中任一个。返回 {items, total}（total 是过滤后总数）。
        """
        where = ["record_reviews.scenario = :s"]
        params: dict = {"s": scenario}
        if verdict:
            where.append("record_reviews.verdict = :verdict")
            params["verdict"] = verdict
        if origin == "self" and project_id:
            where.append("record_reviews.origin_project_id = :pid")
            params["pid"] = project_id
        elif origin == "inherited" and project_id:
            where.append("record_reviews.origin_project_id <> :pid")
            params["pid"] = project_id
        clause = " AND ".join(where)
        rows = self._conn().execute(
            text("SELECT record_reviews.*, projects.slug AS origin_project_slug"
                 " FROM record_reviews LEFT JOIN projects"
                 " ON record_reviews.origin_project_id = projects.id"
                 f" WHERE {clause} ORDER BY record_reviews.updated_at DESC, record_reviews.id"),
            params).mappings().fetchall()
        wanted = None
        if labels:
            wanted = {labels} if isinstance(labels, str) else set(labels)
        items = []
        for row in rows:
            item = _review(row)
            if wanted is not None and not (wanted & set(item["labels"] or [])):
                continue
            item["origin_project_slug"] = row["origin_project_slug"] or ""
            items.append(item)
        total = len(items)
        start = int(page) * int(page_size)
        return {"items": items[start:start + int(page_size)], "total": total}

    # ---- project releases（结论落库，PR E §4.5、D8、P5）-----------------

    def create_release(self, *, project_id, name, products=None, bundle_id=None,
                       bundle_sha256=None, train_job_id=None, run_artifact=None,
                       eval_artifact=None, comparison_artifact=None, regression_artifact=None,
                       calibration_artifact=None, verdict="candidate", note="") -> dict:
        """落一行结论：gates_snapshot 与 metrics 都在此服务端现算（调 gates.evaluate），
        不接受客户端提交数字（P5：证据先于宣告）。products 是端点读好的产物 payload 字典
        （report/comparison/comparison_public/calibration），缺的产物让对应闸判失败并说明缺什么。

        同项目重名由 UNIQUE(project_id, name) 拦，抛 sa.exc.IntegrityError，端点转 409。
        """
        from . import gates
        products = products or {}
        snapshot = [{"id": g.id, "ok": bool(g.ok), "detail": g.detail,
                     "actual": g.actual, "need": g.need}
                    for g in (*gates.evaluate("train", **products),
                              *gates.evaluate("deploy", **products))]
        report = products.get("report") or {}
        clean = report.get("clean") or {}
        paired = ((products.get("comparison") or {}).get("paired") or {}).get("acc") or {}
        metrics = {"acc": clean.get("acc"), "ece": clean.get("ece"), "brier": clean.get("brier"),
                   "aurc": clean.get("aurc"), "coverage": clean.get("coverage_at_5pct_error"),
                   "ci95": paired.get("ci95"), "delta": paired.get("macro_acc_delta")}
        release_id = uuid.uuid4().hex
        self._conn().execute(
            text("INSERT INTO project_releases (id, project_id, name, bundle_id, bundle_sha256,"
                 " train_job_id, run_artifact, eval_artifact, comparison_artifact,"
                 " regression_artifact, calibration_artifact, metrics, gates_snapshot, verdict,"
                 " note, created_at)"
                 " VALUES (:id,:pid,:name,:bid,:bsha,:tj,:run,:ev,:cmp,:reg,:cal,:metrics,:gates,"
                 ":verdict,:note,:created)"),
            dict(id=release_id, pid=project_id, name=name, bid=bundle_id, bsha=bundle_sha256,
                 tj=train_job_id, run=run_artifact, ev=eval_artifact, cmp=comparison_artifact,
                 reg=regression_artifact, cal=calibration_artifact,
                 metrics=_dumps(metrics), gates=_dumps(snapshot),
                 verdict=verdict or "candidate", note=note or "", created=_now()))
        return self.get_release(release_id)

    def get_release(self, release_id) -> dict | None:
        row = self._conn().execute(
            text("SELECT * FROM project_releases WHERE id = :id"),
            {"id": release_id}).mappings().fetchone()
        return _release(row) if row else None

    def list_releases(self, project_id) -> list[dict]:
        rows = self._conn().execute(
            text("SELECT * FROM project_releases WHERE project_id = :p ORDER BY created_at DESC"),
            {"p": project_id}).mappings().fetchall()
        return [_release(row) for row in rows]

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

    def project_lineage(self, project_id) -> dict:
        """项目的血缘图：{nodes:[{id,kind,version}], edges:[{parent,child,relation,job_id}]}。

        D10：只 JOIN 既有 `lineage` 表（取父在本项目产物集内的出边）+ `bundle_members` 的
        composed_of/overlay 边（父=成员源产物，子=bundle 产物），不新建表。version 取该产物
        最新 seq（无版本则 None，兼容旧产物）；前端只渲染，不重算。"""
        nodes: dict[str, dict] = {}

        def add_node(aid: str, version=None) -> None:
            if aid not in nodes:
                nodes[aid] = {"id": aid, "kind": aid.partition(":")[0], "version": version}
            elif version is not None and nodes[aid]["version"] is None:
                nodes[aid]["version"] = version

        def latest_seq(aid: str):
            versions = self.list_artifact_versions(aid)
            return versions[0]["seq"] if versions else None

        for art in self.list_project_artifacts(project_id):
            add_node(art["id"], latest_seq(art["id"]))
        pset = set(nodes)

        edges: list[dict] = []
        seen: set[tuple] = set()

        def add_edge(parent, child, relation, job_id=None) -> None:
            key = (parent, child, relation)
            if key in seen:
                return
            seen.add(key)
            edges.append({"parent": parent, "child": child, "relation": relation, "job_id": job_id})

        for aid in pset:
            for edge in self.lineage_of(aid):
                if edge["child"] in pset:
                    add_edge(aid, edge["child"], edge["relation"], edge.get("job_id"))

        for bundle in self.list_bundles(project_id):
            bid = bundle["artifact_id"]
            add_node(bid, latest_seq(bid))
            for member in self.get_bundle_members(bundle["id"]):
                parent = member["source_artifact"]
                version = self.get_artifact_version(member["version_id"])
                add_node(parent, version["seq"] if version else latest_seq(parent))
                relation = "overlay" if member["op"] == "overlay" else "composed_of"
                add_edge(parent, bid, relation, version["job_id"] if version else None)

        return {"nodes": list(nodes.values()), "edges": edges}

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

    SEED_ORIGIN = "domains"

    def seed_scenarios(self, force: bool = False,
                       only_domains: "tuple[str, ...] | None" = None) -> dict:
        """幂等播种：把 docs/domains 五个领域的全量 spec 登记进 scenario_domains / scenarios。

        领域清单、中英标签、轨制派生、spec 内容都来自 kev/console.scenario_specs（它直接读
        docs/domains/<领域>/specs/*.json 与 kev/console/distill/configs、generators/gen_*.py），
        不再依赖 run_matrix.SCENARIOS——那份清单只含旧 docs/medical 的 10 个医疗场景。

        - 域：按 spec_dir 认领既有行（旧库里手工建的同义 slug 由 LEGACY_DOMAIN_SLUGS 认领），
          认领后把空的 spec_dir 补上；没有才新建，所以用户改过的域名/排序不会被动。
        - 场景：按 slug 去重。新行整行写入；既有行只刷新派生列（track / generator_kind /
          distill_yaml）与种子行的 spec_path，**不动**用户改过的中英文标签、sort、category、spec_json。
        - spec_json：为空时写入文件内容；force=True 且内容变了才经 write_spec_file 覆盖（旧内容进历史）。
        - only_domains：只处理这些领域 slug（按领域分批导入时用），默认全量。

        返回统计（domains_created / scenarios_created / scenarios_updated / specs_written），
        供 scripts/import_domain_specs.py 汇报。
        """
        from . import scenario_specs
        entries = scenario_specs.entries()
        domain_rows = list(scenario_specs.domains())
        if only_domains:
            wanted = set(only_domains)
            entries = [e for e in entries if e.domain.slug in wanted]
            domain_rows = [d for d in domain_rows if d.slug in wanted]
        now = _now()
        stats = {"domains_created": 0, "scenarios_created": 0,
                 "scenarios_updated": 0, "specs_written": 0}
        with self.tx() as conn:
            domains = [dict(r) for r in conn.execute(
                text("SELECT id, slug, spec_dir FROM scenario_domains")).mappings().fetchall()]

            def find_domain(spec_dir: str) -> dict | None:
                aliases = scenario_specs.LEGACY_DOMAIN_SLUGS.get(spec_dir, ())
                for row in domains:
                    if row["spec_dir"] == spec_dir or row["slug"] == spec_dir or row["slug"] in aliases:
                        return row
                return None

            domain_ids: dict[str, str] = {}
            for domain in domain_rows:
                row = find_domain(domain.spec_dir)
                if row is None:
                    domain_id = uuid.uuid4().hex
                    conn.execute(
                        text("INSERT INTO scenario_domains (id, slug, label_zh, label_en, sort, spec_dir, created_at)"
                             " VALUES (:id,:slug,:label_zh,:label_en,:sort,:spec_dir,:created_at)"),
                        dict(id=domain_id, slug=domain.slug, label_zh=domain.label_zh,
                             label_en=domain.label_en, sort=domain.sort,
                             spec_dir=domain.spec_dir, created_at=now))
                    row = {"id": domain_id, "slug": domain.slug, "spec_dir": domain.spec_dir}
                    domains.append(row)
                    stats["domains_created"] += 1
                elif not row["spec_dir"]:
                    conn.execute(text("UPDATE scenario_domains SET spec_dir=:d WHERE id=:id"),
                                 {"d": domain.spec_dir, "id": row["id"]})
                    row["spec_dir"] = domain.spec_dir
                domain_ids[domain.slug] = row["id"]

            for entry in entries:
                row = conn.execute(text("SELECT * FROM scenarios WHERE slug=:s"),
                                   {"s": entry.slug}).mappings().fetchone()
                # distill yaml 内容（DB 为编辑真相源）：从路径指向的仓库文件读，不存在则 None。
                yaml_path = (paths.ROOT / entry.distill_yaml) if entry.distill_yaml else None
                yaml_content = (yaml_path.read_text(encoding="utf-8")
                                if yaml_path and yaml_path.is_file() else None)
                if row is None:
                    conn.execute(
                        self._upsert_ignore_sql(
                            "scenarios",
                            ["id", "domain_id", "slug", "label_zh", "label_en", "spec_path", "spec_json",
                             "category", "sort", "track", "generator_kind", "distill_yaml",
                             "distill_yaml_content", "origin", "created_at", "updated_at"],
                            ["slug"]),
                        dict(id=uuid.uuid4().hex, domain_id=domain_ids[entry.domain.slug],
                             slug=entry.slug, label_zh=entry.label_zh, label_en=entry.label_en,
                             spec_path=entry.spec_path, spec_json=entry.content,
                             category=entry.domain.slug, sort=entry.sort, track=entry.track,
                             generator_kind=entry.generator_kind, distill_yaml=entry.distill_yaml,
                             distill_yaml_content=yaml_content,
                             origin=self.SEED_ORIGIN, created_at=now, updated_at=now))
                    stats["scenarios_created"] += 1
                    stats["specs_written"] += 1
                    continue
                row = dict(row)
                sets = ["track=:track", "generator_kind=:generator_kind",
                        "distill_yaml=:distill_yaml", "updated_at=:updated_at"]
                params = dict(track=entry.track, generator_kind=entry.generator_kind,
                              distill_yaml=entry.distill_yaml, updated_at=now, id=row["id"])
                # 旧库的种子行（origin 还是空但 spec_path 已指向 docs/domains）认领导入来源，
                # 之后 spec_path 跟着目录走；用户手工建的行（spec_path 在别处）不碰。
                seeded = row.get("origin") == self.SEED_ORIGIN or (
                    not row.get("origin") and str(row.get("spec_path") or "").startswith("docs/domains/"))
                if seeded:
                    if not row.get("origin"):
                        sets.append("origin=:origin")
                        params["origin"] = self.SEED_ORIGIN
                    if row.get("spec_path") != entry.spec_path:
                        sets.append("spec_path=:spec_path")
                        params["spec_path"] = entry.spec_path
                if not row.get("spec_json") and entry.content:
                    sets.append("spec_json=:spec_json")
                    params["spec_json"] = entry.content
                    stats["specs_written"] += 1
                # distill_yaml_content 为空且文件存在时回填（不覆盖用户已编辑内容，与 spec_json 同策略）。
                if not row.get("distill_yaml_content") and yaml_content:
                    sets.append("distill_yaml_content=:distill_yaml_content")
                    params["distill_yaml_content"] = yaml_content
                conn.execute(text(f"UPDATE scenarios SET {', '.join(sets)} WHERE id=:id"), params)
                stats["scenarios_updated"] += 1

        if force:
            # --force 是「以文件为准重新导入」：内容变了才写，write_spec_file 会把覆盖前的库内
            # 内容归档进 scenario_spec_history（保留最近 SPEC_HISTORY_LIMIT 版）。
            for entry in entries:
                row = self.get_scenario_by_slug(entry.slug)
                if row is not None and row.get("spec_json") != entry.content:
                    self.write_spec_file(entry.slug, entry.content)
                    stats["specs_written"] += 1
        return stats

    def _backfill_domain_dirs(self) -> None:
        """给旧库的域行补 spec_dir：slug 与目录同名直接用，命中别名的按别名认领，手工建的留空。"""
        from . import scenario_specs
        by_slug = {d.slug: d.spec_dir for d in scenario_specs.domains()}
        aliases = {slug: spec_dir for spec_dir, names in scenario_specs.LEGACY_DOMAIN_SLUGS.items()
                   for slug in names}
        rows = self._conn().execute(
            text("SELECT id, slug, spec_dir FROM scenario_domains")).mappings().fetchall()
        for row in rows:
            if row["spec_dir"]:
                continue
            target = by_slug.get(row["slug"]) or aliases.get(row["slug"]) or ""
            if target:
                self._conn().execute(
                    text("UPDATE scenario_domains SET spec_dir=:d WHERE id=:id"),
                    {"d": target, "id": row["id"]})

    def _backfill_distill_yaml(self) -> None:
        """给旧库回填 scenarios.distill_yaml_content：内容列为空且 distill_yaml 路径指向的仓库
        文件存在时，读文件写入（幂等，不覆盖已编辑内容）。"""
        rows = self._conn().execute(
            text("SELECT id, distill_yaml, distill_yaml_content FROM scenarios"
                 " WHERE distill_yaml <> ''")).mappings().fetchall()
        for row in rows:
            if row["distill_yaml_content"]:
                continue
            path = paths.ROOT / row["distill_yaml"]
            if not path.is_file():
                continue
            self._conn().execute(
                text("UPDATE scenarios SET distill_yaml_content=:c WHERE id=:id"),
                {"c": path.read_text(encoding="utf-8"), "id": row["id"]})

    # ---- stage param specs ------------------------------------------------

    def seed_stage_params(self) -> None:
        """幂等播种：把 stage_params.DEFAULT_SCHEMAS 落库为各 kind 的初始 schema。

        只在 kind 不存在时写入（INSERT OR IGNORE），用户经 API 改过的 schema 不会被覆盖；
        建库即播种，保证 fresh DB 也能开箱即用，且前端无需硬编码任何字段。
        """
        from . import stage_params
        now = _now()
        for kind, fields in stage_params.DEFAULT_SCHEMAS.items():
            with self.tx() as conn:
                conn.execute(
                    self._upsert_ignore_sql(
                        "stage_param_specs",
                        ["kind", "schema_json", "version", "updated_at"],
                        ["kind"]),
                    dict(kind=kind, schema_json=_dumps(fields), version=1, updated_at=now),
                )

    def get_stage_params(self, kind: str):
        """读取某 kind 的提交表单 schema；库里没有则回退到代码默认（DEFAULT_SCHEMAS）。"""
        from . import stage_params
        row = self._conn().execute(
            text("SELECT schema_json, version FROM stage_param_specs WHERE kind=:k"),
            {"k": kind}).mappings().fetchone()
        if row is None:
            return stage_params.DEFAULT_SCHEMAS.get(kind, []), 0, "default"
        return _loads(row["schema_json"]), int(row["version"]), "db"

    def save_stage_params(self, kind: str, fields: list[dict]) -> dict:
        """改某 kind 的 schema：版本 +1，旧版本写入 stage_param_spec_history，再 upsert 新版本。"""
        from . import stage_params
        now = _now()
        with self.tx() as conn:
            row = conn.execute(
                text("SELECT version, schema_json FROM stage_param_specs WHERE kind=:k"),
                {"k": kind}).mappings().fetchone()
            prev_version = int(row["version"]) if row else 0
            prev_schema = row["schema_json"] if row else _dumps(stage_params.DEFAULT_SCHEMAS.get(kind, []))
            new_version = prev_version + 1
            if row is not None:
                conn.execute(
                    text("INSERT INTO stage_param_spec_history (id, kind, schema_json, version, created_at)"
                         " VALUES (:id,:k,:s,:v,:ts)"),
                    dict(id=uuid.uuid4().hex, k=kind, s=prev_schema, v=prev_version, ts=now))
            conn.execute(
                self._upsert_sql(
                    "stage_param_specs",
                    ["kind", "schema_json", "version", "updated_at"],
                    ["kind"]),
                dict(kind=kind, schema_json=_dumps(fields), version=new_version, updated_at=now))
        return {"fields": fields, "version": new_version}

    def list_stage_param_versions(self, kind: str) -> list[dict]:
        rows = self._conn().execute(
            text("SELECT id, kind, schema_json, version, created_at FROM stage_param_spec_history"
                 " WHERE kind=:k ORDER BY created_at DESC"),
            {"k": kind}).mappings().fetchall()
        return [{"id": r["id"], "kind": r["kind"], "version": int(r["version"]),
                 "created_at": r["created_at"], "fields": _loads(r["schema_json"])} for r in rows]

    def rollback_stage_params(self, kind: str, version: int) -> "dict | None":
        """回滚到某一历史版本：把该版本 schema 作为新版本写回（版本+1，当前版本先归档到历史）。

        找不到该历史版本时返回 None（由路由转 404）。回滚同样是「写入」动作，
        会留下版本轨迹，便于审计，而非偷偷覆盖。
        """
        row = self._conn().execute(
            text("SELECT schema_json FROM stage_param_spec_history WHERE kind=:k AND version=:v"),
            {"k": kind, "v": version}).mappings().fetchone()
        if row is None:
            return None
        historical_fields = _loads(row["schema_json"])
        # save_stage_params 会把「当前」归档成新的一条历史，再把历史版 schema 写成新当前版本。
        return self.save_stage_params(kind, historical_fields)

    # ---- job templates ----------------------------------------------------

    @staticmethod
    def _template_row(row) -> dict:
        out = dict(row)
        out["params"] = _loads(out.get("params") or "{}")
        return out

    def list_job_templates(self, kind: "str | None" = None) -> list[dict]:
        if kind:
            rows = self._conn().execute(
                text("SELECT * FROM job_templates WHERE kind=:k ORDER BY updated_at DESC"),
                {"k": kind}).mappings().fetchall()
        else:
            rows = self._conn().execute(
                text("SELECT * FROM job_templates ORDER BY updated_at DESC")).mappings().fetchall()
        return [self._template_row(r) for r in rows]

    def get_job_template(self, template_id: str) -> "dict | None":
        row = self._conn().execute(
            text("SELECT * FROM job_templates WHERE id=:id"),
            {"id": template_id}).mappings().fetchone()
        return self._template_row(row) if row else None

    def create_job_template(self, *, kind: str, name: str, scenario: str = "", params: "dict | None" = None) -> str:
        template_id = uuid.uuid4().hex
        now = _now()
        self._conn().execute(
            text("INSERT INTO job_templates (id, kind, name, scenario, params, created_at, updated_at)"
                 " VALUES (:id,:kind,:name,:scenario,:params,:created,:updated)"),
            dict(id=template_id, kind=kind, name=name, scenario=scenario or "",
                 params=_dumps(params or {}), created=now, updated=now))
        return template_id

    def update_job_template(self, template_id: str, *, name: "str | None" = None,
                            scenario: "str | None" = None, params: "dict | None" = None) -> "dict | None":
        updates, params_bind = [], {"id": template_id}
        if name is not None:
            updates.append("name=:name"); params_bind["name"] = name
        if scenario is not None:
            updates.append("scenario=:scenario"); params_bind["scenario"] = scenario
        if params is not None:
            updates.append("params=:params"); params_bind["params"] = _dumps(params)
        if not updates:
            return self.get_job_template(template_id)
        updates.append("updated_at=:ts"); params_bind["ts"] = _now()
        self._conn().execute(
            text(f"UPDATE job_templates SET {', '.join(updates)} WHERE id=:id"), params_bind)
        return self.get_job_template(template_id)

    def delete_job_template(self, template_id: str) -> bool:
        cur = self._conn().execute(
            text("DELETE FROM job_templates WHERE id=:id"), {"id": template_id})
        return cur.rowcount == 1

    def _backfill_specs(self) -> None:
        """把 docs/domains 下各 spec 文件内容回填进 spec_json 为空的行（只填空，不覆盖库内已编辑的）。

        空库经此即自包含；v<4 的旧库（迁移路径）也借由此把文件内容搬进 DB。库里没有对应文件的
        slug（手工建的场景）保持 spec_json 为 NULL（运行时回退到 spec_path 文件，不影响启动）。
        """
        from . import scenario_specs
        contents = {e.slug: e.content for e in scenario_specs.entries()}
        rows = self._conn().execute(
            text("SELECT id, slug, spec_json FROM scenarios")).mappings().fetchall()
        for row in rows:
            content = contents.get(row["slug"])
            if content is None or row["spec_json"]:
                continue
            self._conn().execute(
                text("UPDATE scenarios SET spec_json=:s, updated_at=:t WHERE id=:id"),
                dict(s=content, t=_now(), id=row["id"]))

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
                "category": s["category"], "sort": s["sort"], "exists": file_exists,
                # 轨制派生列（scenario_specs.derive_track）：前端场景表据此显示「规则生成 / 蒸馏 / 双轨」
                # 并决定该场景能不能跑 generate（engine/script）或蒸馏（distill_yaml 非空）。
                "track": s.get("track"), "generator_kind": s.get("generator_kind"),
                "distill_yaml": s.get("distill_yaml"), "origin": s.get("origin")})
        tree = []
        for d in domains:
            d = dict(d)
            tree.append({
                "id": d["id"], "slug": d["slug"], "label": d[label],
                "label_zh": d["label_zh"], "label_en": d["label_en"],
                "sort": d["sort"], "spec_dir": d.get("spec_dir"),
                "scenarios": by_domain.get(d["id"], [])})
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
        原始文件）；DB 为空时回退到仓库内 docs/domains/medical/specs/<slug>.json；都没有返回 None。
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

    def create_domain(self, *, slug, label_zh, label_en, sort=0, spec_dir="") -> str:
        domain_id = uuid.uuid4().hex
        self._conn().execute(
            text("INSERT INTO scenario_domains (id, slug, label_zh, label_en, sort, spec_dir, created_at)"
                 " VALUES (:id,:slug,:label_zh,:label_en,:sort,:spec_dir,:created_at)"),
            dict(id=domain_id, slug=slug, label_zh=label_zh, label_en=label_en,
                 sort=int(sort), spec_dir=spec_dir or "", created_at=_now()))
        return domain_id

    def update_domain(self, domain_id, *, label_zh=None, label_en=None, sort=None, spec_dir=None) -> bool:
        fields, params = {}, {}
        if label_zh is not None:
            fields["label_zh"] = ":label_zh"; params["label_zh"] = label_zh
        if label_en is not None:
            fields["label_en"] = ":label_en"; params["label_en"] = label_en
        if sort is not None:
            fields["sort"] = ":sort"; params["sort"] = int(sort)
        # spec_dir 与 slug 一样是唯一键（导入按它认领域行）：同域场景只能属于一个目录。
        if spec_dir is not None:
            fields["spec_dir"] = ":spec_dir"; params["spec_dir"] = spec_dir
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
                        category="medical", sort=0, track="", generator_kind="",
                        distill_yaml="", origin="") -> str:
        scenario_id = uuid.uuid4().hex
        now = _now()
        self._conn().execute(
            text("INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path,"
                 " spec_json, category, sort, track, generator_kind, distill_yaml, origin,"
                 " created_at, updated_at)"
                 " VALUES (:id,:domain_id,:slug,:label_zh,:label_en,:spec_path,"
                 " :spec_json,:category,:sort,:track,:generator_kind,:distill_yaml,:origin,"
                 " :created_at,:updated_at)"),
            dict(id=scenario_id, domain_id=domain_id, slug=slug, label_zh=label_zh,
                 label_en=label_en, spec_path=spec_path, spec_json=None, category=category,
                 sort=int(sort), track=track or "", generator_kind=generator_kind or "",
                 distill_yaml=distill_yaml or "", origin=origin or "",
                 created_at=now, updated_at=now))
        return scenario_id

    def update_scenario(self, scenario_id, *, domain_id=None, label_zh=None, label_en=None,
                        spec_path=None, category=None, sort=None, track=None,
                        generator_kind=None, distill_yaml=None) -> bool:
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
        # 轨制三列通常是导入派生的（seed_scenarios 每次重算），但手工场景可以在这儿直接标。
        if track is not None:
            fields["track"] = ":track"; params["track"] = track
        if generator_kind is not None:
            fields["generator_kind"] = ":generator_kind"; params["generator_kind"] = generator_kind
        if distill_yaml is not None:
            fields["distill_yaml"] = ":distill_yaml"; params["distill_yaml"] = distill_yaml
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

    # ---- distill yaml 内容持久化（DB 为编辑真相源，distill_yaml 路径列做回退）----

    def read_distill_yaml(self, slug: str) -> str:
        """读取场景的 distill yaml 内容：优先 DB 的 distill_yaml_content，缺失时回退读
        distill_yaml 路径指向的仓库文件；都没有返回 ''（非蒸馏轨场景合法）。场景不存在抛 KeyError。"""
        row = self.get_scenario_by_slug(slug)
        if row is None:
            raise KeyError(slug)
        content = row.get("distill_yaml_content")
        if content:
            return content
        rel = row.get("distill_yaml")
        if rel:
            path = paths.ROOT / rel
            if path.is_file():
                return path.read_text(encoding="utf-8")
        return ""

    def write_distill_yaml(self, slug: str, content: str) -> None:
        """把 distill yaml 内容写入 DB（不回写仓库文件）。校验 YAML 可解析，失败抛 ValueError。
        不做历史版本（与 spec_json 不同，控制范围）。"""
        row = self.get_scenario_by_slug(slug)
        if row is None:
            raise KeyError(slug)
        if content.strip():
            try:
                yaml.safe_load(content)
            except yaml.YAMLError as error:
                raise ValueError(f"distill yaml 不是合法 YAML：{error}") from error
        self._conn().execute(
            text("UPDATE scenarios SET distill_yaml_content=:c, updated_at=:ts WHERE id=:id"),
            dict(c=content, ts=_now(), id=row["id"]))

    def distill_yaml_file(self, slug: str) -> "Path | None":
        """把 DB 的 distill yaml 内容物化到 data/console/distill-configs/<slug>.yaml，供 easydistill
        CLI 按路径读取（DB 的投影，镜像 spec_file_path）。内容为空时回退到仓库 distill_yaml 路径文件；
        都没有返回 None。"""
        row = self.get_scenario_by_slug(slug)
        if row is None:
            return None
        content = row.get("distill_yaml_content")
        if content:
            directory = paths.CONSOLE_DISTILL_CONFIGS
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{slug}.yaml"
            path.write_text(content, encoding="utf-8")
            return path
        rel = row.get("distill_yaml")
        fallback = (paths.ROOT / rel).resolve() if rel else None
        return fallback if fallback and fallback.is_file() else None

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

    # ---- ch6 管理面：projects / members / quota / webhooks / invoices ------
    #
    # 这一组路由（app.py 的 "projects / members / quota / webhooks / billing" 段）和前端
    # studio 的 projects/members/quota/webhooks/billing 页面都已落地，但数据层缺位：
    # 之前 Store 上根本没有这些方法，也没有对应表，POST /console/api/projects 直接
    # AttributeError → 500。这里补齐表（见 _ddl）与全部读写方法。

    @staticmethod
    def _quota_num(value):
        """限额的部分更新语义：None / 空串表示「这一列不动」，非法值同样当不动。"""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _quota_int(value):
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    # ---- projects ----

    def list_projects(self) -> list[dict]:
        rows = self._conn().execute(
            text("SELECT * FROM projects ORDER BY created_at DESC")).mappings().fetchall()
        return [dict(r) for r in rows]

    def get_project(self, project_id: str):
        row = self._conn().execute(
            text("SELECT * FROM projects WHERE id=:id"),
            {"id": project_id}).mappings().fetchone()
        return dict(row) if row else None

    def project_events(self, project_id: str, *, after_id: int = 0, limit: int = 200) -> list[dict]:
        """跨作业的项目事件流（D10）：events 本身无 project 列，经 jobs.project_id 归属。

        游标语义与 read_events 一致（events.id 全局自增，跨作业天然按时间排序）。
        """
        rows = self._conn().execute(
            text("SELECT events.* FROM events JOIN jobs ON events.job_id = jobs.id"
                 " WHERE jobs.project_id = :p AND events.id > :after_id"
                 " ORDER BY events.id LIMIT :limit"),
            dict(p=project_id, after_id=after_id, limit=limit),
        ).mappings().fetchall()
        return [dict(row) for row in rows]

    def list_project_artifacts(self, project_id: str) -> list[dict]:
        """项目全部作业的 artifacts_in + artifacts_out 去重后逐个解析（D2：
        归属走 jobs.project_id，不给 artifacts 加 project_id 列）；解不到的丢弃。"""
        seen: set[str] = set()
        ordered: list[str] = []
        for job in self.list_jobs(project=project_id, limit=None):
            for aid in (job["artifacts_in"] + job["artifacts_out"]):
                if aid not in seen:
                    seen.add(aid)
                    ordered.append(aid)
        out = []
        for aid in ordered:
            art = self.get_artifact(aid)
            if art:
                out.append(art)
        return out

    def project_summary(self, project_id: str) -> dict | None:
        """get_project 行 + 计数/阶段/最近事件；保留所有原始列，旧调用方照读 slug/name。"""
        project = self.get_project(project_id)
        if project is None:
            return None
        jobs = self.list_jobs(project=project_id, limit=None)  # created_at DESC
        stages: dict[str, str] = {}
        for job in jobs:            # 首次命中即该阶段最新的作业
            stages.setdefault(job["stage"], job["status"])
        artifacts = self.list_project_artifacts(project_id)
        summary = dict(project)
        summary["jobs"] = len(jobs)
        summary["artifacts"] = len(artifacts)
        summary["recent_events"] = self.project_events(project_id, limit=200)[-5:]
        summary["stages"] = stages
        # 用量真数（§4.6-2）：只读 peek，不因摘要读取就补一行 quota（那是写）。
        # 从未 add_usage 过的三列天然是 0，向后兼容旧前端只读原形状。
        summary["usage"] = self._peek_usage(project_id)
        return summary

    def _peek_usage(self, project_id: str) -> dict:
        """读项目用量的三列，缺行返回全 0（不插入，区别于 get_quota 的补行语义）。"""
        row = self._conn().execute(
            text("SELECT storage_gb_used, training_hours_used, api_calls_used"
                 " FROM project_quota WHERE project_id=:pid"),
            dict(pid=project_id)).mappings().fetchone()
        if row is None:
            return {"storage_gb_used": 0.0, "training_hours_used": 0.0, "api_calls_used": 0}
        return {"storage_gb_used": row["storage_gb_used"],
                "training_hours_used": row["training_hours_used"],
                "api_calls_used": row["api_calls_used"]}

    def create_project(self, slug: str, name: str, description: str = "",
                       scenario: str = "", status: str = "active", goal: str = "",
                       freeze_min_records: int = 300,
                       freeze_min_review_ratio: float = 0.10) -> str:
        """slug 重复时抛出 sa.exc.IntegrityError，由路由转成 409。

        一个项目 = 一个场景的一轮（D1）；scenario 列为空串时代表尚未绑场景的
        遗留项目，POST /projects 路由会在进入这里之前拦下空/未知场景。
        """
        project_id = uuid.uuid4().hex
        now = _now()
        self._conn().execute(
            text("INSERT INTO projects (id, slug, name, description, status, scenario, goal,"
                 " freeze_min_records, freeze_min_review_ratio, created_at, updated_at)"
                 " VALUES (:id,:slug,:name,:desc,:status,:scenario,:goal,:fmr,:fmrr,:created,:updated)"),
            dict(id=project_id, slug=slug, name=name, desc=description or "",
                 status=status or "active", scenario=scenario or "", goal=goal or "",
                 fmr=int(freeze_min_records), fmrr=float(freeze_min_review_ratio),
                 created=now, updated=now))
        return project_id

    def scenario_known(self, slug: str) -> bool:
        """场景 slug 是否存在于 scenarios 表（scenarios 按 slug 唯一键）。"""
        row = self._conn().execute(
            text("SELECT 1 FROM scenarios WHERE slug = :slug"), {"slug": slug}).fetchone()
        return row is not None

    def _project_has_rows(self, project_id: str) -> bool:
        """项目下是否已有任何 job 或 bundle（D9 守卫：有则 slug 不可改）。"""
        row = self._conn().execute(
            text("SELECT 1 FROM jobs WHERE project_id=:pid"
                 " UNION SELECT 1 FROM bundles WHERE project_id=:pid LIMIT 1"),
            {"pid": project_id}).fetchone()
        return row is not None

    def update_project(self, project_id: str, name=None, slug=None, description=None,
                       scenario=None, status=None, goal=None, archived_at=None,
                       freeze_min_records=None, freeze_min_review_ratio=None):
        current = self.get_project(project_id)
        if current is None:
            return None
        sets, params = [], {"id": project_id}
        if name is not None:
            sets.append("name=:name")
            params["name"] = name
        if slug is not None:
            # D9：项目已有 job/bundle 时拒改 slug（bundle 路径里带 slug，改了就把
            # 已登记的 path 指向不存在的目录，integrity 全体 missing）。传当前值不算改。
            # 延迟 import 避开 db → stages 包的循环导入（stages/__init__ 会 import 回 db）。
            if slug != current["slug"] and self._project_has_rows(project_id):
                from .stages.base import Conflict
                raise Conflict("项目已有数据，slug 不可改",
                               hint="slug 是产物路径的一段，改名会让已登记的版本集体指向空目录")
            sets.append("slug=:slug")
            params["slug"] = slug
        if description is not None:
            sets.append("description=:desc")
            params["desc"] = description
        if scenario is not None:
            sets.append("scenario=:scenario")
            params["scenario"] = scenario
        if status is not None:
            sets.append("status=:status")
            params["status"] = status
        if goal is not None:
            sets.append("goal=:goal")
            params["goal"] = goal
        if archived_at is not None:
            sets.append("archived_at=:archived_at")
            params["archived_at"] = archived_at
        if freeze_min_records is not None:
            sets.append("freeze_min_records=:fmr")
            params["fmr"] = int(freeze_min_records)
        if freeze_min_review_ratio is not None:
            sets.append("freeze_min_review_ratio=:fmrr")
            params["fmrr"] = float(freeze_min_review_ratio)
        if not sets:
            return self.get_project(project_id)
        sets.append("updated_at=:ts")
        params["ts"] = _now()
        self._conn().execute(
            text(f"UPDATE projects SET {', '.join(sets)} WHERE id=:id"), params)
        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> bool:
        # 手工级联：建表时没用 ON DELETE CASCADE，且 sqlite 的外键不一定启用，
        # 依赖数据库级联会在部分环境留下孤儿行。整个级联包在一个事务里，中途失败不留半成品。
        # 顺序：先把 record_reviews 的来源清成 ''（D13：保留标注行，作用域是场景），再删随项目走的
        # bundles 系（bundle_members → project_releases → bundles），然后既有四表，最后 projects。
        # artifact_versions 不删（版本是产物侧证据，D3：删项目不清空产物历史）。
        with self.tx() as conn:
            conn.execute(
                text("UPDATE record_reviews SET origin_project_id='' WHERE origin_project_id=:pid"),
                dict(pid=project_id))
            conn.execute(
                text("DELETE FROM bundle_members WHERE bundle_id IN"
                     " (SELECT id FROM bundles WHERE project_id=:pid)"), dict(pid=project_id))
            conn.execute(
                text("DELETE FROM project_releases WHERE project_id=:pid"), dict(pid=project_id))
            conn.execute(
                text("DELETE FROM bundles WHERE project_id=:pid"), dict(pid=project_id))
            for table in ("project_members", "project_quota", "webhooks", "invoices"):
                conn.execute(
                    text(f"DELETE FROM {table} WHERE project_id=:pid"), dict(pid=project_id))
            result = conn.execute(
                text("DELETE FROM projects WHERE id=:id"), {"id": project_id})
            return bool(result.rowcount)

    # ---- members ----

    def list_members(self, project_id: str) -> list[dict]:
        rows = self._conn().execute(
            text("SELECT * FROM project_members WHERE project_id=:pid ORDER BY created_at"),
            dict(pid=project_id)).mappings().fetchall()
        return [dict(r) for r in rows]

    def get_member(self, member_id: str):
        row = self._conn().execute(
            text("SELECT * FROM project_members WHERE id=:id"),
            {"id": member_id}).mappings().fetchone()
        return dict(row) if row else None

    def create_member(self, project_id: str, email: str, name: str = "",
                      role: str = "member", status: str = "invited") -> str:
        member_id = uuid.uuid4().hex
        self._conn().execute(
            text("INSERT INTO project_members (id, project_id, email, name, role, status, created_at)"
                 " VALUES (:id,:pid,:email,:name,:role,:status,:created)"),
            dict(id=member_id, pid=project_id, email=email, name=name or "",
                 role=role, status=status, created=_now()))
        return member_id

    def update_member(self, member_id: str, role=None, status=None, name=None):
        if self.get_member(member_id) is None:
            return None
        sets, params = [], {"id": member_id}
        if role is not None:
            sets.append("role=:role")
            params["role"] = role
        if status is not None:
            sets.append("status=:status")
            params["status"] = status
        if name is not None:
            sets.append("name=:name")
            params["name"] = name
        if not sets:
            return self.get_member(member_id)
        self._conn().execute(
            text(f"UPDATE project_members SET {', '.join(sets)} WHERE id=:id"), params)
        return self.get_member(member_id)

    def delete_member(self, member_id: str) -> bool:
        result = self._conn().execute(
            text("DELETE FROM project_members WHERE id=:id"), {"id": member_id})
        return bool(result.rowcount)

    # ---- quota ----

    def _default_quota(self, project_id: str) -> dict:
        now = _now()
        self._conn().execute(
            text("INSERT INTO project_quota (project_id, training_hours_limit, training_hours_used,"
                 " gpu_limit, api_calls_limit, api_calls_used, storage_gb_limit, storage_gb_used,"
                 " updated_at) VALUES (:pid,0,0,0,0,0,0,0,:ts)"),
            dict(pid=project_id, ts=now))
        return {"project_id": project_id, "training_hours_limit": 0.0, "training_hours_used": 0.0,
                "gpu_limit": 0, "api_calls_limit": 0, "api_calls_used": 0,
                "storage_gb_limit": 0.0, "storage_gb_used": 0.0, "updated_at": now}

    def get_quota(self, project_id: str) -> dict:
        """没有记录时补一条全 0 的：配额页不该因为还没设过限额就 404。"""
        row = self._conn().execute(
            text("SELECT * FROM project_quota WHERE project_id=:pid"),
            dict(pid=project_id)).mappings().fetchone()
        if row is None:
            return self._default_quota(project_id)
        return dict(row)

    def set_quota_limits(self, project_id: str, training_hours_limit=None, gpu_limit=None,
                         api_calls_limit=None, storage_gb_limit=None) -> dict:
        if self._conn().execute(
                text("SELECT project_id FROM project_quota WHERE project_id=:pid"),
                dict(pid=project_id)).mappings().fetchone() is None:
            self._default_quota(project_id)
        sets, params = [], {"pid": project_id}
        if training_hours_limit is not None:
            sets.append("training_hours_limit=:thl")
            params["thl"] = float(training_hours_limit)
        if gpu_limit is not None:
            sets.append("gpu_limit=:gl")
            params["gl"] = int(gpu_limit)
        if api_calls_limit is not None:
            sets.append("api_calls_limit=:acl")
            params["acl"] = int(api_calls_limit)
        if storage_gb_limit is not None:
            sets.append("storage_gb_limit=:sgl")
            params["sgl"] = float(storage_gb_limit)
        if sets:
            sets.append("updated_at=:ts")
            params["ts"] = _now()
            self._conn().execute(
                text(f"UPDATE project_quota SET {', '.join(sets)} WHERE project_id=:pid"), params)
        return self.get_quota(project_id)

    def add_usage(self, project_id: str, *, storage_bytes: int = 0,
                  training_seconds: int = 0, api_calls: int = 0) -> dict | None:
        """配额真实用量的累加（§4.6-2：今天三列无任何写入者，页面上是一排 0）。

        单条 UPDATE 把增量加到 `storage_gb_used/training_hours_used/api_calls_used`，
        字节→GB（除以 1024**3）、秒→小时（除以 3600）、调用按整型。不与 `register` 的
        写事务纠缠：调用点都在自身事务之外，这里靠 `_Conn` 的自动提交落库（无行先补全 0）。
        空 project_id（legacy 作业，归属不到项目）直接返回 None，不落任何一列。
        """
        if not project_id:
            return None
        if not (storage_bytes or training_seconds or api_calls):
            return self.get_quota(project_id)
        # 用量只能归属到一个真实存在的项目：project_quota.project_id 外键指向 projects.id，
        # 给不存在的项目补行会撞 FK。作业引用不存在/已删项目时静默跳过，绝不让用量记账打断注册。
        if self._conn().execute(
                text("SELECT 1 FROM projects WHERE id=:pid"), {"pid": project_id}).fetchone() is None:
            return None
        self.get_quota(project_id)  # 没有行则补一条全 0 的，累加才有落点
        self._conn().execute(
            text("UPDATE project_quota SET"
                 " storage_gb_used = storage_gb_used + :gb,"
                 " training_hours_used = training_hours_used + :hrs,"
                 " api_calls_used = api_calls_used + :calls,"
                 " updated_at = :ts WHERE project_id = :pid"),
            dict(gb=float(storage_bytes) / (1024 ** 3), hrs=float(training_seconds) / 3600.0,
                 calls=int(api_calls), ts=_now(), pid=project_id))
        return self.get_quota(project_id)

    # ---- webhooks ----

    def _webhook(self, row) -> dict:
        out = dict(row)
        out["events"] = _loads(out["events"]) if out["events"] else []
        out["active"] = bool(out["active"])
        return out

    def list_webhooks(self, project_id: str) -> list[dict]:
        rows = self._conn().execute(
            text("SELECT * FROM webhooks WHERE project_id=:pid ORDER BY created_at DESC"),
            dict(pid=project_id)).mappings().fetchall()
        return [self._webhook(r) for r in rows]

    def get_webhook(self, webhook_id: str):
        row = self._conn().execute(
            text("SELECT * FROM webhooks WHERE id=:id"),
            {"id": webhook_id}).mappings().fetchone()
        return self._webhook(row) if row else None

    def create_webhook(self, project_id: str, url: str, events=None, secret: str = "") -> str:
        webhook_id = uuid.uuid4().hex
        self._conn().execute(
            text("INSERT INTO webhooks (id, project_id, url, events, secret, active, created_at)"
                 " VALUES (:id,:pid,:url,:events,:secret,1,:created)"),
            dict(id=webhook_id, pid=project_id, url=url, events=_dumps(events or []),
                 secret=secret or "", created=_now()))
        return webhook_id

    def update_webhook(self, webhook_id: str, url=None, events=None, secret=None, active=None):
        if self.get_webhook(webhook_id) is None:
            return None
        sets, params = [], {"id": webhook_id}
        if url is not None:
            sets.append("url=:url")
            params["url"] = url
        if events is not None:
            sets.append("events=:events")
            params["events"] = _dumps(events)
        if secret is not None:
            sets.append("secret=:secret")
            params["secret"] = secret
        if active is not None:
            sets.append("active=:active")
            params["active"] = 1 if active else 0
        if not sets:
            return self.get_webhook(webhook_id)
        self._conn().execute(
            text(f"UPDATE webhooks SET {', '.join(sets)} WHERE id=:id"), params)
        return self.get_webhook(webhook_id)

    def delete_webhook(self, webhook_id: str) -> bool:
        result = self._conn().execute(
            text("DELETE FROM webhooks WHERE id=:id"), {"id": webhook_id})
        return bool(result.rowcount)

    def record_webhook_delivery(self, webhook_id: str, status: int) -> None:
        """ping / 投递后记一次结果；连不上时 status 为 0。"""
        self._conn().execute(
            text("UPDATE webhooks SET last_status=:status, last_delivered_at=:ts WHERE id=:id"),
            dict(id=webhook_id, status=int(status), ts=_now()))

    # ---- invoices ----

    def _invoice(self, row) -> dict:
        out = dict(row)
        out["line_items"] = _loads(out["line_items"]) if out["line_items"] else []
        return out

    def list_invoices(self, project_id: str, period: str | None = None) -> list[dict]:
        sql = "SELECT * FROM invoices WHERE project_id=:pid"
        params = {"pid": project_id}
        if period:
            sql += " AND period=:period"
            params["period"] = period
        sql += " ORDER BY period DESC, issued_at DESC"
        rows = self._conn().execute(text(sql), params).mappings().fetchall()
        return [self._invoice(r) for r in rows]

    def get_invoice(self, invoice_id: str):
        row = self._conn().execute(
            text("SELECT * FROM invoices WHERE id=:id"),
            {"id": invoice_id}).mappings().fetchone()
        return self._invoice(row) if row else None

    def create_invoice(self, project_id: str, period: str, amount: float, currency: str = "USD",
                       status: str = "open", due_at=None, line_items=None) -> str:
        invoice_id = uuid.uuid4().hex
        self._conn().execute(
            text("INSERT INTO invoices (id, project_id, period, amount, currency, status,"
                 " due_at, issued_at, line_items) VALUES (:id,:pid,:period,:amount,:currency,"
                 ":status,:due_at,:issued,:items)"),
            dict(id=invoice_id, pid=project_id, period=period, amount=float(amount),
                 currency=currency or "USD", status=status or "open", due_at=due_at,
                 issued=_now(), items=_dumps(line_items or [])))
        return invoice_id
