"""控制台的契约冻结：它**不改动** kev 的核心文件，且遵守仓库的单一归属约定。

这是最廉价的回归保护。编排层的全部价值都建立在「不碰 kev 核心」之上：
- kev/experiment.py:135-137 的 source_hashes() 在训练前后各校验一次，改核心文件会让
  在途研究轮次失败（27B 的 8×H200 训练不是能重跑的东西）。
- tests/test_unit.py 钉死了 serve.app 的形态与 /v1/models 的字段。

另外冻结三条约定，它们都是本项目踩过的坑：
- 14 种作业齐备且不多不少。
- 每个声明产物的作业都能在 artifacts.RELATION 里查到血缘关系名。
- 编排层代码里不出现 tests/test_conventions.py 保留的环境变量。

Run: uv run python -m pytest tests/test_console_contract.py -q
"""
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# 一个字都不许动
FROZEN = [
    "kev/train.py", "kev/serve.py", "kev/benchmark.py", "kev/calibrate.py",
    "kev/publish.py", "kev/compare.py", "kev/metrics.py", "kev/model.py",
    "kev/checkpoint.py", "kev/data.py", "kev/suite.py", "kev/api.py",
    "kev/experiment.py", "kev/rounds.py", "kev/plot.py",
]

# tests/test_conventions.py 的 single_home 规则：这些只能经 kev.checkpoint 读取
RESERVED_ENV = ("KEV_DTYPE", "KEV_MERGE", "KEV_ATTN", "KEV_LORA_SCALE",
                "KEV_TEMPERATURE", "KEV_BACKEND", "KEV_CUDA_GRAPHS")

ALL_KINDS = {
    "plan_size", "generate", "distill", "goldset", "split", "precheck",
    "train", "baseline", "benchmark", "compare", "calibrate",
    "image", "deploy", "smoke",
}


@pytest.mark.parametrize("relative", FROZEN)
def test_core_file_is_untouched(relative):
    result = subprocess.run(["git", "diff", "--name-only", "HEAD", "--", relative],
                            cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", (
        f"{relative} 被改动了：\n{result.stdout}\n"
        "控制台只能组装 argv，不许改 kev 核心 —— source_hashes() 会让在途研究轮次失败。")


def test_console_package_is_declared_for_packaging():
    """pyproject 的 packages 不含子包时，非 editable 安装会直接 ImportError。"""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    packages = config["tool"]["setuptools"]["packages"]
    assert "kev" in packages
    assert "kev.console" in packages, "kev.console 未声明，非 editable 安装会不可导入"
    assert "kev.console.stages" in packages


def test_console_never_reads_reserved_environment_variables():
    """只查**真正的读取**，不查注释 —— 注释里恰恰要写明「为什么不能读它」。

    匹配 `os.environ` / `environ.get` 附近出现该变量名的行；`test_conventions.py` 的
    正则是 `environ(\\.get)?\\(?\\s*"KEV_..."`，即必须紧跟在 environ 读取后面。
    """
    pattern = re.compile(r'environ\\.get\\(\\s*"(KEV_[A-Z_]+)"|'
                         r'environ\\[\\s*"(KEV_[A-Z_]+)"\\s*\\]')
    for path in sorted((ROOT / "kev/console").rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            for found in pattern.findall(code):
                assert found not in RESERVED_ENV, (
                    f"{path.relative_to(ROOT)}:{number} 读取了保留变量 {found} —— "
                    "它只能经 kev.checkpoint.LoadOptions.from_env 读取")


def test_all_fourteen_kinds_are_registered_and_no_more():
    from kev.console.stages import REGISTRY
    assert set(REGISTRY) == ALL_KINDS


def test_every_kind_declaring_artifacts_has_a_lineage_relation():
    """artifacts.register 用 RELATION[job.kind] 查关系名；缺了就退化成 produced_by。"""
    from kev.console import artifacts
    from kev.console.stages import REGISTRY
    from kev.console.stages.base import JobRequest

    for kind, spec in REGISTRY.items():
        params = {"temperature": "2.35"} if kind in {"image", "deploy"} else {}
        built = spec.preview(JobRequest(scenario="critical-value",
                                        run_name="cv-8b-lora-v1", params=params))
        if built.artifacts_out:
            assert kind in artifacts.RELATION, f"{kind} 声明了产物但 RELATION 里没有条目"


def test_every_declared_artifact_id_resolves_to_a_single_prefix():
    """产物 id 解析出的路径不许有双前缀（data/data/…）—— 那正是曾经踩过的坑：
    传 data/cv 当 id 进去，resolve 会拼成 data/data/cv/summary.json，能返回非空但
    文件永远找不到。"""
    from kev.console import artifacts
    from kev.console.stages import REGISTRY
    from kev.console.stages.base import JobRequest

    for kind, spec in REGISTRY.items():
        params = {"temperature": "2.35"} if kind in {"image", "deploy"} else {}
        built = spec.preview(JobRequest(scenario="critical-value",
                                        run_name="cv-8b-lora-v1", params=params))
        for artifact_id in built.artifacts_out:
            relative = artifacts.resolve(artifact_id)
            assert relative, f"{kind} 的 {artifact_id} 解析为空"
            if relative.startswith("http"):
                continue          # endpoint 解析成 URL，不是文件路径
            for doubled in ("data/data/", "runs/runs/"):
                assert doubled not in relative, f"{kind} 的 {artifact_id} -> {relative}"


def test_no_credential_values_are_persisted_or_served():
    """凭据只能从编排服务的进程环境读，永不落库、永不下发浏览器。"""
    from kev.console.executor import ALLOWED_ENV, SECRET_ENV
    assert not (set(ALLOWED_ENV) & set(SECRET_ENV)), \
        "ALLOWED_ENV 与 SECRET_ENV 不许有交集"
    db = (ROOT / "kev/console/app.py").read_text(encoding="utf-8")
    assert "credentials" in db and "bool(os.environ.get" in db, \
        "/config 必须只回凭据的布尔态"


def test_console_does_not_depend_on_the_removed_legacy_memory_tools():
    """旧的记忆系统（tools/mempalace 等）已下线，控制台不许重新依赖。"""
    for name in ("mempalace", "codebase-memory-mcp", "cbmem"):
        hits = subprocess.run(["git", "grep", "-l", name, "--", "kev/", "playground/src/"],
                              cwd=ROOT, capture_output=True, text=True, check=False)
        assert hits.stdout.strip() == "", f"仍引用已下线的 {name}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))