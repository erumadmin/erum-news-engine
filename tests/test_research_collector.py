#!/usr/bin/env python3
"""Unit tests for deterministic research collection (no network)."""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import research_collector as rc  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "research"


class TestLinkDiscovery(unittest.TestCase):
    def test_extract_urls_from_plain_text(self):
        body = "정보는 참가격(www.price.go.kr) 누리집에 공개한다."
        urls = rc.extract_urls_from_text(body)
        self.assertEqual(len(urls), 1)
        self.assertIn("price.go.kr", urls[0][0])

    def test_extract_links_from_html(self):
        html = (FIXTURES / "policy_with_links.html").read_text(encoding="utf-8")
        links = rc.extract_links_from_html(html, "https://www.korea.kr/news/policyNewsView.do?newsId=1")
        from urllib.parse import urlparse

        hosts = {urlparse(u).netloc for u, _, _ in links}
        self.assertIn("www.ftc.go.kr", hosts)
        self.assertIn("www.price.go.kr", hosts)
        self.assertIn("www.law.go.kr", hosts)
        self.assertNotIn("www.facebook.com", hosts)

    def test_classify_official_domains(self):
        _, etype, rank = rc.classify_domain("https://www.mss.go.kr/site/some/path")
        self.assertEqual(etype, "government")
        self.assertGreaterEqual(rank, 80)

    def test_build_evidence_plan_from_cached_fixture(self):
        raw = json.loads((FIXTURES / "cached_source.json").read_text(encoding="utf-8"))
        html = (FIXTURES / "policy_with_links.html").read_text(encoding="utf-8")
        raw["raw_html"] = html

        plan = rc.build_evidence_plan(raw, assigned_site="IJ", max_fetch=3)
        self.assertGreaterEqual(len(plan.link_candidates), 3)
        self.assertGreaterEqual(len(plan.fetch_targets), 1)
        ranks = [t.reliability_rank for t in plan.fetch_targets]
        self.assertTrue(all(r >= 80 for r in ranks))

    def test_build_evidence_plan_body_only_finds_price_go_kr(self):
        raw = json.loads((FIXTURES / "cached_source.json").read_text(encoding="utf-8"))
        plan = rc.build_evidence_plan(raw, max_fetch=3)
        hosts = [c.domain for c in plan.link_candidates]
        self.assertTrue(any("price.go.kr" in h for h in hosts))

    def test_infer_ministry_hub_from_body(self):
        raw = {
            "url": "https://www.korea.kr/news/policyNewsView.do?newsId=1",
            "title": "t",
            "body": "공정거래위원회는 협약을 체결했다고 밝혔다.",
        }
        plan = rc.build_evidence_plan(raw)
        types = {c.evidence_type for c in plan.link_candidates}
        self.assertIn("ministry_press_hub", types)
        self.assertTrue(any("ftc.go.kr" in c.url for c in plan.link_candidates))

    def test_build_evidence_plan_no_links_notes(self):
        raw = {"url": "https://example.com/a", "title": "t", "body": "링크 없는 짧은 공지입니다."}
        plan = rc.build_evidence_plan(raw)
        self.assertEqual(plan.link_candidates, [])
        self.assertTrue(any("링크 없음" in n for n in plan.notes))


class TestEvidenceFetch(unittest.TestCase):
    def test_collect_evidence_with_mock_fetcher(self):
        raw = json.loads((FIXTURES / "cached_source.json").read_text(encoding="utf-8"))
        html = (FIXTURES / "policy_with_links.html").read_text(encoding="utf-8")
        raw["raw_html"] = html

        mock_html = """
        <html><head><title>공정위 보도자료</title></head>
        <body><article><p>위생용품 내용량 변경 시 사전 고지 의무를 강화합니다.</p></article></body></html>
        """

        def fetcher(url: str):
            resp = MagicMock()
            resp.status_code = 200
            resp.text = mock_html
            return resp

        plan, items = rc.collect_evidence(raw, fetcher, max_fetch=2)
        self.assertLessEqual(len(items), 2)
        ok = [i for i in items if i.fetch_status == "ok"]
        self.assertGreaterEqual(len(ok), 1)
        self.assertIn("보도자료", ok[0].title)

    def test_fetch_error_recorded(self):
        def bad_fetcher(url: str):
            return None

        item = rc.fetch_evidence_page("https://www.ftc.go.kr/www/", bad_fetcher)
        self.assertTrue(item.fetch_status.startswith("error"))


