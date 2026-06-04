#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline.editorial_originality import (
    score_originality_dimension,
    source_has_scenario_material,
)
from engine.pipeline.editorial_scorecard import TARGET_ORIGINALITY


ELECTRIC_SOURCE = """
다음 달 1일부터 시행. 6월부터 11월분 고지서에 각각 표기. 12월부터 선택.
예를 들어 카페·음식점은 시간대별이 유리하고 반대로 단일이 유리할 수 있다.
https://online.kepco.co.kr/
"""

ELECTRIC_PLAIN = (
    "예를 들어 카페나 음식점은 시간대별 요금제가 유리할 수 있고 "
    "단일 요금제가 더 저렴할 수 있다. "
    "6월부터 11월분 비교 고지서 표기. 12월부터 선택. "
    "https://online.kepco.co.kr/ https://www.korea.kr/news/1 "
    "2026-05-28 기준 공식 보도자료"
)

HYGIENE_SOURCE = (
    "앞으로 위생용품의 용량·개수 등을 줄일 경우 제품 포장과 판매장소 등에 "
    "3개월 이상 먼저 알리고, 변경 정보를 공개한다.\n"
    "단위 사양 축소 정보는 참가격(www.price.go.kr) 누리집에 공개한다."
)

HYGIENE_PLAIN = (
    "위생용품 용량 축소 시 3개월 전 포장·판매장소에 알리고 참가격에 공개한다. "
    "협약 체결로 시행된다. https://www.price.go.kr/ https://www.korea.kr/x "
    "2026-05-28 기준"
)


class TestEditorialOriginality(unittest.TestCase):
    def test_target_is_nine(self):
        self.assertEqual(TARGET_ORIGINALITY, 9.0)

    def test_high_originality_electric(self):
        packet = {
            "key_facts": ["다음 달 시행", "11월분 고지"],
            "reader_utility": {
                "as_of_date": "2026-05-28",
                "scenarios": [{"body": "예를 들어 카페·음식점"}],
                "checklist": [
                    {"step": "6월부터 11월분 고지서"},
                    {"step": "12월부터 선택"},
                    {"step": "별도 신청 없이 적용"},
                ],
                "primary_links": [
                    {"url": "https://www.korea.kr/news/1"},
                    {"url": "https://online.kepco.co.kr/"},
                ],
            },
        }
        score, gaps = score_originality_dimension(packet, ELECTRIC_PLAIN, ELECTRIC_SOURCE)
        self.assertGreaterEqual(score, 9.0, gaps)

    def test_hygiene_without_scenario_markers(self):
        self.assertFalse(source_has_scenario_material(HYGIENE_SOURCE))
        packet = {
            "key_facts": [
                "3개월 이상 먼저 알리고",
                "참가격에 공개",
            ],
            "reader_utility": {
                "as_of_date": "2026-05-28",
                "scenarios": [],
                "checklist": [{"step": "3개월 이상 먼저 알리고 변경 정보를 공개"}],
                "primary_links": [
                    {"url": "https://www.korea.kr/x"},
                    {"url": "https://www.price.go.kr/"},
                ],
            },
        }
        score, gaps = score_originality_dimension(packet, HYGIENE_PLAIN, HYGIENE_SOURCE)
        self.assertGreaterEqual(score, 7.0, gaps)


if __name__ == "__main__":
    unittest.main()
