"""Shared HTTP helpers (no dependency on repo-root engine.py)."""

from __future__ import annotations

import time
from urllib.parse import urlparse

import requests

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


def build_request_headers(url: str = "") -> dict:
    headers = dict(REQUEST_HEADERS)
    parsed = urlparse(url or "")
    host = (parsed.netloc or "").lower()
    if "korea.kr" in host:
        headers["Referer"] = "https://www.korea.kr/"
        headers["Origin"] = "https://www.korea.kr"
        headers["Cache-Control"] = "no-cache"
        headers["Pragma"] = "no-cache"
    return headers


def fetch_with_retry(url, max_retries=2, timeout=15, stream=False, retry_statuses=(429, 500, 502, 503, 504)):
    last_response = None
    for attempt in range(max_retries + 1):
        try:
            r = requests.get(url, headers=build_request_headers(url), timeout=timeout, stream=stream)
            last_response = r
            if r.status_code in retry_statuses and attempt < max_retries:
                time.sleep(1 + attempt)
                continue
            return r
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, ConnectionResetError, requests.exceptions.RequestException):
            if attempt < max_retries:
                time.sleep(1 + attempt)
                continue
            return None
    return last_response
