"""P4 regression: stage-specific providers and Gemini/OpenRouter fallbacks."""
from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def _load_engine():
    spec = importlib.util.spec_from_file_location("erum_news_engine_main_p4", ROOT / "engine.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class TestLlmProviderDefaults(unittest.TestCase):
    def test_provider_default_literals(self):
        src = (ROOT / "engine.py").read_text(encoding="utf-8")
        self.assertIn('os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")', src)
        self.assertIn('os.environ.get("LLM_PROVIDER", "upstage")', src)
        self.assertIn('os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-v4-pro")', src)
        self.assertIn('QA_MODEL or "deepseek/deepseek-v4-flash"', src)
        self.assertIn(
            'os.environ.get("OPENROUTER_REWRITE_FALLBACK_MODELS", "deepseek/deepseek-v3.2")',
            src,
        )
        self.assertIn('GEMINI_REWRITE_MIN_OUTPUT_TOKENS", "8000"', src)
        self.assertIn('GEMINI_QA_MIN_OUTPUT_TOKENS", "3000"', src)


class TestAskLlmProviderSelection(unittest.TestCase):
    def setUp(self):
        self.eng = _load_engine()

    def test_missing_upstage_uses_gemini_when_available(self):
        self.eng.UPSTAGE_API_KEY = ""
        self.eng.GEMINI_API_KEY = "g-key"
        self.eng.REWRITE_PROVIDER = "upstage"
        with mock.patch.object(self.eng, "_ask_gemini_rest", return_value="gemini-ok") as gemini:
            out = self.eng.ask_llm("sys", "user", stage="rewrite")
        self.assertEqual(out, "gemini-ok")
        gemini.assert_called_once()

    def test_upstage_401_falls_back_to_gemini(self):
        self.eng.UPSTAGE_API_KEY = "u-key"
        self.eng.GEMINI_API_KEY = "g-key"
        self.eng.REWRITE_PROVIDER = "upstage"

        class Resp:
            status_code = 401

            def raise_for_status(self):
                import requests

                raise requests.HTTPError("401", response=self)

        with mock.patch.object(self.eng.requests, "post", return_value=Resp()):
            with mock.patch.object(self.eng, "_ask_gemini_rest", return_value="fallback-ok") as gemini:
                out = self.eng.ask_llm("sys", "user", stage="rewrite")
        self.assertEqual(out, "fallback-ok")
        gemini.assert_called_once()

    def test_stage_specific_providers(self):
        self.eng.UPSTAGE_API_KEY = "u-key"
        self.eng.GEMINI_API_KEY = "g-key"
        self.eng.OPENROUTER_API_KEY = "o-key"
        self.eng.REWRITE_PROVIDER = "gemini"
        self.eng.QA_PROVIDER = "openrouter"
        with mock.patch.object(self.eng, "_ask_gemini_rest", return_value="rw") as gemini:
            with mock.patch.object(self.eng, "_ask_openrouter", return_value="qa") as openrouter:
                self.assertEqual(self.eng.ask_llm("s", "u", stage="rewrite"), "rw")
                self.assertEqual(self.eng.ask_llm("s", "u", stage="qa"), "qa")
        gemini.assert_called_once()
        openrouter.assert_called_once()

    def test_source_gate_openrouter_key_does_not_force_editorial_openrouter(self):
        self.eng.UPSTAGE_API_KEY = "u-key"
        self.eng.OPENROUTER_API_KEY = "gate-key"
        self.eng.REWRITE_PROVIDER = "upstage"
        self.eng.QA_PROVIDER = "upstage"

        class Resp:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "upstage-ok"}}]}

        with mock.patch.object(self.eng.requests, "post", return_value=Resp()) as post:
            with mock.patch.object(self.eng, "_ask_openrouter") as openrouter:
                out = self.eng.ask_llm("s", "u", stage="rewrite")
        self.assertEqual(out, "upstage-ok")
        openrouter.assert_not_called()
        post.assert_called_once()


class TestQaParseFallback(unittest.TestCase):
    def test_gemini_qa_parse_failure_uses_local_quality(self):
        eng = _load_engine()
        eng.QA_PROVIDER = "gemini"
        body = (
            "<p>정부는 다음 달 1일부터 소비자 보호 정책을 시행한다. 대상은 일반 국민이다.</p>"
            "<p>그동안 현장에서는 부담과 혼란이 있었다.</p>"
            "<p>신청과 확인은 공식 안내 페이지에서 이뤄진다.</p>"
            "<p>다만 시행 범위와 적용 조건에 따라 효과가 달라질 수 있어 유의해야 한다.</p>"
        )
        with mock.patch.object(eng, "ask_llm", return_value="not-json"):
            with mock.patch.object(eng, "validate_content_quality", return_value=(True, "OK")):
                ok, fails, score, fixed = eng.ai_quality_check(
                    "소비자 보호 정책 개편 시행",
                    "정부가 정책을 시행한다.",
                    body,
                    "IJ_",
                )
        self.assertTrue(ok)
        self.assertEqual(score, 78)
        self.assertIsNone(fixed)
        self.assertTrue(any("파싱 실패" in f for f in fails))


if __name__ == "__main__":
    unittest.main()
