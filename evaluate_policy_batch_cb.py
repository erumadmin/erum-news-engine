#!/usr/bin/env python3
"""정책브리핑 20건 캐시 + CB 프롬프트 배치 평가."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_DIR = Path(__file__).resolve().parent
os.environ.setdefault("REVIEW_ONLY", "1")
sys.path.insert(0, str(REPO_DIR))

import engine as eng  # noqa: E402


MEDIA_PREFIX = "CB_"
BATCH_SIZE = int(os.environ.get("POLICY_BATCH_SIZE", "20"))
LOOKBACK_DAYS = int(os.environ.get("POLICY_LOOKBACK_DAYS", "7"))
FETCH_WORKERS = int(os.environ.get("POLICY_FETCH_WORKERS", "6"))
SOURCE_CACHE_DIR = REPO_DIR / "review_outputs" / "source_cache" / "policy_briefing"
ARTICLE_CACHE_DIR = SOURCE_CACHE_DIR / "articles"
BATCH_MANIFEST = SOURCE_CACHE_DIR / "latest_batch.json"

BUSINESS_SEO_SYSTEM_PROMPT = """
너는 정책브리핑 원문을 기업 독자용 기사로 재작성한 결과를 검색 색인성과 SEO 관점에서 평가하는 편집자다.
핵심은 "원문 대비 기업 독자에게 새로운 효용이 생겼는가"다.
반드시 JSON만 출력한다.

평가 기준
- business_utility: 기업 독자가 당장 확인해야 할 의무, 비용, 일정, 예외, 계약·조달 영향이 드러나는가
- search_intent: 제목과 리드가 기업 독자가 실제로 검색할 질문(누가 영향받는가, 무엇이 바뀌는가, 언제 시행되는가, 어떤 조건이 붙는가)에 맞는가
- specificity: 대상, 조치, 시점, 수치, 예외 중 핵심 축이 구체적인가
- distinctiveness: 원문 재서술이 아니라 구조적으로 재배열된 해설 가치가 있는가
- risk_control: 근거 없는 기업 효과 과장이나 홍보 문체 없이 원문 정합성을 지키는가

채점 규칙
- 각 항목은 0~20점
- total은 항목 합계
- verdict는 strong, borderline, weak 중 하나
- reasons는 2~4개

