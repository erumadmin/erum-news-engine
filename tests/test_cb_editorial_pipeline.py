"""Tests for CSR Briefing editorial pipeline (packet rewrite + compliance validation)."""

from __future__ import annotations

import os
import unittest

from engine.pipeline.cb_packet_writer import build_compliance_brief, build_rewrite_user_message_for_cb
from engine.pipeline.cb_rewrite_validate import (
    finalize_cb_editorial_body,
    validate_cb_editorial_rewrite,
    validate_cb_paragraph_roles,
)
from engine.pipeline.cb_scorecard import score_cb_editorial_rewrite


class TestCBPacketWriter(unittest.TestCase):
    def test_cb_packet_toggle_off_by_default(self):
        from engine.pipeline.orchestrator import should_use_cb_editorial_rewrite

        os.environ.pop("CB_PACKET_PIPELINE", None)
        self.assertFalse(should_use_cb_editorial_rewrite("CB"))

    def test_cb_packet_toggle_on(self):
        from engine.pipeline.orchestrator import (
            should_use_cb_editorial_rewrite,
            should_use_packet_editorial_rewrite,
        )

        os.environ["CB_PACKET_PIPELINE"] = "1"
        self.assertTrue(should_use_cb_editorial_rewrite("CB"))
        self.assertTrue(should_use_packet_editorial_rewrite("CB"))
        os.environ.pop("CB_PACKET_PIPELINE", None)

    def test_rewrite_message_contains_compliance_axes(self):
        os.environ["CB_TARGET_ENGINE"] = "1"
        article = {
            "title": "온실가스 배출 공시 기준 개편",
            "url": "https://example.test/cb-1",
            "body": "상장사는 2027년부터 온실가스 배출 공시 기준 변경 사항을 반영해야 한다.",
        }
        packet = {
            "who_is_affected": ["상장사 ESG 담당자", "협력사 실무자"],
            "main_claim": "온실가스 공시 기준이 바뀐다",
            "publish_grade": "B",
            "conditions": ["2027년부터", "상장사 적용"],
            "action_items": ["공시 기준 개정안을 확인한다"],
            "reader_utility": {},
            "compliance_brief": {
                "who_affected": ["상장사 ESG 담당자"],
                "business_change": "공시 기준이 바뀐다",
                "check_items": ["개정안 확인", "적용 범위 검토"],
                "remaining_limits": ["세부 지침 추가 공지 예정"],
            },
        }
        msg = build_rewrite_user_message_for_cb(article, packet, [])
        self.assertIn("CSR 브리핑", msg)
        self.assertIn("기업 실무", msg)
        self.assertIn("compliance_brief", msg)
        os.environ.pop("CB_TARGET_ENGINE", None)

    def test_build_compliance_brief_filters_caption_noise(self):
        packet = {
            "_raw_source": {
                "title": "해외 진출 기업, '유턴' 문턱 낮춰 국내 복귀·지방 투자 유도",
                "body": (
                    "정부는 유턴 인정기준을 완화하고 보조금 지원체계를 개편한다. "
                    "올해 중 법령 정비를 마치고 내년부터 시행할 계획이다."
                ),
            },
            "who_is_affected": ["기업", "중소벤처"],
            "main_claim": "산업통상부는 29일 열린 경제관계장관회의에서 대책을 발표했다.",
            "conditions": [
                "김정관 산업통상부 장관이 현장 간담회를 주재하고 있다. 사진은 기사와 관련 없음. (산업통상부 제공) 2026.4.27. (ⓒ뉴스1, 무단 전재-재배포 금지)",
                "올해 중 법령 정비를 마치고 내년부터 시행할 계획이다.",
            ],
            "action_items": [],
            "key_facts": [
                "정부는 유턴 인정기준을 완화하고 보조금 지원체계를 개편한다.",
            ],
        }
        brief = build_compliance_brief(packet)
        self.assertEqual(brief["who_affected"], ["해외 진출 기업"])
        self.assertIn("유턴 인정기준을 완화", brief["business_change"])
        self.assertNotIn("사진은 기사와 관련 없음", " ".join(brief["check_items"] + brief["remaining_limits"]))


