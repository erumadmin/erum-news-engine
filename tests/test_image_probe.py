"""Tests for non-blocking image probe."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from engine.pipeline.article_images import ImageCandidate, PipelineFailure
from engine.pipeline.image_probe import probe_article_images


class TestImageProbe(unittest.TestCase):
    def test_no_candidates(self):
        with patch("engine.pipeline.image_probe.find_best_image", return_value=[]):
            out = probe_article_images({"url": "https://example.com", "body": ""})
        self.assertEqual(out["status"], "no_candidates")
        self.assertEqual(out["code"], "NO_USABLE_IMAGE")
        self.assertEqual(out["candidates"], [])

    def test_candidates_ok_without_download(self):
        cand = ImageCandidate(
            url="https://cdn.example/a.jpg",
            caption="cap",
            source="rss:media",
            score=100,
        )
        with patch("engine.pipeline.image_probe.find_best_image", return_value=[cand]):
            out = probe_article_images({"url": "https://example.com"}, download=False)
        self.assertEqual(out["status"], "candidates_ok")
        self.assertEqual(out["selected_url"], "https://cdn.example/a.jpg")
        self.assertEqual(out["selected_source"], "rss:media")
        self.assertEqual(len(out["candidates"]), 1)
        self.assertFalse(out["download_ok"])

    def test_pipeline_failure_soft(self):
        failure = PipelineFailure("image", "SOURCE_FETCH_HTTP_5XX", "fail", retryable=True)
        with patch("engine.pipeline.image_probe.find_best_image", side_effect=failure):
            out = probe_article_images({"url": "https://example.com"})
        self.assertEqual(out["status"], "error")
        self.assertEqual(out["code"], "SOURCE_FETCH_HTTP_5XX")


if __name__ == "__main__":
    unittest.main()
