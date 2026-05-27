#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline.ingest import enrich_article_from_page, parse_article_page

FIXTURES = Path(__file__).parent / "fixtures" / "research"


class TestIngest(unittest.TestCase):
    def test_enrich_preserves_long_body_without_storage_truncation(self):
        from engine.pipeline.ingest import enrich_article_from_page

        long_body = "가" * 50000
        html = f"<html><body><div class='view_cont'>{long_body}</div></body></html>"

        def fetcher(url):
            m = type("R", (), {})()
            m.status_code = 200
            m.text = html
            m.raise_for_status = lambda: None
            return m

        article = {"url": "https://www.korea.kr/news/policyNewsView.do?newsId=1", "title": "t", "body": "short"}
        ok, out, _ = enrich_article_from_page(article, fetcher)
        self.assertTrue(ok)
        self.assertGreaterEqual(len(out["body"]), 49000)

    def test_parse_fixture_html(self):
        html = (FIXTURES / "policy_with_links.html").read_text(encoding="utf-8")
        title, body, _ = parse_article_page(html)
        self.assertIn("위생용품", title)
        self.assertGreater(len(body), 100)

    def test_require_fetch_fails_without_network(self):
        article = {
            "url": "https://www.korea.kr/news/policyNewsView.do?newsId=1",
            "title": "t",
            "body": "x" * 50,
        }
        ok, _, reason = enrich_article_from_page(
            article, None, require_fetch=True, min_body_chars=400
        )
        self.assertFalse(ok)
        self.assertIn("fetcher_required", reason)

    def test_enrich_replaces_thin_rss_when_fetch_ok(self):
        long_body = "앞으로 위생용품의 용량을 줄이면 " + "소비자에게 고지한다. " * 40
        html = f"<div class='view_cont'><p>{long_body}</p></div>"
        resp = MagicMock()
        resp.status_code = 200
        resp.text = html
        resp.encoding = "utf-8"

        def fetcher(_url):
            return resp

        article = {"url": "https://www.korea.kr/x", "title": "t", "body": "짧은 rss"}
        ok, out, reason = enrich_article_from_page(
            article, fetcher, require_fetch=True, min_body_chars=400
        )
        self.assertTrue(ok)
        self.assertGreaterEqual(len(out["body"]), 400)
        self.assertIn("full_page", reason)


if __name__ == "__main__":
    unittest.main()
