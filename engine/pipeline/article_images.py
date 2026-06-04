"""Article image discovery, validation, and strict gate."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

_ENGINE_MAIN = None

BLOCKED_IMAGE_PATTERNS = [
    "btn_textview", "icon_logo", "go_new", "koreakr_og", "koreakr_fb",
    "representative", "/btn/", "/bt_/", "/icon/", "rss.png", "rss_icon",
    "print_icon", "facebook_icon", "twitter_icon", "sns_icon", "share_icon",
    "blank.gif", "no_image", "default_image", "logo_korea", "korea_logo",
    "newswire_logo", "nw_logo", "logo_newswire", "/company_img/",
    "korea_logo_2024",
]

MIN_IMAGE_BYTES = 20_000
MIN_IMAGE_WIDTH = int(os.environ.get("MIN_IMAGE_WIDTH", "1200"))
MIN_IMAGE_ASPECT_RATIO = float(os.environ.get("MIN_IMAGE_ASPECT_RATIO", "0.6"))
MAX_IMAGE_ASPECT_RATIO = float(os.environ.get("MAX_IMAGE_ASPECT_RATIO", "2.4"))

CONTACT_ALT_RE = re.compile(r'\d{2,3}-\d{3,4}-\d{4}|담당\s*부서|책임자.*과\s*장|사무관.*주무관')


def _engine_main():
    """Load repo-root engine.py (not the engine/ package)."""
    global _ENGINE_MAIN
    if _ENGINE_MAIN is not None:
        return _ENGINE_MAIN
    import importlib.util
    import sys

    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("erum_news_engine_main", root / "engine.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    _ENGINE_MAIN = mod
    return mod


def fetch_with_retry(url, max_retries=2, timeout=15, stream=False, retry_statuses=(429, 500, 502, 503, 504)):
    return _engine_main().fetch_with_retry(
        url,
        max_retries=max_retries,
        timeout=timeout,
        stream=stream,
        retry_statuses=retry_statuses,
    )


def __getattr__(name: str):
    if name == "PipelineFailure":
        return _engine_main().PipelineFailure
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


@dataclass
class ImageCandidate:
    url: str
    caption: Optional[str]
    source: str
    score: int = 0


@dataclass
class ImageInspection:
    width: int
    height: int
    aspect_ratio: float


def _is_blocked_image_url(url: str) -> bool:
    if not url:
        return True
    lowered = url.lower()
    return any(x in lowered for x in BLOCKED_IMAGE_PATTERNS)


def _caption_from_img(img) -> str:
    caption_text = ""
    node = img.parent
    for _ in range(3):
        if not node:
            break
        fig = node.find("figcaption")
        if fig:
            caption_text = fig.get_text(strip=True)
            break
        node = node.parent

    if not caption_text:
        for sib in img.next_siblings:
            if hasattr(sib, "get_text"):
                caption_text = sib.get_text(strip=True)[:200]
            elif isinstance(sib, str) and sib.strip():
                caption_text = sib.strip()[:200]
            if caption_text:
                break

    alt = img.get("alt", "") or ""
    if CONTACT_ALT_RE.search(alt):
        return caption_text
    if alt and "무단전재" not in alt and "재배포" not in alt:
        caption_text = caption_text or alt
    if "무단전재" in caption_text or "재배포" in caption_text:
        return ""
    clean_cap = re.sub(r"\s*\d{4}\.\d{1,2}\.\d{1,2}\s*", " ", caption_text)
    clean_cap = re.sub(r"\s{2,}", " ", clean_cap).strip()
    return clean_cap if len(clean_cap) >= 8 else ""


def _pick_best_srcset_url(srcset: str) -> Optional[str]:
    if not srcset:
        return None
    best_url = None
    best_score = -1
    for chunk in srcset.split(","):
        part = chunk.strip()
        if not part:
            continue
        tokens = part.split()
        url = tokens[0]
        score = 0
        if len(tokens) > 1:
            m = re.match(r"(\d+)(w|x)?", tokens[1])
            if m:
                score = int(m.group(1))
        if score >= best_score:
            best_score = score
            best_url = url
    return best_url


def fix_newswire_url(url: str) -> str:
    if "newswire.co.kr" in url and "/thumb/" in url:
        return re.sub(r'/thumb/\d+/', '/data/', url).replace('/data/data/', '/data/')
    return url


def _add_image_candidate(candidates: list, seen: set, url: str, caption: str, source: str, score: int, base_url: str = ""):
    if not url:
        return
    full_url = urljoin(base_url, url) if base_url else url
    full_url = fix_newswire_url(full_url)
    if len(full_url) < 10 or _is_blocked_image_url(full_url):
        return
    key = full_url.split("?")[0]
    if key in seen:
        return
    seen.add(key)
    candidates.append(ImageCandidate(url=full_url, caption=caption or None, source=source, score=score))


def _collect_candidates_from_img_tag(candidates: list, seen: set, img, base_url: str, source: str, base_score: int):
    caption = _caption_from_img(img)
    attr_urls = []
    for attr in ("src", "data-src", "data-original", "data-lazy-src", "data-url"):
        val = img.get(attr, "")
        if val:
            attr_urls.append(val)
    for attr in ("srcset", "data-srcset"):
        best = _pick_best_srcset_url(img.get(attr, ""))
        if best:
            attr_urls.append(best)
    for idx, url in enumerate(attr_urls):
        score = base_score - (idx * 4)
        if caption:
            score += 6
        _add_image_candidate(candidates, seen, url, caption, source, score, base_url)


def _extract_candidates_from_html(html: str, base_url: str, source: str) -> list:
    candidates = []
    seen = set()
    if not html:
        return candidates
    try:
        soup = BeautifulSoup(html, 'html.parser')
        meta_selectors = [
            ('meta[property="og:image"]', 95),
            ('meta[property="og:image:secure_url"]', 94),
            ('meta[name="twitter:image"]', 92),
            ('meta[name="twitter:image:src"]', 92),
            ('meta[itemprop="image"]', 90),
        ]
        for selector, score in meta_selectors:
            tag = soup.select_one(selector)
            if tag and tag.get('content'):
                _add_image_candidate(candidates, seen, tag.get('content', ''), None, f"{source}:meta", score, base_url)

        article_nodes = [
            soup.select_one('.view_cont'),
            soup.select_one('.article-content'),
            soup.select_one('#articleBody'),
            soup.select_one('article'),
            soup.select_one('.article-body'),
            soup.select_one('.news_view'),
            soup.select_one('.content'),
        ]
        article_nodes = [node for node in article_nodes if node]
        if not article_nodes:
            article_nodes = [soup]

        for node in article_nodes:
            for img in node.select('img'):
                _collect_candidates_from_img_tag(candidates, seen, img, base_url, f"{source}:img", 84)

        for script in soup.select('script[type="application/ld+json"]'):
            raw = script.get_text(strip=True)
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except Exception:
                continue

            def _walk(value):
                if isinstance(value, dict):
                    for k, v in value.items():
                        if k == "image":
                            if isinstance(v, str):
                                _add_image_candidate(candidates, seen, v, None, f"{source}:jsonld", 88, base_url)
                            elif isinstance(v, list):
                                for item in v:
                                    if isinstance(item, str):
                                        _add_image_candidate(candidates, seen, item, None, f"{source}:jsonld", 88, base_url)
                        else:
                            _walk(v)
                elif isinstance(value, list):
                    for item in value:
                        _walk(item)

            _walk(payload)
    except Exception:
        pass
    return candidates


def is_valid_image(url):
    if not url:
        return False
    if 'korea.kr/newsWeb/resources/attaches' in url:
        return True
    try:
        r = fetch_with_retry(url, timeout=10, stream=True)
        if not (r and r.status_code == 200):
            return False
        if 'image' not in r.headers.get('Content-Type', '').lower():
            return False
        cl = int(r.headers.get('Content-Length', 0))
        if 0 < cl < MIN_IMAGE_BYTES:
            print(f" [크기 미달 {cl//1024}KB < {MIN_IMAGE_BYTES//1024}KB, 스킵]", end="")
            return False
        return True
    except Exception:
        return False


def inspect_image_bytes(img_bytes: bytes) -> Optional[ImageInspection]:
    try:
        from PIL import Image
        import io as _io
        img = Image.open(_io.BytesIO(img_bytes))
        width, height = img.size
        if width <= 0 or height <= 0:
            return None
        return ImageInspection(width=width, height=height, aspect_ratio=width / height)
    except Exception:
        return None


def assess_image_quality(inspection: Optional[ImageInspection]) -> Tuple[bool, str]:
    if inspection is None:
        return False, "해상도 판독 실패"
    if inspection.width < MIN_IMAGE_WIDTH:
        return False, f"해상도 미달({inspection.width}x{inspection.height})"
    if inspection.aspect_ratio < MIN_IMAGE_ASPECT_RATIO or inspection.aspect_ratio > MAX_IMAGE_ASPECT_RATIO:
        return False, f"비율 부적합({inspection.width}x{inspection.height})"
    return True, "OK"


def extract_image_from_html(html: str, base_url: str = "") -> Tuple[Optional[str], Optional[str]]:
    """HTML 문자열에서 이미지를 추출 (RSS summary용)"""
    candidates = _extract_candidates_from_html(html, base_url, "rss")
    if not candidates:
        return None, None
    best = max(candidates, key=lambda c: c.score)
    return best.url, best.caption


def extract_image_with_caption(url: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        r = fetch_with_retry(url, timeout=15)
        if not r or r.status_code != 200:
            return None, None
        candidates = _extract_candidates_from_html(r.text, url, "page")
        if not candidates:
            return None, None
        best = max(candidates, key=lambda c: c.score)
        return best.url, best.caption
    except Exception:
        return None, None


def find_best_image(article):
    rss_img = article.get("image", "").strip()
    rss_body = article.get("body", "")
    link = article.get("url", "").strip()
    candidates: list[ImageCandidate] = []
    seen = set()
    page_retryable = False

    if rss_img and not _is_blocked_image_url(rss_img):
        _add_image_candidate(candidates, seen, rss_img, None, "rss:media", 100, "")
    elif rss_img:
        print(f" [1순위 블록:{rss_img[:50]}]", end="")
    else:
        print(f" [1순위:RSS이미지없음]", end="")

    if rss_body and "<img" in rss_body.lower():
        candidates.extend(_extract_candidates_from_html(rss_body, article.get("url", ""), "rss"))
    else:
        print(f" [2순위:body img없음]", end="")

    if link:
        raw_html = article.get("raw_html", "")
        need_fetch = True
        if raw_html:
            candidates.extend(_extract_candidates_from_html(raw_html, link, "page"))
            high_quality = [c for c in candidates if c.score >= 88]
            if high_quality:
                need_fetch = False
        if need_fetch:
            try:
                r = fetch_with_retry(link, timeout=15)
                if r and r.status_code == 200:
                    candidates.extend(_extract_candidates_from_html(r.text, link, "page"))
                elif not r:
                    page_retryable = True
                    print(f" [3순위 네트워크실패]", end="")
                elif r and r.status_code in (401, 403):
                    print(f" [3순위 차단:{r.status_code}]", end="")
                elif r and r.status_code in (429, 500, 502, 503, 504):
                    page_retryable = True
                    print(f" [3순위 서버오류:{r.status_code}]", end="")
                else:
                    print(f" [3순위 실패:{getattr(r, 'status_code', 'none')}]", end="")
            except Exception:
                page_retryable = True
                print(f" [3순위 예외]", end="")

    if not candidates:
        if page_retryable:
            raise _engine_main().PipelineFailure("image", "SOURCE_FETCH_HTTP_5XX", "기사 본문 조회 실패", retryable=True)
        return []

    candidates = sorted(candidates, key=lambda c: c.score, reverse=True)
    unique = []
    seen_urls = set()
    for cand in candidates:
        key = cand.url.split("?")[0]
        if key in seen_urls:
            continue
        seen_urls.add(key)
        unique.append(cand)
    return unique


def download_best_image(candidates: list[ImageCandidate]) -> Tuple[bytes, str, str, Optional[str], str]:
    eng = _engine_main()
    retryable_seen = False
    blocked_seen = False
    quality_seen = False
    for cand in candidates:
        try:
            if _is_blocked_image_url(cand.url):
                blocked_seen = True
                continue

            is_korea_kr = 'korea.kr/newsWeb/resources/attaches' in cand.url
            if is_korea_kr:
                kr_headers = dict(eng.REQUEST_HEADERS)
                kr_headers['Referer'] = 'https://www.korea.kr/'
                img_resp = requests.get(cand.url, headers=kr_headers, timeout=20)
            else:
                img_resp = fetch_with_retry(cand.url, timeout=20, stream=True)

            if not img_resp:
                retryable_seen = True
                continue
            if img_resp.status_code in (401, 403):
                blocked_seen = True
                continue
            if img_resp.status_code in (429, 500, 502, 503, 504):
                retryable_seen = True
                continue
            if img_resp.status_code != 200:
                continue

            ct = img_resp.headers.get("content-type", "")
            if 'image' not in ct.lower() and 'octet-stream' not in ct.lower():
                continue

            candidate_bytes = img_resp.content
            if len(candidate_bytes) < MIN_IMAGE_BYTES:
                continue
            inspection = inspect_image_bytes(candidate_bytes)
            quality_ok, quality_reason = assess_image_quality(inspection)
            if not quality_ok:
                quality_seen = True
                print(f" [품질 미달:{quality_reason}]", end="")
                continue

            filename = re.sub(r'[^\w\.-]', '', cand.url.split("/")[-1].split("?")[0])[-50:]
            if not filename:
                filename = f"img_{hash(cand.url) & 0xFFFFFF:06x}.jpg"
            return candidate_bytes, ct if 'image' in ct.lower() else "image/jpeg", filename, cand.caption, cand.url
        except Exception:
            retryable_seen = True
            continue

    if retryable_seen:
        raise eng.PipelineFailure("image", "IMAGE_FETCH_HTTP_5XX", "이미지 다운로드 실패", retryable=True)
    if quality_seen:
        raise eng.PipelineFailure("image", "IMAGE_QUALITY_TOO_LOW", "대표이미지 품질 미달", retryable=False)
    raise eng.PipelineFailure("image", "NO_USABLE_IMAGE", "사용 가능한 이미지 없음", retryable=False)


def require_article_image(article: dict, *, download: bool = True) -> dict:
    """Strict gate: candidates + download required. Raises PipelineFailure on failure.

    Returns {img_bytes, content_type, filename, caption, selected_url, image_status}.
    """
    candidates = find_best_image(article)
    if not candidates:
        raise _engine_main().PipelineFailure("image", "NO_USABLE_IMAGE", "이미지 후보 없음", retryable=False)
    if not download:
        best = candidates[0]
        return {
            "img_bytes": None,
            "content_type": None,
            "filename": None,
            "caption": best.caption,
            "selected_url": best.url,
            "image_status": "candidates_ok",
        }
    img_bytes, ct, fn, cap, url = download_best_image(candidates)
    return {
        "img_bytes": img_bytes,
        "content_type": ct,
        "filename": fn,
        "caption": cap,
        "selected_url": url,
        "image_status": "download_ok",
    }