class TestActionItems(unittest.TestCase):
    def test_action_items_includes_price_portal_from_body(self):
        raw = json.loads((FIXTURES / "cached_source.json").read_text(encoding="utf-8"))
        raw["body"] = (raw.get("body") or "") + "\n정보는 참가격(www.price.go.kr)에 공개한다."
        result = rc.run_research_pipeline(raw, fetcher=None, assigned_site="IJ", max_fetch=0)
        actions = result["packet"].get("action_items") or []
        joined = " ".join(actions)
        self.assertIn("price.go.kr", joined)

    def test_action_items_includes_kepco_and_energy_market_urls(self):
        body = (
            "자세한 내용은 한전ON(https://online.kepco.co.kr/) 또는 "
            "에너지마켓플레이스(https://en-ter.co.kr/)에서 확인할 수 있다."
        )
        actions = rc._extract_action_items(body)
        joined = " ".join(actions)
        self.assertIn("kepco.co.kr", joined)
        self.assertIn("en-ter.co.kr", joined)


class TestResearchPacket(unittest.TestCase):
    def test_packet_grade_with_mock_evidence(self):
        raw = json.loads((FIXTURES / "cached_source.json").read_text(encoding="utf-8"))
        evidence = [
            rc.EvidenceItem(
                evidence_type="government",
                url="https://www.ftc.go.kr/www/",
                title="보도자료",
                body_excerpt="고지 의무 " + "소비자 보호 " * 12,
                published_at=None,
                reliability_rank=90,
                collected_at="2026-05-21T00:00:00+09:00",
                fetch_status="ok",
            ),
            rc.EvidenceItem(
                evidence_type="government",
                url="https://www.price.go.kr/",
                title="참가격",
                body_excerpt="가격 정보 " + "참가격 서비스 " * 12,
                published_at=None,
                reliability_rank=90,
                collected_at="2026-05-21T00:00:00+09:00",
                fetch_status="ok",
            ),
        ]
        raw["body"] = (raw["body"] + "\n") * 20  # MIN_BODY_CHARS_FOR_GRADE_A
        packet = rc.build_research_packet(raw, evidence, assigned_site="IJ")
        self.assertIn(packet.publish_grade, ("A", "B"))
        self.assertGreaterEqual(packet.official_evidence_count, 2)
        self.assertEqual(packet.research_meta.get("packet_version"), 2)
        self.assertIn("primary_links", packet.reader_utility)
        readiness = rc.assess_research_readiness(packet)
        self.assertTrue(readiness["ready_for_writing"])

    def test_thin_body_with_title_only_evidence_cannot_be_a(self):
        raw = json.loads((FIXTURES / "cached_source.json").read_text(encoding="utf-8"))
        evidence = [
            rc.EvidenceItem(
                evidence_type="government",
                url="https://www.law.go.kr/x",
                title="법령",
                body_excerpt="짧음",
                published_at=None,
                reliability_rank=95,
                collected_at="2026-05-21T00:00:00+09:00",
                fetch_status="ok",
            ),
            rc.EvidenceItem(
                evidence_type="government",
                url="https://www.price.go.kr/",
                title="참가격",
                body_excerpt="짧음2",
                published_at=None,
                reliability_rank=90,
                collected_at="2026-05-21T00:00:00+09:00",
                fetch_status="ok",
            ),
        ]
        packet = rc.build_research_packet(raw, evidence, assigned_site="IJ")
        self.assertNotEqual(packet.publish_grade, "A")
        self.assertEqual(packet.official_evidence_count, 0)

    def test_packet_grade_D_without_evidence(self):
        raw = json.loads((FIXTURES / "cached_source.json").read_text(encoding="utf-8"))
        packet = rc.build_research_packet(raw, [], assigned_site="IJ")
        self.assertEqual(packet.publish_grade, "C")  # key_facts from body still exist
        packet_thin = rc.build_research_packet(
            {"title": "t", "body": "짧음", "url": "https://x.com"},
            [],
        )
        self.assertEqual(packet_thin.publish_grade, "D")

    def test_run_pipeline_offline(self):
        raw = json.loads((FIXTURES / "cached_source.json").read_text(encoding="utf-8"))
        raw["raw_html"] = (FIXTURES / "policy_with_links.html").read_text(encoding="utf-8")
        result = rc.run_research_pipeline(raw, fetcher=None, max_fetch=2)
        self.assertIn("packet", result)
        self.assertIn("readiness", result)
        self.assertIn("plan", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
