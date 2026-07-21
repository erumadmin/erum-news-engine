#!/usr/bin/env python3
"""
뉴스와이어 source gate dry-run / 리뷰 리포트.

기본: 후보 50건+ 수집(원문 보강) → 로컬(+옵션 LLM) 게이트 → 발행 없이 라우팅 리포트 저장.

  SOURCE_GATE_LLM=0 .venv/bin/python scripts/run_newswire_source_gate_dry_run.py
  .venv/bin/python scripts/run_newswire_source_gate_dry_run.py --limit 60 --with-llm
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv()
    local_env = Path.home() / ".env.erum_infra"
    if local_env.exists():
        load_dotenv(local_env, override=False)
except Exception:
    pass

import feedparser

from engine.pipeline.ingest import enrich_article_from_page, parse_article_page
from engine.pipeline.source_gate import SourceGateConfig, screen_newswire_candidates
from engine.utils.http import fetch_with_retry

KST = ZoneInfo("Asia/Seoul")
NEWSWIRE_URL = os.environ.get("NEWSWIRE_RSS_URL", "https://api.newswire.co.kr/rss/all")


def _feed_time_to_kst(dt):
    if not dt:
        return None
    return datetime.fromtimestamp(calendar.timegm(dt), tz=timezone.utc).astimezone(KST)


def _extract_og_image(html: str) -> str:
    m = re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        html or "",
        re.I,
    ) or re.search(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        html or "",
        re.I,
    )
    return m.group(1) if m else ""


def _extract_article_image(html: str) -> str:
    from engine.pipeline.article_images import BLOCKED_IMAGE_PATTERNS

    og = _extract_og_image(html)
    if og and not any(x in og.lower() for x in BLOCKED_IMAGE_PATTERNS):
        # Prefer non-logo og images; newswire og is often usable photo
        if "logo" not in og.lower():
            return og
    # Fall back to first content image
    for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html or "", re.I):
        src = m.group(1)
        if not src.startswith("http"):
            if src.startswith("//"):
                src = "https:" + src
            else:
                continue
        low = src.lower()
        if any(x in low for x in BLOCKED_IMAGE_PATTERNS):
            continue
        if any(k in low for k in ("thumb", "photo", "image", "/data/", "release")):
            return src
    return og


def collect_rss_seed() -> list[dict]:
    resp = fetch_with_retry(NEWSWIRE_URL, timeout=25)
    if not resp or resp.status_code != 200:
        raise RuntimeError(f"RSS fetch failed: HTTP {getattr(resp, 'status_code', None)}")
    resp.encoding = "utf-8"
    parsed = feedparser.parse(resp.text)
    out: list[dict] = []
    for e in parsed.entries:
        if not getattr(e, "link", None):
            continue
        img = ""
        if hasattr(e, "media_content"):
            for mc in e.media_content:
                if "image" in mc.get("type", ""):
                    img = mc.get("url", "")
                    break
        dt = e.get("published_parsed") or e.get("updated_parsed")
        out.append(
            {
                "url": e.link,
                "url_id": e.link.replace("https://", "").replace("http://", "")[:500],
                "title": (e.title or "")[:1000],
                "body": (e.get("summary") or "")[:30000],
                "image": img,
                "source_published_at": _feed_time_to_kst(dt),
                "source_type": "newswire",
                "feed_name": "뉴스와이어",
                "feed_url": NEWSWIRE_URL,
            }
        )
    return out


def _latest_news_no(seed: list[dict]) -> int:
    nos = []
    for a in seed:
        m = re.search(r"[?&]no=(\d+)", a.get("url") or "")
        if m:
            nos.append(int(m.group(1)))
    return max(nos) if nos else 0


def _has_news_no(articles: list[dict], news_no: int) -> bool:
    pat = re.compile(rf"[?&]no={news_no}\b")
    return any(pat.search(a.get("url") or "") for a in articles)


def expand_by_news_ids(seed: list[dict], limit: int) -> list[dict]:
    """RSS는 보통 15건뿐이라, 최신 no부터 역순으로 원문 페이지를 채워 50건+ 확보."""
    latest = _latest_news_no(seed)
    if latest <= 0:
        return list(seed)[:limit]

    collected: list[dict] = list(seed)
    if len(collected) >= limit:
        return collected[:limit]

    cursor = latest
    attempts = 0
    max_attempts = max(limit * 4, 150)
    while len(collected) < limit and attempts < max_attempts and cursor > 0:
        attempts += 1
        news_no = cursor
        cursor -= 1
        if _has_news_no(collected, news_no):
            continue
        url = f"https://www.newswire.co.kr/newsRead.php?no={news_no}&sourceType=rss"
        resp = fetch_with_retry(url, timeout=20)
        if not resp or resp.status_code != 200:
            continue
        resp.encoding = "utf-8"
        title, body, html = parse_article_page(resp.text, page_url=url)
        if not title or title.strip().lower() == "error" or len(body) < 400:
            continue
        if len(re.findall(r"[가-힣]", title)) < 2:
            continue  # skip English-only wire copies in dry-run pool
        article = {
            "url": url,
            "url_id": url.replace("https://", "").replace("http://", "")[:500],
            "title": title[:1000],
            "body": body[:40000],
            "raw_html": html,
            "image": _extract_article_image(html),
            "source_published_at": datetime.now(tz=KST),
            "source_type": "newswire",
            "feed_name": "뉴스와이어-id-scan",
            "feed_url": NEWSWIRE_URL,
            "ingest_source": "full_page",
        }
        collected.append(article)
        print(f"   + id-scan {len(collected)}/{limit}: {title[:40]}", flush=True)
    return collected


def enrich_all(articles: list[dict]) -> list[dict]:
    out = []
    for i, art in enumerate(articles, 1):
        if (art.get("ingest_source") == "full_page") and len(art.get("body") or "") >= 800:
            if not art.get("image"):
                art["image"] = _extract_article_image(art.get("raw_html") or "")
            out.append(art)
            continue
        _ok, enriched, reason = enrich_article_from_page(art, fetch_with_retry, require_fetch=False)
        if not enriched.get("image"):
            enriched["image"] = _extract_article_image(enriched.get("raw_html") or "")
        out.append(enriched)
        print(f"   enrich {i}/{len(articles)}: {reason}", flush=True)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Newswire source gate dry-run report")
    parser.add_argument("--limit", type=int, default=60, help="후보 목표 건수 (기본 60)")
    parser.add_argument("--with-llm", action="store_true", help="DeepSeek LLM 게이트 호출")
    parser.add_argument("--no-llm", action="store_true", help="로컬만")
    parser.add_argument(
        "--max-selected",
        type=int,
        default=None,
        help="최종 ROUTE 상한 (기본=NEWSWIRE_MAX_SELECTED_PER_RUN)",
    )
    parser.add_argument("--out-dir", default="", help="리포트 출력 디렉터리")
    args = parser.parse_args()

    use_llm = bool(args.with_llm) and not args.no_llm
    if os.environ.get("SOURCE_GATE_LLM") == "1":
        use_llm = True
    if os.environ.get("SOURCE_GATE_LLM") == "0" or args.no_llm:
        use_llm = False

    os.environ.setdefault("NEWSWIRE_DAYTIME_MODE", "screened")
    cfg = SourceGateConfig.from_env()
    # Keep production cap by default; allow explicit override for wide sampling.
    if args.max_selected is not None:
        cfg = SourceGateConfig(**{**cfg.__dict__, "max_selected_per_run": max(1, args.max_selected)})
    elif os.environ.get("SOURCE_GATE_DRY_RUN_RELAX_CAP", "0") == "1":
        cfg = SourceGateConfig(
            **{**cfg.__dict__, "max_selected_per_run": max(cfg.max_selected_per_run, 20)}
        )

    print("📡 뉴스와이어 RSS 시드 수집...")
    seed = collect_rss_seed()
    print(f"   RSS {len(seed)}건 → id-scan으로 {args.limit}건 목표 확장")
    candidates = expand_by_news_ids(seed, args.limit)
    print(f"📥 원문 보강 {len(candidates)}건...")
    candidates = enrich_all(candidates)
    print(f"   후보 {len(candidates)}건 | LLM={'ON' if use_llm else 'OFF'}")
    if len(candidates) < 50:
        print(f"⚠️ 후보가 50건 미만입니다 ({len(candidates)}).")

    selected, stats, decisions = screen_newswire_candidates(
        candidates,
        cfg=cfg,
        llm_enabled=use_llm,
        daily_published=0,
        daily_limit=50,
    )
    print(stats.format_report())

    out_dir = Path(args.out_dir) if args.out_dir else (ROOT / "review_outputs" / "source_gate")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=KST).strftime("%Y%m%d_%H%M%S")
    report = {
        "generated_at": datetime.now(tz=KST).isoformat(timespec="seconds"),
        "mode": "dry-run",
        "llm_enabled": use_llm,
        "config": {
            "model": cfg.model,
            "auto_drop_below": cfg.auto_drop_below,
            "auto_route_above": cfg.auto_route_above,
            "max_selected_per_run": cfg.max_selected_per_run,
            "max_per_site_per_run": cfg.max_per_site_per_run,
            "max_daily_share_pct": cfg.max_daily_share_pct,
        },
        "stats": {
            "input_candidates": stats.input_candidates,
            "local_drop": stats.local_drop,
            "local_route": stats.local_route,
            "llm_calls": stats.llm_calls,
            "llm_route": stats.llm_route,
            "llm_drop": stats.llm_drop,
            "final_selected": stats.final_selected,
            "site_counts": dict(stats.site_counts),
            "drop_reasons_top5": stats.drop_reasons.most_common(5),
            "pr_risk_flags": stats.pr_risk_flags,
            "parse_fail_drops": stats.parse_fail_drops,
        },
        "selected": [
            {
                "title": a.get("title"),
                "url": a.get("url"),
                "site": a.get("_source_gate_site"),
                "gate": a.get("_source_gate"),
            }
            for a in selected
        ],
        "decisions": decisions,
    }
    json_path = out_dir / f"newswire_source_gate_{stamp}.json"
    md_path = out_dir / f"newswire_source_gate_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    lines = [
        f"# 뉴스와이어 Source Gate Dry-Run ({stamp})",
        "",
        f"- 후보: {stats.input_candidates}",
        f"- LLM: {'ON' if use_llm else 'OFF'} (calls={stats.llm_calls})",
        f"- 최종 ROUTE: {stats.final_selected} "
        f"(IJ={stats.site_counts.get('IJ', 0)} NN={stats.site_counts.get('NN', 0)} "
        f"CB={stats.site_counts.get('CB', 0)})",
        "",
        "## 통계",
        "```",
        stats.format_report(),
        "```",
        "",
        "## ROUTE 샘플 (최대 20)",
    ]
    for a in selected[:20]:
        g = a.get("_source_gate") or {}
        lines.append(
            f"- [{a.get('_source_gate_site')}] {a.get('title', '')[:80]} "
            f"(score={g.get('score')}, stage={g.get('stage')})"
        )
    lines.extend(["", "## DROP 사유 top5"])
    for reason, cnt in stats.drop_reasons.most_common(5):
        lines.append(f"- {reason}: {cnt}")
    sample = decisions[:20]
    lines.extend(["", "## 사람 검수 샘플 20건"])
    for i, d in enumerate(sample, 1):
        lines.append(
            f"{i}. [{d.get('decision')}/{d.get('site')}] {d.get('title', '')[:70]} "
            f"| {d.get('reason')} | stage={d.get('stage')}"
        )
    lines.extend(
        [
            "",
            "## 검수 체크리스트",
            "- [ ] 과통과(홍보성 ROUTE) 여부",
            "- [ ] 과탈락(실무성 DROP) 여부",
            "- [ ] IJ 엄격 / CB 우선 / NN 생활성만 허용 준수",
            "- [ ] 1원문=1매체",
            "",
            f"JSON: `{json_path}`",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"📝 리포트: {md_path}")
    print(f"🧾 JSON: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
