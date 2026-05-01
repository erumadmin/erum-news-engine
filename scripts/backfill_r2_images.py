#!/usr/bin/env python3
"""
Backfill article featured images into Cloudflare R2.

Default mode is dry-run:
  python scripts/backfill_r2_images.py

Apply updates:
  python scripts/backfill_r2_images.py --apply

Scope examples:
  python scripts/backfill_r2_images.py --site IJ --limit 20 --apply
  python scripts/backfill_r2_images.py --all-external --apply
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
import sys
from datetime import datetime
from typing import Dict, Iterable, Optional, Tuple
from urllib.parse import urlparse

import boto3
import requests
from botocore.config import Config
from dotenv import load_dotenv
from PIL import Image


def load_env() -> None:
    load_dotenv()
    local_env_path = os.path.expanduser("~/.env.erum_infra")
    if os.path.exists(local_env_path):
        load_dotenv(local_env_path, override=False)


load_env()

API_BASE = os.environ.get("API_BASE", "https://erum-one.com").rstrip("/")
API_KEY = os.environ.get("ERUM_API_KEY") or os.environ.get("ADMIN_API_KEY") or "eRuM@AdminKey2026!"
HEADERS = {"x-api-key": API_KEY, "Content-Type": "application/json"}

R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "erum-news-images")
R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL", "https://pub-dd677a54d7cf4d8cabd2c3238f4558c9.r2.dev").rstrip("/")

SITES = ("IJ", "NN", "CB")
PAGE_SIZE = 100
MIN_IMAGE_BYTES = 20 * 1024


def require_r2_config() -> None:
    missing = [
        name
        for name, value in {
            "R2_ACCOUNT_ID": R2_ACCOUNT_ID,
            "R2_ACCESS_KEY_ID": R2_ACCESS_KEY_ID,
            "R2_SECRET_ACCESS_KEY": R2_SECRET_ACCESS_KEY,
            "R2_BUCKET_NAME": R2_BUCKET_NAME,
            "R2_PUBLIC_URL": R2_PUBLIC_URL,
        }.items()
        if not value
    ]
    if missing:
        raise SystemExit(f"Missing R2 config: {', '.join(missing)}")


def request_headers_for_image(url: str) -> dict:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    if "korea.kr" in urlparse(url).netloc.lower():
        headers["Referer"] = "https://www.korea.kr/"
    return headers


def fetch_articles(site: str) -> Iterable[dict]:
    page = 1
    while True:
        params = {"site": site, "status": "PUBLISHED", "page": page, "limit": PAGE_SIZE}
        response = requests.get(f"{API_BASE}/api/articles", params=params, headers=HEADERS, timeout=30)
        response.raise_for_status()
        payload = response.json()
        articles = payload.get("articles", [])
        if not articles:
            return
        yield from articles
        if len(articles) < PAGE_SIZE or page * PAGE_SIZE >= int(payload.get("total") or 0):
            return
        page += 1


def should_backfill(url: Optional[str], include_all_external: bool) -> bool:
    if not url:
        return False
    if R2_PUBLIC_URL and url.startswith(R2_PUBLIC_URL):
        return False
    if ".r2.dev/" in url or "/news/" in url and "r2" in url.lower():
        return False
    if "korea.kr/newsWeb/resources/attaches" in url:
        return True
    return include_all_external


def download_image(url: str) -> Tuple[bytes, str]:
    response = requests.get(url, headers=request_headers_for_image(url), timeout=35)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    if "image" not in content_type.lower() and "octet-stream" not in content_type.lower():
        raise ValueError(f"not an image content-type: {content_type}")
    if len(response.content) < MIN_IMAGE_BYTES:
        raise ValueError(f"image too small: {len(response.content)} bytes")
    return response.content, content_type if "image" in content_type.lower() else "image/jpeg"


def safe_stem(url: str, article_id: int) -> str:
    source_name = urlparse(url).path.rsplit("/", 1)[-1].split("?", 1)[0]
    source_stem = re.sub(r"[^\w.-]+", "-", source_name.rsplit(".", 1)[0]).strip("-._")
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"{article_id}-{source_stem or 'image'}-{digest}"[:90]


def build_webp_variants(image_bytes: bytes, stem: str) -> Dict[str, Tuple[bytes, str, str]]:
    image = Image.open(io.BytesIO(image_bytes))
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")

    def render(max_width: int, quality: int, suffix: str) -> Tuple[bytes, str, str]:
        variant = image.copy()
        if variant.width > max_width:
            ratio = max_width / variant.width
            variant = variant.resize((max_width, int(variant.height * ratio)), Image.LANCZOS)
        output = io.BytesIO()
        variant.save(output, format="WEBP", quality=quality)
        return output.getvalue(), "image/webp", f"{stem}{suffix}.webp"

    return {
        "master": render(2000, 89, ""),
        "thumb": render(640, 80, "__thumb"),
    }


def upload_to_r2(site: str, article_id: int, source_url: str, image_bytes: bytes) -> str:
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )
    stem = safe_stem(source_url, article_id)
    month = datetime.now().strftime("%Y/%m")
    uploaded: Dict[str, str] = {}
    for variant_name, (body, content_type, filename) in build_webp_variants(image_bytes, stem).items():
        key = f"news/{site.lower()}/{month}/{filename}"
        s3.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=key,
            Body=body,
            ContentType=content_type,
            CacheControl="public, max-age=31536000, immutable",
        )
        uploaded[variant_name] = f"{R2_PUBLIC_URL}/{key}"
    return uploaded["master"]


def update_article(article_id: int, r2_url: str) -> None:
    response = requests.put(
        f"{API_BASE}/api/articles/{article_id}",
        json={"featuredImageUrl": r2_url},
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()


def run() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Update article featuredImageUrl values")
    parser.add_argument("--site", choices=SITES, help="Limit to one site")
    parser.add_argument("--limit", type=int, default=0, help="Maximum matching articles to process")
    parser.add_argument("--all-external", action="store_true", help="Backfill every non-R2 external image URL")
    args = parser.parse_args()

    require_r2_config()

    sites = (args.site,) if args.site else SITES
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== R2 image backfill [{mode}] ===")

    matched = 0
    updated = 0
    failed = 0

    for site in sites:
        for article in fetch_articles(site):
            article_id = int(article["id"])
            current_url = article.get("featuredImageUrl") or ""
            if not should_backfill(current_url, args.all_external):
                continue

            matched += 1
            title = (article.get("title") or "")[:50]
            print(f"[{site}] {article_id} {title}")
            print(f"  from: {current_url}")

            if args.limit and matched > args.limit:
                print("  limit reached")
                return 0 if failed == 0 else 1

            try:
                image_bytes, _ = download_image(current_url)
                r2_url = upload_to_r2(site, article_id, current_url, image_bytes)
                print(f"  to:   {r2_url}")
                if args.apply:
                    update_article(article_id, r2_url)
                    updated += 1
                    print("  updated")
            except Exception as exc:
                failed += 1
                print(f"  failed: {str(exc)[:200]}")

    print(f"\nmatched={matched} updated={updated} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
