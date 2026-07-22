"""Desk Fit routing + prompt North Star presence."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from engine.pipeline.desk_fit import cb_is_nonfit
from engine.profiles import route_primary
from engine.profiles.cb import CBProfile
from engine.profiles.ij import IJProfile
from engine.profiles.nn import NNProfile


class TestDeskFit(unittest.TestCase):
    def test_cb_rejects_icu_performance_subsidy(self):
        raw = {
            "title": "중환자 진료 많이 할수록 더 보상…중환자실 부하지수 도입",
            "body": (
                "상급종합병원이 중환자 진료를 많이 할수록 더 많은 보상을 받게 된다. "
                "보건복지부는 중환자실 부하지수를 도입하고 성과보상을 차등 지급한다. "
                "병상과 간호 등급, 건강보험 청구자료를 기준으로 한다."
            ),
            "source_type": "policy_briefing",
            "url": "https://www.korea.kr/news/policyNewsView.do?newsId=148968481",
        }
        nonfit, reason = cb_is_nonfit(raw)
        self.assertTrue(nonfit, reason)
        cand = CBProfile().candidate_filter(raw)
        self.assertFalse(cand.accept)
        self.assertIn("cb_nonfit", cand.reason)

    def test_cb_accepts_logistics_safety(self):
        raw = {
            "title": "국토부, 물류시설 화재안전관리체계 전면 개선",
            "body": (
                "대형 물류창고·공장 사업주는 소방설비 기준을 맞춰야 한다. "
                "미이행 시 시정명령·과태료 대상이며 일정 규모 미만은 유예된다. "
                "조달·계약 조건에도 반영될 수 있다."
            ),
            "source_type": "policy_briefing",
        }
        nonfit, reason = cb_is_nonfit(raw)
        self.assertFalse(nonfit, reason)
        cand = CBProfile().candidate_filter(raw)
        self.assertTrue(cand.accept, cand.reason)

    def test_icu_routes_away_from_cb(self):
        raw = {
            "title": "중환자 진료 많이 할수록 더 보상…중환자실 부하지수 도입",
            "body": (
                "상급종합병원 중환자실 부하지수와 성과보상, 병상, 환자 진료. "
                "정책 제도 시행 지원 개편."
            ),
            "source_type": "policy_briefing",
            "url": "https://www.korea.kr/x",
        }
        route = route_primary(raw)
        self.assertNotEqual(route.site, "CB")

    def test_desk_prompts_have_north_star_and_hard_fail(self):
        for name, needle in (
            ("news_editor_ij.md", "구조·대상·한계"),
            ("news_editor_nn.md", "생활 안내"),
            ("news_editor_cb.md", "의무·비용·일정"),
        ):
            text = (ROOT / "prompts" / name).read_text(encoding="utf-8")
            self.assertIn("Hard-Fail", text)
            self.assertIn(needle, text)
            self.assertIn("prompts/desks/", text)

    def test_desks_compare_example_exists(self):
        p = ROOT / "prompts" / "desks" / "compare_example_icu.md"
        self.assertTrue(p.is_file())
        text = p.read_text(encoding="utf-8")
        self.assertIn("CB", text)
        self.assertIn("비적합", text)


    def test_desk_v10_mechanism_in_para2_passes(self):
        from engine.pipeline.rewrite_validate import validate_paragraph_roles

        paras = [
            "정부가 중환자실 부하지수를 도입해 상급종합병원 보상을 개편한다. " * 2,
            "부하지수는 병상·간호 등급·청구자료를 기준으로 산정하고 성과보상과 연계한다. " * 2,
            "적용 대상은 상급종합병원이며 시범 규모와 예외는 원문 범위다. " * 2,
            "다만 시범 기간과 전국 확대 일정은 아직 확정되지 않았다. " * 2,
        ]
        ok, msg = validate_paragraph_roles(paras)
        self.assertTrue(ok, msg)

    def test_assess_cb_fit_skips_icu(self):
        import importlib.util

        from engine.pipeline.desk_fit import cb_is_nonfit

        raw = {
            "title": "중환자 진료 많이 할수록 더 보상…중환자실 부하지수 도입",
            "body": "상급종합병원 중환자실 부하지수 성과보상 병상 환자 진료 건강보험 청구",
        }
        self.assertTrue(cb_is_nonfit(raw)[0])
        spec = importlib.util.spec_from_file_location(
            "erum_engine_main", ROOT / "engine.py"
        )
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        mode, reason = mod.assess_cb_article_fit(raw)
        self.assertEqual(mode, "skip")
        self.assertIn("cb_nonfit", reason)


class TestDeskPromptSafetyStillPresent(unittest.TestCase):
    def test_ij_short_source_and_fidelity_lines(self):
        common = (ROOT / "prompts" / "news_editor_common.md").read_text(encoding="utf-8")
        ij = (ROOT / "prompts" / "news_editor_ij.md").read_text(encoding="utf-8")
        self.assertIn("원문에 없는 비용, 요금, 사업자 선정, 시범 운영", common)
        self.assertIn("저정보 원문", ij)
        self.assertIn("의무화", ij)
        self.assertIn("상충", ij)


if __name__ == "__main__":
    unittest.main()
