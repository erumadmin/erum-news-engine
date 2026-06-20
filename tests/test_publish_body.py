import unittest
from unittest.mock import patch

from engine.pipeline.publish_body import (
    prepare_cb_publish_body,
    prepare_ij_publish_body,
    prepare_nn_publish_body,
    render_sources_footer_html,
)
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

    def test_publish_ready_without_research_gate_does_not_fail_by_default(self):
        body = (
            "<p>상장사 ESG 담당자는 2027년부터 공시 기준 변경을 반영해야 한다. 준비 일정 조정이 필요하다.</p>"
            "<p>기존에는 항목 해석이 제각각이어서 비교 가능성이 낮았다. 비교 가능성을 높이려는 조치다.</p>"
            "<p>기업은 적용 범위와 제출 시점을 먼저 확인해야 한다. 내부 검증 절차도 점검해야 한다.</p>"
            "<p>다만 세부 지침은 추가 공지에 따라 바뀔 수 있다. 예외 범위도 함께 확인해야 한다.</p>"
        )
        packet = {
            "reader_utility": {"primary_links": [{"url": "https://example.test/cb", "label": "개정안"}]}
        }
        with patch.dict(
            "os.environ",
            {"CB_PUBLISH_V4": "1", "CB_TARGET_ENGINE": "1", "EDITORIAL_FORCE_SITE": "CB"},
            clear=False,
        ):
            gate = article_publish_ready("제목 테스트", "리드", body, packet, article={"url": "https://example.test/cb"}, score_total=9.6)
        self.assertTrue(gate["research_ok"])

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

    def test_prepare_nn_publish_body_footer_class(self):
        body = (
            "<p>청년 창업자는 국공유재산 사용료가 줄어든다. 적용은 2026년부터다.</p>"
            "<p>그동안 임대료 부담이 컸다. 소규모 사업자 지원 목적이다.</p>"
            "<p>신청은 구청 누리집에서 한다. 3월부터 접수한다.</p>"
            "<p>다만 지역·업종별 조건이 다를 수 있다.</p>"
        )
        packet = {
            "risk_flags": [],
            "reader_utility": {
                "primary_links": [{"url": "https://www.korea.kr/x", "label": "정책브리핑"}]
            },
        }
        out = prepare_nn_publish_body("제목", "리드", body, packet, article={"url": "https://korea.kr/x"})
        self.assertIn("nn-sources-footer", out["body_html"])

    def test_prepare_cb_publish_body_footer_class(self):
        body = (
            "<p>상장사 ESG 담당자는 2027년부터 공시 기준 변경을 반영해야 한다.</p>"
            "<p>기존에는 항목 해석이 제각각이어서 비교 가능성이 낮았다.</p>"
            "<p>기업은 적용 범위와 제출 시점을 먼저 확인해야 한다.</p>"
            "<p>다만 세부 지침은 추가 공지에 따라 바뀔 수 있다.</p>"
        )
        packet = {
            "risk_flags": [],
            "reader_utility": {
                "primary_links": [{"url": "https://example.test/cb", "label": "개정안"}]
            },
        }
        out = prepare_cb_publish_body("제목", "리드", body, packet, article={"url": "https://example.test/cb"})
        self.assertIn("cb-sources-footer", out["body_html"])
