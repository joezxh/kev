"""子进程执行器：起进程、tee 日志、落事件、取消、凭据注入。

沿用 kev/experiment.py:288-303 已验证的模式：Popen(stdout=PIPE, stderr=STDOUT) 逐行 tee。
三处加强：
- start_new_session=True + os.killpg（Windows 上是 taskkill /T），取消时杀整棵树。
  否则 torchrun 的子进程会变孤儿继续占 GPU。
- 凭据只在 spawn 时从本进程环境变量注入子进程，永不落库（spec §12）。
- reader 线程绝不能死：任何 unforeseen 的异常都收敛成「跳过这一行」，因为一行怪数据
  打死 reader = 作业永远不到终态 = UI 永久转圈（Task 2 评审的硬要求）。
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text

from .db import TERMINAL, Store
from .events import DEFAULT_BUFFER, MetricBuffer, parse_step

# 允许持久化到 jobs.env_overlay 的非敏感键。其余一律不落库。
# KEV_SERVE_RUN 只是运行名（不是凭据），deploy 阶段要靠它告诉容器加载哪个 checkpoint。
ALLOWED_ENV = frozenset({
    "HF_ENDPOINT", "KEV_GEN_BASE_URL", "KEV_GEN_MODEL", "KEV_SERVE_RUN",
    "KEV_SERVE_GPU", "KEV_APP_NAME", "KEV_REF", "OMP_NUM_THREADS", "PYTHONIOENCODING",
})

# 敏感键：只从本进程环境变量读，spawn 时注入子进程，只在 UI 显示布尔态。
# 注意 KEV_TEMPERATURE 不在此列也不得读取 —— 它只能经 kev.checkpoint.LoadOptions.from_env
# （tests/test_conventions.py 的 single_home 规则）；部署温度从 calibration.json 取。
SECRET_ENV = ("KEV_API_KEY", "KEV_GEN_API_KEYS", "KEV_HF_SECRET", "KEV_SERVE_SECRET", "HF_TOKEN")

BATCH = 10

# TERMINAL（作业终态集合）由 kev.console.db 拥有 —— 状态机是它的家，本模块只读。
# signal.SIGKILL 只存在于 POSIX；Windows 上升级档退化成同一个 signal.SIGTERM。
SIGKILL = getattr(signal, "SIGKILL", signal.SIGTERM)


@dataclass
class ProcessHandle:
    job_id: str
    pid: int
    popen: subprocess.Popen


class LocalExecutor:
    def __init__(self, store: Store, *, secret_env=None, buffer_limit: int = DEFAULT_BUFFER,
                 on_finished=None):
        self.store = store
        self.secret_env = tuple(secret_env) if secret_env is not None else SECRET_ENV
        # spawn() 要用 buffer_limit 建每个作业的指标缓冲，所以它得挂在实例上：
        # 只当构造参数的话，spawn 里的裸名字在运行期是 NameError（brief Step 3 的 bug）。
        self.buffer_limit = buffer_limit
        # 进程自然退出后调用一次（cancel 不算）。app.py 用它注册产物 —— 这是产物注册
        # 的唯一触发点，所以它必须在 store.transition 之后、在 reader 线程末尾。
        self.on_finished = on_finished
        self._handles: dict[str, ProcessHandle] = {}
        self._metrics: dict[str, MetricBuffer] = {}
        # cancel() 在杀进程前登记：reader 线程收尾时看到它就让路，不再把作业标成
        # failed/succeeded。没有它就是两个线程抢同一个终态，谁后写谁赢（见 cancel）。
        self._canceling: set[str] = set()
        self._lock = threading.Lock()

    # ---- env --------------------------------------------------------------

    def build_env(self, overlay: dict | None = None) -> dict:
        env = dict(os.environ)
        for key, value in (overlay or {}).items():
            if key not in ALLOWED_ENV:
                raise ValueError(
                    f"env_overlay may not carry {key!r}; allowed: {sorted(ALLOWED_ENV)}"
                )
            env[key] = str(value)
        for key in self.secret_env:
            value = os.environ.get(key)
            if value:
                env[key] = value
        env.setdefault("PYTHONIOENCODING", "utf-8")
        return env

    # ---- lifecycle --------------------------------------------------------

    def spawn(self, job_id, argv, *, cwd, log_path, env_overlay=None) -> ProcessHandle:
        env = self.build_env(env_overlay)
        self._record_overlay(job_id, env_overlay)
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        popen = subprocess.Popen(
            [str(part) for part in argv],
            cwd=str(cwd), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            start_new_session=True,
        )
        handle = ProcessHandle(job_id=job_id, pid=popen.pid, popen=popen)
        with self._lock:
            self._handles[job_id] = handle
            self._metrics[job_id] = MetricBuffer(self.buffer_limit)
        self.store.transition(job_id, "running")
        threading.Thread(target=self._pump, args=(job_id, popen, log_path),
                         name=f"console-{job_id[:8]}", daemon=True).start()
        return handle

    def _record_overlay(self, job_id, overlay) -> None:
        """把这次真正跑的非敏感键写回 jobs.env_overlay —— 审计问的是「跑的时候是什么」，
        不是「建作业时填了什么」。build_env 已经按 ALLOWED_ENV 拒过一遍，凭据进不来这里，
        所以这一列永远不会出现 SECRET_ENV（spec §12）。"""
        if not overlay:
            return
        payload = json.dumps({key: str(value) for key, value in overlay.items()},
                             ensure_ascii=False, allow_nan=False)
        with self.store.tx() as connection:
            connection.execute(
                text("UPDATE jobs SET env_overlay = :overlay WHERE id = :jid"),
                {"overlay": payload, "jid": job_id},
            )

    def _pump(self, job_id, popen, log_path) -> None:
        """reader 线程。**绝不能带着未捕获异常死掉** —— 作业卡在 running 就意味着
        UI 永久转角。所以主体出错也必须把作业推到终态（failed），而不是静默退出。
        """
        try:
            self._stream(job_id, popen, log_path)
        except Exception as error:          # noqa: BLE001 - 见 docstring
            self._force_terminal(job_id, f"reader 线程异常：{error!r}")

    def _stream(self, job_id, popen, log_path) -> None:
        buffer = self._metrics[job_id]
        pending: list[tuple[str, str]] = []
        with open(log_path, "a", encoding="utf-8", newline="") as sink:
            for line in popen.stdout:
                try:
                    sink.write(line)
                    pending.append(("stdout", line.rstrip("\n")))
                    point = parse_step(line)
                    if point is not None:
                        buffer.push(point)
                except Exception:  # 单行处理失败只丢这一行，reader 线程必须活着走到终态
                    pass
                if len(pending) >= BATCH:
                    self._flush(job_id, pending)
                    pending = []
            sink.flush()
        if pending:
            self._flush(job_id, pending)
        self._settle(job_id, popen.wait())

    def _settle(self, job_id, code) -> None:
        """落定终态。

        与 cancel() 抢同一个终态时，Store.transition 的原子条件 UPDATE（BEGIN IMMEDIATE
        + `WHERE status IN (...)`）保证**恰好一个赢家**；输的一方安静返回，且**不**回调
        on_finished —— 产物注册是赢家的责任，两边都注册会重复写血缘。
        """
        with self._lock:
            self._handles.pop(job_id, None)
            if job_id in self._canceling:
                return          # cancel() 正在把它标成 canceled
        try:
            self.store.transition(
                job_id, "succeeded" if code == 0 else "failed", exit_code=code,
                error=None if code == 0 else f"exit {code}: {self.store.tail_text(job_id, lines=5)}")
        except ValueError:
            return              # cancel() / 崩溃恢复抢先了，终态已归它
        if self.on_finished is not None:
            try:
                self.on_finished(job_id, code)
            except Exception:  # 注册失败不能改写已经落定的作业状态
                pass

    def _force_terminal(self, job_id, error) -> None:
        """reader 线程出意外时的兜底：尽力把作业推到终态，绝不让它卡在 running。"""
        try:
            job = self.store.get_job(job_id)
            if job is not None and job["status"] not in TERMINAL:
                self.store.transition(job_id, "failed", error=error)
        except Exception:      # 连兜底都失败时不静默：挂到线程上让它在日志里可见
            import threading as _threading
            _threading.excepthook(type(error), (error,), error.__traceback__)

    def _flush(self, job_id, rows) -> None:
        try:
            self.store.append_events(job_id, rows)
        except Exception:  # 事件落库失败不能连带杀掉训练进程
            pass

    def cancel(self, job_id) -> bool:
        with self._lock:
            handle = self._handles.get(job_id)
            if handle is not None:
                # 先登记再杀：进程一死 reader 线程就会醒，它必须看到这是「取消」
                # 而不是让它先 transition(failed)，否则 cancel 之后状态是 failed。
                self._canceling.add(job_id)
        if handle is None:
            return False
        self._signal_group(handle.pid, signal.SIGTERM)
        deadline = time.time() + 5.0
        while time.time() < deadline and handle.popen.poll() is None:
            time.sleep(0.05)
        if handle.popen.poll() is None:
            self._signal_group(handle.pid, SIGKILL)
        try:
            if self.store.get_job(job_id)["status"] not in TERMINAL:
                try:
                    self.store.transition(job_id, "canceled", exit_code=handle.popen.returncode)
                except ValueError:
                    pass          # reader 线程在同一瞬间赢了终态（原子 UPDATE 判的）
        finally:
            # 转移落定之后才撤登记：撤得太早，reader 线程会看到「没在取消、状态还是
            # running」的组合，自己去写 failed。
            with self._lock:
                self._canceling.discard(job_id)
        return True

    @staticmethod
    def _signal_group(pid, sig) -> None:
        """杀整棵树。POSIX 靠 setsid 建的进程组；Windows 没有组信号，taskkill /T
        沿父子关系遍历，效果等价（没有 SIGTERM 那一档的温和退场，直接强杀）。"""
        if os.name == "nt":
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                               capture_output=True, check=False)
                return
            except OSError:
                pass          # taskkill 不可用，退化成只杀父进程
        try:
            os.killpg(os.getpgid(pid), sig)
        except (OSError, AttributeError):  # OSError 含 ProcessLookupError / PermissionError
            pass

    def wait(self, job_id, timeout: float | None = None) -> int:
        """轮询到终态，返回 exit_code（cancel 不走 exit_code 的话是 None）。生产代码由 SSE
        推流，测试里靠它等；timeout=None 无限等，否则等满就抛 TimeoutError。"""
        deadline = None if timeout is None else time.time() + timeout
        while deadline is None or time.time() < deadline:
            job = self.store.get_job(job_id)
            if job is not None and job["status"] in TERMINAL:
                return job["exit_code"]
            time.sleep(0.05)
        raise TimeoutError(f"job {job_id} is still {self.store.get_job(job_id)['status']} after {timeout}s")

    # ---- reads ------------------------------------------------------------

    def metrics(self, job_id) -> MetricBuffer:
        """取（必要时建）该作业的指标缓冲。未 spawn 的作业也必须用配置的 limit，
        否则 UI 的「仅显示最近 N 点」提示会报出一个与实际不符的数字。"""
        with self._lock:
            if job_id not in self._metrics:
                self._metrics[job_id] = MetricBuffer(self.buffer_limit)
            return self._metrics[job_id]

    def live(self) -> set[str]:
        with self._lock:
            return set(self._handles)
