"""Tests for non-blocking image probe."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from engine.pipeline.image_probe import probe_article_images


class TestImageProbe(unittest.TestCase):
    def test_no_candidates(self):
        with patch(
            "engine.pipeline.image_probe.require_article_image",
            side_effect=type(
                "PipelineFailure",
                (Exception,),
                {"code": "NO_USABLE_IMAGE", "message": "이미지 후보 없음"},
            )("image", "NO_USABLE_IMAGE", "이미지 후보 없음"),
        ):
            out = probe_article_images({"url": "https://example.com", "body": ""})
        self.assertEqual(out["status"], "download_failed")
        self.assertEqual(out["code"], "NO_USABLE_IMAGE")

    def test_candidates_ok_without_download(self):
        with patch(
            "engine.pipeline.image_probe.require_article_image",
            return_value={
                "img_bytes": None,
                "content_type": None,
                "filename": None,
                "caption": "cap",
                "selected_url": "https://cdn.example/a.jpg",
                "image_status": "candidates_ok",
            },
        ):
            out = probe_article_images({"url": "https://example.com"}, download=False)
        self.assertEqual(out["status"], "candidates_ok")
        self.assertEqual(out["selected_url"], "https://cdn.example/a.jpg")
        self.assertFalse(out["download_ok"])

    def test_pipeline_failure_soft(self):
        with patch(
            "engine.pipeline.image_probe.require_article_image",
            side_effect=type(
                "PipelineFailure",
                (Exception,),
                {"code": "SOURCE_FETCH_HTTP_5XX", "message": "fail"},
            )("image", "SOURCE_FETCH_HTTP_5XX", "fail"),
        ):
            out = probe_article_images({"url": "https://example.com"})
        self.assertEqual(out["status"], "error")
        self.assertEqual(out["code"], "SOURCE_FETCH_HTTP_5XX")


if __name__ == "__main__":
    unittest.main()
