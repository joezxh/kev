"""Regression: DB-projected vertical.INDUSTRIES == legacy hardcoded _medical/_finance/_legal/_education/_support.

The test uses a fresh tmp_path Store so it picks up the current docs/medical/specs/*.json on every run
(spec.json backfill only fills empty rows, so a stale persistent DB hides schema changes).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


SNAPSHOTS = Path(__file__).parent / "fixtures" / "_legacy_snapshots"


@pytest.fixture
def fresh_store(tmp_path):
    from kev.console.db import Store
    return Store(tmp_path / "db.sqlite")


def test_medical_industry_matches_hardcoded(fresh_store):
    from kev.console.services.routing import sync_registry
    reg = sync_registry(fresh_store)
    medical = reg.industry("medical")
    expected = json.loads((SNAPSHOTS / "medical_industry.json").read_text(encoding="utf-8"))
    actual = {s.name: {"risk": s.risk, "human_review": s.human_review,
                       "evidence_question": s.evidence_question, "note": s.note}
              for s in medical.scenarios.values()}
    assert actual == expected, f"DB-projected medical industry differs from legacy hardcoded:\n{actual}"


def test_other_industries_empty_until_out_of_scope(fresh_store):
    """The 5 medical scenarios are the only ones DB-projected; finance/legal/education/support are out of scope."""
    from kev.console.services.routing import sync_registry
    reg = sync_registry(fresh_store)
    for industry_name in ("finance", "legal", "education", "support"):
        if industry_name in reg:
            assert len(reg.industry(industry_name).scenarios) == 0, (
                f"{industry_name} has scenarios; they are not part of this spec's scope"
            )
