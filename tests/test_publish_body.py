import unittest
from unittest.mock import patch

from engine.pipeline.publish_body import prepare_ij_publish_body, render_sources_footer_html
from engine.pipeline.publish_validate import article_publish_ready, publish_sanitize_body


class TestPublishBody(unittest.TestCase):
    def test_render_sources_footer_html(self):
        footer = [{"url": "https://www.korea.kr/x", "label": "정책브리핑"}]
        html = render_sources_footer_html(footer)
        self.assertIn("관련 링크", html)
        self.assertIn("https://www.korea.kr/x", html)
        self.assertNotIn("https://", html.split("관련 링크")[0])  # URLs only in footer section

    def test_render_sources_footer_empty_is_blank(self):
        # No links → no empty footer section emitted.
        self.assertEqual(render_sources_footer_html([]).strip(), "")

    def test_render_sources_footer_escapes_html(self):
        footer = [
            {
                "url": 'https://example.com/?a=1&b="x"',
                "label": '<img onerror="alert(1)">',
            }
        ]
        html = render_sources_footer_html(footer)
        self.assertNotIn("<img onerror", html)
        self.assertIn("&lt;img onerror", html)
        self.assertIn("&amp;b=", html)

    def test_footer_appended_and_no_urls_in_paragraphs(self):
        # Behaviour we can assert WITHOUT depending on the gate verdict:
        # exposed URLs get moved out of paragraphs and into the footer block.
        packet = {
            "reader_utility": {
                "primary_links": [{"url": "https://online.kepco.co.kr/", "label": "한전ON"}]
            }
        }
        body = "<p>본문 문단 하나.</p><p>본문 문단 둘.</p><p>본문 문단 셋.</p><p>본문 문단 넷.</p>"
        out = prepare_ij_publish_body("제목", "리드", body, packet, article={})
        self.assertIn("관련 링크", out["body_html"])
        # any URL appears only after the footer marker, never in the prose above it
        head = out["body_html"].split("관련 링크")[0]
        self.assertNotIn("https://", head)

    def test_publish_ready_mirrors_gate(self):
        # prepare_ij_publish_body MUST NOT invent its own verdict; it delegates
        # to article_publish_ready so the live publish gate stays single-source.
        packet = {"reader_utility": {"primary_links": []}}
        body = "<p>본문 문단 하나.</p><p>본문 문단 둘.</p><p>본문 문단 셋.</p><p>본문 문단 넷.</p>"
        out = prepare_ij_publish_body("제목", "리드", body, packet, article={})
        sanitized, _ = publish_sanitize_body(body, packet, article={})
        gate = article_publish_ready("제목", "리드", sanitized, packet, article={})
        self.assertEqual(out["publish_ready"], gate["article_publish_ready"])

    @patch("engine.pipeline.publish_body.article_publish_ready")
    def test_publish_ready_false_when_gate_fails(self, mock_ready):
        mock_ready.return_value = {
            "article_publish_ready": False,
            "publish_validation": {"ok": False, "message": "test failure"},
        }
        body = "<p>본문 문단 하나.</p><p>본문 문단 둘.</p><p>본문 문단 셋.</p><p>본문 문단 넷.</p>"
        packet = {"reader_utility": {"primary_links": []}}
        out = prepare_ij_publish_body("제목", "리드", body, packet, article={})
        self.assertFalse(out["publish_ready"])
        self.assertFalse(out["gate"]["article_publish_ready"])
        mock_ready.assert_called_once()
        sanitized, _ = publish_sanitize_body(body, packet, article={})
        self.assertEqual(mock_ready.call_args[0][2], sanitized)
