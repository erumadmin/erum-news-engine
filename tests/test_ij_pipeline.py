"""Tests for IJ editorial pipeline — image gate before research."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline import article_images as ai
from engine.pipeline.ij_pipeline import run_ij_editorial_stages
from engine.types import CandidateDecision, PlacementScore, RouteScore


def _enriched_article():
    return {
        "url": "https://www.korea.kr/article/1",
        "title": "정책 개편 안내",
        "body": "정부는 소비자 보호 정책을 개편한다. " * 20,
        "raw_html": "<p>body</p>",
    }


def _mock_profile():
    profile = MagicMock()
    profile.candidate_filter.return_value = CandidateDecision(accept=True, reason="ok")
    profile.collect_evidence_plan.return_value = {"max_fetch": 3}
    profile.placement_config.return_value = {}
    return profile


class TestIjPipelineOrder(unittest.TestCase):
    @patch("engine.pipeline.ij_pipeline.score_placement")
    @patch("engine.pipeline.ij_pipeline.rc.run_research_pipeline")
    @patch("engine.pipeline.ij_pipeline.require_article_image")
    @patch("engine.pipeline.ij_pipeline.get_profile")
    @patch("engine.pipeline.ij_pipeline.route_primary")
    @patch("engine.pipeline.ij_pipeline.enrich_article_from_page")
    def test_image_failure_skips_research(
        self,
        mock_enrich,
        mock_route,
        mock_get_profile,
        mock_require_image,
        mock_research,
        mock_placement,
    ):
        enriched = _enriched_article()
        mock_enrich.return_value = (True, dict(enriched), "cached")
        mock_route.return_value = RouteScore(site="IJ", score=60.0, reason="policy")
        mock_get_profile.return_value = _mock_profile()
        mock_require_image.side_effect = ai.PipelineFailure(
            "image", "NO_USABLE_IMAGE", "이미지 후보 없음", retryable=False
        )

        article = dict(enriched)
        result = run_ij_editorial_stages(article, fetcher=None)

        self.assertIsNone(result)
        mock_research.assert_not_called()
        self.assertEqual(article.get("_skip_reason"), "NO_USABLE_IMAGE")
        self.assertEqual(article.get("_skip_image_status"), "NO_USABLE_IMAGE")
        self.assertNotIn("_ij_img_result", article)

    @patch("engine.pipeline.ij_pipeline.score_placement")
    @patch("engine.pipeline.ij_pipeline.rc.run_research_pipeline")
    @patch("engine.pipeline.ij_pipeline.require_article_image")
    @patch("engine.pipeline.ij_pipeline.get_profile")
    @patch("engine.pipeline.ij_pipeline.route_primary")
    @patch("engine.pipeline.ij_pipeline.enrich_article_from_page")
    def test_image_success_runs_research(
        self,
        mock_enrich,
        mock_route,
        mock_get_profile,
        mock_require_image,
        mock_research,
        mock_placement,
    ):
        enriched = _enriched_article()
        mock_enrich.return_value = (True, dict(enriched), "cached")
        mock_route.return_value = RouteScore(site="IJ", score=60.0, reason="policy")
        mock_get_profile.return_value = _mock_profile()
        img_result = {
            "img_bytes": b"x" * 12000,
            "content_type": "image/jpeg",
            "filename": "hero.jpg",
            "caption": "cap",
            "selected_url": "https://cdn.example/hero.jpg",
            "image_status": "download_ok",
        }
        mock_require_image.return_value = img_result
        mock_research.return_value = {
            "packet": {
                "publish_grade": "B",
                "placement_hint": {},
                "site": "IJ",
                "risk_flags": [],
            },
            "evidence": [],
        }
        mock_placement.return_value = PlacementScore(total=55, slot="ledger")

        article = dict(enriched)
        result = run_ij_editorial_stages(article, fetcher=None)

        self.assertIsNotNone(result)
        mock_research.assert_called_once()
        mock_require_image.assert_called_once()
        self.assertEqual(article.get("_ij_img_result"), img_result)
        self.assertEqual(result.assigned_site, "IJ")

    @patch("engine.pipeline.ij_pipeline.score_placement")
    @patch("engine.pipeline.ij_pipeline.rc.run_research_pipeline")
    @patch("engine.pipeline.ij_pipeline.require_article_image")
    @patch("engine.pipeline.ij_pipeline.get_profile")
    @patch("engine.pipeline.ij_pipeline.route_primary")
    @patch("engine.pipeline.ij_pipeline.enrich_article_from_page")
    def test_nn_skips_image_gate(
        self,
        mock_enrich,
        mock_route,
        mock_get_profile,
        mock_require_image,
        mock_research,
        mock_placement,
    ):
        enriched = _enriched_article()
        mock_enrich.return_value = (True, dict(enriched), "cached")
        mock_route.return_value = RouteScore(site="NN", score=50.0, reason="news")
        mock_get_profile.return_value = _mock_profile()
        mock_research.return_value = {
            "packet": {"publish_grade": "B", "placement_hint": {}, "risk_flags": []},
            "evidence": [],
        }
        mock_placement.return_value = PlacementScore(total=40, slot="ledger")

        article = dict(enriched)
        result = run_ij_editorial_stages(article, fetcher=None)

        self.assertIsNotNone(result)
        mock_require_image.assert_not_called()
        mock_research.assert_called_once()
        self.assertNotIn("_ij_img_result", article)


if __name__ == "__main__":
    unittest.main()
