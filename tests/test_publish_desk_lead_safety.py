"""Publish-path desk safety: no ICU/소방 template bleed, desk-aware sanitize."""

from __future__ import annotations

import os
import unittest

from engine.pipeline.cb_rewrite_validate import _polish_cb_paragraphs, repair_cb_lead
from engine.pipeline.nn_rewrite_validate import finalize_nn_editorial_body, fix_nn_para1_lead_opener
from engine.pipeline.publish_validate import publish_sanitize_body, resolve_publish_site, validate_publish_article
from engine.pipeline.rewrite_validate import _paragraph_plain_blocks, finalize_ij_editorial_body
from engine.pipeline.topic_particles import source_is_icu_load_index, with_topic_particle


class TestResolvePublishSite(unittest.TestCase):
    def test_packet_briefs_override_force_default(self):
        os.environ.pop("EDITORIAL_FORCE_SITE", None)
        self.assertEqual(resolve_publish_site({"community_brief": {}}), "NN")
        self.assertEqual(resolve_publish_site({"compliance_brief": {}}), "CB")
        self.assertEqual(resolve_publish_site({}), "IJ")
        self.assertEqual(resolve_publish_site({"assigned_site": "CB"}), "CB")


class TestPublishSanitizeDeskRouting(unittest.TestCase):
    def test_cb_packet_does_not_use_ij_lead_fixer_without_force_site(self):
        os.environ.pop("EDITORIAL_FORCE_SITE", None)
        os.environ["CB_PUBLISH_V4"] = "1"
        os.environ["IJ_PUBLISH_V4"] = "1"
        body = (
            "<p>정부가 단일종목 레버리지 상품 규제를 발표했다. 예탁금이 오른다.</p>"
            "<p>시장 변동성 확대 우려가 제기됐다. 관계기관이 점검했다.</p>"
            "<p>예탁금은 3000만 원 현금이며 교육은 3시간이다. LP 제재도 강화된다.</p>"
            "<p>다만 시행일과 종료 시점은 미정이다. 후속 공지를 확인해야 한다.</p>"
        )
        packet = {
            "compliance_brief": {
                "who_affected": ["증권사·운용사"],
                "business_change": "신규 출시 중단·예탁금 상향",
                "remaining_limits": ["시행일 미정"],
            },
            "main_claim": "정부가 단일종목 레버리지 상품 규제를 강화한다",
        }
        cleaned, _ = publish_sanitize_body(body, packet, {"body": "과태료 없이 예탁금만 상향"})
        p0 = _paragraph_plain_blocks(cleaned)[0]
        self.assertFalse(p0.startswith("정부"), p0)
        self.assertNotIn("스프링클러", p0)
        os.environ.pop("CB_PUBLISH_V4", None)


