#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any

from engine.utils.vercel_cpu_audit import (
    classify_http_probe,
    extract_team_softblock,
    summarize_article_api_result,
)


DEFAULT_TEAM_SLUG = "erums-projects-cfc8699e"
DEFAULT_SITE_URLS = [
    "https://erum-one.com",
    "https://impactjournal.kr",
    "https://neighbornews.kr",
    "https://csrbriefing.kr",
]
DEFAULT_ARTICLE_API_URLS = [
    "https://erum-one.com/api/articles?site=IJ&status=PUBLISHED&page=1&limit=1",
    "https://erum-one.com/api/articles?site=NN&status=PUBLISHED&page=1&limit=1",
    "https://erum-one.com/api/articles?site=CB&status=PUBLISHED&page=1&limit=1",
]


def fetch_text(url: str) -> tuple[int, dict[str, str], str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "erum-news-engine/vercel-cpu-audit",
            "Accept": "*/*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.getcode(), dict(response.headers.items()), response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        return error.code, dict(error.headers.items()), body


def fetch_team_payload(team_slug: str) -> dict[str, Any]:
    command = ["vercel", "api", "/v2/teams?limit=20"]
    completed = subprocess.run(command, capture_output=True, text=True, check=True)
    payload = json.loads(completed.stdout)
    return extract_team_softblock(payload, team_slug)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Vercel CPU mitigation recovery state.")
    parser.add_argument("--team-slug", default=DEFAULT_TEAM_SLUG)
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    args = parser.parse_args()

    team_state = fetch_team_payload(args.team_slug)

    site_results = []
    for url in DEFAULT_SITE_URLS:
        status_code, headers, body_text = fetch_text(url)
        site_results.append(classify_http_probe(url, status_code, headers, body_text))

    article_api_results = []
    for url in DEFAULT_ARTICLE_API_URLS:
        status_code, headers, body_text = fetch_text(url)
        article_api_results.append(summarize_article_api_result(url, status_code, headers, body_text))

    blocked = bool(team_state.get("soft_block")) or any(result["status"] != "ok" for result in site_results + article_api_results)
    report = {
        "team": team_state,
        "sites": site_results,
        "article_api": article_api_results,
        "ready_for_live_review": not blocked,
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
