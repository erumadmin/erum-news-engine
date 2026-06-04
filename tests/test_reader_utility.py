#!/usr/bin/env python3
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline.reader_utility import (
    build_reader_utility,
    extract_checklist,
    extract_scenarios,
    score_reader_value_dimension,
)
import research_collector as rc


ELECTRIC_BODY = """
다음 달 1일부터 시행한다. 전기위원회 서면 심의를 거쳤다.
6월부터 11월분 고지서에 두 요금을 표기한다.
예를 들어 카페·음식점 등 낮 시간대 전기 사용이 많은 업종은 시간대별 요금이 유리할 수 있다.
12월부터는 가장 유리한 요금을 선택해 적용받을 수 있다.
자세한 내용은 한전ON(https://online.kepco.co.kr/)에서 확인할 수 있다.
"""


class TestReaderUtility(unittest.TestCase):
    def setUp(self):
        os.environ["IJ_PUBLISH_V4"] = "0"

    def tearDown(self):
        os.environ.pop("IJ_PUBLISH_V4", None)

    def test_extract_scenarios_from_body(self):
        scenarios = extract_scenarios(ELECTRIC_BODY)
        self.assertGreaterEqual(len(scenarios), 1)
        self.assertIn("카페", scenarios[0]["body"])

    def test_extract_checklist_requires_date_or_period(self):
        checklist = extract_checklist(ELECTRIC_BODY)
        self.assertGreaterEqual(len(checklist), 1)

    def test_source_confirmation_when_no_fetch(self):
        raw = {
            "title": "위생용품",
            "body": "앞으로 위생용품의 용량·개수 등을 줄일 경우 제품 포장과 판매장소 등에 3개월 이상 먼저 알리고, 변경 정보를 공개한다.\n공정거래위원회는 14일 협약을 체결했다고 밝혔다.",
            "url": "https://www.korea.kr/news/1",
        }
        ru = build_reader_utility(raw, [])
        self.assertGreaterEqual(len(ru.get("evidence_quotes") or []), 1)
        self.assertEqual(
            (ru.get("evidence_quotes") or [{}])[0].get("used_for"),
            "source_confirmation",
        )

    def test_build_reader_utility_has_primary_link(self):
        raw = {
            "title": "전기요금",
            "body": ELECTRIC_BODY,
            "url": "https://www.korea.kr/news/1",
        }
        ru = build_reader_utility(raw, [])
        self.assertTrue(ru.get("as_of_date"))
        urls = [link["url"] for link in ru.get("primary_links") or []]
        self.assertTrue(any("korea.kr" in u for u in urls))

    def test_packet_v2_fields(self):
        raw = {
            "title": "전기요금",
            "body": (ELECTRIC_BODY + "\n") * 15,
            "url": "https://www.korea.kr/news/1",
        }
        packet = rc.build_research_packet(raw, [], assigned_site="IJ")
        self.assertEqual(packet.research_meta.get("packet_version"), 2)
        self.assertIn("primary_links", packet.reader_utility)

    def test_score_reader_value_dimension(self):
        packet = {
            "reader_utility": {
                "scenarios": [{"body": "카페·음식점 등 낮 시간대 전기"}],
                "checklist": [
                    {"step": "6월부터 11월분 고지서 확인"},
                    {"step": "12월부터 유리한 요금 선택"},
                ],
                "as_of_date": "2026-05-28",
                "primary_links": [
                    {"url": "https://online.kepco.co.kr/"},
                    {"url": "https://www.korea.kr/x"},
                ],
                "evidence_quotes": [],
            }
        }
        plain = (
            "카페·음식점 낮 시간대. 6월부터 11월분 고지서. 12월부터 선택. "
            "기준 2026-05-28. https://online.kepco.co.kr/ https://www.korea.kr/x"
        )
        score, gaps = score_reader_value_dimension(packet, plain)
        self.assertGreaterEqual(score, 7.0, gaps)


if __name__ == "__main__":
    unittest.main()
