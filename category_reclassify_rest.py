#!/usr/bin/env python3
"""NN/CB 카테고리 통합 + Gemini 재분류 (WP REST API) — concurrent.futures로 동시 10개 PUT"""

import argparse, base64, json, logging, os, sys, time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── 사이트 설정 (환경변수) ──
SITES = {
    "NN": {
        "name": "이웃뉴스", "base": "https://neighbornews.kr",
        "user": "rkwkgkgk",
        "app_pw": os.environ.get("WP_NN_APP_PW", os.environ.get("WP_APP_PASSWORD", "")),
    },
    "CB": {
        "name": "CSR브리핑", "base": "https://csrbriefing.kr",
        "user": "rkwkgkgk",
        "app_pw": os.environ.get("WP_CB_APP_PW", os.environ.get("WP_APP_PASSWORD", "")),
    },
}

STANDARD_CATEGORIES = ["정치", "사회", "경제", "IT/과학", "문화/생활", "국제", "환경"]

MERGE_MAP = {
    "IT과학": "IT/과학", "IT・과학": "IT/과학", "과학기술": "IT/과학",
    "산업/IT": "IT/과학", "산업IT": "IT/과학", "산업/IT/과학": "IT/과학",
    "과학・IT": "IT/과학", "과학": "IT/과학", "산업과학": "IT/과학",
    "산업기술": "IT/과학",
    "경제 및 금융": "경제", "산업경제": "경제", "산업/경제": "경제",
    "생활/경제": "경제", "경제]": "경제",
    "사회생활": "사회", "사회]": "사회",
    "세계": "국제", "국방": "국제", "군사/국방": "국제",
    "국제, 정치": "국제", "국제, IT/과학": "국제",
    "국제오피니언": "국제",
    "법정책": "정치",
    "문화생활": "문화/생활", "문화・생활": "문화/생활",
    "여행": "문화/생활", "스포츠": "문화/생활",
    "건강생활": "문화/생활", "건강/생활": "문화/생활",
    "건강/의료": "문화/생활", "건강의료": "문화/생활",
    "건강・의료": "문화/생활", "건강/의학": "문화/생활",
    "의학": "문화/생활", "보험": "문화/생활", "식품": "문화/생활",
    "게임": "문화/생활", "교육": "문화/생활", "오피니언": "문화/생활",
    "교통": "문화/생활",
    "에너지": "환경", "농업": "환경", "농업/농촌": "환경",
    "농업/환경": "환경", "환경/산림": "환경",
    "산업에너지": "환경",
}

# Stage 2 에서 Gemini가 처리할 복합 카테고리
GEMINI_COMPLEX = {"국제, 사회", "국제, 사회, 환경", "국제, 사회, 오피니언",
                  "국제, 사회, IT/과학, 오피니언"}
KEEP_CATEGORIES = {"미분류", "건강/과학"}

GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_BATCH_SIZE = 20
MAX_WORKERS = 10  # 동시 PUT 요청 수

# ── 로거 ──
def setup_logger(site_key):
    logger = logging.getLogger(site_key)
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    if not logger.handlers:
        logger.addHandler(ch)
    return logger

# ── Gemini REST API 직접 호출 ──
def gemini_generate(prompt, api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1}
    }
    for attempt in range(5):
        try:
            r = requests.post(url, json=payload, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** attempt * 5)
                continue
            r.raise_for_status()
            data = r.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            time.sleep(2 ** attempt * 2)
    return None

