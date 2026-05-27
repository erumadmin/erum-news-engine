#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline import tier_c as tc


class TestTierC(unittest.TestCase):
    def test_should_run_tier_c_when_no_substantive_official_evidence(self):
        packet = {"key_facts": ["한 줄"], "risk_flags": ["official_evidence_missing"]}
        evidence = [{"fetch_status": "ok", "body_excerpt": "짧음", "reliability_rank": 90}]
        self.assertTrue(tc.should_run_tier_c(packet, evidence))

    def test_collect_tier_c_adds_evidence_with_url(self):
        raw = {"title": "협약", "body": "공정위 협약 참가격 www.price.go.kr", "url": "https://www.korea.kr/1"}
        packet = {"key_facts": ["a"], "risk_flags": ["official_evidence_missing"]}
        evidence: list = []

        def fetcher(url):
            m = MagicMock()
            m.status_code = 200
            m.text = f"<html><title>t</title><article><p>{'x' * 120}</p></article></html>"
            return m

        added = tc.collect_tier_c_evidence(raw, evidence, packet, fetcher, max_fetch=2)
        self.assertTrue(any("price.go.kr" in (e.get("url") or "") for e in added))

    def test_collect_tier_c_fetches_kepco_reader_url(self):
        raw = {
            "title": "전기요금",
            "body": "확인: https://online.kepco.co.kr/ 및 https://en-ter.co.kr/",
            "url": "https://www.korea.kr/1",
        }
        packet = {"key_facts": ["a", "b", "c"], "risk_flags": ["official_evidence_missing"]}

        def fetcher(url):
            m = MagicMock()
            m.status_code = 200
            m.text = f"<html><title>t</title><article><p>{'요금 안내 ' * 20}</p></article></html>"
            return m

        added = tc.collect_tier_c_evidence(raw, [], packet, fetcher, max_fetch=2)
        urls = " ".join(e.get("url") or "" for e in added)
        self.assertIn("kepco.co.kr", urls)
