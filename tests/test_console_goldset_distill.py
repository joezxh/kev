"""goldset_audit 与 distill 守护调度的 argv 组装（Task 7.4 项 2、项 5）。

Run: uv run python -m pytest tests/test_console_goldset_distill.py -q
"""
import pytest

from kev.console import paths as console_paths
from kev.console.stages import Invalid, JobRequest
from kev.console.stages import data as d


def req(params=None, *, scenario="critical-value", run_name="cv-8b-lora-v1"):
    return JobRequest(scenario=scenario, run_name=run_name, params=params or {})


def flag(argv, name):
    assert name in argv, f"{name} 不在 argv 里：{argv}"
    return argv[argv.index(name) + 1]


# ---- goldset_audit --------------------------------------------------------

def test_goldset_audit_requires_both_labellings():
    with pytest.raises(Invalid, match="a"):
        d.goldset_audit.preview(req({"b": "data/cv.b.jsonl"}))
    with pytest.raises(Invalid, match="b"):
        d.goldset_audit.preview(req({"a": "data/cv.a.jsonl"}))


def test_goldset_audit_argv_uses_the_audit_subcommand():
    built = d.goldset_audit.preview(req({"a": "data/cv.a.jsonl",
                                          "b": "data/cv.b.jsonl",
                                          "out": "data/cv.disagree.jsonl",
                                          "threshold": "0.1"}))
    argv = built.argv
    assert argv[1].endswith("make_goldset.py")
    assert argv[2] == "audit"
    assert argv[3] == "data/cv.a.jsonl" and argv[4] == "data/cv.b.jsonl"
    assert flag(argv, "--out") == "data/cv.disagree.jsonl"
    assert flag(argv, "--threshold") == "0.1"
    assert built.artifacts_out == []   # 诊断作业，不写新数据集


def test_goldset_audit_default_threshold():
    built = d.goldset_audit.preview(req({"a": "x", "b": "y"}))
    assert flag(built.argv, "--threshold") == "0.05"


# ---- distill 守护调度 ----------------------------------------------------

def test_distill_daemon_requires_schedule():
    with pytest.raises(Invalid, match="HH:MM"):
        d.distill_daemon.preview(req({"skip_exists_check": True}))


def test_distill_daemon_appends_schedule_and_persists_at_start():
    built = d.distill_daemon.preview(req({"schedule": "03:00",
                                           "daily_limit": "200000",
                                           "state_dir": ".distill-cv",
                                           "skip_exists_check": True}))
    argv = built.argv
    assert argv[1].endswith("generate_data.py")
    assert flag(argv, "--schedule") == "03:00"
    assert flag(argv, "--daily-limit") == "200000"
    assert flag(argv, "--state-dir") == ".distill-cv"
    # 守护进程永不自然退出 -> spawn 后立即注册
    assert d.distill_daemon.persist == "start"


def test_distill_one_shot_allows_omitting_schedule():
    built = d.distill.preview(req({"category": "critical-value",
                                    "skip_exists_check": True}))
    assert "--schedule" not in built.argv
    assert d.distill.persist == "success"


def test_goldset_audit_script_exists():
    assert (console_paths.GENERATORS / "make_goldset.py").exists()


def test_distill_build_injects_provider_env(monkeypatch):
    import json
    import tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp()) / "secrets.json"
    tmp.write_text(json.dumps({"p1": {"keys": ["sk-x"], "base_url": "http://g",
                                      "model": "m", "daily_limit": 7}}), encoding="utf-8")
    monkeypatch.setattr("kev.console.secrets.DEFAULT_PATH", tmp)
    built = d.distill.preview(req({"provider_id": "p1", "category": "critical-value",
                                    "state_dir": ".d", "skip_exists_check": True}))
    assert built.env["KEV_GEN_BASE_URL"] == "http://g"
    assert built.env["KEV_GEN_MODEL"] == "m"
    assert built.env["KEV_GEN_API_KEYS"] == "sk-x"
    assert "--daily-limit" in built.argv and built.argv[built.argv.index("--daily-limit") + 1] == "7"


def test_distill_build_rejects_unknown_provider():
    with pytest.raises(Invalid, match="未知蒸馏配置"):
        d.distill.preview(req({"provider_id": "nope", "category": "critical-value",
                                "skip_exists_check": True}))
