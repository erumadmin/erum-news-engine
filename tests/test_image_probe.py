"""Tests for non-blocking image probe."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from engine.pipeline.image_probe import probe_article_images


class TestImageProbe(unittest.TestCase):
    def test_no_candidates(self):
        mock_eng = MagicMock(find_best_image=MagicMock(return_value=[]))
        with patch("engine.pipeline.image_probe._engine_main", return_value=mock_eng):
            out = probe_article_images({"url": "https://example.com", "body": ""})
        self.assertEqual(out["status"], "no_candidates")
        self.assertEqual(out["code"], "NO_USABLE_IMAGE")

    def test_candidates_ok_without_download(self):
        cand = MagicMock(url="https://cdn.example/a.jpg", caption="cap", source="rss:media", score=100)
        mock_eng = MagicMock(find_best_image=MagicMock(return_value=[cand]))
        with patch("engine.pipeline.image_probe._engine_main", return_value=mock_eng):
            out = probe_article_images({"url": "https://example.com"}, download=False)
        self.assertEqual(out["status"], "candidates_ok")
        self.assertEqual(out["selected_url"], "https://cdn.example/a.jpg")
        self.assertFalse(out["download_ok"])

    def test_pipeline_failure_soft(self):
        class PipelineFailure(Exception):
            def __init__(self, stage, code, message, retryable=False):
                self.code = code
                self.message = message

        mock_eng = MagicMock()
        mock_eng.PipelineFailure = PipelineFailure
        mock_eng.find_best_image = MagicMock(
            side_effect=PipelineFailure("image", "SOURCE_FETCH_HTTP_5XX", "fail")
        )
        with patch("engine.pipeline.image_probe._engine_main", return_value=mock_eng):
            out = probe_article_images({"url": "https://example.com"})
        self.assertEqual(out["status"], "error")
        self.assertEqual(out["code"], "SOURCE_FETCH_HTTP_5XX")


if __name__ == "__main__":
    unittest.main()
