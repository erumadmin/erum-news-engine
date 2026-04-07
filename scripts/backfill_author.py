"""
기존 기사 author 소급 업데이트 스크립트
조직도: ~/projects/001.EPR_erumcompany/mgmt/03_operations/언론사_편집국_조직도.md

사용법:
  python scripts/backfill_author.py          # dry-run (실제 업데이트 없음)
  python scripts/backfill_author.py --apply  # 실제 업데이트 실행
"""

import os
import sys
import time
import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE = os.environ.get("API_BASE", "https://erum-one.com")
API_KEY  = os.environ.get("ERUM_API_KEY") or os.environ.get("ADMIN_API_KEY") or "eRuM@AdminKey2026!"
HEADERS  = {"x-api-key": API_KEY, "Content-Type": "application/json"}

DRY_RUN = "--apply" not in sys.argv

# 카테고리명 → 기자명 매핑 (조직도 기준)
JOURNALIST_MAP = {
    "IJ": {"정치": "오지현", "경제": "이성민", "사회": "윤성민", "IT/과학": "장예린", "문화/생활": "한재원", "국제": "서민준", "환경": "나혜진"},
    "NN": {"정치": "최지훈", "경제": "윤재원", "사회": "박서연", "IT/과학": "임태양", "문화/생활": "강미래", "국제": "송현아", "환경": "김도현"},
    "CB": {"정치": "김민서", "경제": "이준혁", "사회": "박지은", "IT/과학": "최현우", "문화/생활": "정수빈", "국제": "한다영", "환경": "오태준"},
}

def fetch_articles(site: str, page: int, limit: int = 100) -> list:
    params = {"site": site, "status": "PUBLISHED", "page": page, "limit": limit}
    r = requests.get(f"{API_BASE}/api/articles", params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json().get("articles", [])

def update_author(article_id: int, author: str) -> bool:
    r = requests.put(
        f"{API_BASE}/api/articles/{article_id}",
        json={"author": author},
        headers=HEADERS,
        timeout=30,
    )
    return r.ok

def run():
    mode = "DRY-RUN" if DRY_RUN else "APPLY"
    print(f"=== 기자 소급 업데이트 [{mode}] ===\n")

    total_updated = 0
    total_skipped = 0
    total_error   = 0

    for site, cat_map in JOURNALIST_MAP.items():
        print(f"[{site}] 처리 시작")
        page = 1
        while True:
            articles = fetch_articles(site, page)
            if not articles:
                break

            for a in articles:
                article_id = a["id"]
                category   = a.get("category", {})
                cat_name   = category.get("name", "") if category else ""
                current    = a.get("author") or ""
                journalist = cat_map.get(cat_name)

                if not journalist:
                    # 카테고리 매핑 없음 (카테고리 미분류 등)
                    total_skipped += 1
                    continue

                if current and current not in ("편집국", ""):
                    # 이미 실명 기자 있으면 스킵
                    total_skipped += 1
                    continue

                if DRY_RUN:
                    print(f"  [{site}] ID:{article_id} | {cat_name} → {journalist} (dry-run)")
                    total_updated += 1
                else:
                    ok = update_author(article_id, journalist)
                    if ok:
                        print(f"  [{site}] ID:{article_id} | {cat_name} → {journalist} ✅")
                        total_updated += 1
                    else:
                        print(f"  [{site}] ID:{article_id} | 업데이트 실패 ❌")
                        total_error += 1
                    time.sleep(0.1)  # API 부하 방지

            if len(articles) < 100:
                break
            page += 1

        print(f"[{site}] 완료\n")

    print("=" * 40)
    print(f"업데이트: {total_updated}건")
    print(f"스킵:     {total_skipped}건 (기자 있거나 카테고리 미분류)")
    print(f"오류:     {total_error}건")
    if DRY_RUN:
        print("\n※ dry-run 결과입니다. 실제 적용하려면 --apply 옵션을 추가하세요.")

if __name__ == "__main__":
    run()
