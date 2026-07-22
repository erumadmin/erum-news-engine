"""Category alias normalize + keyword fallback before DEFAULT_CATEGORY."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_engine_py():
    spec = importlib.util.spec_from_file_location(
        "erum_news_engine_category", ROOT / "engine.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


eng = _load_engine_py()


class TestNormalizeCategoryAliases(unittest.TestCase):
    def test_policy_near_miss_maps_to_politics(self):
        self.assertEqual(eng.normalize_category_name("정책"), "정치")

    def test_it_science_aliases(self):
        self.assertEqual(eng.normalize_category_name("IT과학"), "IT/과학")
        self.assertEqual(eng.normalize_category_name("IT/과학"), "IT/과학")
        self.assertEqual(eng.normalize_category_name("tech"), "IT/과학")
        self.assertEqual(eng.normalize_category_name("과학"), "IT/과학")

    def test_existing_canonical_unchanged(self):
        for name in ("정치", "사회", "경제", "IT/과학", "문화/생활", "국제", "환경"):
            self.assertEqual(eng.normalize_category_name(name), name)

    def test_common_near_miss_aliases(self):
        self.assertEqual(eng.normalize_category_name("행정"), "정치")
        self.assertEqual(eng.normalize_category_name("산업"), "경제")
        self.assertEqual(eng.normalize_category_name("금융"), "경제")
        self.assertEqual(eng.normalize_category_name("복지"), "사회")
        self.assertEqual(eng.normalize_category_name("교육"), "사회")
        self.assertEqual(eng.normalize_category_name("외교"), "국제")
        self.assertEqual(eng.normalize_category_name("기후"), "환경")
        self.assertEqual(eng.normalize_category_name("문화"), "문화/생활")


class TestHybridMetaKeywordFallback(unittest.TestCase):
    def test_empty_ai_cat_uses_keyword_hit(self):
        title = "대통령 국회 예산안 처리"
        body = "대통령과 국회가 예산안을 처리한다."
        cat, _tags = eng.get_hybrid_meta(title, body, "", [])
        self.assertEqual(cat, "정치")

    def test_none_ai_cat_uses_keyword_hit(self):
        title = "반도체 AI 플랫폼 기술 투자"
        body = "인공지능과 반도체 기술 경쟁이 가속화된다."
        cat, _tags = eng.get_hybrid_meta(title, body, None, [])
        self.assertEqual(cat, "IT/과학")

    def test_unknown_label_uses_keyword_before_default(self):
        title = "기후 탄소 중립 ESG 에너지 전환"
        body = "환경부와 탄소중립 정책이 추진된다."
        cat, _tags = eng.get_hybrid_meta(title, body, "기타", [])
        self.assertEqual(cat, "환경")

    def test_unknown_with_no_keywords_falls_to_default(self):
        title = "오늘 날씨 안내"
        body = "구름이 조금 낀다."
        cat, _tags = eng.get_hybrid_meta(title, body, "알수없음", [])
        self.assertEqual(cat, eng.DEFAULT_CATEGORY)

    def test_policy_label_maps_even_without_body_keywords(self):
        title = "브리핑 요약"
        body = "관련 내용을 정리했다."
        cat, _tags = eng.get_hybrid_meta(title, body, "정책", [])
        self.assertEqual(cat, "정치")

    def test_valid_ai_cat_unchanged(self):
        cat, _tags = eng.get_hybrid_meta(
            "제목", "본문 경제 금융 투자", "경제", ["투자"]
        )
        self.assertEqual(cat, "경제")


class TestCategoryPromptConstraint(unittest.TestCase):
    def test_common_prompt_lists_slash_canonical_names(self):
        text = (ROOT / "prompts" / "news_editor_common.md").read_text(encoding="utf-8")
        self.assertIn("IT/과학", text)
        self.assertIn("문화/생활", text)
        # Near-miss freeform labels should be discouraged
        self.assertRegex(text, r"7개|일곱|오직|그대로|금지")


if __name__ == "__main__":
    unittest.main()