class TestNoHardcodedTemplateBleed(unittest.TestCase):
    def test_nn_lead_fallback_not_icu_when_source_unrelated(self):
        paras = ["규제합리화위원회는 이동판매를 허용하기로 했다.", "배경", "조건 문단입니다." * 3, "다만 예외가 있다."]
        packet = {
            "community_brief": {
                "who_affected": ["야구장 관람객"],
                "life_change": "관람석 조리식품 이동판매가 허용되기로 했다",
                "conditions": ["건강진단 연 1회"],
            }
        }
        out = fix_nn_para1_lead_opener(
            paras,
            packet,
            "야구장 조리식품 이동판매를 허용하기로 했다. 건강진단 연 1회.",
        )
        self.assertNotIn("중환자", out[0])
        self.assertNotIn("성과보상", out[0])
        self.assertIn("관람객", out[0])

    def test_cb_lead_과태료_alone_not_소방_template(self):
        paras = ["정부가 과태료 기준을 발표했다.", "b", "c", "다만 유예가 있다."]
        packet = {
            "compliance_brief": {
                "who_affected": ["관련 기업"],
                "business_change": "과태료 기준이 강화된다",
            }
        }
        out = repair_cb_lead(
            paras,
            packet,
            "관련 기업은 공시 의무 위반 시 과태료가 부과된다. 설비 기준 언급은 없다.",
        )
        self.assertNotIn("스프링클러", out[0])
        self.assertFalse(out[0].startswith("정부"), out[0])

    def test_cb_polish_keeps_four_paragraphs_on_duplicate(self):
        dup = "관련 기업은 바뀌는 의무·기준을 확인하고 적용 일정을 점검해야 한다. " * 2
        paras = [dup, dup, "적용 범위와 시행 일정을 점검해야 한다. 과태료도 본다.", "다만 유예 범위는 미정이다. 후속 고시를 본다."]
        out = _polish_cb_paragraphs(paras)
        self.assertEqual(len(out), 4)
        self.assertTrue(all(out))

    def test_ij_finalize_no_icu_stub_on_unrelated_복지부(self):
        os.environ["IJ_PUBLISH_V4"] = "1"
        os.environ["IJ_TARGET_ENGINE"] = "0"
        body = (
            "<p>보건복지부는 발표했다.</p>"
            "<p>배경 문단입니다. 제도 변화 이유를 설명했다.</p>"
            "<p>작동 구조와 대상·수치를 담은 문단입니다. 기준이 바뀐다.</p>"
            "<p>다만 시행 범위와 예외는 후속 안내에 따른다. 조건을 확인한다.</p>"
        )
        article = {"body": "보건복지부는 어린이집 지원 기준을 조정한다고 밝혔다."}
        packet = {"main_claim": "어린이집 지원 기준 조정", "key_facts": [], "reader_utility": {}}
        fixed = finalize_ij_editorial_body(body, packet, article)
        plain = " ".join(_paragraph_plain_blocks(fixed))
        self.assertNotIn("부하지수", plain)
        self.assertNotIn("800억", plain)
        os.environ.pop("IJ_PUBLISH_V4", None)

    def test_validate_publish_cb_rejects_agency_lead(self):
        os.environ["CB_PUBLISH_V4"] = "1"
        os.environ["IJ_PUBLISH_V4"] = "1"
        # Empty brief so repair_cb_lead cannot invent a business opener
        body = (
            "<p>국토교통부는 관련 기준을 강화한다고 21일 밝혔다. "
            "적용 일정과 세부 범위가 함께 바뀌며 현장 준비가 필요하다.</p>"
            "<p>기존 인력 기준만으로는 위험을 반영하지 못했다는 지적이 있었다. "
            "보완 필요성이 제기되며 관계기관이 점검을 이어갔다.</p>"
            "<p>적용 범위·시행 일정·과태료·조달 반영 여부를 점검해야 한다. "
            "규모 미만 사업장 유예 여부도 함께 확인해야 한다.</p>"
            "<p>다만 세부 고시와 유예 범위는 아직 미정이다. "
            "후속 공지와 예외 적용 여부를 계속 확인해야 한다. "
            "종료 일정도 확정되지 않았다.</p>"
        )
        packet = {
            "compliance_brief": {"who_affected": [], "business_change": "", "remaining_limits": ["유예"]},
            "assigned_site": "CB",
            "reader_utility": {"primary_links": []},
        }
        ok, msg = validate_publish_article(
            "물류시설 기준 강화 조치",
            "",
            body,
            packet,
            {"body": "국토교통부는 관련 기준을 강화한다고 밝혔다."},
        )
        self.assertFalse(ok, msg)
        self.assertTrue(
            any(k in msg for k in ("기관", "리드", "기업 실무")),
            msg,
        )
        os.environ.pop("CB_PUBLISH_V4", None)

    def test_nn_patient_who_without_icu_source_no_icu_opener(self):
        paras = ["환자 가족이 영향을 받는다.", "배경", "조건 문단입니다." * 3, "다만 예외가 있다."]
        packet = {
            "community_brief": {
                "who_affected": ["환자 가족"],
                "life_change": "외래 진료비가 조정된다",
                "conditions": ["상급종합병원·종합병원 모두 해당"],
            }
        }
        source = "환자 가족은 외래 진료비 조정을 확인해야 한다. 상급종합병원과 종합병원이 포함된다."
        out = fix_nn_para1_lead_opener(paras, packet, source)
        self.assertNotIn("중환자실", out[0])
        self.assertNotIn("성과보상", out[0])
        self.assertNotIn("포함되지 않는다", out[0])

    def test_nn_no_30_70_inject_on_bare_percent(self):
        os.environ["NN_PUBLISH_V4"] = "1"
        body = (
            "<p>야구장 관람객은 이동판매가 허용된다. 대상·제외·시행 시점을 확인해야 한다.</p>"
            "<p>기존에는 반입이 제한돼 불편이 컸다. 현장 요구가 이어졌다.</p>"
            "<p>건강진단 연 1회와 위생 기준을 지켜야 한다. 판매 품목도 제한된다.</p>"
            "<p>다만 세부 시행일과 예외는 후속 안내에 따른다. 조건을 확인한다.</p>"
        )
        packet = {
            "community_brief": {
                "who_affected": ["야구장 관람객"],
                "life_change": "이동판매 허용",
                "conditions": ["건강진단"],
                "remaining_limits": ["시행일 미정"],
            },
            "key_facts": [],
            "main_claim": "이동판매 허용",
        }
        fixed = finalize_nn_editorial_body(
            body,
            packet,
            {"body": "야구장 조리식품 이동판매를 허용한다. 이용료는 30% 인하한다."},
        )
        plain = " ".join(_paragraph_plain_blocks(fixed))
        self.assertNotIn("부하지수", plain)
        self.assertNotIn("등급 가중", plain)
        os.environ.pop("NN_PUBLISH_V4", None)

    def test_ij_no_종합병원_exclusion_on_unrelated_종합병원(self):
        os.environ["IJ_PUBLISH_V4"] = "1"
        os.environ["IJ_TARGET_ENGINE"] = "0"
        body = (
            "<p>보건복지부는 어린이집 지원 기준을 조정한다고 21일 밝혔다. "
            "적용 대상과 시행 시점을 함께 확인해야 한다.</p>"
            "<p>현장 수요 증가와 지원 공백이 지적됐다. 제도 보완이 필요했다.</p>"
            "<p>지원 대상·기준·기간이 바뀌며 종합병원 인근 시설도 포함된다. "
            "세부 요건은 고시에 따른다.</p>"
            "<p>다만 시행 범위와 예외는 후속 안내에 따른다. 조건을 확인한다.</p>"
        )
        article = {
            "body": (
                "보건복지부는 어린이집 지원 기준을 조정한다고 밝혔다. "
                "종합병원 인근 시설도 지원 대상에 포함할 수 있다."
            )
        }
        packet = {"main_claim": "어린이집 지원 기준 조정", "key_facts": [], "reader_utility": {}}
        fixed = finalize_ij_editorial_body(body, packet, article)
        plain = " ".join(_paragraph_plain_blocks(fixed))
        self.assertNotIn("종합병원은 포함되지 않는다", plain)
        self.assertNotIn("종합병원은 이번 평가 대상에 포함되지 않는다", plain)
        self.assertNotIn("부하지수", plain)
        os.environ.pop("IJ_PUBLISH_V4", None)

    def test_cb_polish_duplicate_not_editor_instruction(self):
        dup = "관련 기업은 바뀌는 의무·기준을 확인하고 적용 일정을 점검해야 한다. " * 2
        paras = [dup, dup, "적용 범위와 시행 일정을 점검해야 한다. 과태료도 본다.", "다만 유예 범위는 미정이다. 후속 고시를 본다."]
        out = _polish_cb_paragraphs(paras)
        self.assertNotIn("정리한다", out[1])
        self.assertNotIn("규제 강화 배경을 짧게", out[1])
        self.assertIn("기업은", out[1])

    def test_cb_lead_topic_particle_for_batchim_noun(self):
        paras = ["정부가 기준을 발표했다.", "b", "c", "다만 유예가 있다."]
        packet = {
            "compliance_brief": {
                "who_affected": ["중소기업"],
                "business_change": "공시 의무가 강화된다",
            }
        }
        out = repair_cb_lead(paras, packet, "중소기업은 공시 의무가 강화된다.")
        self.assertTrue(out[0].startswith("중소기업은"), out[0])
        self.assertNotIn("중소기업는", out[0])


