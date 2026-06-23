#!/usr/bin/env python3
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline.editorial_report import write_editorial_quality_bundle


class TestEditorialReport(unittest.TestCase):
    def test_bundle_writes_compare_and_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            score = {"total": 9.5, "target": 9.5, "passes": True, "gaps": [], "dimensions": {}}
            variant = {
                "title": "제목",
                "excerpt": "리드",
                "body": "<p>첫 문단입니다. 다음 달 1일부터 시행합니다.</p>"
                "<p>그동안 우려가 있었습니다.</p>"
                "<p>고지서 표기와 한전 요금 안내입니다.</p>"
                "<p>다만 조건은 공식 안내를 확인해야 합니다.</p>",
                "qa_score": 120,
            }

            class Ctx:
                packet = {"key_facts": [], "risk_flags": []}
                evidence = []

            paths = write_editorial_quality_bundle(
                out,
                ts="test",
                article={"url": "http://x", "title": "원제", "body": "원문"},
                editorial_ctx=Ctx(),
                variant=variant,
                score=score,
                attempt=1,
            )
            self.assertTrue(Path(paths["compare"]).is_file())
            self.assertTrue(Path(paths["body_html"]).is_file())
            compare = Path(paths["compare"]).read_text(encoding="utf-8")
            self.assertIn("채점: 9.5", compare)
            self.assertIn("<p>첫 문단", compare)
            payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
            self.assertEqual(payload["body_html"].count("<p>"), 4)

    def test_bundle_supports_cb_site_specific_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            score = {"total": 9.62, "target": 9.5, "passes": True, "gaps": [], "dimensions": {}}
            variant = {
                "title": "위생용품 용량 축소 시 3개월 전 고지 의무화",
                "excerpt": "기업은 용량 축소 시 사전 고지와 공개 의무를 따라야 한다.",
                "body": "<p>기업은 위생용품 용량 축소 시 사전 고지 의무를 따라야 한다.</p>"
                "<p>이번 조치는 소비자 혼란을 줄이기 위한 협약에 따른 것이다.</p>"
                "<p>기업은 적용 범위와 고지 방식을 먼저 확인해야 한다.</p>"
                "<p>다만 세부 예외 범위는 추가 안내에 따라 달라질 수 있다.</p>",
                "qa_score": 114,
                "prefix": "CB_",
            }

            class Ctx:
                packet = {"key_facts": [], "risk_flags": []}
                evidence = []

            paths = write_editorial_quality_bundle(
                out,
                ts="cbtest",
                article={"url": "http://x", "title": "원제", "body": "원문"},
                editorial_ctx=Ctx(),
                variant=variant,
                score=score,
                attempt=1,
                site_code="CB",
                report_label="CB",
                body_prefix="editorial_cb_body",
            )
            self.assertTrue(Path(paths["body_html"]).name.startswith("editorial_cb_body_"))
            compare = Path(paths["compare"]).read_text(encoding="utf-8")
            self.assertIn("원문 vs 패킷 기반 CB 기사 비교", compare)
            self.assertIn("## CB 재작성", compare)
            self.assertNotIn("## IJ 재작성", compare)


if __name__ == "__main__":
    unittest.main()
