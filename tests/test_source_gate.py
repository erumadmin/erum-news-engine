#!/usr/bin/env python3
"""Offline/unit tests for newswire source gate."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from collections import Counter
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline.media_plan import build_media_plan_for_editorial
from engine.pipeline.source_gate import (
    GateDecision,
    SourceGateConfig,
    SourceGateStats,
    best_local_route,
    compute_local_scores,
    decide_article,
    is_public_policy_signal,
    is_recruit_promo,
    is_soft_cb_promo,
    is_weak_nn_promo,
    local_hard_drop,
    parse_llm_gate_json,
    ranking_score,
    revalidate_route_decision,
    screen_newswire_candidates,
)
from engine.types import EditorialContext, PlacementScore


def _long_ko(n: int = 900, *, topical: bool = True) -> str:
    if topical:
        base = "중소기업 ESG 공시 대응과 공급망 실사 규제가 확대되고 있다. "
    else:
        base = "오늘 날씨가 맑고 바람이 선선하다. 점심 메뉴를 고민하는 사람들이 많다. "
    return (base * ((n // len(base)) + 1))[:n]


class TestLocalHardDrop(unittest.TestCase):
    def test_short_body_drops_without_llm(self):
        cfg = SourceGateConfig(min_body_chars=800)
        art = {
            "title": "테스트 주식회사, ESG 공시 안내",
            "body": "짧은 본문",
            "image": "https://cdn.example.com/photo.jpg",
        }
        d = local_hard_drop(art, cfg=cfg)
        self.assertIsNotNone(d)
        self.assertEqual(d.decision, "DROP")
        self.assertIn("short_body", d.reason)

    def test_promo_title_drops(self):
        cfg = SourceGateConfig(min_body_chars=800)
        art = {
            "title": "여름 할인 쿠폰 이벤트 진행",
            "body": _long_ko(),
            "image": "https://cdn.example.com/photo.jpg",
        }
        d = local_hard_drop(art, cfg=cfg)
        self.assertEqual(d.decision, "DROP")
        self.assertIn("promo", d.reason)

    def test_no_image_drops(self):
        cfg = SourceGateConfig(min_body_chars=800, soft_image_for_cb=True)
        art = {
            "title": "환경 정책과 복지 제도 개선",
            "body": _long_ko(topical=False) + " 정책 제도 복지 환경 공공기관 ",
            "image": "https://cdn.newswire.co.kr/newswire_logo.png",
        }
        d = local_hard_drop(art, cfg=cfg)
        self.assertEqual(d.decision, "DROP")
        self.assertEqual(d.reason, "no_usable_image")

    def test_no_image_soft_for_cb(self):
        cfg = SourceGateConfig(min_body_chars=800, soft_image_for_cb=True)
        art = {
            "title": "중기 ESG 공시·공급망 규제 안내",
            "body": _long_ko() + " ESG CSR 탄소 공급망 공시 규제",
            "image": "",
        }
        d = local_hard_drop(art, cfg=cfg)
        self.assertIsNone(d)
        self.assertTrue(art.get("_no_image_soft"))

    def test_award_frame_drops_even_with_context(self):
        cfg = SourceGateConfig(min_body_chars=800)
        art = {
            "title": "독거노인종합지원센터, 대통령 표창 수상",
            "body": (
                "취약계층 복지 정책과 사회문제 대응, 공공기관 돌봄체계를 구축했다. "
                + ("본문내용 " * 200)
            ),
            "image": "https://cdn.example.com/photo.jpg",
        }
        d = local_hard_drop(art, cfg=cfg)
        self.assertIsNotNone(d)
        self.assertEqual(d.decision, "DROP")
        self.assertEqual(d.reason, "award_frame")

    def test_award_only_drops(self):
        cfg = SourceGateConfig(min_body_chars=800)
        art = {
            "title": "○○기업, 혁신 대상 수상",
            "body": "우리 회사는 최고 혁신 기업으로 선정되었습니다. " + ("홍보문장 " * 200),
            "image": "https://cdn.example.com/photo.jpg",
        }
        d = local_hard_drop(art, cfg=cfg)
        self.assertIsNotNone(d)
        self.assertEqual(d.decision, "DROP")
        self.assertIn("award", d.reason)


class TestLocalScores(unittest.TestCase):
    def test_cb_preferred_for_esg(self):
        art = {
            "title": "중기 ESG 공시·공급망 규제 대응 가이드",
            "body": _long_ko() + " ESG CSR 탄소 공급망 공시 규제 투자",
            "image": "https://cdn.example.com/a.jpg",
        }
        scores = compute_local_scores(art)
        site, score = best_local_route(scores)
        self.assertEqual(site, "CB")
        self.assertGreaterEqual(score, 35)


class TestDecideThresholds(unittest.TestCase):
    def test_auto_drop_below_skips_llm(self):
        cfg = SourceGateConfig(
            auto_drop_below=35,
            auto_route_above=82,
            min_body_chars=100,
        )
        art = {
            "title": "일반 소식",
            "body": _long_ko(200, topical=False),
            "image": "https://cdn.example.com/a.jpg",
        }
        # Force low scores by using empty-ish content after hard filter passes
        calls = {"n": 0}

        def boom(*_a, **_k):
            calls["n"] += 1
            raise AssertionError("LLM should not be called")

        d = decide_article(art, cfg=cfg, llm_enabled=True, http_post=boom)
        self.assertEqual(d.decision, "DROP")
        self.assertEqual(calls["n"], 0)
        self.assertTrue(d.stage.startswith("local"))

    def test_auto_route_above_skips_llm(self):
        cfg = SourceGateConfig(
            auto_drop_below=35,
            auto_route_above=50,
            min_body_chars=100,
        )
        art = {
            "title": "ESG 공시 공급망 규제 탄소 금융 투자 지속가능성",
            "body": _long_ko(200) + " ESG CSR 탄소 공급망 공시 규제 투자 AI 보안 금융 지속가능성",
            "image": "https://cdn.example.com/a.jpg",
        }
        calls = {"n": 0}

        def boom(*_a, **_k):
            calls["n"] += 1
            raise AssertionError("LLM should not be called")

        d = decide_article(art, cfg=cfg, llm_enabled=True, http_post=boom)
        self.assertEqual(d.decision, "ROUTE")
        self.assertEqual(d.site, "CB")
        self.assertEqual(calls["n"], 0)
        self.assertEqual(d.stage, "local_route")

    def test_ambiguous_calls_llm_once(self):
        cfg = SourceGateConfig(
            auto_drop_below=10,
            auto_route_above=95,
            llm_min_score=10,
            llm_max_score=94,
            min_body_chars=100,
            openrouter_api_key="test-key",
            llm_retry=0,
        )
        art = {
            "title": "지역 주민 생활 건강 교육 안내",
            "body": _long_ko(200, topical=False) + " 지역 주민 생활 건강 교육 문화",
            "image": "https://cdn.example.com/a.jpg",
            "url": "https://www.newswire.co.kr/newsRead.php?no=1",
        }

        class Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "decision": "ROUTE",
                                        "site": "NN",
                                        "score": 70,
                                        "reason": "생활·지역 정보",
                                        "rewrite_angle": "주민 체감 포인트",
                                        "risk_flags": ["PR_TONE"],
                                        "must_avoid": ["최고 표현"],
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ]
                }

        mock_post = MagicMock(return_value=Resp())
        d = decide_article(art, cfg=cfg, llm_enabled=True, http_post=mock_post)
        self.assertEqual(d.decision, "ROUTE")
        self.assertEqual(d.site, "NN")
        self.assertEqual(mock_post.call_count, 1)

    def test_site_cap_skips_llm(self):
        cfg = SourceGateConfig(
            auto_drop_below=10,
            auto_route_above=95,
            llm_min_score=10,
            llm_max_score=94,
            min_body_chars=100,
            max_per_site_per_run=1,
            max_ij_per_run=1,
            openrouter_api_key="test-key",
        )
        art = {
            "title": "지역 주민 생활 건강 교육 안내",
            "body": _long_ko(200, topical=False) + " 지역 주민 생활 건강 교육 문화 관광 소상공인 소비자",
            "image": "https://cdn.example.com/a.jpg",
        }
        site_counts = Counter({"NN": 1, "CB": 1, "IJ": 1})
        calls = {"n": 0}

        def boom(*_a, **_k):
            calls["n"] += 1
            raise AssertionError("LLM should not be called when all sites capped")

        d = decide_article(
            art,
            cfg=cfg,
            llm_enabled=True,
            http_post=boom,
            site_counts=site_counts,
        )
        self.assertEqual(d.decision, "DROP")
        self.assertIn("site_cap", d.reason)
        self.assertEqual(calls["n"], 0)

    def test_preferred_cb_site_cap_not_below_threshold(self):
        """CB=49 preferred but capped → site_cap:CB, not local_below_threshold:IJ."""
        cfg = SourceGateConfig(
            auto_drop_below=35,
            auto_route_above=82,
            min_body_chars=100,
            max_per_site_per_run=3,
            max_ij_per_run=2,
            openrouter_api_key="test-key",
        )
        art = {
            "title": "한화큐셀, 미국 애리조나에 초대형 에너지 복합단지 건설",
            "body": _long_ko(200, topical=False) + " 투자 공급망",
            "image": "https://cdn.example.com/a.jpg",
        }
        scores = {"IJ": 32.0, "NN": 20.0, "CB": 49.0, "pr_penalty": 0.0}
        site_counts = Counter({"CB": 3})  # CB full; IJ/NN still open
        stats = SourceGateStats()
        calls = {"n": 0}

        def boom(*_a, **_k):
            calls["n"] += 1
            raise AssertionError("LLM must not run when preferred site is capped")

        with patch("engine.pipeline.source_gate.compute_local_scores", return_value=scores):
            d = decide_article(
                art,
                cfg=cfg,
                stats=stats,
                llm_enabled=True,
                http_post=boom,
                site_counts=site_counts,
            )
        self.assertEqual(d.decision, "DROP")
        self.assertEqual(d.reason, "site_cap:CB")
        self.assertNotIn("below_threshold", d.reason)
        self.assertEqual(calls["n"], 0)
        self.assertEqual(stats.llm_calls, 0)
        self.assertEqual(stats.llm_skipped_site_cap, 1)

    def test_preferred_nn_site_cap_not_below_threshold(self):
        """NN=68 preferred but capped → site_cap:NN (복날 오리류)."""
        cfg = SourceGateConfig(
            auto_drop_below=35,
            auto_route_above=82,
            min_body_chars=100,
            max_per_site_per_run=3,
            max_ij_per_run=2,
            openrouter_api_key="test-key",
        )
        art = {
            "title": "복날 맞아 지역 주민 생활 오리 특선 안내",
            "body": _long_ko(200, topical=False) + " 지역 주민 생활 건강 문화",
            "image": "https://cdn.example.com/a.jpg",
        }
        scores = {"IJ": 32.0, "NN": 68.0, "CB": 25.0, "pr_penalty": 0.0}
        site_counts = Counter({"NN": 3})
        stats = SourceGateStats()
        calls = {"n": 0}

        def boom(*_a, **_k):
            calls["n"] += 1
            raise AssertionError("LLM must not run when preferred NN is capped")

        with patch("engine.pipeline.source_gate.compute_local_scores", return_value=scores):
            d = decide_article(
                art,
                cfg=cfg,
                stats=stats,
                llm_enabled=True,
                http_post=boom,
                site_counts=site_counts,
            )
        self.assertEqual(d.decision, "DROP")
        self.assertEqual(d.reason, "site_cap:NN")
        self.assertNotIn("below_threshold", d.reason)
        self.assertEqual(calls["n"], 0)
        self.assertEqual(stats.llm_skipped_site_cap, 1)

    def test_weak_nn_promo_skips_local_auto_route(self):
        """금천 에어로빅류: 신규 프로그램·인기 → local_auto_route 금지, weak_nn_promo DROP."""
        cfg = SourceGateConfig(
            auto_drop_below=35,
            auto_route_above=50,
            llm_min_score=10,
            llm_max_score=100,
            min_body_chars=100,
            openrouter_api_key="test-key",
            llm_retry=0,
        )
        art = {
            "title": "금천구민문화체육센터, 신규 프로그램 ‘스텝박스 에어로빅’ 인기",
            "body": (
                _long_ko(200, topical=False)
                + " 지역 주민 생활 건강 교육 문화 관광 신규 프로그램 인기 모집"
                + " 행정 안전 센터 안내"  # incidental body hits must not clear weak promo
            ),
            "image": "https://cdn.example.com/a.jpg",
            "url": "https://www.newswire.co.kr/newsRead.php?no=99",
        }
        self.assertTrue(is_weak_nn_promo(art))

        calls = {"n": 0}

        def boom(*_a, **_k):
            calls["n"] += 1
            raise AssertionError("weak NN promo must DROP without LLM auto-route path")

        with patch(
            "engine.pipeline.source_gate.compute_local_scores",
            return_value={"IJ": 20.0, "NN": 92.0, "CB": 25.0, "pr_penalty": 0.0},
        ):
            d = decide_article(art, cfg=cfg, llm_enabled=True, http_post=boom)
        self.assertEqual(calls["n"], 0)
        self.assertEqual(d.decision, "DROP")
        self.assertEqual(d.reason, "weak_nn_promo")
        self.assertNotIn("local_auto_route", d.reason)
        self.assertNotEqual(d.stage, "local_route")

    def test_aerobics_title_is_weak_nn_promo(self):
        art = {
            "title": "금천구민문화체육센터, 신규 프로그램 ‘스텝박스 에어로빅’ 인기",
            "body": _long_ko(200, topical=False) + " 지역 주민 생활 건강 교육 문화",
            "image": "https://cdn.example.com/a.jpg",
        }
        self.assertTrue(is_weak_nn_promo(art))

    def test_public_nn_not_weak_promo(self):
        art = {
            "title": "고립은둔 청년 복지 지원 정책 안내",
            "body": _long_ko(200, topical=False) + " 복지 정책 공공 돌봄 취약계층 사회문제 지역 주민",
            "image": "https://cdn.example.com/a.jpg",
        }
        self.assertFalse(is_weak_nn_promo(art))
        self.assertTrue(is_public_policy_signal(art))

    def test_public_policy_article_not_weak_promo(self):
        art = {
            "title": "서울시 고립은둔 청년 조례·예산 지원 확대",
            "body": _long_ko(200, topical=False) + " 정책 복지 취약계층 공모사업 지역 주민",
            "image": "https://cdn.example.com/a.jpg",
        }
        self.assertTrue(is_public_policy_signal(art))
        self.assertFalse(is_weak_nn_promo(art))

    def test_dbridge_recruit_promo_detected(self):
        art = {
            "title": "청년과 동아일보가 함께하는 ‘D-Bridge 미디어 커리어 빌드업’ 3·4기 교육생 모집",
            "body": (
                _long_ko(200, topical=False)
                + " 미디어 커리어 빌드업 교육생 모집 파트너 프로그램 수강생"
            ),
            "image": "https://cdn.example.com/a.jpg",
        }
        self.assertTrue(is_recruit_promo(art))
        self.assertFalse(is_public_policy_signal(art))

    def test_dbridge_recruit_drops_not_nn_route(self):
        """D-Bridge-class 교육생 모집 must DROP — not NN ROUTE (llm off / local)."""
        cfg = SourceGateConfig(
            auto_drop_below=10,
            auto_route_above=50,
            llm_min_score=10,
            llm_max_score=100,
            min_body_chars=100,
            openrouter_api_key="test-key",
            llm_retry=0,
        )
        art = {
            "title": "청년과 동아일보가 함께하는 ‘D-Bridge 미디어 커리어 빌드업’ 3·4기 교육생 모집",
            "body": (
                _long_ko(200, topical=False)
                + " 지역 주민 생활 건강 교육 문화 미디어 커리어 빌드업 교육생 모집"
            ),
            "image": "https://cdn.example.com/a.jpg",
            "url": "https://www.newswire.co.kr/newsRead.php?no=dbridge",
        }
        calls = {"n": 0}

        def boom(*_a, **_k):
            calls["n"] += 1
            raise AssertionError("recruit promo must DROP without LLM")

        with patch(
            "engine.pipeline.source_gate.compute_local_scores",
            return_value={"IJ": 20.0, "NN": 68.0, "CB": 25.0, "pr_penalty": 0.0},
        ):
            d = decide_article(art, cfg=cfg, llm_enabled=False, http_post=boom)
        self.assertEqual(calls["n"], 0)
        self.assertEqual(d.decision, "DROP")
        self.assertEqual(d.reason, "recruit_promo")
        self.assertNotEqual(d.site, "NN")

    def test_dbridge_body_public_keywords_still_recruit_drop(self):
        """Title-strong cohort (교육생 모집 + 미디어 커리어) must DROP even if body has 고립/은둔/복지."""
        cfg = SourceGateConfig(
            auto_drop_below=10,
            auto_route_above=50,
            llm_min_score=10,
            llm_max_score=100,
            min_body_chars=100,
            openrouter_api_key="test-key",
            llm_retry=0,
        )
        art = {
            "title": "청년과 동아일보가 함께하는 ‘D-Bridge 미디어 커리어 빌드업’ 3·4기 교육생 모집",
            "body": (
                _long_ko(200, topical=False)
                + " 고립 은둔 청년 복지 지원 미디어 커리어 교육생 모집 파트너 프로그램"
            ),
            "image": "https://cdn.example.com/a.jpg",
            "url": "https://www.newswire.co.kr/newsRead.php?no=dbridge-body-public",
        }
        # Body public keywords trip is_public_policy_signal, but must not clear title-strong recruit.
        self.assertTrue(is_public_policy_signal(art))
        self.assertTrue(is_recruit_promo(art))

        calls = {"n": 0}

        def boom(*_a, **_k):
            calls["n"] += 1
            raise AssertionError("title-strong recruit must DROP without LLM")

        with patch(
            "engine.pipeline.source_gate.compute_local_scores",
            return_value={"IJ": 20.0, "NN": 68.0, "CB": 25.0, "pr_penalty": 0.0},
        ):
            d = decide_article(art, cfg=cfg, llm_enabled=False, http_post=boom)
        self.assertEqual(calls["n"], 0)
        self.assertEqual(d.decision, "DROP")
        self.assertEqual(d.reason, "recruit_promo")
        self.assertNotEqual(d.site, "NN")

    def test_public_isolated_youth_still_routes_nn(self):
        """고립은둔 / 학교밖 public programs must NOT false-positive as recruit_promo."""
        cfg = SourceGateConfig(
            auto_drop_below=10,
            auto_route_above=50,
            min_body_chars=100,
        )
        art = {
            "title": "서울시 고립은둔 청소년 체험 프로그램·학교밖 지원 확대",
            "body": (
                _long_ko(200, topical=False)
                + " 복지 정책 고립은둔 학교밖 취약계층 돌봄 지역 주민 생활 교육"
            ),
            "image": "https://cdn.example.com/a.jpg",
        }
        self.assertTrue(is_public_policy_signal(art))
        self.assertFalse(is_recruit_promo(art))
        self.assertFalse(is_weak_nn_promo(art))

        with patch(
            "engine.pipeline.source_gate.compute_local_scores",
            return_value={"IJ": 40.0, "NN": 85.0, "CB": 20.0, "pr_penalty": 0.0},
        ):
            d = decide_article(art, cfg=cfg, llm_enabled=False)
        self.assertEqual(d.decision, "ROUTE")
        self.assertEqual(d.site, "NN")

    def test_ij_dominates_cb_revalidate_to_ij(self):
        """밀리언드림즈-class: local IJ=58 ≫ CB=31 → cannot stay CB."""
        art = {
            "title": "사회적기업 밀리언드림즈, 교정시설 AI 실무 교육 확대",
            "body": _long_ko(200, topical=False) + " 복지 정책 교육 취약계층 사회문제 공공기관",
            "image": "https://cdn.example.com/a.jpg",
        }
        scores = {"IJ": 58.0, "NN": 40.0, "CB": 31.0, "pr_penalty": 0.0}
        raw = GateDecision(
            "ROUTE",
            site="CB",
            score=75,
            reason="llm_cb",
            stage="llm",
            scores=scores,
            must_avoid=["IJ"],
        )
        out = revalidate_route_decision(art, raw, scores, allowed=["IJ", "NN", "CB"])
        self.assertEqual(out.decision, "ROUTE")
        self.assertEqual(out.site, "IJ")
        self.assertIn("ij_fidelity", out.reason)

    def test_ij_dominates_cb_decide_cannot_stay_cb(self):
        """Patched scores IJ=58 CB=31: decide path must not ship as CB."""
        cfg = SourceGateConfig(
            auto_drop_below=10,
            auto_route_above=50,
            min_body_chars=100,
        )
        art = {
            "title": "사회적기업 밀리언드림즈, 교정시설 AI 실무 교육",
            "body": _long_ko(200, topical=False) + " 복지 정책 교육 취약계층 사회문제",
            "image": "https://cdn.example.com/a.jpg",
        }
        scores = {"IJ": 58.0, "NN": 40.0, "CB": 31.0, "pr_penalty": 0.0}
        with patch("engine.pipeline.source_gate.compute_local_scores", return_value=scores):
            with patch(
                "engine.pipeline.source_gate.best_local_route",
                return_value=("CB", 75.0),
            ):
                d = decide_article(art, cfg=cfg, llm_enabled=False)
        self.assertEqual(d.decision, "ROUTE")
        self.assertEqual(d.site, "IJ")
        self.assertNotEqual(d.site, "CB")

    def test_recruit_promo_rank_penalty_if_routed(self):
        """If recruit somehow ROUTE, ranking must heavily penalize vs public NN."""
        recruit = {
            "title": "D-Bridge 미디어 커리어 빌드업 3기 교육생 모집",
            "body": _long_ko(200, topical=False) + " 미디어 커리어 교육생 모집",
            "image": "https://cdn.example.com/r.jpg",
        }
        public = {
            "title": "서울시 고립은둔 청년 복지 지원 정책 확대",
            "body": _long_ko(200, topical=False) + " 복지 정책 돌봄 취약계층 사회문제 지역 주민",
            "image": "https://cdn.example.com/p.jpg",
        }
        self.assertTrue(is_recruit_promo(recruit))
        recruit_d = GateDecision(
            "ROUTE", site="NN", score=68, scores={"IJ": 20, "NN": 68, "CB": 25, "pr_penalty": 0}
        )
        public_d = GateDecision(
            "ROUTE", site="NN", score=80, scores={"IJ": 55, "NN": 80, "CB": 20, "pr_penalty": 0}
        )
        self.assertGreater(ranking_score(public, public_d), ranking_score(recruit, recruit_d))

    def test_bitgo_product_launch_is_soft_cb_promo(self):
        art = {
            "title": "비트고, 비트코인 월렛용 새로운 양자 위험 관리 기능 출시",
            "body": (
                _long_ko(200, topical=False)
                + " AI 보안 금융 투자 기관 대상 양자 위험 평가 월렛 기능 출시"
            ),
            "image": "https://cdn.example.com/bitgo.jpg",
        }
        self.assertTrue(is_soft_cb_promo(art))

    def test_elliptic_partner_program_is_soft_cb_promo(self):
        art = {
            "title": "엘립틱, 서클의 에이전틱 디자인 파트너 프로그램 참여 발표",
            "body": (
                _long_ko(200, topical=False)
                + " 블록체인 디지털 자산 컴플라이언스 솔루션 파트너 프로그램 AI 보안 금융"
            ),
            "image": "https://cdn.example.com/elliptic.jpg",
        }
        self.assertTrue(is_soft_cb_promo(art))

    def test_defiance_etf_launch_is_soft_cb_promo(self):
        """Defiance-class UCITS ETF / fund product launch must be soft_cb_promo."""
        art = {
            "title": "Defiance, 유럽 최초 포토닉스 UCITS ETF 출시",
            "body": (
                _long_ko(200, topical=False)
                + " 포토닉스 AI 인프라 데이터센터 공급망 변화 투자 금융 UCITS ETF 출시"
            ),
            "image": "https://cdn.example.com/defiance.jpg",
        }
        self.assertTrue(is_soft_cb_promo(art))

    def test_fund_etn_launch_is_soft_cb_promo(self):
        art = {
            "title": "○○자산운용, 신규 ETN·상장지수펀드 출시",
            "body": (
                _long_ko(200, topical=False)
                + " 신규 ETF 펀드 출시 투자 상품 안내 AI 보안 금융"
            ),
            "image": "https://cdn.example.com/etn.jpg",
        }
        self.assertTrue(is_soft_cb_promo(art))

    def test_hanwha_epc_not_soft_cb_promo(self):
        art = {
            "title": "한화큐셀, 미국 애리조나에 초대형 에너지 복합단지 건설",
            "body": (
                _long_ko(200, topical=False)
                + " 재생에너지 공급망 EPC 투자 계약 공장 건설 IRA 정책"
            ),
            "image": "https://cdn.example.com/hanwha.jpg",
        }
        self.assertFalse(is_soft_cb_promo(art))

    def test_russell_ma_not_soft_cb_promo(self):
        art = {
            "title": "러셀 인베스트먼트, 새로운 장기 주주 발표",
            "body": (
                _long_ko(200, topical=False)
                + " 장기 주주 지분 인수 합병 투자 금융 공시"
            ),
            "image": "https://cdn.example.com/russell.jpg",
        }
        self.assertFalse(is_soft_cb_promo(art))

    def test_soft_cb_promo_hard_drops(self):
        """BitGo/Elliptic/Defiance-class soft CB must hard DROP soft_cb_promo (no CB auto-route)."""
        cfg = SourceGateConfig(
            auto_drop_below=10,
            auto_route_above=50,
            min_body_chars=100,
            openrouter_api_key="test-key",
            llm_retry=0,
        )
        bitgo = {
            "title": "비트고, 비트코인 월렛용 새로운 양자 위험 관리 기능 출시",
            "body": (
                _long_ko(200, topical=False)
                + " AI 보안 금융 투자 기관 대상 양자 위험 평가 월렛 기능 출시"
            ),
            "image": "https://cdn.example.com/bitgo.jpg",
            "url": "https://www.newswire.co.kr/newsRead.php?no=bitgo",
        }
        elliptic = {
            "title": "엘립틱, 서클의 에이전틱 디자인 파트너 프로그램 참여 발표",
            "body": (
                _long_ko(200, topical=False)
                + " 블록체인 디지털 자산 컴플라이언스 파트너 프로그램 AI 보안"
            ),
            "image": "https://cdn.example.com/elliptic.jpg",
            "url": "https://www.newswire.co.kr/newsRead.php?no=elliptic",
        }
        defiance = {
            "title": "Defiance, 유럽 최초 포토닉스 UCITS ETF 출시",
            "body": (
                _long_ko(200, topical=False)
                + " 포토닉스 AI 인프라 데이터센터 공급망 변화 투자 금융 UCITS ETF 출시"
            ),
            "image": "https://cdn.example.com/defiance.jpg",
            "url": "https://www.newswire.co.kr/newsRead.php?no=defiance",
        }
        calls = {"n": 0}

        def boom(*_a, **_k):
            calls["n"] += 1
            raise AssertionError("soft CB promo must DROP without LLM")

        for art in (bitgo, elliptic, defiance):
            with patch(
                "engine.pipeline.source_gate.compute_local_scores",
                return_value={"IJ": 20.0, "NN": 25.0, "CB": 85.0, "pr_penalty": 8.0},
            ):
                d = decide_article(art, cfg=cfg, llm_enabled=True, http_post=boom)
            self.assertEqual(d.decision, "DROP", msg=art["title"])
            self.assertEqual(d.reason, "soft_cb_promo", msg=art["title"])
            self.assertNotEqual(d.site, "CB")
        self.assertEqual(calls["n"], 0)

    def test_hanwha_epc_still_routes_cb(self):
        """한화큐셀-class EPC / 에너지 복합단지 must still ROUTE CB."""
        cfg = SourceGateConfig(
            auto_drop_below=10,
            auto_route_above=50,
            min_body_chars=100,
        )
        art = {
            "title": "한화큐셀, 미국 애리조나에 초대형 에너지 복합단지 건설",
            "body": (
                _long_ko(200, topical=False)
                + " 재생에너지 공급망 EPC 투자 계약 공장 건설 IRA 정책"
            ),
            "image": "https://cdn.example.com/hanwha.jpg",
        }
        self.assertFalse(is_soft_cb_promo(art))
        with patch(
            "engine.pipeline.source_gate.compute_local_scores",
            return_value={"IJ": 32.0, "NN": 20.0, "CB": 85.0, "pr_penalty": 0.0},
        ):
            d = decide_article(art, cfg=cfg, llm_enabled=False)
        self.assertEqual(d.decision, "ROUTE")
        self.assertEqual(d.site, "CB")

    def test_russell_ma_still_routes_cb(self):
        """러셀 M&A / 장기 주주 must still ROUTE CB (not soft ETF drop)."""
        cfg = SourceGateConfig(
            auto_drop_below=10,
            auto_route_above=50,
            min_body_chars=100,
        )
        art = {
            "title": "러셀 인베스트먼트, 새로운 장기 주주 발표",
            "body": (
                _long_ko(200, topical=False)
                + " 장기 주주 지분 인수 합병 투자 금융 공시"
            ),
            "image": "https://cdn.example.com/russell.jpg",
        }
        self.assertFalse(is_soft_cb_promo(art))
        with patch(
            "engine.pipeline.source_gate.compute_local_scores",
            return_value={"IJ": 20.0, "NN": 25.0, "CB": 78.0, "pr_penalty": 0.0},
        ):
            d = decide_article(art, cfg=cfg, llm_enabled=False)
        self.assertEqual(d.decision, "ROUTE")
        self.assertEqual(d.site, "CB")

    def test_soft_cb_revalidate_drops_cb_route(self):
        """LLM/local CB ROUTE of soft promo must revalidate to soft_cb_promo DROP."""
        art = {
            "title": "엘립틱, 서클의 에이전틱 디자인 파트너 프로그램 참여 발표",
            "body": _long_ko(200, topical=False) + " 파트너 프로그램 AI 보안 금융",
            "image": "https://cdn.example.com/e.jpg",
        }
        scores = {"IJ": 20.0, "NN": 25.0, "CB": 67.0, "pr_penalty": 8.0}
        raw = GateDecision(
            "ROUTE", site="CB", score=67, reason="llm_cb", stage="llm", scores=scores
        )
        out = revalidate_route_decision(art, raw, scores, allowed=["IJ", "NN", "CB"])
        self.assertEqual(out.decision, "DROP")
        self.assertEqual(out.reason, "soft_cb_promo")

    def test_defiance_etf_revalidate_drops_llm_cb(self):
        """LLM cannot ROUTE Defiance-class soft ETF launch as CB."""
        art = {
            "title": "Defiance, 유럽 최초 포토닉스 UCITS ETF 출시",
            "body": (
                _long_ko(200, topical=False)
                + " 포토닉스 AI 인프라 데이터센터 공급망 변화 투자 금융 UCITS ETF 출시"
            ),
            "image": "https://cdn.example.com/defiance.jpg",
        }
        scores = {"IJ": 20.0, "NN": 25.0, "CB": 78.0, "pr_penalty": 32.0}
        raw = GateDecision(
            "ROUTE", site="CB", score=78, reason="llm_cb_etf", stage="llm", scores=scores
        )
        out = revalidate_route_decision(art, raw, scores, allowed=["IJ", "NN", "CB"])
        self.assertEqual(out.decision, "DROP")
        self.assertEqual(out.reason, "soft_cb_promo")
        self.assertNotEqual(out.site, "CB")

    def test_soft_cb_rank_loses_to_hanwha_when_cap1(self):
        """BitGo soft CB must lose CB slot (cap=1) to 한화 EPC keeper under rank fill."""
        cfg = SourceGateConfig(
            max_selected_per_run=1,
            max_per_site_per_run=1,
            max_ij_per_run=1,
            auto_drop_below=10,
            auto_route_above=50,
            min_body_chars=100,
        )
        bitgo = {
            "title": "비트고, 비트코인 월렛용 새로운 양자 위험 관리 기능 출시",
            "body": (
                _long_ko(200, topical=False)
                + " AI 보안 금융 투자 월렛 기능 출시 양자 위험 관리"
            ),
            "image": "https://cdn.example.com/bitgo.jpg",
            "url": "https://www.newswire.co.kr/newsRead.php?no=bitgo",
        }
        hanwha = {
            "title": "한화큐셀, 미국 애리조나에 초대형 에너지 복합단지 건설",
            "body": (
                _long_ko(200, topical=False)
                + " 재생에너지 공급망 EPC 투자 계약 공장 건설 IRA"
            ),
            "image": "https://cdn.example.com/hanwha.jpg",
            "url": "https://www.newswire.co.kr/newsRead.php?no=hanwha",
        }
        self.assertTrue(is_soft_cb_promo(bitgo))
        self.assertFalse(is_soft_cb_promo(hanwha))

        score_map = {
            bitgo["url"]: {"IJ": 20.0, "NN": 25.0, "CB": 90.0, "pr_penalty": 8.0},
            hanwha["url"]: {"IJ": 32.0, "NN": 20.0, "CB": 70.0, "pr_penalty": 0.0},
        }

        def fake_scores(article):
            return dict(score_map[article["url"]])

        with patch("engine.pipeline.source_gate.compute_local_scores", side_effect=fake_scores):
            selected, _stats, decisions = screen_newswire_candidates(
                [bitgo, hanwha],
                cfg=cfg,
                llm_enabled=False,
                daily_published=0,
                daily_limit=50,
            )
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["url"], hanwha["url"])
        self.assertEqual(selected[0]["_source_gate_site"], "CB")
        bitgo_d = next(d for d in decisions if d.get("url") == bitgo["url"])
        self.assertEqual(bitgo_d["decision"], "DROP")
        self.assertIn("soft_cb_promo", bitgo_d.get("reason") or "")

        # Even if BitGo somehow ROUTE CB, rank must lose to Hanwha
        fake_bitgo = GateDecision("ROUTE", site="CB", score=90, scores=score_map[bitgo["url"]])
        hanwha_route = GateDecision("ROUTE", site="CB", score=70, scores=score_map[hanwha["url"]])
        self.assertGreater(
            ranking_score(hanwha, hanwha_route),
            ranking_score(bitgo, fake_bitgo),
        )

    def test_hanwha_ops_cb_score_beats_mid_soft_esg(self):
        """한화 EPC/복합단지 local CB must beat mid soft-ESG CB_BOOST fluff (~49 hole)."""
        hanwha = {
            "title": "한화큐셀, 미국 애리조나에 초대형 에너지 복합단지 건설",
            "body": (
                _long_ko(200, topical=False)
                + " 재생에너지 공급망 EPC 투자 계약 공장 건설 IRA 정책"
            ),
            "image": "https://cdn.example.com/hanwha.jpg",
        }
        mid_esg = {
            "title": "가든프로젝트, ESG Solutions와 지속가능성 투자 확대",
            "body": (
                _long_ko(200, topical=False)
                + " ESG 탄소 지속가능성 투자 친환경 솔루션"
            ),
            "image": "https://cdn.example.com/garden.jpg",
        }
        h_scores = compute_local_scores(hanwha)
        m_scores = compute_local_scores(mid_esg)
        self.assertGreaterEqual(h_scores["CB"], 70.0)
        self.assertGreater(h_scores["CB"], m_scores["CB"])
        h_d = GateDecision("ROUTE", site="CB", score=h_scores["CB"], scores=h_scores)
        m_d = GateDecision("ROUTE", site="CB", score=m_scores["CB"], scores=m_scores)
        self.assertGreater(ranking_score(hanwha, h_d), ranking_score(mid_esg, m_d))

    def test_hanwha_ops_cb_wins_rank_vs_mid_cb_cap1(self):
        """Under run/site cap=1, 한화 substantive CB must beat mid soft-ESG CB."""
        cfg = SourceGateConfig(
            max_selected_per_run=1,
            max_per_site_per_run=1,
            max_ij_per_run=1,
            auto_drop_below=10,
            auto_route_above=50,
            min_body_chars=100,
        )
        mid_esg = {
            "title": "가든프로젝트, ESG Solutions와 지속가능성 투자 확대",
            "body": (
                _long_ko(200, topical=False)
                + " ESG 탄소 지속가능성 투자 친환경 솔루션"
            ),
            "image": "https://cdn.example.com/garden.jpg",
            "url": "https://www.newswire.co.kr/newsRead.php?no=garden",
        }
        hanwha = {
            "title": "한화큐셀, 미국 애리조나에 초대형 에너지 복합단지 건설",
            "body": (
                _long_ko(200, topical=False)
                + " 재생에너지 공급망 EPC 투자 계약 공장 건설 IRA"
            ),
            "image": "https://cdn.example.com/hanwha.jpg",
            "url": "https://www.newswire.co.kr/newsRead.php?no=hanwha",
        }
        selected, _stats, decisions = screen_newswire_candidates(
            [mid_esg, hanwha],
            cfg=cfg,
            llm_enabled=False,
            daily_published=0,
            daily_limit=50,
        )
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["url"], hanwha["url"])
        self.assertEqual(selected[0]["_source_gate_site"], "CB")
        mid_d = next(d for d in decisions if d.get("url") == mid_esg["url"])
        self.assertEqual(mid_d["decision"], "DROP")
        self.assertIn("rank", mid_d.get("reason") or "")

    def test_llm_empty_json_fallback_routes_when_local_strong(self):
        """Empty LLM content → llm_fallback_local ROUTE when local ops CB is strong."""
        cfg = SourceGateConfig(
            auto_drop_below=35,
            auto_route_above=120,  # keep ops-boosted CB in LLM band
            llm_min_score=10,
            llm_max_score=119,
            min_body_chars=100,
            openrouter_api_key="test-key",
            llm_retry=0,
        )
        art = {
            "title": "한화큐셀, 미국 애리조나에 초대형 에너지 복합단지 건설",
            "body": (
                _long_ko(200, topical=False)
                + " 재생에너지 공급망 EPC 투자 계약 공장 건설 IRA 정책"
            ),
            "image": "https://cdn.example.com/hanwha.jpg",
            "url": "https://www.newswire.co.kr/newsRead.php?no=hanwha-fb",
        }

        class Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": ""}}]}

        mock_post = MagicMock(return_value=Resp())
        d = decide_article(art, cfg=cfg, llm_enabled=True, http_post=mock_post)
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(d.decision, "ROUTE")
        self.assertEqual(d.site, "CB")
        self.assertEqual(d.stage, "llm_fallback")
        self.assertIn("llm_fallback_local", d.reason)
        self.assertNotEqual(d.stage, "parse_fail")

    def test_llm_empty_json_still_drops_when_local_weak(self):
        """Empty LLM content → parse_fail DROP when local scores are also weak."""
        cfg = SourceGateConfig(
            auto_drop_below=35,
            auto_route_above=95,
            llm_min_score=10,
            llm_max_score=94,
            min_body_chars=100,
            openrouter_api_key="test-key",
            llm_retry=0,
        )
        art = {
            "title": "일반 회사 소식 안내",
            "body": _long_ko(200, topical=False) + " 오늘 행사 안내 문의처",
            "image": "https://cdn.example.com/weak.jpg",
            "url": "https://www.newswire.co.kr/newsRead.php?no=weak-fb",
        }

        class Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": ""}}]}

        mock_post = MagicMock(return_value=Resp())
        # Force ambiguous mid-band with weak scores so LLM path runs.
        with patch(
            "engine.pipeline.source_gate.compute_local_scores",
            return_value={"IJ": 20.0, "NN": 22.0, "CB": 38.0, "pr_penalty": 0.0},
        ):
            with patch(
                "engine.pipeline.source_gate.best_local_route",
                return_value=("CB", 38.0),
            ):
                d = decide_article(art, cfg=cfg, llm_enabled=True, http_post=mock_post)
        self.assertEqual(d.decision, "DROP")
        self.assertEqual(d.stage, "parse_fail")
        self.assertIn("llm_parse_or_call_fail", d.reason)

    def test_llm_empty_json_fallback_public_nn(self):
        """Public NN with strong local score must fallback-ROUTE on empty LLM JSON."""
        cfg = SourceGateConfig(
            auto_drop_below=35,
            auto_route_above=95,
            llm_min_score=10,
            llm_max_score=94,
            min_body_chars=100,
            openrouter_api_key="test-key",
            llm_retry=0,
        )
        art = {
            "title": "종로구 학교밖청소년지원센터, 학교밖 청소년 복지 지원 업무협약",
            "body": (
                _long_ko(200, topical=False)
                + " 복지 정책 학교밖 취약계층 돌봄 지역 주민 생활 교육"
            ),
            "image": "https://cdn.example.com/jongno.jpg",
            "url": "https://www.newswire.co.kr/newsRead.php?no=jongno-fb",
        }
        self.assertTrue(is_public_policy_signal(art))

        class Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": ""}}]}

        mock_post = MagicMock(return_value=Resp())
        with patch(
            "engine.pipeline.source_gate.compute_local_scores",
            return_value={"IJ": 45.0, "NN": 68.0, "CB": 20.0, "pr_penalty": 0.0},
        ):
            d = decide_article(art, cfg=cfg, llm_enabled=True, http_post=mock_post)
        self.assertEqual(d.decision, "ROUTE")
        self.assertEqual(d.site, "NN")
        self.assertEqual(d.stage, "llm_fallback")
        self.assertIn("llm_fallback_local:NN", d.reason)

    def test_llm_ij_award_revalidated_to_drop(self):
        art = {
            "title": "센터, 대통령 표창 수상",
            "_award_frame": True,
            "body": _long_ko(),
        }
        scores = {"IJ": 70, "NN": 40, "CB": 20, "pr_penalty": 8}
        raw = GateDecision("ROUTE", site="IJ", score=78, reason="공공성", stage="llm", scores=scores)
        out = revalidate_route_decision(art, raw, scores, allowed=["IJ", "NN", "CB"])
        self.assertEqual(out.decision, "DROP")
        self.assertIn("award", out.reason)

    def test_parse_fail_stage_distinct_from_llm_calls(self):
        """Bug C: parse_fail increments parse_fail_drops, not llm_drop alone via llm stage."""
        from engine.pipeline.source_gate import GateDecision

        stats = SourceGateStats()
        stats.llm_calls = 1  # call was attempted
        d = GateDecision(
            "DROP",
            score=0,
            reason="llm_parse_or_call_fail:bad json",
            stage="parse_fail",
            risk_flags=["LLM_FAIL"],
        )
        stats.record_decision(d)
        self.assertEqual(stats.parse_fail_drops, 1)
        self.assertEqual(stats.llm_drop, 0)
        self.assertEqual(stats.local_drop, 1)
        self.assertEqual(stats.drop_reasons.get("llm_parse_or_call_fail"), 1)


class TestParseLlm(unittest.TestCase):
    def test_parse_route_and_drop(self):
        route = parse_llm_gate_json(
            '{"decision":"ROUTE","site":"CB","score":78,"reason":"ok",'
            '"rewrite_angle":"a","risk_flags":["PR_TONE"],"must_avoid":[]}'
        )
        self.assertEqual(route.decision, "ROUTE")
        self.assertEqual(route.site, "CB")
        drop = parse_llm_gate_json(
            '{"decision":"DROP","site":null,"score":28,"reason":"홍보",'
            '"rewrite_angle":null,"risk_flags":["AWARD_ONLY"],"must_avoid":[]}'
        )
        self.assertEqual(drop.decision, "DROP")
        self.assertIsNone(drop.site)

    def test_invalid_site_raises(self):
        with self.assertRaises(ValueError):
            parse_llm_gate_json(
                '{"decision":"ROUTE","site":"XY","score":80,"reason":"x",'
                '"rewrite_angle":null,"risk_flags":[],"must_avoid":[]}'
            )


class TestScreenCaps(unittest.TestCase):
    def test_max_selected_and_single_site(self):
        cfg = SourceGateConfig(
            max_selected_per_run=2,
            max_per_site_per_run=2,
            auto_drop_below=10,
            auto_route_above=40,
            min_body_chars=100,
        )
        cands = []
        for i in range(5):
            cands.append(
                {
                    "title": f"기업{i}, ESG 공시 공급망 규제 대응",
                    "body": _long_ko(200) + " ESG 공시 공급망 규제 탄소 투자",
                    "image": f"https://cdn.example.com/{i}.jpg",
                    "url": f"https://www.newswire.co.kr/newsRead.php?no={i}",
                }
            )
        selected, stats, decisions = screen_newswire_candidates(
            cands, cfg=cfg, llm_enabled=False, daily_published=0, daily_limit=50
        )
        self.assertLessEqual(len(selected), 2)
        self.assertEqual(stats.final_selected, len(selected))
        for item in selected:
            self.assertIn(item.get("_source_gate_site"), ("IJ", "NN", "CB"))
            # 1원문=1매체 metadata
            self.assertEqual(len([item["_source_gate_site"]]), 1)

    def test_rank_fill_prefers_higher_score_within_site_cap(self):
        """Low-score NN arriving first must lose the slot to a higher-score NN."""
        cfg = SourceGateConfig(
            max_selected_per_run=1,
            max_per_site_per_run=1,
            max_ij_per_run=1,
            auto_drop_below=10,
            auto_route_above=50,
            min_body_chars=100,
        )
        weak = {
            "title": "지역 주민 생활 건강 안내 A",
            "body": _long_ko(200, topical=False) + " 지역 주민 생활 건강 문화 교육",
            "image": "https://cdn.example.com/weak.jpg",
            "url": "https://www.newswire.co.kr/newsRead.php?no=1",
        }
        strong = {
            "title": "고립은둔 청년 복지 지원 정책 확대",
            "body": _long_ko(200, topical=False) + " 복지 정책 공공 돌봄 취약계층 사회문제 지역 주민 생활",
            "image": "https://cdn.example.com/strong.jpg",
            "url": "https://www.newswire.co.kr/newsRead.php?no=2",
        }
        score_map = {
            weak["url"]: {"IJ": 20.0, "NN": 70.0, "CB": 15.0, "pr_penalty": 0.0},
            strong["url"]: {"IJ": 25.0, "NN": 90.0, "CB": 20.0, "pr_penalty": 0.0},
        }

        def fake_scores(article):
            return dict(score_map[article["url"]])

        with patch("engine.pipeline.source_gate.compute_local_scores", side_effect=fake_scores):
            # Arrival order: weak first — FIFO would pick weak; rank fill must pick strong
            selected, stats, decisions = screen_newswire_candidates(
                [weak, strong],
                cfg=cfg,
                llm_enabled=False,
                daily_published=0,
                daily_limit=50,
            )
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["url"], strong["url"])
        self.assertEqual(selected[0]["_source_gate_site"], "NN")
        capped = [d for d in decisions if d.get("decision") == "DROP" and "rank" in (d.get("reason") or "")]
        self.assertTrue(any("site_cap" in (d.get("reason") or "") for d in capped))
        weak_d = GateDecision("ROUTE", site="NN", score=70, scores=score_map[weak["url"]])
        strong_d = GateDecision("ROUTE", site="NN", score=90, scores=score_map[strong["url"]])
        self.assertGreater(ranking_score(strong, strong_d), ranking_score(weak, weak_d))

    def test_rank_fill_public_beats_aerobics_weak_nn(self):
        """High-score aerobics NN must lose the run slot to slightly lower public NN/IJ."""
        cfg = SourceGateConfig(
            max_selected_per_run=1,
            max_per_site_per_run=2,
            max_ij_per_run=2,
            auto_drop_below=10,
            auto_route_above=50,
            min_body_chars=100,
        )
        aerobics = {
            "title": "금천구민문화체육센터, 신규 프로그램 ‘스텝박스 에어로빅’ 인기",
            "body": (
                _long_ko(200, topical=False)
                + " 지역 주민 생활 건강 교육 문화 관광 신규 프로그램 인기 모집 행정 안전"
            ),
            "image": "https://cdn.example.com/aero.jpg",
            "url": "https://www.newswire.co.kr/newsRead.php?no=aero",
        }
        public_nn = {
            "title": "서울시 고립은둔 청년 복지 지원 정책 확대",
            "body": _long_ko(200, topical=False) + " 복지 정책 돌봄 취약계층 사회문제 지역 주민 생활",
            "image": "https://cdn.example.com/public.jpg",
            "url": "https://www.newswire.co.kr/newsRead.php?no=public",
        }
        self.assertTrue(is_weak_nn_promo(aerobics))
        self.assertFalse(is_weak_nn_promo(public_nn))

        score_map = {
            aerobics["url"]: {"IJ": 20.0, "NN": 92.0, "CB": 15.0, "pr_penalty": 0.0},
            public_nn["url"]: {"IJ": 55.0, "NN": 80.0, "CB": 20.0, "pr_penalty": 0.0},
        }

        def fake_scores(article):
            return dict(score_map[article["url"]])

        with patch("engine.pipeline.source_gate.compute_local_scores", side_effect=fake_scores):
            selected, _stats, decisions = screen_newswire_candidates(
                [aerobics, public_nn],
                cfg=cfg,
                llm_enabled=False,
                daily_published=0,
                daily_limit=50,
            )
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["url"], public_nn["url"])
        aero_d = next(d for d in decisions if d.get("url") == aerobics["url"])
        self.assertEqual(aero_d["decision"], "DROP")
        self.assertTrue(
            "weak_nn_promo" in (aero_d.get("reason") or "")
            or "rank" in (aero_d.get("reason") or ""),
            msg=f"unexpected aerobics decision: {aero_d}",
        )
        # Even if aerobics were ROUTE, rank_score must lose to public
        fake_aero_route = GateDecision("ROUTE", site="NN", score=92, scores=score_map[aerobics["url"]])
        public_route = GateDecision("ROUTE", site="NN", score=80, scores=score_map[public_nn["url"]])
        self.assertGreater(
            ranking_score(public_nn, public_route),
            ranking_score(aerobics, fake_aero_route),
        )


class TestMediaPlanSourceGate(unittest.TestCase):
    def test_source_gate_cb_not_skipped_by_fit(self):
        ctx = EditorialContext(
            assigned_site="CB",
            routing_reason="source_gate:CB",
            publish_grade="B",
            placement=PlacementScore(total=55, slot="ledger"),
            packet={"site": "CB", "publish_grade": "B", "risk_flags": []},
            evidence=[],
            use_packet_writing=True,
        )
        article = {"_source_gate_site": "CB", "title": "행사 개최", "body": "홍보"}
        plan = build_media_plan_for_editorial(
            ctx,
            assess_cb_article_fit=lambda _a: ("skip", "weak"),
            article=article,
        )
        self.assertTrue(plan["CB_"]["enabled"])
        self.assertFalse(plan["IJ_"]["enabled"])
        self.assertFalse(plan["NN_"]["enabled"])


if __name__ == "__main__":
    unittest.main()
