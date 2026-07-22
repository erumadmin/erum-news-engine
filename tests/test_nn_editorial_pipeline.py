"""Tests for Neighbor News editorial pipeline (packet rewrite + community brief)."""

from __future__ import annotations

import os
import unittest

from engine.pipeline.nn_community_brief import (
    build_community_brief,
    format_community_brief_block,
    score_community_axes,
    validate_nn_forbidden_phrases,
    validate_nn_lead,
)
from engine.pipeline.nn_packet_writer import build_rewrite_user_message_for_nn
from engine.pipeline.nn_rewrite_validate import (
    finalize_nn_editorial_body,
    normalize_nn_forbidden_phrases,
    validate_nn_editorial_rewrite,
    validate_nn_paragraph_roles,
)
from engine.pipeline.orchestrator import (
    should_use_nn_editorial_rewrite,
    should_use_packet_editorial_rewrite,
)


class TestNNOrchestrator(unittest.TestCase):
    def test_nn_packet_off_by_default(self):
        os.environ.pop("NN_PACKET_PIPELINE", None)
        self.assertFalse(should_use_nn_editorial_rewrite("NN"))

    def test_nn_packet_on(self):
        os.environ["NN_PACKET_PIPELINE"] = "1"
        self.assertTrue(should_use_nn_editorial_rewrite("NN"))
        self.assertTrue(should_use_packet_editorial_rewrite("NN"))
        os.environ.pop("NN_PACKET_PIPELINE", None)


class TestNNCommunityBrief(unittest.TestCase):
    def test_build_and_format_brief(self):
        packet = {
            "who_is_affected": ["청년 창업자", "소상공인"],
            "main_claim": "국공유재산 사용료가 줄어든다",
            "conditions": ["2026년부터", "서울·부산 한정"],
            "action_items": ["지자체 홈페이지에서 신청"],
            "key_facts": ["사용료 30% 인하"],
            "reader_utility": {
                "checklist": [{"step": "거주지 구청 누리집에서 신청서를 제출한다"}],
            },
        }
        brief = build_community_brief({**packet, "_raw_source": {"body": "청년 창업자 신청"}})
        self.assertIn("청년", brief["who_affected"][0])
        block = format_community_brief_block({**packet, "community_brief": brief})
        self.assertIn("이웃뉴스", block)
        self.assertIn("누구 해당", block)

    def test_validate_lead_rejects_institution(self):
        ok, msg = validate_nn_lead(["정부가 새 지원책을 발표했다. 청년 대상이다."])
        self.assertFalse(ok)
        self.assertIn("기관명", msg)

    def test_validate_lead_rejects_hospital_일수록_subject(self):
        ok, msg = validate_nn_lead(
            [
                "중증 환자와 소아 중환자를 많이 진료하는 상급종합병원일수록 더 많은 보상금을 받게 된다. "
                "올해 하반기다."
            ]
        )
        self.assertFalse(ok)
        self.assertIn("공급자", msg)

    def test_validate_lead_rejects_mohw_subject(self):
        ok, msg = validate_nn_lead(
            ["보건복지부는 중환자실 부하지수를 올해 하반기 도입한다. 환자 가족은 영향을 본다."]
        )
        self.assertFalse(ok)

    def test_validate_lead_accepts_person_subject(self):
        ok, _ = validate_nn_lead(["청년 창업자는 국공유재산 사용료 부담이 줄어든다. 2026년부터 적용된다."])
        self.assertTrue(ok)

    def test_validate_lead_accepts_patient_family_subject(self):
        ok, _ = validate_nn_lead(
            ["중증 환자 가족은 상급종합병원 중환자실 성과보상 체계가 바뀌면 진료 여건 변화를 체감할 수 있다."]
        )
        self.assertTrue(ok)

    def test_forbidden_phrases(self):
        ok, msg = validate_nn_forbidden_phrases("지역 경제 활성화를 도모한다")
        self.assertFalse(ok)
        self.assertIn("도모", msg)

    def test_forbidden_phrases_allow_policy_term(self):
        ok, msg = validate_nn_forbidden_phrases(
            "공무원은 적극행정 보호 체계로 감사 부담이 줄어든다. 소송 지원 한도도 확대된다."
        )
        self.assertTrue(ok, msg)