# ── WP REST API 클라이언트 ──
class WPClient:
    def __init__(self, base, user, app_pw, dry_run, logger):
        self.base = base.rstrip("/")
        cred = base64.b64encode(f"{user}:{app_pw}".encode()).decode()
        self.headers = {"Authorization": f"Basic {cred}", "Content-Type": "application/json"}
        self.dry_run = dry_run
        self.log = logger

    def _req(self, method, path, **kw):
        url = f"{self.base}{path}"
        for attempt in range(5):
            try:
                r = requests.request(method, url, headers=self.headers, timeout=60, **kw)
                if r.status_code == 429 or r.status_code >= 500:
                    wait = min(2 ** attempt * 5, 60)
                    self.log.warning(f"HTTP {r.status_code} — {wait}s 후 재시도")
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                return r.json() if r.text else {}
            except Exception as e:
                wait = min(2 ** attempt * 2, 30)
                self.log.warning(f"요청 오류: {e} — {wait}s 재시도 ({attempt+1}/5)")
                time.sleep(wait)
        self.log.error(f"최종 실패: {method} {path}")
        return None

    def get_categories(self):
        cats, page = [], 1
        while True:
            data = self._req("GET", f"/wp-json/wp/v2/categories?per_page=100&page={page}")
            if not data: break
            cats.extend(data)
            if len(data) < 100: break
            page += 1
        return cats

    def create_category(self, name):
        if self.dry_run:
            self.log.info(f"[DRY-RUN] 카테고리 생성: {name}")
            return {"id": -1, "name": name}
        return self._req("POST", "/wp-json/wp/v2/categories", json={"name": name})

    def get_posts_by_cat(self, cat_id):
        posts, page = [], 1
        while True:
            data = self._req("GET", f"/wp-json/wp/v2/posts?categories={cat_id}&per_page=100&page={page}&_fields=id,title,categories&status=any")
            if not data: break
            posts.extend(data)
            if len(data) < 100: break
            page += 1
        return posts

    def get_all_posts(self):
        posts, page = [], 1
        while True:
            data = self._req("GET", f"/wp-json/wp/v2/posts?per_page=100&page={page}&_fields=id,title,categories&status=any")
            if not data: break
            posts.extend(data)
            self.log.info(f"  기사 로드: {len(posts)}건...")
            if len(data) < 100: break
            page += 1
        return posts

    def update_post_cat(self, post_id, cat_ids):
        if self.dry_run:
            self.log.debug(f"[DRY-RUN] 기사 {post_id} → {cat_ids}")
            return True
        r = self._req("PUT", f"/wp-json/wp/v2/posts/{post_id}", json={"categories": cat_ids})
        return r is not None

    def update_post_cat_bulk(self, tasks):
        """tasks: list of (post_id, cat_ids) — ThreadPoolExecutor로 동시 PUT"""
        if self.dry_run:
            for post_id, cat_ids in tasks:
                self.log.debug(f"[DRY-RUN] 기사 {post_id} → {cat_ids}")
            return len(tasks), 0

        success, fail = 0, 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {ex.submit(self.update_post_cat, pid, cids): pid
                       for pid, cids in tasks}
            for fut in as_completed(futures):
                if fut.result():
                    success += 1
                else:
                    fail += 1
        return success, fail

    def delete_category(self, cat_id):
        if self.dry_run:
            self.log.info(f"[DRY-RUN] 카테고리 {cat_id} 삭제")
            return True
        return self._req("DELETE", f"/wp-json/wp/v2/categories/{cat_id}?force=true") is not None

# ── 진행 상태 ──
class Progress:
    def __init__(self, site_key, stage):
        self.path = f"/tmp/reclass_progress_{site_key}_{stage}.json"
        self.data = {}
        if os.path.exists(self.path):
            try: self.data = json.loads(open(self.path).read())
            except: pass
    def save(self):
        open(self.path, "w").write(json.dumps(self.data, ensure_ascii=False))
    def is_done(self, key): return self.data.get(key) == "done"
    def mark_done(self, key):
        self.data[key] = "done"
        self.save()

