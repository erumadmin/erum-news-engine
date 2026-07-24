"""Draft tracking and PUBLISHED promotion for auto news."""
from __future__ import annotations

import os
import subprocess
from typing import Any, Optional

import requests


AUTHOR_SLUG_BY_SITE_CAT = {
    "IJ": {
        "politics": ("오지현", "oh-jihyun"),
        "economy": ("이성민", "lee-sungmin"),
        "society": ("윤성민", "yun-sungmin"),
        "it-science": ("장예린", "jang-yerin"),
        "culture-life": ("한재원", "han-jaewon"),
        "international": ("서민준", "seo-minjun"),
        "environment": ("나혜진", "na-hyejin"),
    },
    "NN": {
        "politics": ("최지훈", "choi-jihun"),
        "economy": ("윤재원", "yun-jaewon"),
        "society": ("박서연", "park-seoyeon"),
        "it-science": ("임태양", "im-taeyang"),
        "culture-life": ("강미래", "kang-mirae"),
        "international": ("송현아", "song-hyuna"),
        "environment": ("김도현", "kim-dohyun"),
    },
    "CB": {
        "politics": ("김민서", "kim-minseo"),
        "economy": ("이준혁", "lee-junhyuk"),
        "society": ("박지은", "park-jieun"),
        "it-science": ("최현우", "choi-hyunwoo"),
        "culture-life": ("정수빈", "jeong-subin"),
        "international": ("한다영", "han-dayoung"),
        "environment": ("오태준", "oh-taejun"),
    },
}


def resolve_author_for_site(site: str, category_slug: str | None) -> tuple[Optional[str], Optional[str]]:
    table = AUTHOR_SLUG_BY_SITE_CAT.get(site, {})
    if category_slug and category_slug in table:
        return table[category_slug]
    return None, None


def engine_commit_sha() -> str:
    env = os.environ.get("ENGINE_COMMIT") or os.environ.get("GIT_COMMIT")
    if env:
        return env.strip()
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def normalize_source_id(url_id: str) -> str:
    return (url_id or "").strip()


def ensure_draft_tracking_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS auto_news_drafts (
          id BIGINT AUTO_INCREMENT PRIMARY KEY,
          url_id VARCHAR(512) NOT NULL,
          site VARCHAR(8) NOT NULL,
          article_id INT NOT NULL,
          content_hash CHAR(64) DEFAULT NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
          engine_commit VARCHAR(64) DEFAULT NULL,
          prompt_version VARCHAR(64) DEFAULT NULL,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          UNIQUE KEY uq_auto_news_drafts_url (url_id),
          KEY idx_auto_news_drafts_article (article_id),
          KEY idx_auto_news_drafts_created (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    # Existing installs created without created_at index — add if missing.
    try:
        cursor.execute(
            """
            SELECT 1 FROM information_schema.statistics
            WHERE table_schema = DATABASE()
              AND table_name = 'auto_news_drafts'
              AND index_name = 'idx_auto_news_drafts_created'
            LIMIT 1
            """
        )
        if cursor.fetchone() is None:
            cursor.execute(
                "ALTER TABLE auto_news_drafts ADD KEY idx_auto_news_drafts_created (created_at)"
            )
    except Exception:
        # Best-effort; COUNT still works without the index.
        pass


def count_unique_drafts_in_kst_day(cursor, now=None) -> int:
    """
    Count unique url_ids with created_at in KST half-open window [today 00:00, tomorrow 00:00).

    Uses naive KST wall-clock bounds against DATETIME columns that store KST-naive timestamps.
    Does not use DATE(created_at) or the DB session timezone.
    Includes rows later promoted to PUBLISHED.
    """
    from erum_pipeline.kst_time import kst_naive_day_window

    ensure_draft_tracking_table(cursor)
    start, end = kst_naive_day_window(now)
    cursor.execute(
        """
        SELECT COUNT(DISTINCT url_id) AS cnt
        FROM auto_news_drafts
        WHERE created_at >= %s AND created_at < %s
        """,
        (start, end),
    )
    row = cursor.fetchone()
    if row is None:
        return 0
    if isinstance(row, dict):
        return int(row.get("cnt") or 0)
    return int(row[0] or 0)


def count_unique_drafts_created_on_date(cursor, day) -> int:
    """
    Count unique url_ids for a KST calendar ``day`` via the same half-open window policy.
    """
    from datetime import datetime, time

    from erum_pipeline.kst_time import KST

    noon = datetime.combine(day, time(12, 0), tzinfo=KST)
    return count_unique_drafts_in_kst_day(cursor, noon)


def list_tracked_draft_url_ids(cursor) -> set[str]:
    """All url_ids ever recorded in auto_news_drafts (DRAFT or PUBLISHED)."""
    ensure_draft_tracking_table(cursor)
    cursor.execute("SELECT url_id FROM auto_news_drafts")
    rows = cursor.fetchall() or []
    out: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            uid = row.get("url_id")
        else:
            uid = row[0]
        if uid:
            out.add(str(uid))
    return out


def record_draft_mapping(
    cursor,
    *,
    url_id: str,
    site: str,
    article_id: int,
    content_hash: Optional[str] = None,
    engine_commit: Optional[str] = None,
    prompt_version: Optional[str] = None,
    created_at=None,
) -> None:
    """
    Insert draft mapping with explicit KST-naive ``created_at`` (same policy as daily limits).
    ON DUPLICATE KEY UPDATE must not rewrite ``created_at``.
    """
    from erum_pipeline.kst_time import now_kst_naive

    ensure_draft_tracking_table(cursor)
    ts = created_at if created_at is not None else now_kst_naive()
    cursor.execute(
        """
        INSERT INTO auto_news_drafts
          (url_id, site, article_id, content_hash, status, engine_commit, prompt_version, created_at)
        VALUES (%s, %s, %s, %s, 'DRAFT', %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          site=VALUES(site),
          article_id=VALUES(article_id),
          content_hash=VALUES(content_hash),
          status='DRAFT',
          engine_commit=VALUES(engine_commit),
          prompt_version=VALUES(prompt_version)
        """,
        (url_id, site, article_id, content_hash, engine_commit, prompt_version, ts),
    )


def lookup_draft_by_source(cursor, url_id: str) -> Optional[dict[str, Any]]:
    ensure_draft_tracking_table(cursor)
    cursor.execute("SELECT * FROM auto_news_drafts WHERE url_id=%s LIMIT 1", (url_id,))
    row = cursor.fetchone()
    if not row:
        return None
    if isinstance(row, dict):
        return row
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


def promote_article_to_published(
    *,
    api_base: str,
    api_key: str,
    article_id: int,
    content_hash: str,
    timeout: int = 30,
) -> dict[str, Any]:
    """Approve then publish the same Article ID."""
    from erum_pipeline.vercel_bypass import merge_portal_headers

    headers = merge_portal_headers({"x-api-key": api_key, "Content-Type": "application/json"})
    approve = requests.post(
        f"{api_base}/api/articles/{article_id}/approve",
        json={"contentHash": content_hash},
        headers=headers,
        timeout=timeout,
    )
    approve.raise_for_status()
    publish = requests.post(
        f"{api_base}/api/articles/{article_id}/publish",
        json={},
        headers=headers,
        timeout=timeout,
    )
    publish.raise_for_status()
    return publish.json()


def mark_draft_published(cursor, url_id: str) -> None:
    ensure_draft_tracking_table(cursor)
    cursor.execute(
        "UPDATE auto_news_drafts SET status='PUBLISHED' WHERE url_id=%s",
        (url_id,),
    )
