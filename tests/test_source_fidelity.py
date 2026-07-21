"""P5: unsupported numeric/detail guards and short-source prompt safety."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from engine.pipeline.rewrite_validate import validate_source_fidelity


class TestSourceFidelity(unittest.TestCase):
    def test_unsupported_number_fails(self):
        ok, msg = validate_source_fidelity(
            title="정책 개편",
            body="<p>정부는 30% 감축을 시행한다.</p>",
            article={"title": "정책 개편", "body": "정부는 제도를 시행한다."},
        )
        self.assertFalse(ok)
        self.assertIn("원문에 없는 수치", msg)

    def test_unsupported_detail_from_list_fails(self):
        ok, msg = validate_source_fidelity(
            title="전력 정책",
            body="<p>정부는 시범 운영을 확대한다. 전남 주민 수혜가 크다.</p>",
            article={"title": "전력 정책", "body": "정부는 전력 정책을 추진한다."},
        )
        self.assertFalse(ok)
        self.assertIn("원문에 없는 구체화", msg)

    def test_supported_number_and_detail_pass(self):
        source = "정부는 시범 운영을 시작한다. 전남에서 30% 감축한다."
        ok, msg = validate_source_fidelity(
            title="전력 정책",
            body="<p>정부는 시범 운영을 시작한다. 전남에서 30% 감축한다.</p>",
            article={"title": "전력 정책", "body": source},
            excerpt="시범 운영을 시작한다.",
        )
        self.assertTrue(ok, msg)

    def test_short_source_prompt_safety_text_present(self):
        common = (ROOT / "prompts" / "news_editor_common.md").read_text(encoding="utf-8")
        ij = (ROOT / "prompts" / "news_editor_ij.md").read_text(encoding="utf-8")
        self.assertIn("원문에 없는 비용, 요금, 사업자 선정, 시범 운영", common)
        self.assertIn("짧은 정책 단신이면 3문단 450~650자", common)
        self.assertIn("저정보 원문 안전 모드", ij)
        self.assertIn("없는 축을 추정해 채우지 않는다", ij)


if __name__ == "__main__":
    unittest.main()