출력 JSON 형식
{
  "scores": {
    "business_utility": 0,
    "search_intent": 0,
    "specificity": 0,
    "distinctiveness": 0,
    "risk_control": 0
  },
  "total": 0,
  "verdict": "strong",
  "reasons": ["..."]
}
""".strip()


@dataclass
class VariantResult:
    title: str
    excerpt: str
    body: str
    body_chars: int
    valid: bool
    valid_msg: str
    qa_score: int
    qa_pass: bool
    qa_fails: List[str]
    fixed_applied: bool
    seo_total: int
    seo_verdict: str
    seo_reasons: List[str]
    attempts: List[dict]


def git_show(path_in_repo: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(REPO_DIR), "show", f"HEAD:{path_in_repo}"],
        text=True,
    )


def prompt_versions() -> Dict[str, str]:
    common_text = (REPO_DIR / "prompts" / "news_editor_common.md").read_text(encoding="utf-8")
    baseline_specific = git_show("prompts/news_editor_cb.md")
    current_specific = (REPO_DIR / "prompts" / "news_editor_cb.md").read_text(encoding="utf-8")
    return {
        "baseline": f"{common_text}\n\n{baseline_specific}",
        "current": f"{common_text}\n\n{current_specific}",
    }


def article_cache_path(url_id: str) -> Path:
    safe_id = re.sub(r"[^0-9A-Za-z._-]+", "_", url_id).strip("_") or "article"
    return ARTICLE_CACHE_DIR / f"{safe_id}.json"


def serialize_article(article: dict) -> dict:
    source_published_at = article.get("source_published_at")
    if isinstance(source_published_at, datetime):
        source_published_at = source_published_at.isoformat()
    return {
        "url": article.get("url", ""),
        "url_id": article.get("url_id", ""),
        "title": article.get("title", ""),
        "body": article.get("body", ""),
        "image": article.get("image", ""),
        "source_published_at": source_published_at,
        "body_source": article.get("body_source", "unknown"),
        "cached_at": eng.now_kst().isoformat(),
    }


def deserialize_article(data: dict) -> dict:
    article = dict(data)
    source_published_at = article.get("source_published_at")
    if isinstance(source_published_at, str) and source_published_at:
        try:
            article["source_published_at"] = datetime.fromisoformat(source_published_at)
        except Exception:
            article["source_published_at"] = None
    return article


def save_article_cache(article: dict) -> None:
    ARTICLE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    article_cache_path(article.get("url_id", "")).write_text(
        json.dumps(serialize_article(article), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_article_cache(url_id: str) -> Optional[dict]:
    path = article_cache_path(url_id)
    if not path.exists():
        return None
    try:
        return deserialize_article(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def fetch_full_page_article(article: dict) -> Optional[dict]:
    resp = eng.fetch_with_retry(article["url"], max_retries=1, timeout=20)
    if not resp or resp.status_code != 200:
        return None
    resp.encoding = "utf-8"
    soup = eng.BeautifulSoup(resp.text, "html.parser")

    title = ""
    h1 = soup.select_one("h1")
    if h1:
        title = h1.get_text(" ", strip=True)
    if not title:
        og_title = soup.find("meta", attrs={"property": "og:title"}) or soup.find("meta", attrs={"name": "og:title"})
        if og_title and og_title.get("content"):
            title = og_title.get("content", "").strip()
    if not title:
        title = article.get("title", "")

    body_node = (
        soup.select_one(".view_cont")
        or soup.select_one(".article-content")
        or soup.select_one("#articleBody")
        or soup.select_one("article")
        or soup.select_one(".content")
        or soup.select_one(".view_cont")
    )
    body_text = body_node.get_text(separator="\n", strip=True) if body_node else eng.strip_html_tags(resp.text)

    main_node = soup.select_one("main.main") or soup.select_one("section.area_contents") or soup.select_one("main")
    source_published_at = article.get("source_published_at")
    if not source_published_at and main_node:
        source_published_at = eng._extract_first_date(main_node.get_text(" ", strip=True)[:1200])
    if not source_published_at:
        source_published_at = eng._extract_first_date(soup.get_text(" ", strip=True)[:1200])

    upgraded = dict(article)
    upgraded.update(
        {
            "title": title[:1000],
            "body": body_text[:40000],
            "source_published_at": source_published_at,
            "body_source": "page",
        }
    )
    return upgraded


def collect_policy_feed_articles(limit: int) -> List[dict]:
    eng.RETRY_DAYS = max(eng.RETRY_DAYS, LOOKBACK_DAYS)
    rules = {
        "blocked_ids": set(),
        "blocked_title_hashes": set(),
        "blocked_source_urls": set(),
        "allowed_ids": set(),
        "allowed_title_hashes": set(),
        "allowed_source_urls": set(),
    }
    articles = eng.collect_articles(set(), set(), set(), limit, rules=rules, review_mode=True)
    for article in articles:
        article["body_source"] = "rss"
        save_article_cache(article)
    return articles


def upgrade_articles_from_pages(feed_articles: List[dict]) -> List[dict]:
    upgraded_map: Dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        future_map = {pool.submit(fetch_full_page_article, article): article for article in feed_articles}
        for future in as_completed(future_map):
            base = future_map[future]
            result = None
            try:
                result = future.result()
            except Exception:
                result = None
            final_article = result or load_article_cache(base["url_id"]) or base
            if not final_article.get("body_source"):
                final_article["body_source"] = "rss"
            save_article_cache(final_article)
            upgraded_map[base["url_id"]] = final_article
    return [upgraded_map[a["url_id"]] for a in feed_articles if a["url_id"] in upgraded_map]


def load_cached_batch() -> List[dict]:
    if not BATCH_MANIFEST.exists():
        return []
    try:
        data = json.loads(BATCH_MANIFEST.read_text(encoding="utf-8"))
        article_ids = data.get("article_ids", [])
        articles = []
        for url_id in article_ids:
            cached = load_article_cache(url_id)
            if cached:
                articles.append(cached)
        return articles
    except Exception:
        return []


def save_batch_manifest(articles: List[dict]) -> None:
    SOURCE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": eng.now_kst().isoformat(),
        "lookback_days": LOOKBACK_DAYS,
        "article_ids": [article.get("url_id", "") for article in articles],
        "source_counts": {
            "page": sum(1 for article in articles if article.get("body_source") == "page"),
            "rss": sum(1 for article in articles if article.get("body_source") == "rss"),
        },
    }
    BATCH_MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_policy_batch(limit: int) -> Tuple[List[dict], str]:
    print(f"Collecting policy briefing batch ({limit})...", flush=True)
    feed_articles = collect_policy_feed_articles(limit)
    if feed_articles:
        print(f"Collected {len(feed_articles)} feed articles. Upgrading to full page cache...", flush=True)
        articles = upgrade_articles_from_pages(feed_articles)
        save_batch_manifest(articles)
        return articles, "live_policy_feed"

    cached_articles = load_cached_batch()
    if cached_articles:
        return cached_articles[:limit], "cached_policy_batch"

    return [], "unavailable"


def parse_json_block(raw: str) -> dict:
    clean = re.sub(r"```json\s*", "", raw or "")
    clean = re.sub(r"```\s*", "", clean).strip()
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(clean)
    return obj


def judge_business_utility(article: dict, variant: dict) -> Tuple[int, str, List[str]]:
    source_plain = re.sub(r"\s+", " ", eng.strip_html_tags(article.get("body", ""))).strip()[:2200]
    body_plain = re.sub(r"\s+", " ", eng.strip_html_tags(variant.get("body", ""))).strip()[:2200]
    user_text = "\n".join(
        [
            "원문 기사",
            f"제목: {(article.get('title') or '').strip()}",
            f"출처 URL: {(article.get('url') or '').strip()}",
            f"본문: {source_plain}",
            "",
            "재작성 기사",
            f"제목: {(variant.get('title') or '').strip()}",
            f"리드문: {(variant.get('excerpt') or '').strip()}",
            f"본문: {body_plain}",
        ]
    )
    try:
        raw = eng.ask_llm(
            BUSINESS_SEO_SYSTEM_PROMPT,
            user_text,
            model=eng.UPSTAGE_MODEL_QA,
            max_output_tokens=700,
            stage="qa",
        )
        result = parse_json_block(raw)
        total = int(result.get("total", 0))
        verdict = str(result.get("verdict", "weak")).strip() or "weak"
        reasons = [str(x).strip() for x in result.get("reasons", []) if str(x).strip()]
        return total, verdict, reasons[:4]
    except Exception as exc:
        return 0, "weak", [f"SEO judge parse fail: {str(exc)[:120]}"]


def rewrite_variant(article: dict, persona: str) -> VariantResult:
    rewrite_input = eng.build_rewrite_user_message(article)
    token_budgets = [eng.UPSTAGE_REWRITE_MAX_OUTPUT_TOKENS]
    if eng.UPSTAGE_REWRITE_RETRY_MAX_OUTPUT_TOKENS not in token_budgets:
        token_budgets.append(eng.UPSTAGE_REWRITE_RETRY_MAX_OUTPUT_TOKENS)

    parsed = None
    valid = False
    valid_msg = ""
    attempts: List[dict] = []

    for idx, max_tokens in enumerate(token_budgets):
        raw = eng.ask_llm(
            persona,
            rewrite_input,
            model=eng.UPSTAGE_MODEL_REWRITE,
            max_output_tokens=max_tokens,
            stage="rewrite",
        )
        parsed = eng.parse_llm_response(raw)
        valid, valid_msg = eng.validate_content_quality(parsed["title"], parsed["body"])
        body_chars = len(re.sub(r"\s+", " ", eng.strip_html_tags(parsed["body"])).strip())
        attempts.append(
            {
                "tokens": max_tokens,
                "valid": valid,
                "msg": valid_msg,
                "title": parsed["title"],
                "body_chars": body_chars,
            }
        )
        if valid:
            break
        if idx + 1 >= len(token_budgets) or not eng.should_retry_rewrite_validation(valid_msg):
            break

    if parsed is None:
        return VariantResult("", "", "", 0, False, "재작성 결과 없음", 0, False, ["재작성 결과 없음"], False, 0, "weak", ["재작성 실패"], attempts)

    final_variant = parsed
    qa_pass = False
    qa_fails: List[str] = []
    qa_score = 0
    fixed_applied = False

    if valid:
        qa_pass, qa_fails, qa_score, fixed = eng.ai_quality_check(
            parsed["title"],
            parsed.get("excerpt", ""),
            parsed["body"],
            MEDIA_PREFIX,
            source_article=article,
        )
        if not qa_pass and fixed:
            fixed_valid, fixed_msg = eng.validate_content_quality(fixed["title"], fixed["body"])
            if fixed_valid:
                final_variant = fixed
                valid = True
                valid_msg = fixed_msg
                fixed_applied = True
                qa_pass = True

    body_chars = len(re.sub(r"\s+", " ", eng.strip_html_tags(final_variant["body"])).strip())
    seo_total, seo_verdict, seo_reasons = judge_business_utility(article, final_variant) if valid else (0, "weak", [valid_msg])

    return VariantResult(
        title=final_variant["title"],
        excerpt=final_variant.get("excerpt", ""),
        body=final_variant["body"],
        body_chars=body_chars,
        valid=valid,
        valid_msg=valid_msg,
        qa_score=qa_score,
        qa_pass=qa_pass,
        qa_fails=qa_fails,
        fixed_applied=fixed_applied,
        seo_total=seo_total,
        seo_verdict=seo_verdict,
        seo_reasons=seo_reasons,
        attempts=attempts,
    )


def to_plain_result(result: VariantResult) -> dict:
    return {
        "title": result.title,
        "excerpt": result.excerpt,
        "body_chars": result.body_chars,
        "valid": result.valid,
        "valid_msg": result.valid_msg,
        "qa_score": result.qa_score,
        "qa_pass": result.qa_pass,
        "qa_fails": result.qa_fails,
        "fixed_applied": result.fixed_applied,
        "seo_total": result.seo_total,
        "seo_verdict": result.seo_verdict,
        "seo_reasons": result.seo_reasons,
        "attempts": result.attempts,
    }


def summarize_rows(rows: List[dict]) -> dict:
    return {
        "sample_size": len(rows),
        "baseline_avg_qa": round(sum(r["baseline"]["qa_score"] for r in rows) / len(rows), 2),
        "current_avg_qa": round(sum(r["current"]["qa_score"] for r in rows) / len(rows), 2),
        "baseline_avg_seo": round(sum(r["baseline"]["seo_total"] for r in rows) / len(rows), 2),
        "current_avg_seo": round(sum(r["current"]["seo_total"] for r in rows) / len(rows), 2),
        "baseline_valid_count": sum(1 for r in rows if r["baseline"]["valid"]),
        "current_valid_count": sum(1 for r in rows if r["current"]["valid"]),
        "baseline_pass_count": sum(1 for r in rows if r["baseline"]["qa_pass"]),
        "current_pass_count": sum(1 for r in rows if r["current"]["qa_pass"]),
        "seo_improved_count": sum(1 for r in rows if r["current"]["seo_total"] > r["baseline"]["seo_total"]),
        "seo_same_count": sum(1 for r in rows if r["current"]["seo_total"] == r["baseline"]["seo_total"]),
        "seo_regressed_count": sum(1 for r in rows if r["current"]["seo_total"] < r["baseline"]["seo_total"]),
        "current_strong_count": sum(1 for r in rows if r["current"]["seo_verdict"] == "strong"),
        "current_borderline_count": sum(1 for r in rows if r["current"]["seo_verdict"] == "borderline"),
        "current_weak_count": sum(1 for r in rows if r["current"]["seo_verdict"] == "weak"),
    }


def build_markdown(report: dict) -> str:
    lines = [
        "# 정책브리핑 20건 CB 프롬프트 평가",
        "",
        f"- 생성 시각(KST): {report['created_at']}",
        f"- 원문 소스: {report['source_mode']}",
        f"- 대상 기사 수: {report['sample_size']}",
        f"- 수집 기준일: 최근 {report['lookback_days']}일",
        f"- 캐시 구성: page {report['source_counts']['page']} / rss {report['source_counts']['rss']}",
        "",
        "## 요약",
        "",
        f"- QA 평균: {report['summary']['baseline_avg_qa']} -> {report['summary']['current_avg_qa']}",
        f"- 기업 독자 SEO 효용 평균: {report['summary']['baseline_avg_seo']} -> {report['summary']['current_avg_seo']}",
        f"- 유효성: {report['summary']['baseline_valid_count']}/{report['sample_size']} -> {report['summary']['current_valid_count']}/{report['sample_size']}",
        f"- SEO 판정: strong {report['summary']['current_strong_count']} / borderline {report['summary']['current_borderline_count']} / weak {report['summary']['current_weak_count']}",
        f"- SEO 개선/동일/하락: {report['summary']['seo_improved_count']} / {report['summary']['seo_same_count']} / {report['summary']['seo_regressed_count']}",
        "",
        "| 기사 | source | baseline SEO | current SEO | verdict | baseline QA | current QA |",
        "|---|---|---:|---:|---|---:|---:|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row['source_title']} | {row['body_source']} | {row['baseline']['seo_total']} | {row['current']['seo_total']} | "
            f"{row['current']['seo_verdict']} | {row['baseline']['qa_score']} | {row['current']['qa_score']} |"
        )
    weak_rows = [r for r in report["rows"] if r["current"]["seo_verdict"] == "weak"]
    if weak_rows:
        lines.extend(["", "## Weak 사례", ""])
        for row in weak_rows:
            lines.append(f"- {row['source_title']}: {', '.join(row['current']['seo_reasons'])}")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    prompts = prompt_versions()
    articles, source_mode = build_policy_batch(BATCH_SIZE)
    if not articles:
        raise RuntimeError("정책브리핑 배치를 수집하지 못했습니다.")

    rows = []
    for idx, article in enumerate(articles, 1):
        print(f"[CB_] {idx}/{len(articles)} {article.get('title', '')[:80]}", flush=True)
        baseline = rewrite_variant(article, prompts["baseline"])
        current = rewrite_variant(article, prompts["current"])
        rows.append(
            {
                "source_title": article.get("title", ""),
                "source_url": article.get("url", ""),
                "body_source": article.get("body_source", "unknown"),
                "baseline": to_plain_result(baseline),
                "current": to_plain_result(current),
            }
        )

    report = {
        "created_at": eng.now_kst().strftime("%Y-%m-%d %H:%M:%S"),
        "source_mode": source_mode,
        "sample_size": len(rows),
        "lookback_days": LOOKBACK_DAYS,
        "source_counts": {
            "page": sum(1 for article in articles if article.get("body_source") == "page"),
            "rss": sum(1 for article in articles if article.get("body_source") == "rss"),
        },
        "summary": summarize_rows(rows),
        "rows": rows,
    }

    output_dir = REPO_DIR / "review_outputs"
    output_dir.mkdir(exist_ok=True)
    ts = eng.now_kst().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"policy_batch_cb_{ts}.json"
    md_path = output_dir / f"policy_batch_cb_{ts}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_markdown(report), encoding="utf-8")
    print(f"JSON: {json_path}")
    print(f"MD:   {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
