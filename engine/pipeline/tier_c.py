"""
Tier C: supplemental evidence when Tier A/B leaves fact gaps.

Default: deterministic extra official URLs from body + ministry hubs.
Optional TIER_C_USE_LLM=1 + GEMINI_API_KEY for URL hints (still HTTP-fetched).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable
from urllib.parse import urlparse

import research_collector as rc

MIN_KEY_FACTS_FOR_TIER_C = int(os.environ.get("TIER_C_MIN_KEY_FACTS", "3"))


def should_run_tier_c(packet: dict[str, Any], evidence: list[dict[str, Any]]) -> bool:
    if os.environ.get("TIER_C_ENABLED", "1") == "0":
        return False
    risk = packet.get("risk_flags") or []
    if "official_evidence_missing" in risk:
        return True
    substantive = sum(
        1
        for e in evidence
        if e.get("fetch_status") == "ok"
        and len((e.get("body_excerpt") or "").strip()) >= rc.SUBSTANTIVE_EVIDENCE_EXCERPT_CHARS
        and int(e.get("reliability_rank") or 0) >= 80
    )
    if substantive < 1:
        return True
    if len(packet.get("key_facts") or []) < MIN_KEY_FACTS_FOR_TIER_C:
        return True
    return False


def _existing_urls(evidence: list[dict[str, Any]], raw_source: dict[str, Any]) -> set[str]:
    urls = {(raw_source.get("url") or raw_source.get("source_url") or "").strip()}
    for e in evidence:
        u = (e.get("url") or "").strip()
        if u:
            urls.add(u)
    return {u for u in urls if u}


def _deterministic_tier_c_targets(
    raw_source: dict[str, Any],
    existing: set[str],
    *,
    max_new: int = 2,
) -> list[str]:
    body = (raw_source.get("body") or raw_source.get("source_body") or "")
    title = (raw_source.get("title") or "")
    text = f"{title}\n{body}"
    candidates: list[str] = []
    for url, _anchor in rc.extract_urls_from_text(text):
        if url in existing:
            continue
        _host, _etype, rank = rc.classify_domain(url)
        if rank >= 80:
            candidates.append(url)
    for pattern, hub_url, _etype in rc.MINISTRY_PRESS_HUBS:
        if re.search(pattern, text) and hub_url not in existing and hub_url not in candidates:
            candidates.append(hub_url)
    return candidates[:max_new]


def _llm_suggest_urls(
    raw_source: dict[str, Any],
    existing: set[str],
    *,
    max_urls: int = 2,
) -> list[str]:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return []
    try:
        import requests

        title = (raw_source.get("title") or "")[:200]
        body = (raw_source.get("body") or "")[:2000]
        prompt = (
            f"List up to {max_urls} official South Korean government URLs (.go.kr) "
            f"that would verify this policy story. JSON array of strings only.\n"
            f"Title: {title}\nBody: {body}"
        )
        model = os.environ.get("GEMINI_MODEL_REWRITE", "gemini-2.0-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        resp = requests.post(
            url,
            params={"key": api_key},
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 256},
            },
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        m = re.search(r"\[[\s\S]*\]", text)
        if not m:
            return []
        urls = json.loads(m.group(0))
        out: list[str] = []
        for u in urls:
            if not isinstance(u, str):
                continue
            u = u.strip()
            if not u.startswith("http") or u in existing:
                continue
            host = urlparse(u).netloc
            if ".go.kr" not in host and "korea.kr" not in host:
                continue
            out.append(u)
        return out[:max_urls]
    except Exception:
        return []


def collect_tier_c_evidence(
    raw_source: dict[str, Any],
    evidence: list[dict[str, Any]],
    packet: dict[str, Any],
    fetcher: Callable[[str], Any],
    *,
    max_fetch: int = 2,
) -> list[dict[str, Any]]:
    if not should_run_tier_c(packet, evidence):
        return []
    existing = _existing_urls(evidence, raw_source)
    targets = _deterministic_tier_c_targets(raw_source, existing, max_new=max_fetch)
    if not targets and os.environ.get("TIER_C_USE_LLM") == "1":
        targets = _llm_suggest_urls(raw_source, existing, max_urls=max_fetch)
    from dataclasses import asdict

    added: list[dict[str, Any]] = []
    for url in targets:
        if url in existing:
            continue
        item = rc.fetch_evidence_page(url, fetcher)
        row = asdict(item)
        row["evidence_type"] = row.get("evidence_type") or "tier_c"
        if row.get("fetch_status") == "ok":
            added.append(row)
            existing.add(url)
        if len(added) >= max_fetch:
            break
    return added
