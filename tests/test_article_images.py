"""Tests for article_images module."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from engine.pipeline import article_images as ai
from engine.pipeline.exceptions import PipelineFailure


class TestArticleImages(unittest.TestCase):
    def test_uses_raw_html_when_present(self):
        """raw_html with og:image should skip live page fetch."""
        html = (
            '<html><head>'
            '<meta property="og:image" content="https://cdn.example/hero.jpg"/>'
            '</head></html>'
        )
        article = {
            "url": "https://example.com/article/1",
            "body": "",
            "raw_html": html,
        }
        mock_fetch = MagicMock()
        with patch.object(ai, "fetch_with_retry", mock_fetch):
            candidates = ai.find_best_image(article)
        mock_fetch.assert_not_called()
        self.assertTrue(candidates)
        self.assertEqual(candidates[0].url, "https://cdn.example/hero.jpg")

    def test_require_raises_no_candidates(self):
        article = {"url": "https://example.com", "body": "", "image": ""}
        with patch.object(ai, "find_best_image", return_value=[]):
            with self.assertRaises(ai.PipelineFailure) as ctx:
                ai.require_article_image(article)
        self.assertEqual(ctx.exception.code, "NO_USABLE_IMAGE")

    def test_require_returns_bytes_on_success(self):
        cand = ai.ImageCandidate(
            url="https://cdn.example/a.jpg",
            caption="cap",
            source="page:meta",
            score=95,
        )
        big_bytes = b"x" * ai.MIN_IMAGE_BYTES
        with patch.object(ai, "find_best_image", return_value=[cand]):
            with patch.object(
                ai,
                "download_best_image",
                return_value=(big_bytes, "image/jpeg", "a.jpg", "cap", cand.url),
            ):
                result = ai.require_article_image(article={"url": "https://example.com"})
        self.assertEqual(result["image_status"], "download_ok")
        self.assertEqual(result["img_bytes"], big_bytes)
        self.assertEqual(result["selected_url"], cand.url)

    def test_require_raises_quality_too_low(self):
        cand = ai.ImageCandidate(
            url="https://cdn.example/low.jpg",
            caption=None,
            source="page:meta",
            score=95,
        )
        failure = PipelineFailure(
            "image", "IMAGE_QUALITY_TOO_LOW", "대표이미지 품질 미달", retryable=False
        )
        with patch.object(ai, "find_best_image", return_value=[cand]):
            with patch.object(ai, "download_best_image", side_effect=failure):
                with self.assertRaises(PipelineFailure) as ctx:
                    ai.require_article_image(article={"url": "https://example.com"})
        self.assertEqual(ctx.exception.code, "IMAGE_QUALITY_TOO_LOW")

    def test_require_download_false_returns_candidates(self):
        cand = ai.ImageCandidate(
            url="https://cdn.example/a.jpg",
            caption="cap",
            source="page:meta",
            score=90,
        )
        with patch.object(ai, "find_best_image", return_value=[cand]):
            result = ai.require_article_image(
                article={"url": "https://example.com"}, download=False
            )
        self.assertEqual(result["image_status"], "candidates_ok")
        self.assertIsNone(result["img_bytes"])
        self.assertEqual(result["selected_url"], cand.url)

    def test_find_best_image_uses_raw_html_before_fetch(self):
        html = (
            '<html><head>'
            '<meta property="og:image" content="https://cdn.example/hero-hq.jpg"/>'
            '</head><body></body></html>'
        )
        article = {
            "url": "https://example.com/article/2",
            "body": "",
            "raw_html": html,
        }
        mock_fetch = MagicMock()
        with patch.object(ai, "fetch_with_retry", mock_fetch):
            candidates = ai.find_best_image(article)
        mock_fetch.assert_not_called()
        self.assertTrue(any(c.url == "https://cdn.example/hero-hq.jpg" for c in candidates))


if __name__ == "__main__":
    unittest.main()
