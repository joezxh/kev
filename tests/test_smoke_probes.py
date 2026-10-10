"""Regression: db.list_smoke_probes() == legacy hardcoded SMOKE_PROBES (5 medical scenarios).

The test uses a fresh tmp_path Store so it picks up the current docs/medical/specs/*.json on every run
(spec.json backfill only fills empty rows, so a stale persistent DB hides schema changes). The expected
fixture is a dict keyed by scenario; the test iterates the dict's values.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


SNAPSHOTS = Path(__file__).parent / "fixtures" / "_legacy_snapshots"


def test_smoke_probes_match_hardcoded(tmp_path):
    from kev.console.db import Store
    store = Store(tmp_path / "db.sqlite")
    actual = store.list_smoke_probes()
    expected = json.loads((SNAPSHOTS / "SMOKE_PROBES.json").read_text(encoding="utf-8"))
    # expected is a dict keyed by scenario slug; normalise to the list-of-dicts shape `list_smoke_probes()` returns.
    if isinstance(expected, dict):
        expected_list = [{"scenario": slug, **body} for slug, body in expected.items()]
    else:
        expected_list = expected
    # Compare by scenario, state, questions, expected_label
    by_scenario_actual = {p["scenario"]: p for p in actual}
    by_scenario_expected = {p["scenario"]: p for p in expected_list}
    assert set(by_scenario_actual.keys()) == set(by_scenario_expected.keys()), (
        f"scenario sets differ: {set(by_scenario_actual.keys()) ^ set(by_scenario_expected.keys())}"
    )
    for slug in by_scenario_expected:
        for field in ("state", "questions", "expected_label"):
            assert by_scenario_actual[slug][field] == by_scenario_expected[slug][field], (
                f"{slug}.{field} differs: actual={by_scenario_actual[slug][field]!r} expected={by_scenario_expected[slug][field]!r}"
            )