class TestCBRewriteValidate(unittest.TestCase):
    def _sample_body(self):
        return (
            "<p>상장사 ESG 담당자는 2027년부터 온실가스 배출 공시 기준 변경 사항을 반영해야 한다. "
            "공시 범위와 산정 기준이 달라져 준비 일정 조정이 필요하다.</p>"
            "<p>이번 개편은 기존 공시 항목이 기업별로 달리 해석되던 문제를 줄이기 위한 조치다. "
            "감독 당국은 비교 가능성과 검증 가능성을 높이겠다는 입장을 밝혔다.</p>"
            "<p>기업은 개정안의 적용 범위와 제출 시점을 먼저 확인해야 한다. "
            "협력사 데이터 수집 체계와 내부 검증 절차도 함께 점검할 필요가 있다.</p>"
            "<p>다만 세부 산정 예시와 일부 업종별 기준은 추가 공지로 보완될 예정이어서, "
            "최종 시행 전까지 예외 범위와 유예 여부를 계속 확인해야 한다.</p>"
        )

    def test_paragraph_roles_ok(self):
        from engine.pipeline.rewrite_validate import _paragraph_plain_blocks

        paras = _paragraph_plain_blocks(self._sample_body())
        ok, msg = validate_cb_paragraph_roles(paras)
        self.assertTrue(ok, msg)

    def test_finalize_and_validate(self):
        os.environ["CB_PUBLISH_V4"] = "1"
        article = {
            "body": "상장사 공시 기준 2027년 적용 범위 제출 시점 예외 업종",
        }
        packet = {
            "who_is_affected": ["상장사 ESG 담당자", "협력사 실무자"],
            "main_claim": "상장사는 2027년부터 온실가스 배출 공시 기준 변경 사항을 반영해야 한다",
            "conditions": ["2027년부터", "상장사 적용", "일부 업종 추가 지침 예정"],
            "action_items": ["개정안 확인", "내부 검증 절차 점검"],
            "reader_utility": {},
            "risk_flags": [],
            "compliance_brief": {
                "who_affected": ["상장사 ESG 담당자"],
                "business_change": "공시 기준이 바뀐다",
                "check_items": ["개정안 확인", "검증 절차 점검"],
                "remaining_limits": ["세부 산정 예시 추가 공지 예정"],
            },
        }
        body = finalize_cb_editorial_body(self._sample_body(), packet, article)
        ok, msg = validate_cb_editorial_rewrite(
            "상장사 온실가스 공시 기준 개편",
            body,
            packet,
            article,
        )
        self.assertTrue(ok, msg)
        os.environ.pop("CB_PUBLISH_V4", None)

    def test_finalize_repairs_non_business_lead(self):
        article = {
            "body": "상장사 ESG 담당자는 2027년부터 온실가스 공시 기준 변경을 반영해야 한다",
        }
        packet = {
            "who_is_affected": ["상장사 ESG 담당자"],
            "main_claim": "2027년부터 온실가스 공시 기준 변경을 반영해야 한다",
            "conditions": ["2027년부터", "상장사 적용"],
            "action_items": ["개정안 확인"],
            "reader_utility": {},
            "risk_flags": [],
            "compliance_brief": {
                "who_affected": ["상장사 ESG 담당자"],
                "business_change": "2027년부터 온실가스 공시 기준 변경을 반영해야 한다",
                "check_items": ["개정안 확인"],
                "remaining_limits": ["세부 지침 추가 공지 예정"],
            },
        }
        body = (
            "<p>정부는 관련 개편안을 발표했다.</p>"
            "<p>기존 공시 항목 해석 차이를 줄이기 위한 조치다. 기업별 비교 가능성을 높이려는 목적이다.</p>"
            "<p>기업은 개정안과 적용 범위를 먼저 확인해야 한다. 제출 일정도 점검해야 한다.</p>"
            "<p>다만 세부 지침은 추가 공지에 따라 달라질 수 있다.</p>"
        )
        fixed = finalize_cb_editorial_body(body, packet, article)
        self.assertIn("상장사 ESG 담당자", fixed)

    def test_finalize_reframes_source_copy_lead(self):
        article = {
            "body": "정부는 2027년부터 온실가스 공시 기준을 개편한다. 상장사 ESG 담당자는 내부 검증 절차를 조정해야 한다.",
        }
        packet = {
            "who_is_affected": ["상장사 ESG 담당자"],
            "main_claim": "2027년부터 온실가스 공시 기준이 개편된다",
            "conditions": ["2027년부터", "상장사 적용"],
            "action_items": ["개정안 확인"],
            "reader_utility": {},
            "risk_flags": [],
            "compliance_brief": {
                "who_affected": ["상장사 ESG 담당자"],
                "business_change": "2027년부터 온실가스 공시 기준이 개편된다",
                "check_items": ["개정안 확인"],
                "remaining_limits": ["세부 지침 추가 공지 예정"],
            },
        }
        body = (
            "<p>정부는 2027년부터 온실가스 공시 기준을 개편한다.</p>"
            "<p>기존 공시 항목 해석 차이를 줄이기 위한 조치다. 기업별 비교 가능성을 높이려는 목적이다.</p>"
            "<p>기업은 개정안과 적용 범위를 먼저 확인해야 한다. 제출 일정도 점검해야 한다.</p>"
            "<p>다만 세부 지침은 추가 공지에 따라 달라질 수 있다.</p>"
        )
        fixed = finalize_cb_editorial_body(body, packet, article)
        self.assertIn("상장사 ESG 담당자", fixed)
        self.assertNotIn("<p>정부는 2027년부터 온실가스 공시 기준을 개편한다.</p>", fixed)

    def test_finalize_injects_check_and_limit_clauses(self):
        article = {
            "body": "상장사 ESG 담당자는 2027년부터 온실가스 공시 기준 변경을 반영해야 한다",
        }
        packet = {
            "who_is_affected": ["상장사 ESG 담당자"],
            "main_claim": "2027년부터 온실가스 공시 기준 변경을 반영해야 한다",
            "conditions": ["2027년부터", "상장사 적용", "세부 지침 추가 공지 예정"],
            "action_items": ["개정안 확인", "적용 범위 점검"],
            "reader_utility": {},
            "risk_flags": [],
            "compliance_brief": {
                "who_affected": ["상장사 ESG 담당자"],
                "business_change": "2027년부터 온실가스 공시 기준 변경을 반영해야 한다",
                "check_items": ["개정안 확인", "적용 범위 점검"],
                "remaining_limits": ["세부 지침 추가 공지 예정"],
            },
        }
        body = (
            "<p>상장사 ESG 담당자는 2027년부터 공시 기준 변경을 반영해야 한다. 준비 일정 조정이 필요하다.</p>"
            "<p>기존 공시 항목 해석 차이를 줄이기 위한 조치다. 비교 가능성을 높이려는 목적이다.</p>"
            "<p>기업은 내부 검토를 진행해야 한다. 실무팀 협의가 필요하다.</p>"
            "<p>다만 변동 가능성이 있다.</p>"
        )
        fixed = finalize_cb_editorial_body(body, packet, article)
        self.assertIn("개정안 확인", fixed)
        self.assertIn("세부 지침 추가 공지 예정", fixed)

    def test_cb_scorecard_uses_sources_footer_for_confirmation(self):
        os.environ["CB_PUBLISH_V4"] = "1"
        article = {
            "body": "상장사 ESG 담당자는 2027년부터 공시 기준 변경을 반영해야 한다. 적용 범위와 제출 절차는 공식 안내에서 확인할 수 있다.",
        }
        packet = {
            "key_facts": ["2027년부터", "적용 범위", "제출 절차"],
            "who_is_affected": ["상장사 ESG 담당자"],
            "main_claim": "2027년부터 공시 기준 변경을 반영해야 한다",
            "conditions": ["2027년부터", "상장사 적용"],
            "action_items": ["개정안 확인"],
            "risk_flags": [],
            "reader_utility": {
                "primary_links": [{"url": "https://www.korea.kr/briefing/example", "label": "정부 보도자료"}],
                "checklist": [{"step": "개정안 확인"}, {"step": "적용 범위 점검"}],
                "scenarios": [],
            },
            "compliance_brief": {
                "who_affected": ["상장사 ESG 담당자"],
                "business_change": "2027년부터 공시 기준 변경을 반영해야 한다",
                "check_items": ["개정안 확인", "적용 범위 점검"],
                "remaining_limits": ["세부 지침 추가 공지 예정"],
            },
        }
        body = (
            "<p>상장사 ESG 담당자는 2027년부터 공시 기준 변경을 반영해야 한다. 준비 일정 조정이 필요하다.</p>"
            "<p>기존 공시 항목 해석 차이를 줄이기 위한 조치다. 비교 가능성과 검증 가능성을 높이겠다는 취지다.</p>"
            "<p>기업은 개정안 확인과 적용 범위 점검을 먼저 진행해야 한다. 제출 절차는 정부 보도자료를 통해 확인할 수 있다.</p>"
            "<p>다만 세부 지침 추가 공지 예정이어서 예외 범위와 시행 시점을 계속 확인해야 한다.</p>"
        )
        score = score_cb_editorial_rewrite("CB 제목", "리드", body, article, packet)
        self.assertTrue(score["sources_footer"])
        self.assertNotIn("확인 인용 미반영", score["gaps"])
        os.environ.pop("CB_PUBLISH_V4", None)


if __name__ == "__main__":
    unittest.main()
