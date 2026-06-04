#!/usr/bin/env python3
"""TDD tests for IJ publish-first v4 (ij-news-engine-target-design-v4.md)."""

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline.publish_validate import (
    article_publish_ready,
    body_has_exposed_urls,
    is_publish_v4_enabled,
    publish_sanitize_body,
    validate_publish_article,
)


class TestPublishV4(unittest.TestCase):
    def setUp(self):
        os.environ["IJ_PUBLISH_V4"] = "1"
        os.environ["IJ_TARGET_ENGINE"] = "1"

    def tearDown(self):
        os.environ.pop("IJ_PUBLISH_V4", None)
        os.environ["IJ_TARGET_ENGINE"] = "0"

    def test_v4_enabled_by_default(self):
        os.environ.pop("IJ_PUBLISH_V4", None)
        self.assertTrue(is_publish_v4_enabled())

    def test_body_has_exposed_urls(self):
        self.assertTrue(body_has_exposed_urls("참고: https://www.korea.kr/x"))
        self.assertTrue(body_has_exposed_urls("www.kepco.co.kr 안내"))
        self.assertFalse(body_has_exposed_urls("한전 누리집에서 확인한다."))

    def test_sanitize_strips_urls_to_footer(self):
        body = (
            "<p>정부는 다음 달 1일부터 전기요금 제도를 시행한다. "
            "대상은 일반용(갑)Ⅱ이다.</p>"
            "<p>그동안 시간대별 요금 부담 우려가 있었다.</p>"
            "<p>한전은 고지서에 표기한다. https://online.kepco.co.kr 에서 확인한다.</p>"
            "<p>다만 법적 의무화가 아닌 고지 방식이며 조건을 유의해야 한다.</p>"
        )
        packet = {
            "reader_utility": {
                "primary_links": [{"url": "https://online.kepco.co.kr/", "label": "한전ON"}]
            }
        }
        cleaned, footer = publish_sanitize_body(body, packet)
        plain = cleaned.replace("<p>", "").replace("</p>", " ")
        self.assertFalse(body_has_exposed_urls(plain))
        self.assertTrue(any("kepco" in (f.get("url") or "") for f in footer))

    def test_sanitize_strips_procedural_cta(self):
        body = (
            "<p>정부는 제도를 시행한다. 대상은 일반 국민이다.</p>"
            "<p>그동안 부담 우려가 있었다.</p>"
            "<p>한전은 고지서에 표기한다. "
            '공식 보도에 따르면, "또한 올해 공무원 보수를…" '
            "자세한 절차는 보도자료 원문에서 확인할 수 있다.</p>"
            "<p>다만 시행 범위에 따라 효과가 달라질 수 있다.</p>"
        )
        cleaned, _ = publish_sanitize_body(body, {})
        self.assertNotIn("보도자료 원문", cleaned)
        self.assertNotIn("자세한 절차는", cleaned)
        self.assertNotIn("공식 보도에 따르면", cleaned)

    def test_validate_rejects_incomplete_after_repair(self):
        pad = "적용 대상과 시행 시점은 원문 보도자료를 기준으로 확인한다."
        body = (
            f"<p>정부는 다음 달 1일부터 시행한다. 대상은 일반용(갑)Ⅱ이다. {pad}</p>"
            f"<p>그동안 시간대별 요금 부담 우려가 있었다. 전기위원회 심의를 거쳤다. {pad}</p>"
            f"<p>한전은 고지서에 시간대별·단일 요금을 표기하고 유리한 요금을 자동 적용한다. "
            f"비상근무수당을 일 8000원에서 1만 6000원으로 인상하고 월 지급 상한을</p>"
            f"<p>다만 법적 의무화가 아닌 고지 방식이며 조건과 한계를 유의해야 한다. {pad}</p>"
        )
        ok, msg = validate_publish_article(
            "자영업자 전기요금 선택권 확대",
            "리드",
            body,
            {},
            {"body": "다음 달 1일"},
        )
        self.assertFalse(ok)
        self.assertIn("미완성", msg)

    def test_repair_incomplete_paragraph_drops_fragment(self):
        from engine.pipeline.publish_validate import (
            paragraph_is_complete,
            repair_incomplete_paragraph,
        )

        p = (
            "재난·안전 담당 공무원에 대한 격무·정근 가산금을 각각 월 5만 원 신설했으며, "
            "비상근무수당을 일 8000원에서 1만 6000원으로 인상했다. "
            "재난·안전 담당 공무원에 대한 격무·정근 가산금을 각각 월 5만 원 신설했으며, "
            "비상근무수당을 일 8000원에서 1만 6000원으로, 월 지급"
        )
        repaired = repair_incomplete_paragraph(p)
        self.assertIn("인상했다.", repaired)
        self.assertNotIn("월 지급", repaired)
        self.assertTrue(paragraph_is_complete(repaired))

    def test_sanitize_strips_inline_as_of_date(self):
        body = (
            "<p>정부는 톱티어 비자 제도를 시행한다. 대상은 연구·산업 인력이다.</p>"
            "<p>그동안 해외 인재 유치 경쟁이 치열했다.</p>"
            "<p>과기정통부는 절차를 안내한다.</p>"
            "<p>다만 시행 범위에 따라 효과가 달라질 수 있다. 기준: 2026-06-01.</p>"
        )
        cleaned, _ = publish_sanitize_body(body, {})
        self.assertNotIn("기준:", cleaned)
        self.assertNotIn("2026-06-01", cleaned)

    def test_sanitize_strips_coalition_external_phrases(self):
        body = (
            "<p>연대·대외 안내 시 정부는 톱티어 비자를 시행한다. "
            "파트너·수혜자에게도 영향이 있다.</p>"
            "<p>그동안 인재 유치 경쟁.</p>"
            "<p>과기정통부 안내.</p>"
            "<p>다만 시행 범위에 따라 효과가 달라질 수 있다.</p>"
        )
        cleaned, _ = publish_sanitize_body(body, {})
        self.assertNotIn("연대·대외", cleaned)
        self.assertNotIn("파트너·수혜자", cleaned)

    def test_v4_rewrite_uses_publish_template_not_coalition(self):
        from engine.pipeline.packet_writer import build_rewrite_user_message_from_editorial

        os.environ["IJ_TARGET_ENGINE"] = "1"
        os.environ["IJ_PUBLISH_V4"] = "1"
        packet = {
            "key_facts": ["사실"],
            "journalist_brief": {"lead_question": "Q"},
            "field_takeaways": {"who": "NGO"},
        }
        msg = build_rewrite_user_message_from_editorial(
            {"title": "T", "url": "https://www.korea.kr/x", "body": "본문"},
            packet,
        )
        self.assertNotIn("파트너·수혜자에게 설명", msg)
        self.assertNotIn("연대·보고 관점에서", msg)
        self.assertIn("연대·보고」「연대·대외", msg)
        self.assertIn("4번째 <p>", msg)

    def test_sanitize_removes_coalition_mid_paragraph(self):
        body = (
            "<p>정부는 다음 달 1일부터 시행한다. 연대·보고 관점에서 현장 점검이 필요하다.</p>"
            "<p>그동안 부담 우려.</p><p>한전 고지서.</p><p>다만 조건 유의.</p>"
        )
        cleaned, _ = publish_sanitize_body(body, {})
        self.assertNotIn("연대·보고", cleaned)

    def test_sanitize_does_not_reinject_coalition_lead_line(self):
        pad = "적용 대상과 시행 시점은 원문 보도자료를 기준으로 확인한다."
        body = (
            f"<p>연대·보고 관점에서 앞으로 위생용품 용량을 줄이면 3개월 전에 알린다. {pad}</p>"
            f"<p>그동안 사전 고지 의무가 없어 혼란이 있었다. {pad}</p>"
            f"<p>참가격 누리집에 변경 이력을 공개한다. {pad}</p>"
            f"<p>다만 시행 범위에 따라 효과가 달라질 수 있어 유의해야 한다. {pad}</p>"
        )
        packet = {
            "main_claim": "앞으로 위생용품 용량·개수를 줄이면 3개월 전에 알린다.",
            "field_takeaways": {
                "lead_line": "연대·보고 관점에서 앞으로 위생용품 용량·개수를 줄이면 3개월 전에 알린다."
            },
        }
        cleaned, _ = publish_sanitize_body(body, packet)
        self.assertNotIn("연대·보고", cleaned)

    def test_sanitize_removes_coalition_opener(self):
        body = (
            "<p>연대·보고 관점에서 정부는 다음 달 1일부터 시행한다. "
            "대상은 일반용(갑)Ⅱ 등이다.</p>"
            "<p>그동안 시간대별 요금 부담 우려가 있었다. 전기위원회 심의.</p>"
            "<p>한전은 고지서에 시간대별·단일 요금을 표기하고 자동 적용한다.</p>"
            "<p>다만 시행 범위와 적용 조건에 따라 효과가 달라질 수 있어 유의해야 한다.</p>"
        )
        packet = {"field_takeaways": {"lead_line": "정부는 다음 달 1일부터"}}
        cleaned, _ = publish_sanitize_body(body, packet)
        self.assertNotIn("연대·보고 관점에서", cleaned)

    def test_sanitize_strips_numbered_para_prefix(self):
        body = (
            "<p>정부는 다음 달 1일부터 시행한다. 대상은 일반용(갑)Ⅱ이다.</p>"
            "<p>그동안 부담 우려가 있었다.</p>"
            "<p>3. 단위 사양 축소 정보는 고지서에 표기된다.</p>"
            "<p>다만 조건과 한계를 유의해야 한다.</p>"
        )
        cleaned, _ = publish_sanitize_body(body, {})
        self.assertNotRegex(cleaned, r"3\.\s+단위")

    def test_validate_sanitizes_briefing_opener_before_check(self):
        pad = "적용 대상과 시행 시점은 원문 보도자료를 기준으로 확인한다."
        body = (
            f"<p>연대·보고 관점에서 정부는 다음 달 1일부터 소규모 자영업자 전기요금 제도를 시행한다. {pad}</p>"
            f"<p>그동안 시간대별 요금 부담 우려가 있었다. 전기위원회 심의를 거쳤다. {pad}</p>"
            f"<p>한전은 고지서에 시간대별·단일 요금을 표기하고 유리한 요금을 자동 적용한다. {pad}</p>"
            f"<p>다만 법적 의무화가 아닌 고지 방식이며 조건과 한계를 유의해야 한다. {pad}</p>"
        )
        ok, msg = validate_publish_article(
            "자영업자 전기요금 선택권 확대",
            "리드",
            body,
            {"field_takeaways": {"lead_line": "정부는 다음 달 1일부터"}},
            {"body": "다음 달 1일부터"},
        )
        self.assertTrue(ok, msg)
        plain = body.replace("<p>", "").replace("</p>", " ")
        self.assertIn("연대", plain)

    def test_validate_accepts_clean_publish_body(self):
        pad = "적용 대상과 시행 시점은 원문 보도자료를 기준으로 확인한다."
        body = (
            f"<p>정부는 다음 달 1일부터 소규모 자영업자 전기요금 제도를 시행한다. "
            f"대상은 일반용(갑)Ⅱ 등이다. {pad}</p>"
            f"<p>그동안 시간대별 요금 부담 우려가 있었다. 전기위원회 심의를 거쳤다. {pad}</p>"
            f"<p>한전은 고지서에 시간대별·단일 요금을 각각 표기하고 유리한 요금을 자동 적용한다. {pad}</p>"
            f"<p>다만 법적 의무화가 아닌 고지 방식이며 12월부터 선택한다. "
            f"시행 범위에 따라 효과가 달라질 수 있어 유의해야 한다. {pad}</p>"
        )
        packet = {
            "key_facts": ["다음 달 1일", "전기위원회"],
            "field_takeaways": {"lead_line": "정부는 다음 달 1일부터"},
            "research_gate": {"research_depth": 8.0, "research_insufficient": False},
            "discovered_facts": [{"fact": "한전ON에서 요금 비교 시뮬레이션을 제공한다." * 2}],
        }
        ok, msg = validate_publish_article(
            "자영업자 전기요금 선택권 확대",
            "리드",
            body,
            packet,
            {"body": "다음 달 1일부터 시행한다. 전기위원회. 11월. 12월."},
        )
        self.assertTrue(ok, msg)

    def test_para1_lead_v4_uses_anchor_not_strict_prefix(self):
        from engine.pipeline.rewrite_validate import validate_para1_lead

        lead = "해외 진출 기업의 국내 복귀(유턴) 지원 문턱을 낮춘다."
        packet = {
            "main_claim": lead,
            "field_takeaways": {"lead_line": lead},
        }
        pad = "적용 대상과 시행 시점은 원문 보도자료를 기준으로 확인한다."
        paras = [
            f"중소벤처기업부는 {lead} 관련 제도를 추진한다. {pad}",
            f"그동안 복귀 절차가 복잡했다. {pad}",
            f"지자체와 연계해 지원한다. {pad}",
            f"다만 시행 범위에 따라 효과가 달라질 수 있어 유의해야 한다. {pad}",
        ]
        ok, msg = validate_para1_lead(paras, packet, None)
        self.assertTrue(ok, msg)

    def test_validate_rejects_generic_limitation_boilerplate(self):
        pad = "적용 대상과 시행 시점은 원문 보도자료를 기준으로 확인한다."
        from engine.pipeline.rewrite_validate import DEFAULT_LIMITATION_SENTENCE

        body = (
            f"<p>정부는 다음 달 1일부터 소규모 자영업자 전기요금 제도를 시행한다. "
            f"대상은 일반용(갑)Ⅱ 등이다. {pad}</p>"
            f"<p>그동안 시간대별 요금 부담 우려가 있었다. 전기위원회 심의를 거쳤다. {pad}</p>"
            f"<p>한전은 고지서에 시간대별·단일 요금을 표기한다. {pad}</p>"
            f"<p>{DEFAULT_LIMITATION_SENTENCE} "
            f"보도·안내 내용은 2026-06-01 기준 공식 보도자료를 참고한다. {pad}</p>"
        )
        packet = {"field_takeaways": {"lead_line": "정부는 다음 달 1일부터"}}
        article = {"body": "다음 달 1일부터. 전기위원회. 11월. 12월."}
        cleaned, _ = publish_sanitize_body(body, packet, article)
        plain = cleaned.replace("<p>", "").replace("</p>", " ")
        self.assertNotIn("시행 범위·적용 조건", plain)
        self.assertNotIn("보도·안내 내용은", plain)
        ok, msg = validate_publish_article(
            "자영업자 전기요금 선택권 확대",
            "리드",
            body,
            packet,
            article,
        )
        self.assertFalse(ok)

    def test_finalize_v4_strips_boilerplate_from_para4(self):
        from engine.pipeline.rewrite_validate import (
            DEFAULT_LIMITATION_SENTENCE,
            finalize_ij_editorial_body,
            _paragraph_plain_blocks,
        )

        pad = "적용 대상과 시행 시점은 원문 보도자료를 기준으로 확인한다."
        body = (
            f"<p>정부는 다음 달 1일부터 소규모 자영업자 전기요금 제도를 시행한다. {pad}</p>"
            f"<p>그동안 시간대별 요금 부담 우려. 전기위원회 심의. {pad}</p>"
            f"<p>한전은 고지서에 표기한다. {pad}</p>"
            f"<p>{DEFAULT_LIMITATION_SENTENCE} "
            f"보도·안내 내용은 2026-06-01 기준 공식 보도자료를 참고한다. {pad}</p>"
        )
        packet = {
            "main_claim": "정부는 다음 달 1일부터",
            "field_takeaways": {"lead_line": "정부는 다음 달 1일부터"},
            "reader_utility": {"as_of_date": "2026-06-01"},
            "journalist_brief": {
                "coalition_gaps": [
                    "6개월 비교 기간에는 별도 신청 없이 낮은 요금이 자동 적용된다."
                ],
            },
            "research_gate": {"research_depth": 8.0, "research_insufficient": False},
        }
        article = {"body": "다음 달 1일부터. 전기위원회. 11월. 12월. 고지서."}
        out = finalize_ij_editorial_body(body, packet, article)
        p4 = _paragraph_plain_blocks(out)[3]
        self.assertNotIn("시행 범위·적용 조건", p4)
        self.assertNotIn("보도·안내 내용은", p4)

    def test_build_v4_limitation_from_key_facts(self):
        from engine.pipeline.rewrite_validate import (
            build_v4_limitation_from_packet,
            validate_limitation_paragraph,
        )

        packet = {
            "key_facts": ["올해 중 유턴법 법령 정비 후 내년 본격 시행 예정이다."],
            "journalist_brief": {"coalition_gaps": []},
        }
        lim = build_v4_limitation_from_packet(packet, "한전은 고지서에 표기한다.")
        self.assertTrue(lim.startswith("다만"))
        self.assertNotIn("시행 범위·적용 조건", lim)
        ok, _ = validate_limitation_paragraph(lim, "한전은 고지서에 표기한다.")
        self.assertTrue(ok)

    def test_build_v4_limitation_evidence_missing_fallback(self):
        from engine.pipeline.rewrite_validate import (
            build_v4_limitation_from_packet,
            is_publish_boilerplate_para4,
        )

        lim = build_v4_limitation_from_packet(
            {"risk_flags": ["official_evidence_missing"], "key_facts": []},
            "조치 내용.",
        )
        self.assertTrue(lim.startswith("다만"))
        self.assertFalse(is_publish_boilerplate_para4(lim))

    def test_ensure_valid_limitation_v4_uses_stripped_caution(self):
        from engine.pipeline.rewrite_validate import (
            ensure_valid_limitation_paragraph,
            _paragraph_plain_blocks,
        )

        body = (
            "<p>정부는 다음 달 1일부터 시행한다. 대상은 일반용(갑)Ⅱ 등이다. "
            "적용 대상과 시행 시점은 원문 보도자료를 기준으로 확인한다.</p>"
            "<p>그동안 시간대별 요금 부담 우려가 있었다. 전기위원회 심의를 거쳤다.</p>"
            "<p>한전은 고지서에 표기한다. 적용 대상과 시행 시점은 원문 보도자료를 기준으로 확인한다.</p>"
            "<p>다만 정책 확장만 언급한다.</p>"
        )
        packet = {
            "field_takeaways": {
                "caution_line": (
                    "연대·대외 안내 시 6개월 비교 기간에는 별도 신청 없이 "
                    "낮은 요금이 자동 적용된다는 점을 유의해야 한다."
                ),
            },
            "journalist_brief": {"coalition_gaps": []},
        }
        out = ensure_valid_limitation_paragraph(body, packet)
        p4 = _paragraph_plain_blocks(out)[3]
        self.assertIn("자동 적용", p4)
        self.assertNotIn("연대·대외", p4)

    def test_irrelevant_evidence_quote_filtered(self):
        from engine.pipeline.reader_utility import is_irrelevant_evidence_snippet

        self.assertTrue(
            is_irrelevant_evidence_snippet(
                "보다 안정적인 서비스 제공을 위해 시스템 점검이 진행중이며 "
                "서비스 문의는 홈페이지 담당자에게 연락"
            )
        )
        self.assertFalse(
            is_irrelevant_evidence_snippet(
                "톱티어 비자는 연구 성과와 국내 유치 필요성을 종합 검토한다."
            )
        )

    def test_ensure_valid_limitation_no_default_in_v4(self):
        from engine.pipeline.rewrite_validate import (
            DEFAULT_LIMITATION_SENTENCE,
            ensure_valid_limitation_paragraph,
            _paragraph_plain_blocks,
        )

        body = (
            "<p>리드 문장이 충분히 길어야 한다. 적용 대상은 원문 보도자료 기준.</p>"
            "<p>배경 설명도 충분히 길어야 한다. 전기위원회 심의를 거쳤다.</p>"
            "<p>조치 내용도 충분히 길어야 한다. 한전 고지서에 표기한다.</p>"
            "<p>다만 정책 확장만 언급한다.</p>"
        )
        out = ensure_valid_limitation_paragraph(body, {})
        p4 = _paragraph_plain_blocks(out)[3]
        self.assertNotEqual(p4.strip(), DEFAULT_LIMITATION_SENTENCE.strip())
        self.assertNotIn("시행 범위·적용 조건", p4)

    def test_fix_ij_llm_body_markup_flattens_and_denews(self):
        from engine.pipeline.rewrite_validate import fix_ij_llm_body_markup

        body = (
            "<p><p>정부는 추진합니다.</p></p>"
            "<p>배경 설명입니다.</p>"
            "<p>조치 내용…</p>"
            "<p>다만 조건을 유의합니다.</p>"
        )
        fixed = fix_ij_llm_body_markup(body)
        self.assertNotRegex(fixed, r"<p[^>]*>\s*<p")
        self.assertNotIn("습니다", fixed)
        self.assertNotIn("…", fixed)

    def test_should_retry_includes_para4_limitation_msg(self):
        src = (ROOT / "engine.py").read_text(encoding="utf-8")
        self.assertIn('"4문단 한계"', src)
        self.assertIn('"한계·유의 부족"', src)

    def test_article_publish_ready_requires_score(self):
        body = (
            "<p>정부는 다음 달 1일부터 시행한다. 대상은 일반용(갑)Ⅱ이다.</p>"
            "<p>그동안 부담 우려.</p>"
            "<p>한전 고지서 표기.</p>"
            "<p>다만 조건 유의.</p>"
        )
        packet = {"research_gate": {"research_depth": 8.0, "research_insufficient": False}}
        result = article_publish_ready(
            "제목",
            "리드",
            body,
            packet,
            {"body": "다음 달 1일부터. 전기위원회. 11월. 12월. 고지서."},
            score_total=9.6,
        )
        self.assertIn("article_publish_ready", result)
        self.assertIn("publish_validation", result)


if __name__ == "__main__":
    unittest.main()
