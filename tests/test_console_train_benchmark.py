"""train 高级开关与 benchmark 高级选项的 argv 组装（Task 7.4 项 3、项 4）。

Run: uv run python -m pytest tests/test_console_train_benchmark.py -q
"""
import pytest

from kev.console.stages import Invalid, JobRequest
from kev.console.stages import eval as ev
from kev.console.stages import train as tr


def req(params=None, *, scenario="critical-value", run_name="cv-8b-lora-v1"):
    return JobRequest(scenario=scenario, run_name=run_name, params=params or {})


def flag(argv, name):
    assert name in argv, f"{name} 不在 argv 里：{argv}"
    return argv[argv.index(name) + 1]


# ---- train 高级开关 --------------------------------------------------------

def test_train_advanced_keys_are_forwarded_when_set():
    # 高级开关默认不传；设了才出现。
    base = tr.build_argv(req())
    for key in tr.ADVANCED_KEYS:
        assert f"--{key}" not in base, f"{key} 默认不该出现"
    argv = tr.build_argv(req({"perm_kl": "0.1", "ord_w": "0.5",
                               "label_smoothing": "0.05", "brier_w": "1.0",
                               "focal_gamma": "2.0", "p_none": "0.2",
                               "synthetic_repeat": "3", "public_frac": "0.5",
                               "special_embeddings": "1", "option_isolation": "1",
                               "snapshot_every_steps": "200", "anchor": "data/cv/anchor.jsonl",
                               "anchor_w": "1.0", "anchor_sources": "cv",
                               "train_sources": "cv", "holdout": "data/cv.gold.jsonl"}))
    assert flag(argv, "--perm_kl") == "0.1"
    assert flag(argv, "--ord_w") == "0.5"
    assert flag(argv, "--label_smoothing") == "0.05"
    assert flag(argv, "--brier_w") == "1.0"
    assert flag(argv, "--focal_gamma") == "2.0"
    assert flag(argv, "--p_none") == "0.2"
    assert flag(argv, "--synthetic_repeat") == "3"
    assert flag(argv, "--public_frac") == "0.5"
    assert flag(argv, "--special_embeddings") == "1"
    assert flag(argv, "--option_isolation") == "1"
    assert flag(argv, "--snapshot_every_steps") == "200"
    assert flag(argv, "--anchor") == "data/cv/anchor.jsonl"
    assert flag(argv, "--anchor_w") == "1.0"
    assert flag(argv, "--anchor_sources") == "cv"
    assert flag(argv, "--train_sources") == "cv"
    assert flag(argv, "--holdout") == "data/cv.gold.jsonl"


def test_train_anchor_requires_anchor_w():
    with pytest.raises(Invalid, match="anchor_w"):
        tr.build_argv(req({"anchor": "data/cv/anchor.jsonl"}))
    # anchor_w 给正值时通过
    argv = tr.build_argv(req({"anchor": "data/cv/anchor.jsonl", "anchor_w": "1.0"}))
    assert flag(argv, "--anchor_w") == "1.0"


def test_train_none_pair_max_state_requires_p_none_pair():
    with pytest.raises(Invalid, match="p_none_pair"):
        tr.build_argv(req({"none_pair_max_state": "50"}))
    argv = tr.build_argv(req({"none_pair_max_state": "50", "p_none_pair": "0.1"}))
    assert flag(argv, "--p_none_pair") == "0.1"


# ---- benchmark 高级选项 ----------------------------------------------------

def test_benchmark_default_points_at_local_run_and_partition():
    argv = ev.benchmark.preview(req({"data": "data/cv"})).argv
    assert argv[1:3] == ["-m", "kev.benchmark"]
    assert flag(argv, "--run") == "runs/cv-8b-lora-v1"
    assert flag(argv, "--data") == "data/cv/development.jsonl"


def test_benchmark_remote_mode_skips_local_run():
    built = ev.benchmark.preview(req({"remote": "https://kev.example.com/v1",
                                       "remote_model": "kev-latest",
                                       "remote_concurrency": "4",
                                       "allow_test": "1", "date_facts": "1",
                                       "rotations": "3"}))
    argv = built.argv
    assert "--run" not in argv
    assert flag(argv, "--remote") == "https://kev.example.com/v1"
    assert flag(argv, "--remote-model") == "kev-latest"
    assert flag(argv, "--remote-concurrency") == "4"
    assert "--allow-test" in argv
    assert "--date_facts" in argv
    assert flag(argv, "--rotations") == "3"
    # 远程打分不读本地 checkpoint -> 没有本地 run 产物
    assert built.artifacts_in == []


def test_benchmark_suite_mode_replaces_data():
    built = ev.benchmark.preview(req({"suite": "evals/v7/decision-v7",
                                      "split": "train"}))
    assert "--data" not in built.argv
    assert flag(built.argv, "--suite") == "evals/v7/decision-v7"
    assert flag(built.argv, "--split") == "train"
