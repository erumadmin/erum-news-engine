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


if __name__ == "__main__":
    unittest.main()
