#!/usr/bin/env python3
"""Tests for multi-brand editorial pipeline (offline)."""

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline.orchestrator import (
    enrich_raw_source,
    run_pre_publish_pipeline,
    should_use_ij_editorial_rewrite,
)
from engine.pipeline.placement import score_placement
from engine.profiles import route_primary
from engine.profiles.ij import IJProfile

FIXTURES = Path(__file__).parent / "fixtures" / "research"


class TestRouting(unittest.TestCase):
    def test_policy_briefing_routes_to_ij(self):
        raw = json.loads((FIXTURES / "cached_source.json").read_text(encoding="utf-8"))
        raw["source_type"] = "policy_briefing"
        raw["body"] = (
            "정부는 소비자 보호 정책을 개편하고 시행일을 공표했다. "
            "국민과 기업에 영향을 미치며 의무 사항을 명시했다."
        )
        route = route_primary(raw)
        self.assertEqual(route.site, "IJ")
        self.assertGreater(route.score, 35.0)

    def test_event_notice_drops(self):
        raw = {
            "title": "2026 혁신 포럼 개최 안내",
            "body": "많은 관심 바랍니다.",
            "url": "https://example.com/event",
        }
        route = route_primary(raw)
        self.assertEqual(route.site, "DROP")


class TestPlacement(unittest.TestCase):
    def test_grade_a_can_reach_hero(self):
        packet = {
            "official_evidence_count": 2,
            "key_facts": ["a", "b", "c"],
            "risk_flags": [],
            "image_asset_tier": "official",
            "main_claim": "정책이 바뀐다",
            "why_now": "시행 임박",
        }
        placement = score_placement(
            packet,
            title="소비자 보호 정책 개편, 국민 생활에 미치는 영향은",
            excerpt="정부가 소비자 보호 정책을 개편한다고 발표했다.",
            publish_grade="A",
            thresholds=IJProfile().placement_config(),
        )
        self.assertGreaterEqual(placement.total, 65)
        self.assertIn(placement.slot, ("hero", "secondary_lead", "proof_row"))


class TestMediaPlan(unittest.TestCase):
    def test_editorial_ctx_disables_other_prefixes(self):
        from engine.pipeline.media_plan import build_media_plan_for_editorial
        from engine.types import EditorialContext, PlacementScore

        ctx = EditorialContext(
            assigned_site="IJ",
            routing_reason="test",
            publish_grade="B",
            placement=PlacementScore(total=55, slot="ledger"),
            packet={"site": "IJ", "publish_grade": "B", "risk_flags": []},
            evidence=[],
            use_packet_writing=True,
        )
        plan = build_media_plan_for_editorial(ctx)
        self.assertTrue(plan["IJ_"]["enabled"])
        self.assertFalse(plan["NN_"]["enabled"])
        self.assertFalse(plan["CB_"]["enabled"])

    def test_force_site_cb_keeps_cb_enabled(self):
        from engine.pipeline.media_plan import build_media_plan_for_editorial
        from engine.types import EditorialContext, PlacementScore

        os.environ["EDITORIAL_FORCE_SITE"] = "CB"
        ctx = EditorialContext(
            assigned_site="CB",
            routing_reason="forced",
            publish_grade="B",
            placement=PlacementScore(total=55, slot="ledger"),
            packet={"site": "CB", "publish_grade": "B", "risk_flags": []},
            evidence=[],
            use_packet_writing=True,
        )
        plan = build_media_plan_for_editorial(
            ctx,
            assess_cb_article_fit=lambda _article: ("skip", "weak_signal"),
            article={"title": "x", "body": "y"},
        )
        self.assertTrue(plan["CB_"]["enabled"])
        self.assertEqual(plan["CB_"]["mode"], "forced")
        os.environ.pop("EDITORIAL_FORCE_SITE", None)


class TestOrchestrator(unittest.TestCase):
    def setUp(self):
        os.environ["MIN_SOURCE_BODY_CHARS"] = "150"
        os.environ["EDITORIAL_REQUIRE_FULL_SOURCE"] = "0"

    def test_offline_pipeline_returns_context(self):
        raw = json.loads((FIXTURES / "cached_source.json").read_text(encoding="utf-8"))
        html = (FIXTURES / "policy_with_links.html").read_text(encoding="utf-8")
        article = {
            "url": raw["url"],
            "url_id": "test-id",
            "title": raw["title"],
            "body": raw["body"],
            "raw_html": html,
            "source_type": "policy_briefing",
            "source_published_at": None,
        }
        ctx = run_pre_publish_pipeline(article, fetcher=None, persist=False)
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.assigned_site, "IJ")
        self.assertIn(ctx.publish_grade, ("A", "B", "C"))
        # IJ: 원문 + 리서치 합산 재작성 경로
        self.assertTrue(ctx.use_packet_writing)

    def test_ij_editorial_rewrite_toggle(self):
        os.environ["IJ_PACKET_PIPELINE"] = "1"
        self.assertTrue(should_use_ij_editorial_rewrite("IJ"))
        self.assertFalse(should_use_ij_editorial_rewrite("NN"))
        os.environ["IJ_PACKET_PIPELINE"] = "0"
        self.assertFalse(should_use_ij_editorial_rewrite("IJ"))
        del os.environ["IJ_PACKET_PIPELINE"]

    def test_enrich_raw_source_hash(self):
        article = {"url": "https://www.korea.kr/x", "title": "t", "body": "b"}
        enriched = enrich_raw_source(article)
        self.assertTrue(enriched["source_hash"])


if __name__ == "__main__":
    unittest.main()
