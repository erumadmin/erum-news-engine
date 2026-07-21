"""P3 regression: Korea crawler defaults and source-gate quota invariants."""
import importlib.util
import os
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def _load_engine():
    spec = importlib.util.spec_from_file_location("erum_news_engine_main", ROOT / "engine.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class TestKoreaCrawlerConfig(unittest.TestCase):
    def test_defaults_include_policy_mobile_fallback_and_retry_days(self):
        eng = _load_engine()
        self.assertTrue(eng.KOREA_CRAWLER_ENABLED)
        self.assertEqual(eng.KOREA_CRAWLER_SOURCES[0], "policy")
        self.assertIn("policy", eng.KOREA_CRAWLER_SOURCES)
        self.assertEqual(eng.RETRY_DAYS, 3)
        for key in ("press", "briefing", "policy"):
            cfg = eng.KOREA_POLICY_SOURCES[key]
            self.assertTrue(cfg.get("fallback_urls"))
            self.assertTrue(any("m.korea.kr" in u for u in cfg["fallback_urls"]))

    def test_screened_mode_policy_quota_leaves_room_for_newswire(self):
        eng = _load_engine()
        self.assertEqual(eng.NEWSWIRE_DAYTIME_MODE, "screened")
        limit = 10
        reserved = min(eng.NEWSWIRE_MAX_SELECTED_PER_RUN, limit)
        policy_limit = max(0, limit - reserved)
        self.assertLessEqual(policy_limit + reserved, limit)
        self.assertGreater(reserved, 0)
        self.assertLess(policy_limit, limit)


class TestSourceGateQuota(unittest.TestCase):
    def test_screen_respects_max_selected_and_daily_share(self):
        from engine.pipeline.source_gate import SourceGateConfig, screen_newswire_candidates

        cfg = SourceGateConfig(
            auto_drop_below=10,
            auto_route_above=50,
            llm_min_score=10,
            llm_max_score=49,
            max_selected_per_run=2,
            max_daily_share_pct=30,
            openrouter_api_key="",
        )
        candidates = []
        for i in range(6):
            candidates.append(
                {
                    "url": f"https://www.newswire.co.kr/newsRead.php?no={1000 + i}",
                    "url_id": f"nw_{1000 + i}",
                    "title": f"정책 지원 확대 보도 {i} 정부는 제도를 시행한다",
                    "body": (
                        "정부는 중소기업 지원 정책을 확대한다고 밝혔다. "
                        "대상은 중소기업이며 시행일은 다음 달이다. "
                        "신청 절차와 지원 규모를 공식 안내에서 확인한다. " * 3
                    ),
                    "image": "https://file.newswire.co.kr/data/sample.jpg",
                    "source_type": "newswire",
                    "source_published_at": "2026-07-12T09:00:00+09:00",
                }
            )
        selected, stats, decisions = screen_newswire_candidates(
            candidates,
            cfg=cfg,
            llm_enabled=False,
            daily_published=0,
            daily_limit=10,
        )
        self.assertLessEqual(len(selected), 2)
        # 30% of daily_limit=10 => at most 3, plus per-run 2 => 2
        self.assertLessEqual(len(selected), max(0, int(10 * 0.30)))


if __name__ == "__main__":
    unittest.main()
