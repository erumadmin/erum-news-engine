#!/usr/bin/env python3
"""Tests for editorial hybrid rewrite input."""

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline.packet_writer import build_rewrite_user_message_from_editorial


class TestEditorialHybridRewrite(unittest.TestCase):
    def test_includes_original_body_and_packet(self):
        article = {
            "title": "위생용품 내용량 축소",
            "url": "https://www.korea.kr/news/1",
            "body": "앞으로 위생용품 용량을 줄이면 3개월 전 고지한다. "
            "참가격(www.price.go.kr)에 공개한다.",
            "source_published_at": "2026-05-27",
        }
        packet = {
            "main_claim": "3개월 전 고지",
            "key_facts": ["협약 체결"],
            "publish_grade": "C",
            "risk_flags": ["official_evidence_missing"],
        }
        evidence = [
            {
                "fetch_status": "ok",
                "evidence_type": "government",
                "title": "참가격",
                "url": "https://www.price.go.kr/",
                "body_excerpt": "가격 정보 서비스 " * 10,
            }
        ]
        msg = build_rewrite_user_message_from_editorial(article, packet, evidence)
        self.assertIn("[수집 원문]", msg)
        self.assertIn("참가격(www.price.go.kr)", msg)
        self.assertIn("[리서치 패킷]", msg)
        self.assertIn("3개월 전 고지", msg)
        self.assertIn("[추가 근거]", msg)
        self.assertIn("https://www.price.go.kr/", msg)
        self.assertIn("official_evidence_missing", msg)


if __name__ == "__main__":
    unittest.main()