# ── Stage 1 ──
def run_stage1(wp, dry_run, log):
    log.info("=" * 50)
    log.info("Stage 1: 카테고리 정리")
    log.info("=" * 50)

    all_cats = wp.get_categories()
    by_name = {}
    for c in all_cats:
        by_name.setdefault(c["name"], []).append(c)
    log.info(f"총 {len(all_cats)}개 카테고리")

    # 표준 카테고리 확인/생성
    std_ids = {}
    for name in STANDARD_CATEGORIES:
        cands = by_name.get(name, [])
        if cands:
            std_ids[name] = cands[0]["id"]
            log.info(f"  [존재] {name} (id={cands[0]['id']})")
        else:
            r = wp.create_category(name)
            if r and r.get("id"):
                std_ids[name] = r["id"]
                log.info(f"  [생성] {name} (id={r['id']})")

    # 중복 병합 — bulk PUT 적용
    log.info("중복 카테고리 병합 중...")
    state = Progress("stage1", wp.base.split("//")[1].split(".")[0])
    cats_to_delete = []

    for dup_name, std_name in MERGE_MAP.items():
        if std_name not in std_ids: continue
        cands = by_name.get(dup_name, [])
        if not cands: continue
        std_id = std_ids[std_name]
        for dup in cands:
            if dup["id"] == std_id: continue
            key = f"merge_{dup['id']}"
            if state.is_done(key):
                cats_to_delete.append(dup["id"])
                continue
            posts = wp.get_posts_by_cat(dup["id"])
            log.info(f"  [{dup_name}] id={dup['id']} → [{std_name}] {len(posts)}건")
            tasks = []
            for p in posts:
                new_cats = [c for c in p["categories"] if c != dup["id"]]
                if std_id not in new_cats: new_cats.append(std_id)
                tasks.append((p["id"], new_cats))
            if tasks:
                ok, fail = wp.update_post_cat_bulk(tasks)
                log.info(f"    PUT 완료: {ok}건 성공, {fail}건 실패")
            state.mark_done(key)
            cats_to_delete.append(dup["id"])

    # 같은 이름 다른 ID 병합
    for std_name, std_id in std_ids.items():
        cands = by_name.get(std_name, [])
        for c in cands:
            if c["id"] == std_id: continue
            key = f"same_{c['id']}"
            if state.is_done(key):
                cats_to_delete.append(c["id"])
                continue
            posts = wp.get_posts_by_cat(c["id"])
            log.info(f"  [{std_name}] 중복 id={c['id']} → id={std_id} {len(posts)}건")
            tasks = []
            for p in posts:
                new_cats = [cc for cc in p["categories"] if cc != c["id"]]
                if std_id not in new_cats: new_cats.append(std_id)
                tasks.append((p["id"], new_cats))
            if tasks:
                ok, fail = wp.update_post_cat_bulk(tasks)
                log.info(f"    PUT 완료: {ok}건 성공, {fail}건 실패")
            state.mark_done(key)
            cats_to_delete.append(c["id"])

    # 빈 카테고리 삭제
    log.info("빈 카테고리 삭제 중...")
    updated_cats = wp.get_categories()
    protect = KEEP_CATEGORIES | GEMINI_COMPLEX | set(STANDARD_CATEGORIES)
    deleted = 0
    for c in updated_cats:
        if c["id"] in cats_to_delete and c["name"] not in protect and c["count"] == 0:
            wp.delete_category(c["id"])
            deleted += 1
    log.info(f"삭제: {deleted}개")

