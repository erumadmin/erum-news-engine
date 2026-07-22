#!/usr/bin/env python3
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["IJ_TARGET_ENGINE"] = "0"

from engine.pipeline.rewrite_validate import (
    DEFAULT_LIMITATION_SENTENCE,
    build_rewrite_correction_suffix,
    cap_watch_phrase_repetition,
    ensure_danman_prefix,
    normalize_danman_opener,
    sanitize_editorial_limitation_paragraph,
    temporal_hint_from_source,
    validate_ij_editorial_rewrite,
    validate_limitation_paragraph,
)


class TestRewriteValidate(unittest.TestCase):
    def test_normalize_danman_opener_collapses_repeats(self):
        self.assertEqual(
            normalize_danman_opener("다만 다만, 배달앱 포장은 건강진단 제외다."),
            "다만 배달앱 포장은 건강진단 제외다.",
        )
        self.assertEqual(
            normalize_danman_opener("다만, 다만 제외 대상이 있다."),
            "다만 제외 대상이 있다.",
        )
        self.assertEqual(
            ensure_danman_prefix("다만, 배달앱 제외다."),
            "다만 배달앱 제외다.",
        )
        self.assertEqual(
            ensure_danman_prefix("배달앱 제외다."),
            "다만 배달앱 제외다.",
        )

    def test_sanitize_limitation_collapses_double_danman(self):
        fixed = sanitize_editorial_limitation_paragraph(
            "다만 다만, 배달앱을 통해 포장 제공 시 건강진단 제외. 예외 범위를 확인한다."
        )
        self.assertTrue(fixed.startswith("다만"))
        self.assertNotRegex(fixed, r"다만\s*,?\s*다만")
        self.assertIn("배달앱", fixed)

    def test_validate_limitation_rejects_double_danman(self):
        ok, msg = validate_limitation_paragraph(
            "다만 다만, 제외 대상이 있다. 예외 범위를 유의해야 한다."
        )
        self.assertFalse(ok)
        self.assertIn("다만", msg)

    def test_temporal_hint_next_month(self):
        self.assertEqual(
            temporal_hint_from_source("다음 달 1일부터 시행한다."),
            "다음 달 1일부터",
        )

    def test_four_paragraphs_required(self):
        body = "<p>a</p><p>b</p><p>c</p>"
        packet = {"risk_flags": [], "action_items": []}
        ok, msg = validate_ij_editorial_rewrite("제목입니다", body, packet)
        self.assertFalse(ok)
        self.assertIn("4문단", msg)

    def test_url_and_limitation_required(self):
        body = (
            "<p>정부는 다음 달 1일부터 소규모 자영업자 전기요금 부담 완화 제도를 시행한다. "
            "일반용(갑)Ⅱ 등 대상이다.</p>"
            "<p>그동안 시간대별 요금제로 특정 시간대 사용이 몰리면 부담이 커질 수 있다는 우려가 있었다. "
            "기후부와 한전이 요금 구조 개편을 추진한다.</p>"
            "<p>한전은 고지서에 시간대별·단일 요금을 각각 표기하고 유리한 요금을 자동 적용한다. "
            "https://online.kepco.co.kr 에서 확인한다.</p>"
            "<p>다만 6개월 비교 후 12월부터 선택하며 법적 의무화가 아닌 고지 방식이다. "
            "적용 범위와 남은 조건은 공식 안내를 확인해야 한다.</p>"
        )
        packet = {
            "risk_flags": ["official_evidence_missing"],
            "action_items": ["한전 안내: https://online.kepco.co.kr"],
        }
        article = {
            "title": "자영업자 전기요금 개편",
            "body": (
                "정부는 다음 달 1일부터 소규모 자영업자 전기요금 부담 완화 제도를 시행한다. "
                "일반용(갑)Ⅱ 등 대상이다. 그동안 시간대별 요금제로 특정 시간대 사용이 몰리면 "
                "부담이 커질 수 있다는 우려가 있었다. 기후부와 한전이 요금 구조 개편을 추진한다. "
                "한전은 고지서에 시간대별·단일 요금을 각각 표기하고 유리한 요금을 자동 적용한다. "
                "https://online.kepco.co.kr 에서 확인한다. "
                "다만 6개월 비교 후 12월부터 선택하며 법적 의무화가 아닌 고지 방식이다."
            ),
        }
        ok, msg = validate_ij_editorial_rewrite("자영업자 전기요금 개편", body, packet, article)
        self.assertTrue(ok, msg)

    def test_temporal_normalize_fixes_body(self):
        from engine.pipeline.rewrite_validate import normalize_temporal_in_body

        body = "<p>이달부터 시행합니다.</p>"
        fixed = normalize_temporal_in_body(body, "다음 달 1일부터 시행한다.")
        self.assertIn("다음 달 1일부터", fixed)

    def test_correction_suffix_nonempty(self):
        self.assertIn("4개", build_rewrite_correction_suffix("문단 수 부족"))

    def test_inject_12월_from_source(self):
        from engine.pipeline.rewrite_validate import inject_missing_source_anchors

        body = (
            "<p>다음 달 1일부터 시행한다. 11월분 비교한다.</p>"
            "<p>그동안 부담 우려가 있었다.</p>"
            "<p>고지서에 표기한다. https://online.kepco.co.kr</p>"
            "<p>다만 조건을 확인해야 한다.</p>"
        )
        source = "12월부터 선택. 전기위원회. 11월분"
        out = inject_missing_source_anchors(body, source)
        self.assertIn("12월", out)

    def test_default_limitation_sentence_valid(self):
        ok, msg = validate_limitation_paragraph(DEFAULT_LIMITATION_SENTENCE)
        self.assertTrue(ok, msg)

    def test_cap_watch_phrase_repetition(self):
        body = (
            "<p>유리한 요금 유리한 요금 유리한 요금 안내.</p>"
            "<p>그동안 부담 우려가 있었다.</p>"
            "<p>고지서 표기와 한전 요금 선택.</p>"
            "<p>다만 조건은 공식 안내를 확인한다.</p>"
        )
        fixed = cap_watch_phrase_repetition(body)
        self.assertLessEqual(fixed.count("유리한 요금"), 2)


if __name__ == "__main__":
    unittest.main()
