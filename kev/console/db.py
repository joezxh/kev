"""编排层的持久化：作业状态机、产物、血缘、事件。

三条设计约定（spec §5 / §9）：
- SQLite 单文件，PRAGMA user_version 做 schema 版本，不引 ORM
- 日志文件是真相源，events 表只是给 UI 的可分页尾巴（首屏回填 + Last-Event-ID 续传）
- 状态机集中校验：succeeded -> running 这类转移必须被拒
"""
from __future__ import annotations

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
    "pending": frozenset({"queued", "canceled", "failed"}),
    "queued": frozenset({"running", "canceled", "failed", "interrupted"}),
    "running": TERMINAL,
    "succeeded": frozenset(),
    "failed": frozenset(),
    "canceled": frozenset(),
    "interrupted": frozenset(),
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

    # ---- jobs -------------------------------------------------------------

    def create_job(self, *, kind, stage, scenario, title, request, argv, env_overlay,
                   cwd, log_path, artifacts_in, artifacts_out, parent_id=None) -> str:
        job_id = uuid.uuid4().hex
        self.connect().execute(
            "INSERT INTO jobs (id, kind, stage, scenario, title, status, request, argv, env_overlay, cwd,"
            " log_path, artifacts_in, artifacts_out, parent_id, attempt, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)",
            (job_id, kind, stage, scenario, title, "pending", _dumps(request), _dumps(argv),
             _dumps(env_overlay), str(cwd), str(log_path), _dumps(artifacts_in),
             _dumps(artifacts_out), parent_id, _now()),
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
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if to_status not in ALLOWED[job["status"]]:
            raise ValueError(
                f"illegal transition {job['status']} -> {to_status} for job {job_id}"
            )
        stamps, params = [], [to_status]
        if to_status == "running" and job["started_at"] is None:
            stamps.append("started_at = ?")
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
        params.append(job_id)
        sql = ("UPDATE jobs SET status = ?" + (", " + ", ".join(stamps) if stamps else "")
               + " WHERE id = ?")
        self.connect().execute(sql, params)
        self.connect().commit()

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

    def put_artifact(self, *, kind, name, path, meta, bytes_=None) -> str:
        artifact_id = f"{kind}:{name}"
        self.connect().execute(
            "INSERT INTO artifacts (id, kind, name, path, meta, bytes, created_at) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET path = excluded.path, meta = excluded.meta,"
            " bytes = excluded.bytes",
            (artifact_id, kind, name, str(path), _dumps(meta), bytes_, _now()),
        )
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

    def add_lineage(self, parent, child, relation, job_id=None) -> None:
        self.connect().execute(
            "INSERT OR IGNORE INTO lineage (parent, child, relation, job_id) VALUES (?,?,?,?)",
            (parent, child, relation, job_id),
        )
        self.connect().commit()

    def lineage_of(self, artifact_id) -> list[dict]:
        """出边（这个产物派生了什么）。入边查 child 那一侧。"""
        rows = self.connect().execute(
            "SELECT * FROM lineage WHERE parent = ?", (artifact_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    # ---- events -----------------------------------------------------------

    def append_events(self, job_id, rows) -> int:
        """rows: [(stream, line), ...]。返回最后一条的 id，供 SSE 续传游标使用。"""
        stamp = _now()
        payload = [(job_id, stamp, stream, line) for stream, line in rows]
        connection = self.connect()
        connection.executemany(
            "INSERT INTO events (job_id, ts, stream, line) VALUES (?,?,?,?)", payload
        )
        connection.commit()
        row = connection.execute(
            "SELECT MAX(id) FROM events WHERE job_id = ?", (job_id,)
        ).fetchone()
        return row[0] or 0

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
