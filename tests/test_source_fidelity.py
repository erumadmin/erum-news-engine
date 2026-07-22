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
        self.assertIn("저정보 원문", ij)
        self.assertIn("추정하지 않는다", ij)
        self.assertIn("의무화", common)
        self.assertIn("상충", ij)

    def test_unsupported_norm_verb_의무화_fails(self):
        source = (
            "정부는 소비자 보호 정책을 개편했다. 위생용품 용량을 줄이면 3개월 전 알린다. "
            "공정거래위원회는 제조·유통업체와 협약을 체결했다."
        )
        ok, msg = validate_source_fidelity(
            title="위생용품 용량 줄이면 3개월 전 고지 의무화",
            body="<p>정부가 사전 고지를 의무화했다.</p><p>협약을 체결했다.</p>",
            article={"title": "소비자 보호 정책 개편", "body": source},
            excerpt="사전 고지를 의무화했다.",
        )
        self.assertFalse(ok)
        self.assertIn("원문에 없는 규범 주장", msg)

    def test_supported_norm_verb_의무화_passes(self):
        source = "정부는 사전 고지를 의무화했다. 3개월 전 알린다."
        ok, msg = validate_source_fidelity(
            title="고지 의무화",
            body="<p>정부는 사전 고지를 의무화했다.</p>",
            article={"title": "고지", "body": source},
        )
        self.assertTrue(ok, msg)

    def test_internal_contradiction_시행일_fails(self):
        source = "정부는 정책을 개편하고 시행일을 공표했다. 3개월 전 알린다. 협약을 체결했다."
        body = (
            "<p>정부는 정책을 개편하고 시행일을 공표했다.</p>"
            "<p>기존 문제가 있었다.</p>"
            "<p>3개월 전 고지한다.</p>"
            "<p>다만 정책의 구체적인 시행일은 이번 공표에서 명시되지 않았다.</p>"
        )
        ok, msg = validate_source_fidelity(
            title="정책 개편",
            body=body,
            article={"title": "정책 개편", "body": source},
        )
        self.assertFalse(ok)
        self.assertIn("본문 내부 모순", msg)

    def test_thin_source_invented_background_fails(self):
        source = (
            "정부는 소비자 보호 정책을 개편하고 시행일을 공표했다. "
            "위생용품 용량을 줄이면 3개월 전 알린다. 협약을 체결했다."
        )
        body = (
            "<p>정부는 정책을 개편했다. 협약을 체결했다.</p>"
            "<p>기존에는 내용량이 줄어도 인지하기 어려웠다. "
            "슈링크플레이션 우려가 제기되어 왔다.</p>"
            "<p>3개월 전 알려야 한다.</p>"
            "<p>다만 이행 여부는 관찰이 필요하다.</p>"
        )
        ok, msg = validate_source_fidelity(
            title="정책 개편",
            body=body,
            article={"title": "정책 개편", "body": source},
            packet={"risk_flags": ["thin_source_body"]},
        )
        self.assertFalse(ok)
        self.assertIn("얇은 원문 배경 창작", msg)

    def test_dry_run_20260721_rewrite_fails_fidelity(self):
        source = (
            "정부는 소비자 보호 정책을 개편하고 시행일을 공표했다. 국민과 기업에 영향을 미치며 "
            "의무 사항을 명시했다. 가격 정보는 참가격에서 확인할 수 있다. 앞으로 위생용품의 "
            "용량·개수 등을 줄일 경우 제품 포장과 판매장소 등에 3개월 이상 먼저 알리고, "
            "변경 정보를 공개한다. 공정거래위원회는 한국소비자원, 한국소비자중심기업협회, "
            "위생용품 제조·유통업체와 협약을 체결했다고 밝혔다. 단위 사양 축소 정보는 "
            "참가격 누리집에 공개한다."
        )
        body = (
            "<p>정부는 소비자 보호 정책을 개편하고 시행일을 공표했다. 공정거래위원회는 "
            "한국소비자원, 한국소비자중심기업협회, 위생용품 제조 및 유통업체와 협약을 "
            "체결하며 정책 개편을 공표했다. 이번 조치는 국민과 기업 모두에게 영향을 "
            "미치는 의무 사항으로 명시됐다.</p>"
            "<p>기존에는 제품의 내용량이 줄어들어도 소비자가 이를 즉시 인지하기 어려운 "
            "경우가 많았다. 이로 인해 단위 가격 상승이 포장 변경 없이 이뤄지는 "
            "'슈링크플레이션' 우려가 제기되어 왔다.</p>"
            "<p>새로운 규정에 따라 업체는 위생용품의 용량 또는 개수를 축소할 경우, "
            "변경 사항을 제품 포장과 판매 장소에 3개월 이상 먼저 알려야 한다. "
            "단위 사양이 축소된 정보는 정부 가격정보 포털인 참가격 누리집을 통해 "
            "공개되며, 소비자단체 관계자는 해당 사이트에서 품목별 고시 일정과 변경 "
            "전후 사양을 확인할 수 있다.</p>"
            "<p>다만 정책의 구체적인 시행일은 이번 공표에서 명시되지 않았다. "
            "협약을 통한 자발적 실천을 유도하는 방식이어서 법적 강제력의 범위와 "
            "실제 이행 여부는 추가 관찰이 필요하다.</p>"
        )
        ok, msg = validate_source_fidelity(
            title="위생용품 용량 줄이면 3개월 전 고지 의무화",
            body=body,
            article={"title": "소비자 보호 정책 개편", "body": source},
            excerpt="정부가 소비자 보호 정책을 개편해 사전 고지를 의무화했다.",
            packet={"risk_flags": ["thin_source_body"]},
        )
        self.assertFalse(ok, msg)


if __name__ == "__main__":
    unittest.main()
