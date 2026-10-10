"""契约冻结（Task C1）：本计划不得触碰 kev.serve 的 key 转发与 generate_data 的用量上报。

若后续有人改动下面任一文件，本测试必须失败 —— 这是 spec §3 / §9 的硬性约束：
- kev/serve.py：System One 的 key 转发与用量上报逻辑（唯一允许持有管理 key 的地方）。
- skills/kev-finetune/scripts/generate_data.py：蒸馏脚本，按 --state-dir 落 usage_*.json 供编排服务采集。

Run: uv run python -m pytest tests/test_console_contract_freeze.py -q
"""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# 任务起点：feat/apikey-usage 分支首个功能提交（5649374）的父提交。
FROZEN_BASE = "00e8454"
FROZEN = [
    "kev/serve.py",
    "skills/kev-finetune/scripts/generate_data.py",
]


def _blob(rev: str, rel: str) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", f"{rev}:{rel}"], cwd=REPO
    ).decode().strip()


def test_frozen_contract_files_unchanged_since_task_start():
    missing = [r for r in FROZEN if subprocess.call(
        ["git", "cat-file", "-e", f"{FROZEN_BASE}:{r}"], cwd=REPO) != 0]
    assert not missing, f"冻结基准缺少文件：{missing}"
    for rel in FROZEN:
        assert _blob(FROZEN_BASE, rel) == _blob("HEAD", rel), (
            f"{rel} 自任务起点后被改动，违反冻结契约（spec §3/§9）："
            "kev.serve 的 key 转发与 generate_data 的用量上报逻辑不得被本计划触碰"
        )
