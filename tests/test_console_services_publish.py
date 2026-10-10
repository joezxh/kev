"""kev.console.services.publish: in-process wrapper for the publish stage.

Per the Wave B-5 plan, PublishService covers the single publish stage
(Hub upload). The modal stage stays on Popen because `modal deploy` shells
out to a CLI binary that owns its own state on Modal's side. The actual
kev.publish.run call is mocked here so the test stays in seconds and has
no network / Hub dependency.
"""
from __future__ import annotations

import argparse
import threading
from pathlib import Path

import pytest

from kev.console.db import Store
from kev.console.services.publish import PublishService, kev_publish_run
from kev.console.stages.base import JobRequest


@pytest.fixture
def svc(tmp_path):
    return PublishService(Store(tmp_path / "test.db"), threading.Event())


def _req(params=None) -> JobRequest:
    return JobRequest(scenario="critical-value", run_name="cv-rel",
                      params=params or {})


def test_publish_dispatches_to_kev_publish_run(monkeypatch, svc, tmp_path):
    """PublishService.publish() builds a Namespace and calls kev.publish.run."""
    captured: dict = {}

    def fake_run(args):
        captured["ns"] = args
        return 0

    monkeypatch.setattr("kev.console.services.publish.kev_publish_run", fake_run)
    card = tmp_path / "card.md"
    card.write_text("# model card", encoding="utf-8")
    rc = svc.publish(_req({"repo": "jaredpalmer/kev-0.8b", "card": str(card)}),
                     on_log=lambda s: None, on_metric=lambda p: None)
    assert rc == {"returncode": 0}
    ns = captured["ns"]
    assert ns.repo == "jaredpalmer/kev-0.8b"
    assert ns.card == str(card)
    # Default run path: runs/<run_name>/checkpoint
    assert ns.run == "runs/cv-rel/checkpoint"


def test_publish_forwards_optional_flags(monkeypatch, svc, tmp_path):
    """Optional flags (private, replace, tag, revision, message) are forwarded."""
    captured: dict = {}

    def fake_run(args):
        captured["ns"] = args
        return 0

    monkeypatch.setattr("kev.console.services.publish.kev_publish_run", fake_run)
    card = tmp_path / "card.md"
    card.write_text("# model card", encoding="utf-8")
    rc = svc.publish(_req({"repo": "jaredpalmer/kev-0.8b", "card": str(card),
                           "private": "1", "replace": "1",
                           "tag": "v1", "revision": "main",
                           "message": "release notes"}),
                     on_log=lambda s: None, on_metric=lambda p: None)
    assert rc == {"returncode": 0}
    ns = captured["ns"]
    assert ns.private is True
    assert ns.replace is True
    assert ns.tag == "v1"
    assert ns.revision == "main"
    assert ns.message == "release notes"


def test_publish_requires_repo(svc, tmp_path):
    """Missing repo raises Invalid (matches the stage's gate)."""
    from kev.console.stages.base import Invalid
    card = tmp_path / "card.md"
    card.write_text("# model card", encoding="utf-8")
    with pytest.raises(Invalid) as excinfo:
        svc.publish(_req({"card": str(card)}),
                    on_log=lambda s: None, on_metric=lambda p: None)
    assert excinfo.value.field == "repo"


def test_publish_requires_card(svc, tmp_path):
    """Missing card raises Invalid (matches the stage's gate)."""
    from kev.console.stages.base import Invalid
    with pytest.raises(Invalid) as excinfo:
        svc.publish(_req({"repo": "jaredpalmer/kev-0.8b"}),
                    on_log=lambda s: None, on_metric=lambda p: None)
    assert excinfo.value.field == "card"
