"""sync_registry — projects DB scenarios into kev.vertical.IndustryRegistry.

Spec §3.6. Replaces the 5 hardcoded _medical / _finance / _legal / _education / _support builders. The registry built
here is functionally equivalent to the legacy fallback (verified by tests/test_routing_sync.py).
"""
from __future__ import annotations

import json
from typing import Optional

from kev.vertical import Industry, IndustryRegistry, RISK_LEVELS, Scenario, UnknownScenario


def sync_registry(db_session=None) -> IndustryRegistry:
    """Build an IndustryRegistry from the DB. Returns an empty registry if the DB has no scenarios.

    `db_session` is a `kev.console.db.Store` instance; passing it in keeps the function testable.
    """
    if db_session is None:
        from kev.console.db import Store
        db_session = Store()
    reg = IndustryRegistry()
    for row in db_session._conn().execute(
        __import__("sqlalchemy").text("SELECT slug, category, spec_json FROM scenarios WHERE spec_json IS NOT NULL")
    ).mappings().fetchall():
        try:
            spec = json.loads(row["spec_json"])
        except (ValueError, TypeError):
            continue
        routing = spec.get("routing")
        if not routing:
            continue
        industry_name = row.get("category") or "unknown"
        industry = reg._industries.get(industry_name) or Industry(name=industry_name, title=industry_name)
        if industry_name not in reg._industries:
            reg.add(industry)
        scenario = Scenario(
            name=row["slug"],
            industry=industry_name,
            risk=routing.get("risk", "medium"),
            human_review=routing.get("human_review", True),
            evidence_question=routing.get("evidence_question", ""),
            note=routing.get("note", ""),
        )
        industry.add(scenario)
    return reg
