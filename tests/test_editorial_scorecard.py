#!/usr/bin/env python3
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["IJ_TARGET_ENGINE"] = "0"
os.environ["IJ_PUBLISH_V4"] = "0"

from engine.pipeline.editorial_scorecard import score_editorial_rewrite
from engine.pipeline.rewrite_validate import finalize_ij_editorial_body


class TestEditorialScorecard(unittest.TestCase):
    def test_high_score_well_structured(self):
        source = (
            "다음 달 1일부터 시행한다. 전기위원회 서면 심의. 6월부터 11월분까지 고지서에 표기. "
            "12월부터 선택. 시간대별 단일 요금. https://online.kepco.co.kr/ "
        )
        body = (
            "<p>정부는 다음 달 1일부터 소규모 자영업자 전기요금 제도를 시행한다. "
            "대상은 일반용(갑)Ⅱ 등이다.</p>"
            "<p>그동안 시간대별 요금 부담 우려가 있었다. 전기위원회 심의를 거쳤다.</p>"
            "<p>한전은 고지서에 시간대별·단일 요금을 각각 표기하고 유리한 요금을 자동 적용한다. "
            "https://online.kepco.co.kr 에서 확인한다.</p>"
            "<p>다만 법적 의무화가 아닌 고지 방식이며 12월부터 선택한다. "
            "11월까지 비교한다. 기준 2026-05-28. https://www.korea.kr/x</p>"
        )
        packet = {
            "key_facts": ["다음 달 1일", "전기위원회"],
            "risk_flags": ["official_evidence_missing"],
            "action_items": ["한전: https://online.kepco.co.kr"],
            "reader_utility": {
                "scenarios": [{"body": "시간대별 요금 부담"}],
                "checklist": [
                    {"step": "11월까지 비교"},
                    {"step": "12월부터 선택"},
                ],
                "as_of_date": "2026-05-28",
                "primary_links": [
                    {"url": "https://online.kepco.co.kr/"},
                    {"url": "https://www.korea.kr/x"},
                ],
                "evidence_quotes": [],
            },
        }
        s = score_editorial_rewrite("제목", "리드", body, {"body": source}, packet, qa_score=120)
        self.assertGreaterEqual(s["total"], 9.0)

    def test_finalize_produces_four_paragraphs(self):
        messy = "<p>한 덩어리 " + "문장. " * 30 + "</p>"
        packet = {"risk_flags": ["official_evidence_missing"], "action_items": []}
        out = finalize_ij_editorial_body(messy, packet, {"body": "다음 달 1일부터"})
        self.assertEqual(len(__import__("re").findall(r"<p\b", out, __import__("re").I)), 4)

    def test_nested_p_scores_logical_paragraph_count(self):
        source = "다음 달 1일부터. 전기위원회. 11월. 12월. 고지서. 단일 시간대별. 700억. https://online.kepco.co.kr"
        nested = (
            "<p><p>다음 달 1일부터 시행한다. 11월분 비교 대상이다.</p></p>"
            "<p><p>그동안 부담 우려가 있었다. 전기위원회 심의.</p></p>"
            "<p><p>고지서 표기. 단일 시간대별. https://online.kepco.co.kr</p></p>"
            "<p><p>다만 조건 유의. 12월부터 선택. 700억 투자.</p></p>"
        )
        packet = {"key_facts": [], "risk_flags": [], "action_items": ["https://online.kepco.co.kr"]}
        s = score_editorial_rewrite("제목", "리드", nested, {"body": source}, packet)
        self.assertEqual(s["paragraph_count"], 4)
        self.assertIn("중첩 p 태그", s["gaps"])


if __name__ == "__main__":
    unittest.main()
