#!/usr/bin/env python3
"""authorSlug backfill dry-run (idempotent plan). DO NOT apply on prod without approval.

Usage:
  ERUM_ENV=staging python scripts/backfill_author_slug_dryrun.py
  # prints counts + proposed UPDATEs; never executes writes unless --apply
  # --apply is refused when ERUM_ENV=production
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Ensure repo root import
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from erum_pipeline.reporter_roster import AUTHOR_SLUG_BY_SITE_CAT, name_to_slug_for_site


def load_env_file(path: str) -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def build_name_map() -> dict[str, dict[str, str]]:
    """site -> exact name -> slug (no global name-only)."""
    out: dict[str, dict[str, str]] = {"IJ": {}, "NN": {}, "CB": {}}
    for site, cats in AUTHOR_SLUG_BY_SITE_CAT.items():
        for _cat, (name, slug) in cats.items():
            out[site][name] = slug
    return out


EXCEPTIONS: set[tuple[str, str]] = set()
# Add (site, exact_author_name) pairs that must NOT be auto-mapped.


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default=str(Path.home() / ".env.erum_staging"))
    parser.add_argument("--apply", action="store_true", help="Execute UPDATEs (staging only)")
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()

    load_env_file(args.env_file)
    erum_env = (os.environ.get("ERUM_ENV") or "").strip().lower()
    if args.apply and erum_env == "production":
        print("REFUSED: --apply is forbidden when ERUM_ENV=production")
        return 2

    try:
        import pymysql
    except ImportError:
        print("pymysql required")
        return 1

    conn = pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT") or 3306),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    name_map = build_name_map()
    proposed: list[dict] = []
    counts = Counter()
    by_status = Counter()
    unmapped = Counter()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, site, status, author, authorSlug
            FROM Article
            WHERE author IS NOT NULL AND author <> ''
              AND (authorSlug IS NULL OR authorSlug = '')
            ORDER BY id
            LIMIT %s
            """,
            (args.limit,),
        )
        rows = cur.fetchall() or []

    for row in rows:
        site = row["site"]
        author = (row["author"] or "").strip()
        status = row["status"]
        counts["name_present_slug_null"] += 1
        by_status[f"{site}:{status}"] += 1
        if "편집국" in author.replace(" ", ""):
            counts["desk_name_slug_null"] += 1
            continue
        if (site, author) in EXCEPTIONS:
            counts["exception_skipped"] += 1
            continue
        slug = name_map.get(site, {}).get(author) or name_to_slug_for_site(site, author)
        if not slug:
            unmapped[f"{site}:{author}"] += 1
            counts["unmapped_personal"] += 1
            continue
        proposed.append(
            {
                "id": row["id"],
                "site": site,
                "status": status,
                "author": author,
                "authorSlug": slug,
            }
        )
        counts["proposed"] += 1
        by_status[f"proposed:{site}:{status}"] += 1

    print("=== authorSlug NULL dry-run ===")
    print(f"ERUM_ENV={erum_env} DB_NAME={os.environ.get('DB_NAME')}")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")
    print("by_status:")
    for k, v in sorted(by_status.items()):
        print(f"  {k}: {v}")
    if unmapped:
        print("unmapped (site:name):")
        for k, v in unmapped.most_common(30):
            print(f"  {k}: {v}")

    print(f"\nProposed UPDATEs: {len(proposed)} (idempotent: WHERE authorSlug IS NULL)")
    for item in proposed[:20]:
        print(
            f"  -- id={item['id']} {item['site']} {item['status']} "
            f"{item['author']} -> {item['authorSlug']}"
        )
        print(
            "  UPDATE Article SET authorSlug=%s "
            "WHERE id=%s AND site=%s AND author=%s AND (authorSlug IS NULL OR authorSlug='');"
            % (repr(item["authorSlug"]), item["id"], repr(item["site"]), repr(item["author"]))
        )

    if args.apply:
        if erum_env != "staging":
            print("REFUSED: --apply only allowed for ERUM_ENV=staging")
            return 2
        applied = 0
        with conn.cursor() as cur:
            for item in proposed:
                cur.execute(
                    """
                    UPDATE Article
                    SET authorSlug=%s
                    WHERE id=%s AND site=%s AND author=%s
                      AND (authorSlug IS NULL OR authorSlug='')
                    """,
                    (item["authorSlug"], item["id"], item["site"], item["author"]),
                )
                applied += cur.rowcount
        conn.commit()
        print(f"Applied rows: {applied}")
    else:
        print("Dry-run only (pass --apply on staging to execute).")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
