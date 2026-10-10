"""run_from_db — exec a smoke probe for one scenario (or all) using the DB-projected probe list.

Spec §3.7. Replaces the hardcoded SMOKE_PROBES constant in kev/console/stages/deploy.py.
"""
from __future__ import annotations

from typing import Optional


def run_from_db(scenario: Optional[str] = None) -> list:
    """Run smoke probes from the DB. Returns [{scenario, state, questions, response, expected_label, matched}]."""
    from kev.console.db import Store
    from kev.serve import Server  # imported lazily to avoid GPU init in tests
    store = Store()
    probes = store.list_smoke_probes()
    if scenario:
        probes = [p for p in probes if p["scenario"] == scenario]
    server = Server.from_env()  # loads the default checkpoint
    results = []
    for probe in probes:
        # Build a TypeSafe request from the probe's state + questions
        from kev.api import to_request
        request = to_request(state=probe["state"], questions=probe["questions"])
        response = server.decide(request)
        actual = response.questions[0].label
        expected = probe["expected_label"].get(probe["questions"][0]["qid"])
        results.append({**probe, "actual_label": actual, "matched": actual == expected})
    return results