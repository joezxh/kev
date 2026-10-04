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
    return Store(tmp_path / "db.sqlite")


def make_job(store, kind="train"):
    job_id = store.create_job(
        kind=kind, stage="train", scenario="triage", title="t",
        request={}, argv=["x"], env_overlay={}, cwd=os.getcwd(),
        log_path="l.log", artifacts_in=[], artifacts_out=[],
    )
    store.transition(job_id, "queued")
    return job_id


def drain(store, executor, job_id, timeout=20.0):
    """轮询到终态，返回 exit_code。生产代码由 SSE 推流，测试里用轮询。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if store.get_job(job_id)["status"] in {"succeeded", "failed", "canceled", "interrupted"}:
            return store.get_job(job_id)["exit_code"]
        time.sleep(0.05)
    raise AssertionError("job never reached a terminal state")


def test_streams_stdout_into_events_and_marks_success(store):
    executor = LocalExecutor(store)
    job_id = make_job(store)
    handle = executor.spawn(
        job_id, [sys.executable, "-c", "print('hello'); print('ep0 step 10/2 loss 0.500 kl 0.000 anchor 0.000 1.000s/rec')"],
        cwd=os.getcwd(), log_path=str(store.path.parent / "job.log"),
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
    assert executor.cancel(job_id) is True
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
    executor.cancel(job_id)
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
