#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline.rewrite_validate import (
    build_rewrite_correction_suffix,
    temporal_hint_from_source,
    validate_ij_editorial_rewrite,
)


class TestRewriteValidate(unittest.TestCase):
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
            "<p>변화 내용입니다 충분히 깁니다.</p>"
            "<p>배경 설명입니다 충분히 깁니다.</p>"
            "<p>작동 방식입니다 https://online.kepco.co.kr 안내.</p>"
            "<p>다만 6개월 비교 후 12월 선택 조건이 남습니다.</p>"
        )
        packet = {
            "risk_flags": ["official_evidence_missing"],
            "action_items": ["한전 안내: https://online.kepco.co.kr"],
        }
        article = {"body": "다음 달 1일부터 시행한다."}
        ok, msg = validate_ij_editorial_rewrite("자영업자 전기요금 개편", body, packet, article)
        self.assertTrue(ok, msg)

    def test_temporal_normalize_fixes_body(self):
        from engine.pipeline.rewrite_validate import normalize_temporal_in_body

        body = "<p>이달부터 시행합니다.</p>"
        fixed = normalize_temporal_in_body(body, "다음 달 1일부터 시행한다.")
        self.assertIn("다음 달 1일부터", fixed)

    def test_correction_suffix_nonempty(self):
        self.assertIn("4개", build_rewrite_correction_suffix("문단 수 부족"))


if __name__ == "__main__":
    unittest.main()
