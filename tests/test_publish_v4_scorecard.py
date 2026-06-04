#!/usr/bin/env python3
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline.editorial_scorecard import score_editorial_rewrite
from engine.pipeline.publish_validate import body_has_exposed_urls
from engine.pipeline.rewrite_validate import finalize_ij_editorial_body


class TestPublishV4Scorecard(unittest.TestCase):
    def setUp(self):
        os.environ["IJ_PUBLISH_V4"] = "1"
        os.environ["IJ_TARGET_ENGINE"] = "1"

    def tearDown(self):
        os.environ.pop("IJ_PUBLISH_V4", None)
        os.environ["IJ_TARGET_ENGINE"] = "0"

    def test_finalize_strips_urls_under_v4(self):
        source = "다음 달 1일부터 시행한다. 전기위원회. 11월. 12월. 고지서. 단일 시간대별."
        body = (
            "<p>정부는 다음 달 1일부터 소규모 자영업자 전기요금 제도를 시행한다. "
            "대상은 일반용(갑)Ⅱ 등이다.</p>"
            "<p>그동안 시간대별 요금 부담 우려가 있었다. 전기위원회 심의를 거쳤다.</p>"
            "<p>한전은 고지서에 표기한다. https://online.kepco.co.kr 에서 확인한다.</p>"
            "<p>다만 법적 의무화가 아닌 고지 방식이며 조건을 유의해야 한다.</p>"
        )
        packet = {
            "risk_flags": [],
            "action_items": ["https://online.kepco.co.kr"],
            "reader_utility": {"primary_links": [{"url": "https://online.kepco.co.kr/"}]},
            "research_gate": {"research_depth": 8.0, "research_insufficient": False},
            "field_takeaways": {"lead_line": "정부는 다음 달 1일부터"},
        }
        out = finalize_ij_editorial_body(body, packet, {"body": source})
        plain = out.replace("<p>", "").replace("</p>", " ")
        self.assertFalse(body_has_exposed_urls(plain))
        self.assertTrue(packet.get("sources_footer"))

    def test_v4_scorecard_has_publish_dimensions(self):
        source = (
            "다음 달 1일부터 시행한다. 전기위원회 서면 심의. 6월부터 11월분까지 고지서에 표기. "
            "12월부터 선택. 시간대별 단일 요금."
        )
        pad = "적용 대상과 시행 시점은 원문 보도자료를 기준으로 확인한다."
        body = (
            f"<p>정부는 다음 달 1일부터 소규모 자영업자 전기요금 제도를 시행한다. {pad}</p>"
            f"<p>그동안 시간대별 요금 부담 우려가 있었다. 전기위원회 심의를 거쳤다. {pad}</p>"
            f"<p>한전은 고지서에 시간대별·단일 요금을 각각 표기하고 유리한 요금을 자동 적용한다. {pad}</p>"
            f"<p>다만 법적 의무화가 아닌 고지 방식이며 12월부터 선택한다. {pad}</p>"
        )
        packet = {
            "key_facts": ["다음 달 1일", "전기위원회"],
            "research_gate": {"research_depth": 8.0, "research_insufficient": False},
            "discovered_facts": [],
            "field_takeaways": {"lead_line": "정부는 다음 달 1일부터"},
            "reader_utility": {"primary_links": [], "scenarios": [], "checklist": []},
        }
        s = score_editorial_rewrite("제목 테스트", "리드", body, {"body": source}, packet, qa_score=120)
        dims = s["dimensions"]
        self.assertIn("article_voice", dims)
        self.assertIn("prose_cleanliness", dims)
        self.assertNotIn("coalition_briefing", dims)
        self.assertIn("article_publish_ready", s)


if __name__ == "__main__":
    unittest.main()
