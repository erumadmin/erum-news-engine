import requests
import os
import base64

SITES = {
    "IJ": {
        "base": "https://api.impactjournal.kr",
        "user": "erumadmin",
        "pw_env": "WP_IJ_APP_PW",
        "post_ids": [44038, 44113, 44208, 44274, 44379, 44529, 44613, 44689, 44750, 44816]
    },
    "NN": {
        "base": "https://neighbornews.kr",
        "user": "rkwkgkgk",
        "pw_env": "WP_NN_APP_PW",
        "post_ids": [25663, 25665, 25667, 25669, 25671, 25673, 25675, 25677, 25679, 25681]
    },
    "CB": {
        "base": "https://csrbriefing.kr",
        "user": "rkwkgkgk",
        "pw_env": "WP_CB_APP_PW",
        "post_ids": [23408, 23410, 23412, 23414, 23416, 23418, 23420, 23422, 23424, 23426, 23428]
    }
}

# 플레이스홀더 기준: 12864 bytes (300x80px, 동일 파일명 패턴 9524e8b35c606cd2ab6237fc36e6f668)
PLACEHOLDER_MAX_SIZE = 15000  # 15KB 이하

for prefix, cfg in SITES.items():
    pw = os.environ.get(cfg["pw_env"], "")
    if not pw:
        print(f"[{prefix}] {cfg['pw_env']} 환경변수 없음, 스킵")
        continue

    token = base64.b64encode(f"{cfg['user']}:{pw}".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}

    deleted = 0
    skipped = 0
    errors = 0

    print(f"\n[{prefix}] 처리 시작 ({len(cfg['post_ids'])}개 포스트)")

    for pid in cfg["post_ids"]:
        try:
            # 포스트 정보 조회
            r = requests.get(
                f"{cfg['base']}/wp-json/wp/v2/posts/{pid}?_fields=id,title,featured_media",
                headers=headers, timeout=15
            )
            if r.status_code == 404:
                print(f"  [{prefix}] Post {pid}: 이미 삭제됨 (404)")
                continue
            if r.status_code != 200:
                print(f"  [{prefix}] Post {pid}: 조회 실패 HTTP {r.status_code}")
                errors += 1
                continue

            post = r.json()
            mid = post.get("featured_media", 0)
            title = post.get("title", {}).get("rendered", "?")[:50]

            if not mid:
                print(f"  [{prefix}] Post {pid}: 이미지 없음 — 스킵: {title}")
                skipped += 1
                continue

            # 미디어 정보 조회
            mr = requests.get(
                f"{cfg['base']}/wp-json/wp/v2/media/{mid}?_fields=id,media_details,source_url",
                headers=headers, timeout=15
            )
            if mr.status_code != 200:
                print(f"  [{prefix}] Post {pid}: 미디어 {mid} 조회 실패 HTTP {mr.status_code}")
                errors += 1
                continue

            media = mr.json()
            filesize = media.get("media_details", {}).get("filesize", 0)

            # filesize가 없으면 source_url에서 직접 다운로드해서 크기 확인
            if not filesize:
                src = media.get("source_url", "")
                if src:
                    img_r = requests.get(src, timeout=15)
                    filesize = len(img_r.content) if img_r.status_code == 200 else 0

            if 0 < filesize <= PLACEHOLDER_MAX_SIZE:
                # 플레이스홀더 이미지 — 포스트 삭제
                dr = requests.delete(
                    f"{cfg['base']}/wp-json/wp/v2/posts/{pid}?force=true",
                    headers=headers, timeout=15
                )
                if dr.status_code == 200:
                    # 미디어도 삭제
                    mdr = requests.delete(
                        f"{cfg['base']}/wp-json/wp/v2/media/{mid}?force=true",
                        headers=headers, timeout=15
                    )
                    media_status = "미디어도삭제" if mdr.status_code == 200 else f"미디어삭제실패({mdr.status_code})"
                    print(f"  [OK] [{prefix}] Post {pid} 삭제완료 ({media_status}): {title} [{filesize}bytes]")
                    deleted += 1
                else:
                    print(f"  [FAIL] [{prefix}] Post {pid} 삭제실패 HTTP {dr.status_code}: {title}")
                    errors += 1
            else:
                print(f"  [SKIP] [{prefix}] Post {pid} 정상이미지 ({filesize}bytes): {title}")
                skipped += 1

        except Exception as e:
            print(f"  [ERR] [{prefix}] Post {pid} 예외: {str(e)[:80]}")
            errors += 1

    print(f"\n[{prefix}] 결과 — 삭제: {deleted}개 | 정상스킵: {skipped}개 | 오류: {errors}개")

print("\n전체 완료")