# ── Stage 2 ──
def run_stage2(wp, dry_run, log):
    log.info("=" * 50)
    log.info("Stage 2: Gemini 재분류")
    log.info("=" * 50)

    api_key = os.environ["GOOGLE_API_KEY"]

    all_cats = wp.get_categories()
    std_ids = {}
    for c in all_cats:
        if c["name"] in STANDARD_CATEGORIES:
            std_ids[c["name"]] = c["id"]
    if len(std_ids) < 7:
        log.error(f"표준 카테고리 부족: {std_ids}")
        return

    log.info("전체 기사 로드 중...")
    all_posts = wp.get_all_posts()
    total = len(all_posts)
    log.info(f"총 {total}건")

    state = Progress("stage2", wp.base.split("//")[1].split(".")[0])
    changed, skipped, errors = 0, 0, 0

    for batch_start in range(0, total, GEMINI_BATCH_SIZE):
        batch = all_posts[batch_start:batch_start + GEMINI_BATCH_SIZE]
        bkey = f"b{batch_start}"
        if state.is_done(bkey):
            skipped += len(batch)
            continue

        titles = []
        for i, p in enumerate(batch, 1):
            t = p.get("title", {})
            title = t.get("rendered", "") if isinstance(t, dict) else str(t)
            titles.append(f"{i}. {title}")

        prompt = f"""다음 기사 제목들을 보고 각각 가장 적합한 카테고리 1개를 선택하세요.
카테고리: 정치, 사회, 경제, IT/과학, 문화/생활, 국제, 환경

반드시 아래 JSON 형식으로만 응답하세요:
{{"1": "카테고리", "2": "카테고리", ...}}

기사 목록:
{chr(10).join(titles)}"""

        result_map = {}
        for attempt in range(5):
            try:
                raw = gemini_generate(prompt, api_key)
                if raw is None:
                    raise Exception("Gemini API 응답 없음")
                raw = raw.strip()
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"): raw = raw[4:]
                result_map = json.loads(raw.strip())
                break
            except json.JSONDecodeError:
                time.sleep(2 ** attempt)
            except Exception as e:
                log.warning(f"Gemini 오류: {e}")
                time.sleep(2 ** attempt * 2)
        else:
            errors += len(batch)
            continue

        # 배치 내 PUT 태스크 수집 후 bulk 실행
        put_tasks = []
        batch_skipped = 0
        batch_errors = 0
        for i, p in enumerate(batch, 1):
            cat_name = result_map.get(str(i), "").strip()
            if cat_name not in std_ids:
                batch_errors += 1
                continue
            new_id = std_ids[cat_name]
            cur = p.get("categories", [])
            cur_std = [c for c in cur if c in std_ids.values()]
            if len(cur_std) == 1 and cur_std[0] == new_id:
                batch_skipped += 1
                continue
            put_tasks.append((p["id"], [new_id]))

        if put_tasks:
            ok, fail = wp.update_post_cat_bulk(put_tasks)
            changed += ok
            errors += fail
        skipped += batch_skipped
        errors += batch_errors

        state.mark_done(bkey)
        done = batch_start + len(batch)
        log.info(f"진행: {done}/{total} | 변경: {changed} | 스킵: {skipped} | 에러: {errors}")
        time.sleep(0.3)

    # 결과 요약
    log.info("\n=== 재분류 완료 ===")
    log.info(f"총 기사:  {total:,}")
    log.info(f"변경:     {changed:,}")
    log.info(f"스킵:     {skipped:,}")
    log.info(f"에러:     {errors:,}")

    updated_cats = wp.get_categories()
    log.info("\n카테고리별 분포:")
    for c in sorted(updated_cats, key=lambda x: x["count"], reverse=True):
        if c["name"] in STANDARD_CATEGORIES:
            pct = c["count"] / total * 100 if total > 0 else 0
            log.info(f"  {c['name']:12}: {c['count']:>6,} ({pct:.1f}%)")

# ── main ──
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=list(SITES.keys()) + ["all"], default="all")
    parser.add_argument("--stage", choices=["stage1", "stage2", "all"], default="all")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    sites = list(SITES.keys()) if args.site == "all" else [args.site]

    for sk in sites:
        site = SITES[sk]
        log = setup_logger(sk)
        log.info(f"=== {site['name']} ({site['base']}) ===")
        if args.dry_run: log.info("[DRY-RUN 모드]")
        wp = WPClient(site["base"], site["user"], site["app_pw"], args.dry_run, log)
        if args.stage in ("stage1", "all"): run_stage1(wp, args.dry_run, log)
        if args.stage in ("stage2", "all"): run_stage2(wp, args.dry_run, log)

    print("\n모든 작업 완료.")

if __name__ == "__main__":
    main()
