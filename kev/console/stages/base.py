"""阶段处理器的公共形状。

处理器**只组装 argv，不含业务逻辑**：阈值表、标签规则、指标算法全部仍在
`docs/medical/generators/` 与 `kev/` 里。控制台是编排者，不是规则引擎的第二个实现
—— 这是 `tests/test_conventions.py` 单一归属规则的核心诉求，也是本项目的既有约定。

`StageSpec.preview()` 是纯函数：不 spawn、不写库。UI 用它实时显示将要执行的 argv
（spec §11.2「argv 永远可见」），所以它绝不能有副作用。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field


class Invalid(Exception):
    """表单校验失败 -> 400。`field` 让 UI 把红字标在对应输入框上。"""

    def __init__(self, message: str, *, field: str = "", hint: str = ""):
        super().__init__(message)
        self.message, self.field, self.hint = message, field, hint


class Conflict(Exception):
    """目标目录已存在等不可自动恢复的情况 -> 409。

    绝不自动改名规避：kev.train 与 kev.benchmark.evaluate_records 都是
    `mkdir(exist_ok=False)`，而旧产物必须永久保留（医疗可审计性）。
    """

    def __init__(self, message: str, *, hint: str = ""):
        super().__init__(message)
        self.message, self.hint = message, hint


class Persist(str, Enum):
    """作业的产物什么时候注册。取值与 `artifacts.PERSIST` 一致。

    `register` 本身不判断这个 —— 决定权在 app.py：长驻作业（kev.serve）永远不
    「完成」，所以它的产物必须在 spawn 之后立刻注册，否则端点列表永远是空的。
    """

    SUCCESS = "success"   # 进程自然退出后（on_finished 回调）
    START = "start"       # spawn 之后立刻


class JobRequest(BaseModel):
    """一份作业请求。`params` 的键由各阶段的 `request_model` 校验。"""

    scenario: str = Field(description="场景名，取自 docs/medical/specs/*.json 的 stem")
    run_name: str = Field(default="", description="运行名；须过 run_matrix.check_name（禁点号）")
    params: dict = Field(default_factory=dict)


@dataclass(frozen=True)
class BuiltCommand:
    """一次「组装好但还没跑」的命令。

    `env` 只放**非敏感**键（白名单见 executor.ALLOWED_ENV）；敏感键由执行器在 spawn
    时从自己的进程环境注入，永不落库（spec §12）。
    """

    argv: list
    env: dict = field(default_factory=dict)
    cwd: str = ""
    artifacts_in: list = field(default_factory=list)
    artifacts_out: list = field(default_factory=list)


@dataclass(frozen=True)
class StageSpec:
    kind: str
    stage: str
    title: str
    build: object                 # Callable[[JobRequest], BuiltCommand]
    persist: str = Persist.SUCCESS
    outcome: str = ""             # UI 读它决定成功后的下一步提示

    def preview(self, request: JobRequest) -> BuiltCommand:
        """纯函数：不 spawn、不写库。UI 靠它实时显示 argv。"""
        return self.build(request)
