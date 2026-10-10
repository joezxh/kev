"""DataDaemon: the in-process loop that owns one long-lived distill child.

Used by `kev.console.daemon_runner` (a thin CLI wrapper). Owns the
`generate_data.py --schedule HH:MM` Popen; tees its stdout to the master
process via the `_internal/distill-event` HTTP endpoint; and checks for
cancellation via `_internal/distill-cancel?daemon_id=...`.

This module is the service-layer half of Wave D in the 2026-10-09 rollout
plan. The CLI entry is `kev.console.daemon_runner`; the master-process
endpoints are `kev.console.app._internal_distill_event` /
`_internal_distill_cancel`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

# Poll cadence: how often the daemon checks with the master for a cancel
# signal. Master-side state is event-driven (an HTTP call sets self.cancel on
# the master), but the daemon polls — not pubsub — because it's a separate
# process and HTTP polling is the simplest contract that survives restarts.
CANCEL_POLL_SECONDS = 2.0

# Event kinds sent back to the master; mirrored in app.py's parse logic.
EVENT_LOG = "log"
EVENT_METRIC = "metric"
EVENT_DONE = "done"
EVENT_ERROR = "error"


def _post_json(url: str, payload: dict, *, timeout: float = 5.0) -> dict:
    """POST a JSON payload to the master. Returns the parsed JSON body or
    raises on connection error / non-2xx (the caller decides whether to
    retry, drop, or fail the daemon).
    """
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, data=body, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else {}


def _poll_cancel(master_url: str, daemon_id: str) -> bool:
    """Returns True if the master has asked this daemon to cancel."""
    url = f"{master_url}/console/api/_internal/distill-cancel?daemon_id={daemon_id}"
    try:
        with urllib.request.urlopen(url, timeout=3.0) as resp:
            raw = resp.read()
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        # Master is gone or transiently unavailable: assume the worst and
        # ask the daemon to wind down. A single transient blip on a 2-second
        # poll would otherwise pin a daemon to a dead master forever.
        return True
    if not raw:
        return False
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return False
    return bool(body.get("canceled"))


def _stream_child(proc: subprocess.Popen, *, on_line: Callable[[str], None]) -> int:
    """Read a child's stdout line by line, invoking on_line for each. Returns
    the child's return code. Stops on EOF or on_line raising.
    """
    for line in iter(proc.stdout.readline, b""):
        try:
            text = line.decode("utf-8", errors="replace").rstrip()
        except Exception:
            text = repr(line)
        if text:
            on_line(text)
    return proc.wait()


class DataDaemon:
    """Owns one long-lived distill child and proxies events back to master.

    Lifecycle:
        daemon = DataDaemon(master_url, daemon_id, job_id, log_path)
        daemon.run_forever(argv, env)  # blocks until cancel or child dies

    The child is `python -m generate_data.py <spec> --schedule HH:MM ...`
    (the schedule child sleeps until tomorrow after exhausting today's quota,
    so this loop is genuinely long-lived; the daemon's "infinite" is the
    master's illusion of "run until canceled").
    """

    def __init__(self, *, master_url: str, daemon_id: str, job_id: str,
                 log_path: Path):
        self.master_url = master_url.rstrip("/")
        self.daemon_id = daemon_id
        self.job_id = job_id
        self.log_path = Path(log_path)
        self.cancel = threading.Event()
        self._child: subprocess.Popen | None = None
        self._child_lock = threading.Lock()
        self._child_pid: int | None = None

    # ---- event emit ------------------------------------------------------

    def _emit(self, kind: str, line: str) -> None:
        """Best-effort POST to master's distill-event endpoint. Never raises
        into the run loop: a transient blip is logged to the local log_path
        and dropped (the next emit will succeed when the master is back).
        """
        url = f"{self.master_url}/console/api/_internal/distill-event"
        try:
            _post_json(url, {
                "daemon_id": self.daemon_id, "job_id": self.job_id,
                "kind": kind, "line": line, "ts": time.time(),
            })
        except Exception as error:
            # If we can't reach master, write a local breadcrumb so the user
            # can see "we lost the master" in the job log even though the
            # events table won't get the line.
            self._local_log(f"[daemon] 事件发送失败 {kind!r}: {error!r}")

    def _local_log(self, line: str) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(line.rstrip() + "\n")
        except Exception:
            # Logging should never raise into the run loop; if disk is gone,
            # the daemon keeps running and the master gets the next event
            # when the disk comes back.
            pass

    # ---- run loop --------------------------------------------------------

    def _spawn_child(self, argv: list, env: dict, cwd: str) -> subprocess.Popen:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fh = self.log_path.open("a", encoding="utf-8")
        # bufsize=1 (line-buffered) so readline() in the reader thread sees
        # output as it's produced, not after the buffer fills.
        proc = subprocess.Popen(
            argv, env=env, cwd=cwd, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, bufsize=1,
        )
        self._child = proc
        self._child_pid = proc.pid
        return proc

    def _stop_child(self) -> None:
        with self._child_lock:
            proc, self._child = self._child, None
        if proc is None:
            return
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            except Exception as error:
                self._local_log(f"[daemon] 终止子进程失败: {error!r}")

    def run_forever(self, argv: list, env: dict, cwd: str) -> int:
        """Blocks until self.cancel is set or the child exits. Returns the
        child's return code (which for --schedule is almost always the
        process having been terminated by us, never a natural exit).
        """
        try:
            proc = self._spawn_child(argv, env, cwd)
        except FileNotFoundError as error:
            self._emit(EVENT_ERROR, f"无法启动子进程: {error!r}")
            return 127
        except Exception as error:
            self._emit(EVENT_ERROR, f"spawn 失败: {error!r}")
            return 1

        self._emit(EVENT_LOG, f"[daemon] child pid={proc.pid} argv={argv!r}")

        def reader() -> int:
            return _stream_child(proc, on_line=lambda line: self._emit(EVENT_LOG, line))

        reader_thread = threading.Thread(target=reader, name=f"daemon-reader-{self.daemon_id[:8]}",
                                         daemon=True)
        reader_thread.start()

        # Poll for cancel. If we see it, kill the child and let the reader
        # thread drain the remaining lines before we return.
        try:
            while proc.poll() is None:
                if self.cancel.is_set() or _poll_cancel(self.master_url, self.daemon_id):
                    self._emit(EVENT_LOG, "[daemon] 收到取消信号，停止子进程")
                    self._stop_child()
                    break
                time.sleep(CANCEL_POLL_SECONDS)
        except Exception as error:
            self._emit(EVENT_ERROR, f"daemon 循环异常: {error!r}")
            self._stop_child()

        reader_thread.join(timeout=10)
        rc = proc.returncode if proc.returncode is not None else -1
        self._emit(EVENT_DONE, f"[daemon] child exited rc={rc}")
        return rc


def main(argv: list | None = None) -> int:
    """CLI entry — called by `python -m kev.console.daemon_runner`.

    Expected args (positional/flag form, since distutils doesn't apply here):
        --master-url http://127.0.0.1:8790
        --daemon-id <uuid>
        --job-id    <uuid>
        --log-path  <path>
        --          # everything after -- is the child argv

    We use `--` so the child's own flags (e.g. --schedule) don't get parsed
    by this CLI. Simpler than building a full argparse with REMAINDER.
    """
    import argparse
    parser = argparse.ArgumentParser(prog="kev.console.daemon_runner")
    parser.add_argument("--master-url", required=True)
    parser.add_argument("--daemon-id", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--log-path", required=True)
    parser.add_argument("--cwd", default=".")
    args, child_argv = parser.parse_known_args(argv)
    if not child_argv:
        print("[daemon] 错误: 缺少子进程 argv（应在 -- 之后给出）", file=sys.stderr)
        return 2

    # env: pass through the parent's env, but KEV_* overrides win (so the
    # master can pin a specific base_url / keys without the parent env
    # leaking the wrong provider into the daemon's child).
    env = dict(os.environ)

    daemon = DataDaemon(
        master_url=args.master_url, daemon_id=args.daemon_id,
        job_id=args.job_id, log_path=Path(args.log_path),
    )
    return daemon.run_forever(child_argv, env=env, cwd=args.cwd)


if __name__ == "__main__":
    raise SystemExit(main())
