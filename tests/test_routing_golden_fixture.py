"""Merge-blocking golden fixture loader (no LLM)."""
from __future__ import annotations

import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "golden" / "routing_golden_v0.json"


def test_golden_fixture_exists_and_valid():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert data["fixture_version"] == "fixtures-v0.1"
    cases = data["cases"]
    assert len(cases) >= 4
    actions = {c["expected_action"] for c in cases}
    assert "ROUTE" in actions
    assert "DROP" in actions
    sites = {c["expected_site"] for c in cases if c["expected_action"] == "ROUTE"}
    assert sites == {"IJ", "NN", "CB"}


def test_one_source_one_site_rule_encoded():
    """Contract reminder until media_plan lands in E2."""
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for case in data["cases"]:
        if case["expected_action"] == "ROUTE":
            assert case["expected_site"] in {"IJ", "NN", "CB"}
            # never a list — 1원문=1매체
            assert isinstance(case["expected_site"], str)
