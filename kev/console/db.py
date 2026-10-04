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

SCHEMA_VERSION = 1

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
