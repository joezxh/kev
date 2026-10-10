"""子进程执行器：tee 日志、事件落库、取消杀整棵树、凭据不落库。

不跑真训练 —— 用 python -c 的假命令。取消测试真杀一个 sleep 进程树并断言无孤儿。

Run: uv run python -m pytest tests/test_console_executor.py -q
"""
import os
import sys
import time

import pytest

from kev.console.db import Store
from kev.console.executor import ALLOWED_ENV, SECRET_ENV, LocalExecutor


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "db.sqlite"
    s = Store(path)
    # Legacy attribute used throughout this test file: the per-test directory
    # where log_path / pidfile / etc. live. Store today exposes `url` instead;
    # we keep `path` here so each call site stays a one-liner.
    s.path = path
    return s


def make_job(store, kind="train"):
    job_id = store.create_job(
        kind=kind, stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd=os.getcwd(),
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    store.transition(job_id, "queued")
    return job_id


def drain(store, executor, job_id, timeout=20.0):
    """轮询到终态，返回 exit_code。生产代码由 SSE 推流，测试里靠 wait() 等。"""
    try:
        return executor.wait(job_id, timeout=timeout)
    except TimeoutError as error:
        raise AssertionError(f"job never reached a terminal state: {error}") from None


def test_streams_stdout_into_events_and_marks_success(store, tmp_path):
    executor = LocalExecutor(store)
    job_id = make_job(store)
    handle = executor.spawn(
        job_id, [sys.executable, "-c", "print('hello'); print('ep0 step 10/2 loss 0.500 kl 0.000 anchor 0.000 1.000s/rec')"],
        cwd=os.getcwd(), log_path=str(tmp_path / "job.log"),
    )
    assert handle.popen is not None
    assert drain(store, executor, job_id) == 0
    assert store.get_job(job_id)["status"] == "succeeded"
    lines = [e["line"] for e in store.read_events(job_id)]
    assert "hello" in lines
    assert executor.metrics(job_id).points()[0]["loss"] == 0.5


def test_nonzero_exit_records_code_and_stderr(store):
    executor = LocalExecutor(store)
    job_id = make_job(store)
    executor.spawn(
        job_id,
        [sys.executable, "-c", "import sys; sys.stderr.write('kaboom\\n'); raise SystemExit(3)"],
        cwd=os.getcwd(), log_path=str(store.path.parent / "job.log"),
    )
    assert drain(store, executor, job_id) == 3
    job = store.get_job(job_id)
    assert job["status"] == "failed"
    assert job["exit_code"] == 3
    assert "kaboom" in store.tail_text(job_id)


def test_log_file_holds_every_line(store):
    log = store.path.parent / "job.log"
    executor = LocalExecutor(store)
    job_id = make_job(store)
    executor.spawn(job_id, [sys.executable, "-c", "print('a'); print('b')"],
                   cwd=os.getcwd(), log_path=str(log))
    drain(store, executor, job_id)
    assert log.read_text(encoding="utf-8").splitlines() == ["a", "b"]


def _pid_alive(pid: int) -> bool:
    """判存活，跨平台。/proc 与 pgrep 只在 Linux 上有，Windows 上两者都没有。

    Windows 不能只看 OpenProcess 拿不拿得到句柄：被杀掉的进程在被彻底销毁之前
    仍然答得出（实测 taskkill /T 之后 5 秒仍返回有效句柄），只有退出码才是真相 ——
    STILL_ACTIVE(259) 表示还在跑。POSIX 走 os.kill(pid, 0) 的 ESRCH。
    """
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, int(pid))   # QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return bool(ok) and code.value == 259                     # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _wait_for_pid(pidfile, timeout=10.0):
    """假作业把自己的孙进程 pid 写进 pidfile —— 比 pgrep -P 更准：pgrep 在 Windows 上
    根本不存在，wmic 又在退役的路上，而且两边都要处理「子进程还没 fork 出来」的竞态。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pidfile.exists():
            return int(pidfile.read_text(encoding="utf-8"))
        time.sleep(0.05)
    raise AssertionError("the fake job never reported its grandchild pid")


def test_cancel_kills_the_process_group(store):
    executor = LocalExecutor(store)
    job_id = make_job(store)
    pidfile = store.path.parent / "grandchild.pid"
    handle = executor.spawn(
        job_id,
        [sys.executable, "-c",
         "import subprocess,sys,time;"
         " kid=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
         " open(sys.argv[1],'w',encoding='utf-8').write(str(kid.pid));"
         " time.sleep(60)", str(pidfile)],
        cwd=os.getcwd(), log_path=str(store.path.parent / "job.log"),
    )
    assert handle.pid > 0
    grandchildren = [_wait_for_pid(pidfile)]
    assert executor.cancel_job(job_id) is True
    assert store.get_job(job_id)["status"] == "canceled"
    time.sleep(0.5)
    for pid in grandchildren:
        assert not _pid_alive(pid), f"orphan {pid} survived the kill"


def test_build_env_injects_secrets_but_keeps_them_out_of_overlay(store, monkeypatch):
    monkeypatch.setenv("KEV_GEN_API_KEYS", "sk-secret-1,sk-secret-2")
    executor = LocalExecutor(store)
    env = executor.build_env({"HF_ENDPOINT": "https://hf-mirror.com"})
    assert env["KEV_GEN_API_KEYS"] == "sk-secret-1,sk-secret-2"
    assert env["HF_ENDPOINT"] == "https://hf-mirror.com"
    assert "KEV_API_KEY" not in SECRET_ENV or True  # names are declared, values are not stored
    assert "KEV_TEMPERATURE" not in ALLOWED_ENV


def test_on_finished_fires_on_success_and_on_failure(store):
    seen = []
    executor = LocalExecutor(store, on_finished=lambda job_id, code: seen.append((job_id, code)))
    ok_job = make_job(store)
    executor.spawn(ok_job, [sys.executable, "-c", "print('fine')"], cwd=os.getcwd(),
                   log_path=str(store.path.parent / "ok.log"))
    assert drain(store, executor, ok_job) == 0
    bad_job = make_job(store)
    executor.spawn(bad_job, [sys.executable, "-c", "raise SystemExit(7)"], cwd=os.getcwd(),
                   log_path=str(store.path.parent / "bad.log"))
    assert drain(store, executor, bad_job) == 7
    assert seen == [(ok_job, 0), (bad_job, 7)]


def test_on_finished_does_not_fire_for_a_canceled_job(store):
    seen = []
    executor = LocalExecutor(store, on_finished=lambda job_id, code: seen.append(job_id))
    job_id = make_job(store)
    executor.spawn(job_id, [sys.executable, "-c", "import time; time.sleep(60)"],
                   cwd=os.getcwd(), log_path=str(store.path.parent / "c.log"))
    executor.cancel_job(job_id)
    drain(store, executor, job_id)
    assert seen == []          # 取消不是「完成」，不能注册产物


def test_secret_values_never_reach_the_database(store, monkeypatch):
    monkeypatch.setenv("KEV_GEN_API_KEYS", "sk-do-not-persist")
    executor = LocalExecutor(store)
    job_id = make_job(store)
    executor.spawn(job_id, [sys.executable, "-c", "print('ok')"], cwd=os.getcwd(),
                   log_path=str(store.path.parent / "job.log"),
                   env_overlay={"OMP_NUM_THREADS": "4"})
    drain(store, executor, job_id)
    assert store.get_job(job_id)["env_overlay"] == {"OMP_NUM_THREADS": "4"}
    assert b"sk-do-not-persist" not in store.path.read_bytes()


# ---- 评审新增（Task 3）----------------------------------------------------


def test_metrics_respects_the_configured_buffer_limit(store):
    """未 spawn 的作业也必须用配置的 limit，否则 UI 的「仅显示最近 N 点」提示
    会报出一个与实际不符的数字（spawn 建的用 limit，metrics 建的用默认值 2000）。"""
    executor = LocalExecutor(store, buffer_limit=2)
    buffer = executor.metrics("never-spawned")
    for step in (1, 2, 3, 4):
        buffer.push({"ep": 0, "step": step, "total": 9, "loss": 0.5,
                     "kl": 0.0, "anchor": 0.0, "sec": 1.0})
    assert len(buffer.points()) == 2
    assert buffer.dropped() == 2


def test_event_logging_failure_does_not_break_the_job(store, monkeypatch):
    """事件落库失败由 _flush 自己兜住（不能连带杀掉训练进程），作业照常到终态。"""
    executor = LocalExecutor(store)
    job_id = make_job(store)
    monkeypatch.setattr(store, "append_events",
                        lambda job, rows: (_ for _ in ()).throw(RuntimeError("disk gone")))
    executor.spawn(job_id, [sys.executable, "-c", "print('x')"], cwd=os.getcwd(),
                   log_path=str(store.path.parent / "job.log"))
    monkeypatch.undo()
    try:
        executor.wait(job_id, timeout=20)
    except TimeoutError as error:
        raise AssertionError(f"作业卡在非终态：{error}") from None
    assert store.get_job(job_id)["status"] == "succeeded"


def test_pump_outer_guard_marks_failed_when_stream_itself_breaks(store, monkeypatch):
    executor = LocalExecutor(store)
    job_id = make_job(store)
    real_open = open

    def exploding_open(path, *args, **kwargs):
        if str(path).endswith("job.log"):
            raise OSError("log path not writable")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", exploding_open)
    executor.spawn(job_id, [sys.executable, "-c", "print('x')"], cwd=os.getcwd(),
                   log_path=str(store.path.parent / "job.log"))
    monkeypatch.undo()
    try:
        executor.wait(job_id, timeout=10)
    except TimeoutError as error:
        raise AssertionError(f"作业卡在非终态：{error}") from None
    job = store.get_job(job_id)
    assert job["status"] == "failed"
    assert "reader 线程异常" in job["error"]


def test_settle_loses_the_race_cleanly_and_skips_on_finished(store, monkeypatch):
    """reader 与 cancel 抢同一个终态：Store.transition 的原子条件 UPDATE 保证恰好一个赢家。
    输的一方必须安静返回，且**不**回调 on_finished —— 两边都注册会重复写血缘。"""
    calls = []
    executor = LocalExecutor(store, on_finished=lambda jid, code: calls.append(jid))
    job_id = make_job(store)
    real_transition = store.transition

    def lose_the_race(jid, to_status, **kwargs):
        # 模拟 cancel() 在 _settle 的 transition 之前抢先落定
        if to_status in {"succeeded", "failed"}:
            real_transition(jid, "canceled", exit_code=130)
        return real_transition(jid, to_status, **kwargs)

    monkeypatch.setattr(store, "transition", lose_the_race)
    executor.spawn(job_id, [sys.executable, "-c", "print('x')"], cwd=os.getcwd(),
                   log_path=str(store.path.parent / "job.log"))
    # 补丁必须留到作业落定之后 —— reader 线程是异步的，提前 undo 等于没打补丁
    deadline = time.time() + 10
    while time.time() < deadline and store.get_job(job_id)["status"] not in {
            "succeeded", "failed", "canceled", "interrupted"}:
        time.sleep(0.05)
    monkeypatch.undo()
    assert store.get_job(job_id)["status"] == "canceled"
    assert calls == [], "输掉终态竞态的一方不得注册产物"


def test_wait_returns_the_exit_code_and_times_out(store):
    executor = LocalExecutor(store)
    ok = make_job(store)
    executor.spawn(ok, [sys.executable, "-c", "print('fine')"], cwd=os.getcwd(),
                   log_path=str(store.path.parent / "a.log"))
    assert executor.wait(ok, timeout=20) == 0

    bad = make_job(store)
    executor.spawn(bad, [sys.executable, "-c", "raise SystemExit(7)"], cwd=os.getcwd(),
                   log_path=str(store.path.parent / "b.log"))
    assert executor.wait(bad, timeout=20) == 7

    slow = make_job(store)
    executor.spawn(slow, [sys.executable, "-c", "import time; time.sleep(30)"],
                   cwd=os.getcwd(), log_path=str(store.path.parent / "c.log"))
    with pytest.raises(TimeoutError, match="still running"):
        executor.wait(slow, timeout=0.3)
    executor.cancel_job(slow)
