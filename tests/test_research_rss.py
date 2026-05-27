#!/usr/bin/env python3
"""RSS-shaped raw source tests (engine-compatible ingress)."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import research_collector as rc  # noqa: E402
import research_rss as rr  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "research"


class TestRssEntryMapping(unittest.TestCase):
    def test_rss_entry_to_raw_source_uses_summary_as_html(self):
        html = (FIXTURES / "rss_summary_sample.html").read_text(encoding="utf-8")
        entry = SimpleNamespace(
            link="https://www.korea.kr/news/policyNewsView.do?newsId=148962669",
            title="물티슈·생리대 등 위생용품 내용량 축소",
            summary=html,
            published_parsed=(2026, 4, 14, 17, 31, 0),
            media_content=[],
        )
        raw = rr.rss_entry_to_raw_source(
            entry,
            feed_url="https://www.korea.kr/rss/policy.xml",
            feed_name="정책브리핑-policy",
            source_type="policy_briefing",
        )
        self.assertEqual(raw["source_type"], "policy_briefing")
        self.assertIn("rss_summary", raw)
        self.assertEqual(raw["raw_html"], raw["rss_summary"])
        self.assertIn("공정거래", raw["body"])
        self.assertIn("price.go.kr", raw["body"])

    def test_build_plan_from_rss_shaped_source(self):
        html = (FIXTURES / "rss_summary_sample.html").read_text(encoding="utf-8")
        raw = {
            "url": "https://www.korea.kr/news/policyNewsView.do?newsId=148962669",
            "title": "물티슈 테스트",
            "rss_summary": html,
            "raw_html": html,
            "source_type": "policy_briefing",
            "feed_name": "정책브리핑-policy",
        }
        plan = rc.build_evidence_plan(raw)
        hosts = [c.domain for c in plan.link_candidates]
        self.assertTrue(any("price.go.kr" in h for h in hosts))
        self.assertTrue(any("ftc.go.kr" in c.url for c in plan.link_candidates if c.evidence_type == "ministry_press_hub"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