class TestTopicParticles(unittest.TestCase):
    def test_icu_gate_requires_중환자실_and_marker(self):
        self.assertTrue(source_is_icu_load_index("중환자실 부하지수와 성과보상"))
        self.assertFalse(source_is_icu_load_index("환자 가족 외래 30% 인하 종합병원"))
        self.assertFalse(source_is_icu_load_index("중환자실만 언급"))

    def test_topic_particle_eun_neun(self):
        self.assertEqual(with_topic_particle("중소기업"), "중소기업은")
        self.assertEqual(with_topic_particle("관련 기업"), "관련 기업은")
        self.assertEqual(with_topic_particle("사업주"), "사업주는")


class TestCbHighFixes(unittest.TestCase):
    def test_repair_fixes_broken_particle_even_when_기업_present(self):
        from engine.pipeline.cb_rewrite_validate import repair_cb_lead

        paras = [
            "중소기업는 공시 의무가 강화된다. 적용 일정을 점검해야 한다.",
            "b",
            "c",
            "다만 유예가 있다.",
        ]
        packet = {
            "compliance_brief": {
                "who_affected": ["중소기업"],
                "business_change": "공시 의무가 강화된다",
            }
        }
        out = repair_cb_lead(paras, packet, "중소기업은 공시 의무가 강화된다.")
        self.assertNotIn("중소기업는", out[0])
        self.assertTrue(out[0].startswith("중소기업은"), out[0])

    def test_validate_rejects_broken_particle_and_금융위원회_agency(self):
        from engine.pipeline.cb_rewrite_validate import (
            _cb_has_broken_korean,
            validate_cb_editorial_rewrite,
        )

        self.assertTrue(_cb_has_broken_korean("중소기업는 공시 의무가 강화된다."))
        body = (
            "<p>금융위원회 등 14개 부처가 관련 기준을 강화한다고 밝혔다. "
            "기업 실무 대응과 적용 일정 점검이 함께 필요하며 현장 준비가 요구된다.</p>"
            "<p>기존 기준으로는 위험을 반영하지 못했다는 지적이 있었다. "
            "보완 필요성이 제기되며 관계기관이 점검을 이어갔다.</p>"
            "<p>적용 범위·시행 일정·공시 요건을 점검해야 한다. "
            "제출 시한과 예외 여부도 함께 확인하고 내부 일정을 맞춰야 한다.</p>"
            "<p>다만 세부 고시와 유예 범위는 아직 미정이다. "
            "후속 공지와 예외 적용 여부를 계속 확인해야 한다. "
            "종료 일정도 확정되지 않았다.</p>"
        )
        packet = {
            "compliance_brief": {
                "who_affected": ["관련 기업"],
                "business_change": "기준 강화",
                "remaining_limits": ["유예"],
            }
        }
        ok, msg = validate_cb_editorial_rewrite(
            "금융당국 기준 강화 조치",
            body,
            packet,
            {"body": "금융위가 기준을 강화한다."},
        )
        self.assertFalse(ok, msg)
        self.assertIn("기관", msg)

    def test_strip_invented_norm_keeps_source_backed_의무화(self):
        from engine.pipeline.cb_rewrite_validate import _cb_strip_invented_norm

        src = "관련 설비 설치를 의무화한다. 과태료도 검토한다."
        out = _cb_strip_invented_norm("기업은 설치를 의무화해야 한다.", src)
        self.assertIn("의무화", out)
        out2 = _cb_strip_invented_norm("기업은 설치를 의무화해야 한다.", "과태료만 언급")
        self.assertNotIn("의무화", out2)

    def test_inject_checklist_not_과태료_on_selection_story(self):
        from engine.pipeline.cb_rewrite_validate import inject_cb_business_anchors

        paras = [
            "혁신기업은 우대 선정 절차를 살펴봐야 한다. 신청 일정이 바뀐다.",
            "배경 문단입니다. 정책 취지를 짧게 정리했다.",
            "가점 항목과 우대 혜택을 함께 본다. 서류 준비를 서두른다.",
            "다만 세부 공고는 미정이다. 후속 안내를 본다.",
        ]
        packet = {
            "compliance_brief": {
                "who_affected": ["혁신기업"],
                "business_change": "우대 선정",
                "check_items": [],
                "remaining_limits": ["공고 미정"],
            }
        }
        out = inject_cb_business_anchors(
            paras,
            packet,
            source_text="혁신기업 우대 선정 프로그램을 안내한다. 설비 강제 조항은 없다.",
        )
        self.assertNotIn("과태료", out[2])
        self.assertNotIn("조달·계약", out[2])
        self.assertIn("제출 요건", out[2])

    def test_ij_no_성과보상_link_without_icu_source(self):
        os.environ["IJ_PUBLISH_V4"] = "1"
        os.environ["IJ_TARGET_ENGINE"] = "0"
        body = (
            "<p>정부는 탄소 감축 지수를 도입한다고 밝혔다. "
            "적용 대상과 시행 시점을 함께 확인해야 한다.</p>"
            "<p>평가지수 산식에 배출량을 반영한다. 병상과 무관한 제도다.</p>"
            "<p>대상 기업과 수치 기준이 함께 제시된다. 세부 고시를 본다.</p>"
            "<p>다만 시행 범위와 예외는 후속 안내에 따른다. 조건을 확인한다.</p>"
        )
        article = {"body": "정부는 탄소 감축 지수를 도입한다. 200억 원 규모 예산을 편성한다."}
        packet = {"main_claim": "탄소 감축 지수", "key_facts": [], "reader_utility": {}}
        fixed = finalize_ij_editorial_body(body, packet, article)
        plain = " ".join(_paragraph_plain_blocks(fixed))
        self.assertNotIn("성과보상과 직접 연계", plain)
        os.environ.pop("IJ_PUBLISH_V4", None)


if __name__ == "__main__":
    unittest.main()
