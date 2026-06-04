"""Tests for publish_preflight manifest."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from engine.pipeline.publish_preflight import build_publish_preflight


class TestPublishPreflight(unittest.TestCase):
    def test_review_mode_blocks_api_but_text_ready(self):
        ctx = SimpleNamespace(placement=SimpleNamespace(slot="ledger"), publish_grade="C", assigned_site="IJ")
        score = {"passes": True, "article_publish_ready": True, "total": 10.0}
        variant = {"status": "SUCCESS", "title": "t", "body": "<p>x</p>"}
        probe = {"status": "candidates_ok", "selected_url": "https://img/x.jpg"}
        pf = build_publish_preflight(
            variant=variant,
            article={},
            editorial_ctx=ctx,
            image_probe=probe,
            score=score,
            review_mode=True,
        )
        self.assertTrue(pf["text_publish_ready"])
        self.assertTrue(pf["would_publish_api"])
        self.assertIn("REVIEW_ONLY", pf["blocked_reasons"])

    def test_text_gate_blocks(self):
        pf = build_publish_preflight(
            variant={"status": "FAILED"},
            article={},
            editorial_ctx=None,
            image_probe=None,
            score={"passes": False},
            review_mode=True,
        )
        self.assertFalse(pf["text_publish_ready"])
        self.assertFalse(pf["would_publish_api"])
        self.assertIn("TEXT_GATE", pf["blocked_reasons"])


if __name__ == "__main__":
    unittest.main()