class TestNNPacketWriter(unittest.TestCase):
    def test_rewrite_message_includes_community_brief(self):
        os.environ["NN_TARGET_ENGINE"] = "1"
        article = {
            "title": "청년·소상공인 국공유재산 사용 문턱 완화",
            "url": "https://example.test/1",
            "body": "청년 창업자와 소상공인은 국공유재산 사용료가 인하된다. 2026년부터 서울에서 시행한다.",
        }
        packet = {
            "who_is_affected": ["청년 창업자", "소상공인"],
            "main_claim": "사용료 인하",
            "publish_grade": "B",
            "community_brief": build_community_brief(
                {
                    "who_is_affected": ["청년 창업자"],
                    "main_claim": "사용료 인하",
                    "_raw_source": article,
                }
            ),
            "reader_utility": {},
        }
        msg = build_rewrite_user_message_for_nn(article, packet, [])
        self.assertIn("이웃뉴스", msg)
        self.assertIn("독자 4축", msg)
        os.environ.pop("NN_TARGET_ENGINE", None)


class TestNNRewriteValidate(unittest.TestCase):
    def _sample_body(self):
        return (
            "<p>청년 창업자와 소상공인은 국공유재산 사용료 부담이 줄어든다. "
            "2026년부터 서울·부산에서 먼저 적용되며, 입주 문턱 완화 효과가 기대된다.</p>"
            "<p>그동안 임대료 부담이 커 입주가 어려웠던 소규모 사업자를 돕기 위한 조치다. "
            "기존에는 사용료 할인 폭이 제한적이어서 체감 혜택이 작았다는 지적이 있었다.</p>"
            "<p>신청은 거주지 구청 누리집에서 하며, 2026년 3월부터 접수한다. "
            "제외 대상은 대형 법인이며, 필요 서류는 사업자등록증과 사업계획서다.</p>"
            "<p>다만 적용 지역과 업종에 따라 조건이 달라질 수 있어, "
            "신청 전 구청 안내를 확인해야 한다. 시범 운영 기간에는 일부 업종만 해당된다.</p>"
        )

    def test_paragraph_roles_ok(self):
        from engine.pipeline.rewrite_validate import _paragraph_plain_blocks

        paras = _paragraph_plain_blocks(self._sample_body())
        ok, msg = validate_nn_paragraph_roles(paras)
        self.assertTrue(ok, msg)

    def test_finalize_and_validate(self):
        os.environ["NN_PUBLISH_V4"] = "1"
        article = {
            "body": (
                "청년 창업자와 소상공인은 국공유재산 사용료 부담이 줄어든다. "
                "2026년부터 서울·부산에서 먼저 적용된다. "
                "신청은 거주지 구청 누리집에서 하며, 2026년 3월부터 접수한다. "
                "제외 대상은 대형 법인이며 시범 운영 기간에는 일부 업종만 해당된다."
            ),
        }
        packet = {
            "who_is_affected": ["청년 창업자", "소상공인"],
            "main_claim": "청년 창업자와 소상공인은 국공유재산 사용료 부담이 줄어든다",
            "conditions": ["2026년부터", "구청 누리집 신청", "대형 법인 제외"],
            "action_items": ["거주지 구청 누리집에서 신청"],
            "community_brief": build_community_brief(
                {
                    "who_is_affected": ["청년 창업자", "소상공인"],
                    "main_claim": "청년 창업자와 소상공인은 국공유재산 사용료 부담이 줄어든다",
                    "conditions": ["2026년부터", "구청 신청"],
                    "action_items": ["거주지 구청 누리집에서 신청"],
                    "_raw_source": article,
                }
            ),
            "reader_utility": {},
            "risk_flags": [],
        }
        body = finalize_nn_editorial_body(self._sample_body(), packet, article)
        import re

        from research_collector import strip_html_tags

        plain = re.sub(r"\s+", " ", strip_html_tags(body)).strip()
        axes_score, _ = score_community_axes(packet, plain)
        self.assertGreaterEqual(axes_score, 5.0)
        ok, msg = validate_nn_editorial_rewrite("청년·소상공인 국공유재산 사용료 인하", body, packet, article)
        self.assertTrue(ok, msg)
        os.environ.pop("NN_PUBLISH_V4", None)

    def test_normalize_forbidden_phrase(self):
        body = "<p>청년 창업 지원을 활성화한다.</p>"
        fixed = normalize_nn_forbidden_phrases(body)
        self.assertNotIn("활성화", fixed)
        self.assertIn("확대", fixed)
        fixed = normalize_nn_forbidden_phrases("<p>적극 대응과 적극행정이 필요하다.</p>")
        self.assertNotIn("적극 대응", fixed)
        self.assertIn("우선 대응", fixed)
        self.assertIn("적극행정", fixed)

    def test_finalize_pads_short_lead(self):
        os.environ["NN_PUBLISH_V4"] = "1"
        article = {"body": "청년 창업자는 지원 기준이 바뀐다"}
        packet = {
            "main_claim": "청년 창업자는 지원 기준이 바뀐다",
            "key_facts": ["신청 시기와 대상 업종은 다음 달 공고에서 확인할 수 있다"],
            "community_brief": {
                "who_affected": ["청년 창업자"],
                "life_change": "지원 기준이 바뀐다",
                "conditions": ["신청 시기와 대상 업종은 다음 달 공고에서 확인할 수 있다"],
            },
            "reader_utility": {},
        }
        body = (
            "<p>청년 창업자에게 지원 기준이 바뀐다.</p>"
            "<p>기존 기준은 업종별 편차가 있었다. 조정 이유를 설명했다.</p>"
            "<p>신청 조건과 대상 업종은 공고문에서 확인해야 한다. 접수 시점도 본다.</p>"
            "<p>다만 세부 적용 범위와 시행 일정, 예외 조건은 추가 공지에 따라 달라질 수 있다.</p>"
        )
        fixed = finalize_nn_editorial_body(body, packet, article)
        from engine.pipeline.rewrite_validate import MIN_PARAGRAPH_CHARS, _paragraph_plain_blocks

        paras = _paragraph_plain_blocks(fixed)
        self.assertGreaterEqual(len(paras), 4)
        self.assertTrue(
            all(len(p) >= MIN_PARAGRAPH_CHARS for p in paras[:4]),
            fixed,
        )
        os.environ.pop("NN_PUBLISH_V4", None)

    def test_finalize_collapses_double_danman(self):
        os.environ["NN_PUBLISH_V4"] = "1"
        article = {
            "body": (
                "법령 유권해석으로 야구장 조리식품 이동판매를 허용하기로 했다. "
                "배달앱 포장 제공 시 건강진단 제외."
            )
        }
        packet = {
            "main_claim": "야구장 관람객은 조리식품 이동판매를 이용할 수 있다",
            "who_is_affected": ["야구장 관람객"],
            "conditions": ["배달앱 포장 제공 시 건강진단 제외"],
            "key_facts": ["건강진단 연 1회"],
            "community_brief": {
                "who_affected": ["야구장 관람객"],
                "life_change": "관람석 조리식품 이동판매 허용",
                "conditions": ["배달앱 포장 제공 시 건강진단 제외"],
            },
            "reader_utility": {},
        }
        body = (
            "<p>야구장 관람객은 관람석에서 맥주 외 조리식품 이동판매가 허용되기로 했다. "
            "체육시설 전반이 대상이다.</p>"
            "<p>지금까지 국내에서는 맥주 외 조리식품 이동판매 가능 여부가 불분명했다. "
            "유권해석으로 허용하기로 했다.</p>"
            "<p>관람객은 식품용 용기와 운반 박스 위생을 보면 된다. "
            "이동판매자는 연 1회 건강진단을 받아야 한다.</p>"
            "<p>다만 다만, 배달앱을 통해 포장되어 제공하는 경우 건강진단 제외. "
            "설사·복통이 있으면 판매 업무에서 배제된다.</p>"
        )
        fixed = finalize_nn_editorial_body(body, packet, article)
        from engine.pipeline.rewrite_validate import _paragraph_plain_blocks

        p4 = _paragraph_plain_blocks(fixed)[3]
        self.assertTrue(p4.startswith("다만"), p4)
        self.assertNotRegex(p4, r"다만\s*,?\s*다만")
        os.environ.pop("NN_PUBLISH_V4", None)


if __name__ == "__main__":
    unittest.main()
