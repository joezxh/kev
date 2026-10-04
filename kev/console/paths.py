"""仓库目录布局的唯一归属。

编排服务与 kev CLI 在同一个 checkout 里跑（WSL2 内），所以路径都从 __file__ 推出来，
不读环境变量、不接受外部注入 —— 换了 checkout 布局就应当启动失败，而不是写到别处。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_SCRIPTS = ROOT / "skills/kev-finetune/scripts"
SPECS = ROOT / "docs/medical/specs"
GENERATORS = ROOT / "docs/medical/generators"
CONSOLE_SCRIPTS = ROOT / "docs/medical/console"
DATA = ROOT / "data"
RUNS = ROOT / "runs"
JOB_LOGS = DATA / "console/jobs"
DB_PATH = DATA / "console/kev-console.db"


def ensure_medical_on_path() -> None:
    """把 docs/medical/generators 与 skills/kev-finetune/scripts 加进 sys.path。

    运行名规范（NAME_RE / check_name / SIZES / SCENARIOS / FOUR_B_ONLY）的唯一归属是
    docs/medical/generators/run_matrix.py，医疗测试（tests/test_medical_generators.py:21-22）
    用同样的 sys.path.insert 方式引用它。这里沿用该做法而不是复制常量。
    """
    for directory in (GENERATORS, SKILL_SCRIPTS):
        text = str(directory)
        if text not in sys.path:
            sys.path.insert(0, text)
