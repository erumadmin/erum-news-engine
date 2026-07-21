"""P3: Korea crawler collect_articles behavior with mocked HTTP (no network)."""
from __future__ import annotations

import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
FIXED_NOW = datetime(2026, 7, 20, 10, 0, tzinfo=KST)


def _load_engine():
    spec = importlib.util.spec_from_file_location("erum_news_engine_collect", ROOT / "engine.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _long_body(prefix: str = "정부는 정책을 시행한다") -> str:
    return (prefix + ". 대상과 일정, 신청 절차를 공식 안내에서 확인한다. ") * 8


def _list_html(news_id: str, title: str, date_str: str, view: str = "policyNewsView") -> str:
    return (
        f'<ul><li><a href="{view}.do?newsId={news_id}">{title}</a>'
        f"<span>{date_str}</span></li></ul>"
    )


def _detail_html(title: str, body: str) -> str:
    return (
        f'<html><head><meta property="og:title" content="{title}"/></head>'
        f'<body><main class="main"><div class="view_cont">{body}</div></main></body></html>'
    )


class TestKoreaCrawlerCollect(unittest.TestCase):
    def setUp(self):
        self.eng = _load_engine()
        self.eng.KOREA_CRAWLER_ENABLED = True
        self.eng.KOREA_CRAWLER_MAX_PAGES = 1
        self.eng.KOREA_CRAWLER_SOURCES = ["policy", "briefing", "press"]
        self.eng.NEWSWIRE_DAYTIME_MODE = "off"
        self.eng.EDITORIAL_PIPELINE = False
        self.eng.TARGET_URL_IDS = set()
        self.eng.RETRY_DAYS = 3

    def test_defaults_policy_first_and_retry_days_3(self):
        self.assertEqual(self.eng.KOREA_CRAWLER_SOURCES[0], "policy")
        self.assertEqual(self.eng.RETRY_DAYS, 3)

    def test_crawler_used_rss_skipped_when_enabled(self):
        date_str = FIXED_NOW.strftime("%Y-%m-%d")
        list_html = _list_html("p1", "정책 지원 확대 시행 안내입니다", date_str)
        detail_html = _detail_html("정책 지원 확대 시행 안내입니다", _long_body())
        hit_urls: list[str] = []

        def fake_fetch(url, timeout=20):
            hit_urls.append(url)
            if "policyNewsList" in url or "policyNewsView" in url:
                text = detail_html if "View.do" in url else list_html
                return SimpleNamespace(status_code=200, text=text, encoding="utf-8")
            return SimpleNamespace(status_code=404, text="", encoding="utf-8")

        with mock.patch.object(self.eng, "now_kst", return_value=FIXED_NOW), mock.patch.object(
            self.eng, "fetch_with_retry", side_effect=fake_fetch
        ):
            result = self.eng.collect_articles(set(), set(), set(), limit=1, review_mode=True)

        self.assertTrue(result)
        self.assertTrue(any("korea.kr" in u for u in hit_urls))
        self.assertFalse(any(u.endswith(".xml") for u in hit_urls))

    def test_mobile_fallback_on_list_fetch(self):
        date_str = FIXED_NOW.strftime("%Y-%m-%d")
        list_html = _list_html("m1", "모바일 폴백 정책 뉴스 제목입니다", date_str)
        detail_html = _detail_html("모바일 폴백 정책 뉴스 제목입니다", _long_body("모바일 폴백"))
        tried: list[str] = []

        def fake_fetch(url, timeout=20):
            tried.append(url)
            if "m.korea.kr" in url and "policyNewsList" in url:
                return SimpleNamespace(status_code=200, text=list_html, encoding="utf-8")
            if "policyNewsView" in url:
                return SimpleNamespace(status_code=200, text=detail_html, encoding="utf-8")
            if "www.korea.kr" in url and "policyNewsList" in url:
                return SimpleNamespace(status_code=503, text="", encoding="utf-8")
            return SimpleNamespace(status_code=404, text="", encoding="utf-8")

        with mock.patch.object(self.eng, "now_kst", return_value=FIXED_NOW), mock.patch.object(
            self.eng, "fetch_with_retry", side_effect=fake_fetch
        ):
            result = self.eng.collect_articles(set(), set(), set(), limit=1, review_mode=True)

        self.assertTrue(any("www.korea.kr" in u and "policyNewsList" in u for u in tried))
        self.assertTrue(any("m.korea.kr" in u and "policyNewsList" in u for u in tried))
        self.assertEqual(len(result), 1)

    def test_target_url_ids_bypass_date_filter(self):
        old = FIXED_NOW - timedelta(days=10)
        old_str = old.strftime("%Y-%m-%d")
        news_id = "old99"
        href = f"https://www.korea.kr/news/policyNewsView.do?newsId={news_id}"
        url_id = self.eng.extract_unique_id(href)
        self.eng.TARGET_URL_IDS = {url_id}
        list_html = _list_html(news_id, "오래된 대상 기사 제목입니다", old_str)
        detail_html = _detail_html("오래된 대상 기사 제목입니다", _long_body("오래된 대상"))

        def fake_fetch(url, timeout=20):
            text = detail_html if "View.do" in url else list_html
            if "policyNews" in url:
                return SimpleNamespace(status_code=200, text=text, encoding="utf-8")
            return SimpleNamespace(status_code=404, text="", encoding="utf-8")

        with mock.patch.object(self.eng, "now_kst", return_value=FIXED_NOW), mock.patch.object(
            self.eng, "fetch_with_retry", side_effect=fake_fetch
        ):
            kept = self.eng.collect_articles(set(), set(), set(), limit=1, review_mode=True)
        self.assertEqual(len(kept), 1)

        self.eng.TARGET_URL_IDS = set()
        with mock.patch.object(self.eng, "now_kst", return_value=FIXED_NOW), mock.patch.object(
            self.eng, "fetch_with_retry", side_effect=fake_fetch
        ):
            dropped = self.eng.collect_articles(set(), set(), set(), limit=1, review_mode=True)
        self.assertEqual(dropped, [])

    def test_retry_days_accepts_backlog_within_window(self):
        within = (FIXED_NOW - timedelta(days=2)).strftime("%Y-%m-%d")
        outside = (FIXED_NOW - timedelta(days=4)).strftime("%Y-%m-%d")

        def run_for_date(date_str: str, news_id: str):
            list_html = _list_html(news_id, f"재시도 창 검증 기사 {news_id}", date_str)
            detail_html = _detail_html(f"재시도 창 검증 기사 {news_id}", _long_body(news_id))

            def fake_fetch(url, timeout=20):
                text = detail_html if "View.do" in url else list_html
                if "policyNews" in url:
                    return SimpleNamespace(status_code=200, text=text, encoding="utf-8")
                return SimpleNamespace(status_code=404, text="", encoding="utf-8")

            with mock.patch.object(self.eng, "now_kst", return_value=FIXED_NOW), mock.patch.object(
                self.eng, "fetch_with_retry", side_effect=fake_fetch
            ):
                return self.eng.collect_articles(set(), set(), set(), limit=1, review_mode=True)

        self.assertEqual(len(run_for_date(within, "d2")), 1)
        self.assertEqual(run_for_date(outside, "d4"), [])

    def test_screened_quota_never_exceeds_limit(self):
        self.eng.NEWSWIRE_DAYTIME_MODE = "screened"
        self.eng.NEWSWIRE_MAX_SELECTED_PER_RUN = 5
        date_str = FIXED_NOW.strftime("%Y-%m-%d")
        list_html = _list_html("q1", "쿼터 검증용 정책 기사 제목", date_str)
        detail_html = _detail_html("쿼터 검증용 정책 기사 제목", _long_body("쿼터"))

        def fake_fetch(url, timeout=20):
            if "policyNews" in url:
                text = detail_html if "View.do" in url else list_html
                return SimpleNamespace(status_code=200, text=text, encoding="utf-8")
            return SimpleNamespace(status_code=404, text="", encoding="utf-8")

        selected_nw = []
        for i in range(8):
            selected_nw.append(
                {
                    "url": f"https://www.newswire.co.kr/newsRead.php?no={2000 + i}",
                    "url_id": f"nw_{2000 + i}",
                    "title": f"뉴스와이어 후보 기사 제목 {i}번입니다",
                    "body": _long_body(f"뉴스와이어 {i}"),
                    "image": "",
                    "source_type": "newswire",
                    "source_published_at": FIXED_NOW,
                }
            )

        entries = []
        for i in range(8):
            entries.append(
                SimpleNamespace(
                    link=f"https://www.newswire.co.kr/newsRead.php?no={2000 + i}",
                    title=f"뉴스와이어 후보 기사 제목 {i}번입니다",
                    summary=_long_body(f"뉴스와이어 {i}"),
                    published_parsed=FIXED_NOW.timetuple(),
                    media_content=[],
                )
            )

        def fetch_mix(url, timeout=20):
            if "policyNews" in url:
                text = detail_html if "View.do" in url else list_html
                return SimpleNamespace(status_code=200, text=text, encoding="utf-8")
            if "newswire" in url or url.endswith(".xml"):
                return SimpleNamespace(status_code=200, text="<rss/>", encoding="utf-8")
            return SimpleNamespace(status_code=404, text="", encoding="utf-8")

        with mock.patch.object(self.eng, "now_kst", return_value=FIXED_NOW), mock.patch.object(
            self.eng, "fetch_with_retry", side_effect=fetch_mix
        ), mock.patch("feedparser.parse", return_value=SimpleNamespace(entries=entries)), mock.patch(
            "engine.pipeline.ingest.enrich_article_from_page",
            side_effect=lambda a, *_args, **_kw: (True, a, "ok"),
        ), mock.patch(
            "engine.pipeline.source_gate.screen_newswire_candidates",
            return_value=(selected_nw, SimpleNamespace(format_report=lambda: "ok"), []),
        ), mock.patch(
            "engine.pipeline.source_gate.SourceGateConfig.from_env",
            return_value=SimpleNamespace(),
        ):
            result = self.eng.collect_articles(set(), set(), set(), limit=7, review_mode=True)

        self.assertLessEqual(len(result), 7)
        policy_count = sum(1 for a in result if a.get("source_type") == "policy_briefing")
        nw_count = sum(1 for a in result if a.get("source_type") == "newswire")
        self.assertLessEqual(policy_count, 2)  # limit 7, reserved 5 => policy_limit 2
        self.assertLessEqual(nw_count, 5)

    def test_policy_source_order_policy_before_press(self):
        date_str = FIXED_NOW.strftime("%Y-%m-%d")
        order: list[str] = []

        def fake_extract(html_text, base_url, source_key):
            order.append(source_key)
            view = {
                "policy": "policyNewsView",
                "briefing": "pressBriefingView",
                "press": "pressReleaseView",
            }.get(source_key, "policyNewsView")
            # briefing filter rejects pressReleaseView; use a non-press view name
            if source_key == "briefing":
                href = f"https://www.korea.kr/briefing/otherView.do?newsId={source_key}1"
            else:
                href = f"https://www.korea.kr/news/{view}.do?newsId={source_key}1"
            return [
                {
                    "url": href,
                    "url_id": self.eng.extract_unique_id(href),
                    "title": f"{source_key} 출처 기사 제목입니다",
                    "list_text": f"{source_key} {date_str}",
                    "department": "",
                    "source_published_at": FIXED_NOW,
                }
            ]

        def fake_detail(item, source_name):
            return {
                "url": item["url"],
                "url_id": item["url_id"],
                "title": item["title"],
                "body": _long_body(source_name),
                "image": "",
                "source_published_at": FIXED_NOW,
                "source_name": source_name,
                "department": "",
                "source_type": "policy_briefing",
            }

        def fake_fetch(url, timeout=20):
            return SimpleNamespace(status_code=200, text="<html/>", encoding="utf-8")

        with mock.patch.object(self.eng, "now_kst", return_value=FIXED_NOW), mock.patch.object(
            self.eng, "fetch_with_retry", side_effect=fake_fetch
        ), mock.patch.object(self.eng, "_extract_korea_list_items", side_effect=fake_extract), mock.patch.object(
            self.eng, "_fetch_korea_detail", side_effect=fake_detail
        ):
            result = self.eng.collect_articles(set(), set(), set(), limit=1, review_mode=True)

        self.assertTrue(order)
        self.assertEqual(order[0], "policy")
        self.assertEqual(len(result), 1)
        self.assertIn("policy", result[0]["url_id"] + result[0]["title"])


if __name__ == "__main__":
    unittest.main()
