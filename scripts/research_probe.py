#!/usr/bin/env python3
"""
Research pipeline probe — RSS-first (same ingress as engine.py).

Examples:
  # RSS 최신 N건 (운영과 동일 진입점) + 증거 fetch
  python scripts/research_probe.py --rss --limit 5 --live

  # 특정 피드만
  python scripts/research_probe.py --rss --feed https://www.korea.kr/rss/policy.xml --limit 3 --live

  # RSS 후 기사 페이지까지 보강 (선택)
  python scripts/research_probe.py --rss --limit 2 --live --enrich-page

  # 오프라인 fixture
  python scripts/research_probe.py --fixture tests/fixtures/research/cached_source.json \\
      --html-fixture tests/fixtures/research/rss_summary_sample.html
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import research_collector as rc  # noqa: E402
import research_rss as rr  # noqa: E402

try:
    import requests  # noqa: E402
except ImportError:
    requests = None  # type: ignore

try:
    import engine as eng  # noqa: E402
except Exception:
    eng = None


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def make_fetcher():
    if eng is not None:
        def fetcher(url: str):
            return eng.fetch_with_retry(url, timeout=20)

        return fetcher

    if requests is None:
        raise RuntimeError("requests not installed — live fetch unavailable")

    def fetcher(url: str):
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; erum-research-probe/1.0)",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }
        if "korea.kr" in url:
            headers["Referer"] = "https://www.korea.kr/"
        return requests.get(url, headers=headers, timeout=20)

    return fetcher


def enrich_from_article_page(raw: dict, fetcher) -> dict:
    """RSS summary 외에 기사 상세 페이지 본문을 덧붙임 (선택)."""
    url = raw.get("url") or ""
    if not url:
        return raw
    resp = fetcher(url)
    if not resp or getattr(resp, "status_code", 200) >= 400:
        print(f"  ⚠️ page enrich failed: {getattr(resp, 'status_code', 'none')}", file=sys.stderr)
        return raw
    from bs4 import BeautifulSoup

    out = dict(raw)
    page_html = resp.text or ""
    out["page_html"] = page_html
    node = BeautifulSoup(page_html, "html.parser").select_one(".view_cont")
    if node:
        page_body = node.get_text("\n", strip=True)
        if len(page_body) > len(out.get("body") or ""):
            out["body"] = page_body
        out["raw_html"] = (out.get("rss_summary") or "") + "\n" + str(node)
    return out


def probe_one(raw: dict, *, live: bool, max_fetch: int, enrich_page: bool) -> dict:
    fetcher = make_fetcher() if (live or enrich_page) else None
    work = dict(raw)

    if enrich_page and fetcher:
        work = enrich_from_article_page(work, fetcher)

    evidence_fetcher = fetcher if live else None
    return rc.run_research_pipeline(work, fetcher=evidence_fetcher, max_fetch=max_fetch)


def print_report(raw: dict, result: dict) -> None:
    plan = result["plan"]
    readiness = result["readiness"]
    packet = result["packet"]
    title = raw.get("title") or plan["raw_source_url"]

    print(f"\n{'=' * 60}")
    print(f"📰 {title[:70]}")
    print(f"   feed: {raw.get('feed_name', '-')} | type: {raw.get('source_type', '-')}")
    print(f"   URL: {plan['raw_source_url'][:90]}")
    print(f"   RSS 본문: {len(raw.get('rss_summary') or '')}자 | 텍스트 body: {len(raw.get('body') or '')}자")
    print(f"   링크 후보: {len(plan['link_candidates'])} / fetch 대상: {len(plan['fetch_targets'])}")
    for note in plan.get("notes") or []:
        print(f"   ⚠️ {note}")

    print("   --- 링크 후보 (상위 8) ---")
    for cand in plan["link_candidates"][:8]:
        print(
            f"   [{cand['reliability_rank']:>2}] {cand['evidence_type']:<16} "
            f"{cand['url'][:70]}"
        )

    print("   --- 수집된 증거 ---")
    for ev in result.get("evidence") or []:
        status = ev["fetch_status"]
        title_ev = (ev.get("title") or "")[:50]
        print(f"   {status:<12} {ev['url'][:65]} | {title_ev}")

    print("   --- 패킷 ---")
    print(f"   등급: {packet['publish_grade']} | 배치 힌트: {packet['placement_hint']}")
    print(f"   공식 증거: {packet['official_evidence_count']} | 리스크: {packet['risk_flags']}")
    print(f"   작성 가능: {readiness['ready_for_writing']} | blockers: {readiness['blockers']}")
    print(f"   main_claim: {packet['main_claim'][:100]}...")


def main() -> int:
    parser = argparse.ArgumentParser(description="Research pipeline probe (RSS-first)")
    parser.add_argument("--rss", action="store_true", help="RSS에서 raw source 수집 (engine과 동일)")
    parser.add_argument("--feed", help="단일 RSS feed URL")
    parser.add_argument("--fixture", type=Path, help="JSON raw source fixture")
    parser.add_argument("--url", help="단일 기사 URL (비권장: RSS 없이 직접)")
    parser.add_argument("--cache-dir", type=Path, help="cached article JSON 디렉터리")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--live", action="store_true", help="증거 URL HTTP fetch")
    parser.add_argument("--enrich-page", action="store_true", help="RSS 후 기사 페이지 본문 보강")
    parser.add_argument("--max-fetch", type=int, default=3)
    parser.add_argument("--html-fixture", type=Path, help="--fixture용 RSS summary HTML")
    parser.add_argument("--json-out", type=Path, help="결과 JSON 저장")
    args = parser.parse_args()

    sources: list[dict] = []

    use_network = args.rss or args.feed or args.url or args.enrich_page or args.live
    if use_network and eng is None and requests is None:
        print("install requests (pip install -r requirements.txt)", file=sys.stderr)
        return 1

    fetcher = make_fetcher() if use_network else None

    if args.rss or args.feed:
        if args.feed:
            feeds = [(args.feed, args.feed.rsplit("/", 1)[-1], "policy_briefing")]
        else:
            feeds = rr.DEFAULT_RSS_FEEDS
        assert fetcher is not None
        sources = rr.ingest_rss_feeds(feeds, limit_total=args.limit, fetcher=fetcher)
        if not sources:
            print("RSS에서 항목을 가져오지 못했습니다.", file=sys.stderr)
            return 1
        print(f"📡 RSS {len(sources)}건 수집 (feeds={len(feeds)})")
    elif args.fixture:
        raw = load_json(args.fixture)
        if args.html_fixture:
            html = args.html_fixture.read_text(encoding="utf-8")
            raw["rss_summary"] = html
            raw["raw_html"] = html
        sources = [raw]
    elif args.url:
        sources = [{"url": args.url, "title": args.url, "body": "", "source_type": "manual"}]
    elif args.cache_dir:
        for fp in sorted(args.cache_dir.glob("*.json"))[: args.limit]:
            raw = load_json(fp)
            if not raw.get("rss_summary") and not raw.get("raw_html"):
                raw["rss_summary"] = raw.get("body", "")
                raw["raw_html"] = raw.get("rss_summary", "")
            sources.append(raw)
    else:
        parser.error("use --rss (recommended), --feed, --fixture, --cache-dir, or --url")

    live = args.live or args.rss or bool(args.feed)
    all_results = []
    for raw in sources:
        try:
            result = probe_one(raw, live=live, max_fetch=args.max_fetch, enrich_page=args.enrich_page)
            all_results.append({"raw": raw, "result": result})
            print_report(raw, result)
        except Exception as exc:
            print(f"\n❌ FAILED: {(raw.get('title') or '')[:50]} — {exc}", file=sys.stderr)

    if args.json_out:
        args.json_out.write_text(
            json.dumps(all_results, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"\n💾 wrote {args.json_out}")

    ok_writing = sum(1 for item in all_results if item["result"]["readiness"]["ready_for_writing"])
    print(f"\n📊 요약: {ok_writing}/{len(all_results)}건 작성 가능(B 이상)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
