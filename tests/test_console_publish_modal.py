"""publish / modal 两个新阶段的 argv 组装（Task 7.4 项 1、项 6）。

- publish 调 ``kev.publish``，凭据走 HF_TOKEN（SECRET_ENV），--card 必填路径。
- modal 调外部 ``modal deploy`` CLI，配置全走 env（KEV_SERVE_RUN/GPU/APP_NAME/REF），
  secret 名（KEV_SERVE_SECRET/KEV_HF_SECRET）由 SECRET_ENV 注入。

Run: uv run python -m pytest tests/test_console_publish_modal.py -q
"""
import pytest

from kev.console import paths as console_paths
from kev.console.stages import REGISTRY, Invalid, JobRequest
from kev.console.stages import modal as md
from kev.console.stages import publish as pb


def req(params=None, *, scenario="critical-value", run_name="cv-8b-lora-v1"):
    return JobRequest(scenario=scenario, run_name=run_name, params=params or {})


def flag(argv, name):
    assert name in argv, f"{name} 不在 argv 里：{argv}"
    return argv[argv.index(name) + 1]


# ---- publish ---------------------------------------------------------------

def test_publish_requires_repo_and_card():
    with pytest.raises(Invalid, match="repo"):
        pb.build(req({"card": "docs/model-cards/kev-0.8b.md"}))
    with pytest.raises(Invalid, match="card"):
        pb.build(req({"repo": "jaredpalmer/kev-0.8b"}))


def test_publish_argv_calls_kev_publish_with_run_repo_card():
    built = pb.build(req({"repo": "jaredpalmer/kev-0.8b",
                          "card": "docs/model-cards/kev-0.8b.md",
                          "message": "v0.2 none-of-the-above fix"}))
    assert built.argv[1:3] == ["-m", "kev.publish"]
    assert flag(built.argv, "--run") == "runs/cv-8b-lora-v1/checkpoint"
    assert flag(built.argv, "--repo") == "jaredpalmer/kev-0.8b"
    assert flag(built.argv, "--card") == "docs/model-cards/kev-0.8b.md"
    assert flag(built.argv, "--message") == "v0.2 none-of-the-above fix"


def test_publish_defaults_run_to_the_checkpoint_subdir():
    built = pb.build(req({"repo": "j", "card": "c.md"}))
    assert flag(built.argv, "--run") == "runs/cv-8b-lora-v1/checkpoint"


def test_publish_flags_only_appended_when_explicitly_enabled():
    on = pb.build(req({"repo": "j", "card": "c.md", "private": "1", "replace": "1",
                        "tag": "v0.2", "revision": "candidate"}))
    assert "--private" in on.argv and "--replace" in on.argv
    assert flag(on.argv, "--tag") == "v0.2"
    assert flag(on.argv, "--revision") == "candidate"
    off = pb.build(req({"repo": "j", "card": "c.md", "private": "0", "replace": "0"}))
    assert "--private" not in off.argv and "--replace" not in off.argv
    assert "--tag" not in off.argv and "--revision" not in off.argv


def test_publish_declares_no_local_artifact_and_persists_on_success():
    built = pb.build(req({"repo": "j", "card": "c.md"}))
    assert built.artifacts_out == []
    assert pb.publish.persist == "success"
    assert REGISTRY["publish"] is pb.publish


# ---- modal ----------------------------------------------------------------

def test_modal_deploy_invokes_the_external_cli_with_env():
    built = md.build(req({"run": "jaredpalmer/kev-4b", "gpu": "H100",
                          "app_name": "kev-finetune", "ref": "abc123"}))
    assert built.argv == ["modal", "deploy", str(md.SCRIPT)]
    assert built.env["KEV_SERVE_RUN"] == "jaredpalmer/kev-4b"
    assert built.env["KEV_SERVE_GPU"] == "H100"
    assert built.env["KEV_APP_NAME"] == "kev-finetune"
    assert built.env["KEV_REF"] == "abc123"
    # secret 名由 SECRET_ENV 注入，绝不进 env_overlay
    assert not any("SECRET" in key or "TOKEN" in key for key in built.env)


def test_modal_defaults_gpu_and_app_name():
    built = md.build(req({"run": "cv-8b-lora-v1"}))
    assert built.env["KEV_SERVE_GPU"] == md.DEFAULT_GPU
    assert built.env["KEV_APP_NAME"] == md.DEFAULT_APP
    assert "KEV_REF" not in built.env


def test_modal_falls_back_to_run_name_when_run_omitted():
    built = md.build(req({"run": ""}))
    assert built.env["KEV_SERVE_RUN"] == "cv-8b-lora-v1"


def test_modal_returns_on_success_and_registers_no_local_endpoint():
    built = md.build(req({"run": "cv-8b-lora-v1"}))
    assert built.artifacts_out == []
    assert md.modal.persist == "success"
    assert REGISTRY["modal"] is md.modal


def test_modal_script_path_exists():
    assert md.SCRIPT.exists(), f"modal 脚本不存在：{md.SCRIPT}"
    assert console_paths.SKILL_SCRIPTS.exists()
