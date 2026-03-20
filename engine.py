#!/usr/bin/env python3
"""
────────────────────────────────────────────────────────
[v24.0-GitHub_Actions + Vultr_MariaDB]
- Google Sheets 완전 폐기 → Vultr MariaDB 중복 체크
- GitHub Actions 스케줄 실행 (40분마다)
- 모든 민감 정보 → 환경변수 (GitHub Secrets)
- 구조: RSS 수집 → 중복 확인(DB) → AI 재작성 → WP 발행 → DB 기록
────────────────────────────────────────────────────────
"""
from __future__ import annotations

import sys
import time
import re
import base64
import json
import os
import difflib
import calendar
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urljoin, urlparse, parse_qs

import requests
import feedparser
import pymysql
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ========================= [1. 환경변수 로드] =========================

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
DB_HOST = os.environ["DB_HOST"]
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]
DB_NAME = os.environ["DB_NAME"]

WP_CFG = {
    "IJ_": {
        "base": "https://api.impactjournal.kr",
        "user": "erumadmin",
        "app_pw": os.environ["WP_IJ_APP_PW"],
        "gsc_site": "sc-domain:impactjournal.kr",
        "sitemap": "https://impactjournal.kr/sitemap-news.xml",
    },
    "NN_": {
        "base": "https://neighbornews.kr",
        "user": "rkwkgkgk",
        "app_pw": os.environ["WP_NN_APP_PW"],
        "gsc_site": "sc-domain:neighbornews.kr",
        "sitemap": "https://neighbornews.kr/sitemap-news.xml",
    },
    "CB_": {
        "base": "https://csrbriefing.kr",
        "user": "rkwkgkgk",
        "app_pw": os.environ["WP_CB_APP_PW"],
        "gsc_site": "sc-domain:csrbriefing.kr",
        "sitemap": "https://csrbriefing.kr/sitemap-news.xml",
    },
}

# [모델 설정]
GEMINI_MODEL = "gemini-2.5-pro"
GEMINI_MODEL_QA = "gemini-3.1-flash-lite-preview"

DAILY_PUBLISH_LIMIT = 50
MIN_MEDIA_LIMIT = 1000
MEDIA_PREFIXES = ["IJ_", "NN_", "CB_"]

RSS_FEEDS = [
    "https://www.korea.kr/rss/policy.xml",
    "https://www.korea.kr/rss/dept_opm.xml",
    "https://www.korea.kr/rss/dept_moef.xml",
    "https://www.korea.kr/rss/dept_msit.xml",
    "https://www.korea.kr/rss/dept_moe.xml",
    "https://www.korea.kr/rss/dept_mofa.xml",
    "https://www.korea.kr/rss/dept_unikorea.xml",
    "https://www.korea.kr/rss/dept_moj.xml",
    "https://www.korea.kr/rss/dept_mnd.xml",
    "https://www.korea.kr/rss/dept_mois.xml",
    "https://www.korea.kr/rss/dept_mpva.xml",
    "https://www.korea.kr/rss/dept_mcst.xml",
    "https://www.korea.kr/rss/dept_mafra.xml",
    "https://www.korea.kr/rss/dept_motir.xml",
    "https://www.korea.kr/rss/dept_mw.xml",
    "https://www.korea.kr/rss/dept_mcee.xml",
    "https://www.korea.kr/rss/dept_moel.xml",
    "https://www.korea.kr/rss/dept_mogef.xml",
    "https://www.korea.kr/rss/dept_molit.xml",
    "https://www.korea.kr/rss/dept_mof.xml",
    "https://www.korea.kr/rss/dept_mss.xml",
    "https://www.korea.kr/rss/dept_mpb.xml",
    "https://www.korea.kr/rss/dept_mpm.xml",
    "https://www.korea.kr/rss/dept_moleg.xml",
    "https://www.korea.kr/rss/dept_mfds.xml",
    "https://www.korea.kr/rss/dept_mods.xml",
    "https://www.korea.kr/rss/dept_moip.xml",
    "https://api.newswire.co.kr/rss/all",
]

BLOCKED_IMAGE_PATTERNS = [
    "btn_textview", "icon_logo", "go_new", "koreakr_og", "koreakr_fb",
    "representative", "/btn/", "/bt_/", "/icon/", "rss.png", "rss_icon",
    "print_icon", "facebook_icon", "twitter_icon", "sns_icon", "share_icon",
    "blank.gif", "no_image", "default_image", "logo_korea", "korea_logo",
    "newswire_logo", "nw_logo", "logo_newswire", "/company_img/",
    "korea_logo_2024",
]

# 이미지 최소 파일 크기 (bytes) — 이 이하는 로고/아이콘으로 간주하여 스킵
MIN_IMAGE_BYTES = 50_000

CONTACT_ALT_RE = re.compile(r'\d{2,3}-\d{3,4}-\d{4}|담당\s*부서|책임자.*과\s*장|사무관.*주무관')

COPYRIGHT_KEYWORDS = [
    "무단전재", "재배포", "복제", "금지", "저작권", "Copyright",
    "All rights reserved", "전재", "배포", "승인", "불허", "무단",
]

KEYWORD_CATEGORIES_FALLBACK = {
    "IT/과학": ["ai", "인공지능", "반도체", "it", "플랫폼", "기술"],
    "환경": ["환경부", "기후", "에너지", "탄소", "esg"],
    "문화/생활": ["여행", "관광", "축제", "문화", "예술"],
    "경제": ["경제", "금융", "투자", "수출", "기업", "자동차", "전기차"],
    "국제": ["미국", "중국", "해외", "글로벌"],
    "사회": ["사회", "복지", "의료", "교육", "안전"],
    "정치": ["대통령", "국회", "정책", "행정"],
}
DEFAULT_CATEGORY = "사회"

# IJ 카테고리별 기자 매핑 (WP user ID)
IJ_CATEGORY_AUTHOR = {
    "사회":      2,  # 김민서
    "경제":      3,  # 이준혁
    "IT/과학":   4,  # 박지은
    "환경":      5,  # 정하윤
    "문화/생활":  6,  # 최수빈
    "국제":      7,  # 윤서준
    "정치":      8,  # 강현우
}

# ========================= [2. Gemini / 프롬프트] =========================

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

PROMPT_USER_TEMPLATE = """
# [원문 자료]:
{original_text}
"""

script_dir = os.path.dirname(os.path.abspath(__file__))

def load_skill(skill_name: str) -> str:
    skill_path = os.path.join(script_dir, "prompts", f"{skill_name}.md")
    try:
        with open(skill_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return "본문을 요약해서 기사로 작성하세요. 끝문장은 '다.'로 통일할 것."

PERSONA_DEFINITIONS = {
    "IJ_": load_skill("news_editor_ij"),
    "NN_": load_skill("news_editor_nn"),
    "CB_": load_skill("news_editor_cb"),
}

def ask_gemini(persona, text, model=None):
    use_model = model or GEMINI_MODEL
    user_msg = PROMPT_USER_TEMPLATE.format(original_text=text)
    response = gemini_client.models.generate_content(
        model=use_model,
        contents=user_msg,
        config=types.GenerateContentConfig(system_instruction=persona),
    )
    return response.text.strip()

# ========================= [3. DB 연동 (Vultr MariaDB)] =========================

def get_db_connection():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )

def db_get_existing_ids_and_titles() -> Tuple[set, set]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT url_id, title FROM published_articles")
            rows = cur.fetchall()
        return {r["url_id"] for r in rows}, {r["title"] for r in rows if r["title"]}
    finally:
        conn.close()

def db_record_published(url_id: str, title: str, media: str):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT IGNORE INTO published_articles (url_id, title, media) VALUES (%s, %s, %s)",
                (url_id, title[:1000], media),
            )
        conn.commit()
    finally:
        conn.close()

def db_get_today_count() -> int:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM published_articles WHERE DATE(published_at) = CURDATE()")
            return cur.fetchone()["cnt"]
    finally:
        conn.close()

# ========================= [4. 텍스트 처리 / QA] =========================

def is_mainly_korean(text, threshold=0.5):
    if not text: return False
    clean_text = re.sub(r'[^가-힣a-zA-Z]', '', text)
    if not clean_text: return False
    korean_char_count = len(re.findall(r'[가-힣]', clean_text))
    return (korean_char_count / len(clean_text)) >= threshold

def normalize_text(text):
    if not text: return ""
    text = re.sub(r'\[.*?\]|\(.*?\)', '', text)
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', text)

def is_semantic_duplicate(new_title, existing_titles, threshold=0.9):
    clean_new = normalize_text(new_title)
    if not clean_new: return False
    for ex_title in existing_titles:
        clean_ex = normalize_text(ex_title)
        if not clean_ex: continue
        if clean_new == clean_ex: return True
        if difflib.SequenceMatcher(None, clean_new, clean_ex).ratio() >= threshold:
            print(f"      🚫 [중복] 유사도 높음: '{new_title[:30]}' vs '{ex_title[:30]}'")
            return True
    return False

def extract_unique_id(url):
    if not url: return ""
    if "newswire.co.kr" in url:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if 'no' in qs: return f"nw_{qs['no'][0]}"
    return url.replace("https://", "").replace("http://", "").replace("www.", "").strip().rstrip("/")

def validate_content_quality(title, body):
    # 제목
    if not title or len(title) < 5:
        return False, "제목 누락 또는 너무 짧음"

    # 본문 길이
    if len(body) < 300:
        return False, f"본문 너무 짧음({len(body)}자)"

    # 라벨 잔재
    for label in ["제목:", "본문:", "내용:", "카테고리:", "태그:", "Title:", "Body:"]:
        if label in body:
            return False, f"라벨 잔재 발견({label})"

    # 포맷 오염
    if "**" in body or "##" in body:
        return False, "마크다운(**, ##) 잔재 발견"
    # HTML 태그 검사 제거: clean_body_html()이 의도적으로 <p>/<strong>/<h3> 등을 생성하므로 오탐

    # 미완성 기사
    if "..." in body or "…" in body:
        return False, "말줄임표(미완성 의심) 발견"
    stripped = body.rstrip()
    plain_for_check = re.sub(r'<[^>]+>', '', stripped).strip()
    if plain_for_check and plain_for_check[-1] not in ("다", ".", "!", "?", '"', "'", "〉", "》"):
        return False, f"본문 마지막 문자 비정상({plain_for_check[-1]!r})"

    # 사고 과정 노출
    for pat in ["Step 1", "Step 2", "Phase 1", "분석:", "생각:", "검토:", "THINK"]:
        if pat in body:
            return False, f"내부 추론 노출({pat})"

    # 경어체 혼용
    if re.search(r'(습니다|입니다|드립니다|겠습니다)', body):
        return False, "경어체(습니다) 혼용 발견"

    return True, "OK"

# [v23.0] AI 품질검수 시스템
MEDIA_TONE_DESC = {
    "IJ_": "솔루션 저널리즘 - 사회 문제의 구조적 해결책 제시, 수요자 중심 관점",
    "NN_": "커뮤니티 저널리즘 - 어려운 뉴스를 쉽고 품격 있게, 지역·공동체 소식 중심",
    "CB_": "비즈니스 분석 - 산업 트렌드와 ESG 시사점, 경영 전략 관점",
}

QA_SYSTEM_PROMPT = load_skill("qa_checker")

def ai_quality_check(title: str, body: str, media_prefix: str) -> Tuple[bool, List[str], int, Optional[dict]]:
    try:
        media_tone = MEDIA_TONE_DESC.get(media_prefix, "일반 뉴스")
        system_prompt = QA_SYSTEM_PROMPT.format(media_tone=media_tone)
        article_text = f"제목: {title}\n\n본문:\n{body}"
        raw = ask_gemini(system_prompt, article_text, model=GEMINI_MODEL_QA)
        parts = raw.split("---", 1)
        json_part = parts[0]
        clean = re.sub(r"```json\s*", "", json_part)
        clean = re.sub(r"```\s*", "", clean).strip()
        result = json.loads(clean)
        total = int(result.get("total", 0))
        passed = result.get("pass", False) and total >= 72
        fails = result.get("fails", [])
        if not fails and not passed:
            fails = [f"총점 {total}점 미달"]
        fixed = None
        if not passed and len(parts) > 1:
            fixed = parse_gemini_response(parts[1].strip())
        return passed, fails, total, fixed
    except Exception as e:
        print(f"      ⚠️ [AI검수] 파싱 실패({str(e)[:50]}), 통과 처리")
        return True, [], 0, None

def clean_body_html(text):
    if not text: return ""
    text = text.replace("본문:", "").replace("본문 :", "").replace("내용:", "").replace("내용 :", "")
    text = text.replace("Body:", "").replace("Body :", "").replace("Title:", "").replace("제목:", "")
    text = re.sub(r'^(본문|Body|내용)[:\s-]*', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'^##\s+(.*?)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^###\s+(.*?)$', r'<h4>\1</h4>', text, flags=re.MULTILINE)
    lines = text.split('\n')
    formatted_lines = []
    for line in lines:
        line = line.strip()
        if not line: continue
        if line.startswith('<h') or line.startswith('<li') or line.startswith('<p'):
            formatted_lines.append(line)
        else:
            formatted_lines.append(f"<p>{line}</p>")
    return "".join(formatted_lines)

def parse_gemini_response(text):
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL).strip()
    title_m = re.search(r"(?:제목|Title|헤드라인)[:\s]\s*(.*)", text, re.IGNORECASE)
    if title_m:
        title = title_m.group(1).strip()
    else:
        title = text.split('\n')[0].strip()
    title = re.sub(r"[#\*\[\]]", "", title).strip().strip('"')
    excerpt_m = re.search(r"(?:리드문|Excerpt|요약)[:\s]\s*(.*)", text, re.IGNORECASE)
    excerpt = re.sub(r"[#\*\[\]]", "", excerpt_m.group(1).strip()).strip() if excerpt_m else ""
    cat_m = re.search(r"(?:카테고리|Category)[:\s]\s*(.*)", text, re.IGNORECASE)
    tag_m = re.search(r"(?:태그|Tags)[:\s]\s*(.*)", text, re.IGNORECASE)
    cat = cat_m.group(1).strip() if cat_m else ""
    tags = [t.strip() for t in tag_m.group(1).split(',')] if tag_m else []
    body_raw = text
    if title_m:
        body_raw = body_raw.replace(title_m.group(0), "", 1)
    else:
        body_raw = body_raw.replace(title, "", 1)
    if excerpt_m:
        body_raw = body_raw.replace(excerpt_m.group(0), "", 1)
    if cat_m:
        body_raw = body_raw.split(cat_m.group(0))[0]
    elif tag_m:
        body_raw = body_raw.split(tag_m.group(0))[0]
    final_body = clean_body_html(body_raw)
    # 리드문이 비어 있으면 본문 첫 2문장으로 자동 생성
    if not excerpt and final_body:
        plain = re.sub(r'<[^>]+>', ' ', final_body).strip()
        plain = re.sub(r'\s+', ' ', plain)
        sentences = re.split(r'(?<=[다요])\. *', plain)
        excerpt = '. '.join(s.strip() for s in sentences[:2] if s.strip())
        if len(excerpt) > 160:
            excerpt = excerpt[:157] + '...'
    return {"title": title, "excerpt": excerpt, "body": final_body, "cat": cat, "tags": tags}

def get_hybrid_meta(title, body, ai_cat, ai_tags):
    valid = KEYWORD_CATEGORIES_FALLBACK.keys()
    cat = ai_cat.replace('[', '').replace(']', '').strip()
    if cat not in valid:
        cat = DEFAULT_CATEGORY
    tags = ai_tags
    if not tags:
        all_kw = {k for v in KEYWORD_CATEGORIES_FALLBACK.values() for k in v}
        for k in sorted(list(all_kw), key=len, reverse=True):
            if k in title.lower() or k in body.lower():
                tags.append(k)
            if len(tags) >= 5:
                break
    return cat, tags

def strip_html_tags(html):
    return BeautifulSoup(html, "html.parser").get_text(separator='\n', strip=True) if html else ""

# ========================= [5. 워드프레스 연동] =========================

def _auth_hdr(user, pw):
    return {"Authorization": f"Basic {base64.b64encode(f'{user}:{pw}'.encode()).decode()}", "User-Agent": "Mozilla/5.0"}

class Site:
    def __init__(self, base, user, app_pw):
        self.base = base.rstrip("/")
        self.sess = requests.Session()
        self.sess.headers.update(_auth_hdr(user, app_pw))

    def _safe_json(self, response):
        text = response.text.lstrip('\ufeff').strip()
        if text and not text.startswith('{') and not text.startswith('['):
            idx = text.find('{')
            idx2 = text.find('[')
            if idx < 0: idx = idx2
            elif idx2 >= 0: idx = min(idx, idx2)
            if idx >= 0:
                text = text[idx:]
        decoder = json.JSONDecoder()
        result, _ = decoder.raw_decode(text)
        return result

    def _ensure(self, kind, name):
        if not name: return None
        clean = re.sub(r'[^\w\s가-힣]', '', name).strip()[:30]
        if not clean: return None
        try:
            r = self.sess.get(f"{self.base}/wp-json/wp/v2/{kind}", params={"search": clean, "per_page": 1}, timeout=10)
            if r.ok and self._safe_json(r): return self._safe_json(r)[0]["id"]
            r2 = self.sess.post(f"{self.base}/wp-json/wp/v2/{kind}", json={"name": clean}, timeout=10)
            if r2.status_code == 400: return self._safe_json(r2).get("data", {}).get("term_id")
            r2.raise_for_status()
            return self._safe_json(r2)["id"]
        except:
            return None

    def get_cat_id(self, name): return self._ensure("categories", name)
    def get_tag_ids(self, tags): return [tid for t in tags if (tid := self._ensure("tags", t))]

    def upload_image_bytes(self, img_bytes, filename, content_type, alt, cap=None):
        try:
            h = self.sess.headers.copy()
            h.update({"Content-Disposition": f'attachment; filename="{filename}"', "Content-Type": content_type})
            final_caption = cap if cap and len(cap) > 5 else alt
            p = {"alt_text": alt[:100], "caption": final_caption[:200]}
            up = self.sess.post(f"{self.base}/wp-json/wp/v2/media", headers=h, data=img_bytes, params=p, timeout=40)
            up.raise_for_status()
            result = self._safe_json(up)
            return result.get("id"), result.get("source_url")
        except Exception as e:
            err_msg = str(e)
            if hasattr(e, 'response') and e.response is not None:
                err_msg = e.response.text
            print(f"\n      ❌ [이미지 업로드 에러]: {err_msg[:200]}")
            return None, None

    def create_post(self, title, body, cat, tags, mid=None, excerpt="", author=None):
        d = {"title": title, "content": body, "status": "publish", "categories": [cat] if cat else [], "tags": tags}
        if mid: d["featured_media"] = mid
        if excerpt: d["excerpt"] = excerpt
        if author: d["author"] = author
        r = self.sess.post(f"{self.base}/wp-json/wp/v2/posts", json=d, timeout=30)
        r.raise_for_status()
        return self._safe_json(r)["id"]

    def get_total_media_count(self) -> int:
        try:
            r = self.sess.head(f"{self.base}/wp-json/wp/v2/media", params={"per_page": 1}, timeout=5)
            if r.status_code == 200: return int(r.headers.get('X-WP-Total', 0))
            r = self.sess.get(f"{self.base}/wp-json/wp/v2/media", params={"per_page": 1}, timeout=5)
            return int(r.headers.get('X-WP-Total', 0))
        except:
            return 0

    def delete_oldest_media(self, count):
        if count <= 0: return
        print(f"   - [{self.base}] 구형 이미지 {count}개 삭제 시작...", end="", flush=True)
        remain = count
        while remain > 0:
            batch_size = min(50, remain)
            try:
                r = self.sess.get(f"{self.base}/wp-json/wp/v2/media",
                                  params={"per_page": batch_size, "orderby": "date", "order": "asc", "fields": "id"}, timeout=20)
                if not r.ok: break
                items = self._safe_json(r)
                if not items: break
                deleted_in_batch = 0
                for item in items:
                    try:
                        del_res = self.sess.delete(f"{self.base}/wp-json/wp/v2/media/{item['id']}", params={"force": True}, timeout=10)
                        if del_res.ok: deleted_in_batch += 1
                    except:
                        pass
                remain -= deleted_in_batch
                if deleted_in_batch == 0: break
            except:
                break
        print(" 완료.")

SITES = {k: Site(v['base'], v['user'], v['app_pw']) for k, v in WP_CFG.items()}

# ========================= [6. GSC 사이트맵 제출] =========================

def submit_sitemap_to_gsc(prefix):
    cfg = WP_CFG.get(prefix)
    if not cfg or not cfg.get("gsc_site"): return

    gsc_json_b64 = os.environ.get("GSC_SERVICE_ACCOUNT_JSON")
    if not gsc_json_b64:
        print(f"      ⚠️ [GSC] 서비스 계정 미설정, 사이트맵 제출 생략")
        return

    site_url = cfg["gsc_site"]
    sitemap_url = cfg["sitemap"]
    print(f"      📡 [GSC] 사이트맵 제출 시도: {site_url}")

    try:
        import tempfile, urllib.parse
        sa_json = base64.b64decode(gsc_json_b64).decode("utf-8")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            tmp.write(sa_json)
            tmp_path = tmp.name

        SCOPES = ['https://www.googleapis.com/auth/webmasters']
        creds = service_account.Credentials.from_service_account_file(tmp_path, scopes=SCOPES)
        service = build('searchconsole', 'v1', credentials=creds)
        os.unlink(tmp_path)

        try:
            service.sitemaps().submit(siteUrl=site_url, feedpath=sitemap_url).execute()
            print(f"      ✅ [GSC] 사이트맵 제출 완료: {site_url}")
        except Exception as e:
            if "sc-domain:" in site_url and "403" in str(e):
                encoded_site_url = urllib.parse.quote(site_url, safe='')
                service.sitemaps().submit(siteUrl=encoded_site_url, feedpath=sitemap_url).execute()
                print(f"      ✅ [GSC] 사이트맵 제출 완료(인코딩형식)")
            else:
                raise e
    except Exception as e:
        print(f"      ⚠️ [GSC] 제출 실패: {str(e)[:200]}")

# ========================= [7. 이미지 처리] =========================

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

def fetch_with_retry(url, max_retries=2, timeout=15, stream=False):
    for attempt in range(max_retries + 1):
        try:
            r = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout, stream=stream)
            return r
        except (requests.exceptions.ConnectionError, ConnectionResetError):
            if attempt < max_retries:
                time.sleep(1 + attempt)
                continue
            raise
    return None

def is_valid_image(url):
    if not url: return False
    try:
        r = fetch_with_retry(url, timeout=10, stream=True)
        if not (r and r.status_code == 200): return False
        if 'image' not in r.headers.get('Content-Type', '').lower(): return False
        # Content-Length로 빠른 크기 사전 확인 (헤더에 있을 때만)
        cl = int(r.headers.get('Content-Length', 0))
        if 0 < cl < MIN_IMAGE_BYTES:
            print(f" [크기 미달 {cl//1024}KB < {MIN_IMAGE_BYTES//1024}KB, 스킵]", end="")
            return False
        return True
    except:
        return False

def fix_newswire_url(url: str) -> str:
    if "newswire.co.kr" in url and "/thumb/" in url:
        return re.sub(r'/thumb/\d+/', '/data/', url).replace('/data/data/', '/data/')
    return url

def extract_image_from_html(html: str, base_url: str = "") -> Tuple[Optional[str], Optional[str]]:
    """HTML 문자열에서 이미지를 추출 (RSS summary용)"""
    if not html: return None, None
    try:
        soup = BeautifulSoup(html, 'html.parser')
        for img in soup.select('img'):
            src = img.get('src', '')
            if len(src) < 10: continue
            if any(x in src.lower() for x in BLOCKED_IMAGE_PATTERNS): continue
            alt = img.get('alt', '')
            if alt:
                if CONTACT_ALT_RE.search(alt): continue
                if "무단전재" in alt or "재배포" in alt: src = ""
            if not src: continue
            # 이미지 주변 캡션(figcaption, 다음 형제 태그)에서 copyright 체크
            caption_text = ""
            parent = img.parent
            if parent:
                fig = parent.find('figcaption')
                if fig:
                    caption_text = fig.get_text(strip=True)
                else:
                    for sib in img.next_siblings:
                        if hasattr(sib, 'get_text'):
                            caption_text = sib.get_text(strip=True)[:200]
                        elif isinstance(sib, str) and sib.strip():
                            caption_text = sib.strip()[:200]
                        if caption_text: break
            if "무단전재" in caption_text or "재배포" in caption_text:
                continue
            full_url = urljoin(base_url, src) if base_url else src
            return fix_newswire_url(full_url), alt or caption_text or None
    except:
        pass
    return None, None

def extract_image_with_caption(url: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        r = fetch_with_retry(url, timeout=15)
        if not r or r.status_code != 200: return None, None
        soup = BeautifulSoup(r.text, 'html.parser')
        candidates = []
        if 'newswire.co.kr' in url:
            wrappers = soup.select('.image-wrap, .view_img, .news-photo')
            for w in wrappers:
                img = w.select_one('img')
                if img:
                    cap_tag = w.select_one('.caption') or w.select_one('p')
                    cap_text = img.get('alt') or (cap_tag.get_text(strip=True) if cap_tag else "")
                    candidates.append((img, cap_text))

        if 'korea.kr' in url:
            for img in soup.select('img'):
                src = img.get('src', '')
                if 'newsWeb/resources/attaches' in src:
                    candidates.append((img, img.get('alt', '')))

        article = soup.select_one('.view_cont') or soup.select_one('.article-content') or soup.select_one('#articleBody') or soup.select_one('article')
        if article:
            for img in article.select('img'):
                candidates.append((img, img.get('alt', '')))

        for img, cap in candidates:
            src = img.get('src', '')
            if len(src) < 10 or any(x in src.lower() for x in BLOCKED_IMAGE_PATTERNS): continue
            is_risky = False
            if cap:
                if CONTACT_ALT_RE.search(cap): continue
                clean_cap = re.sub(r'[\(\[]사진=.*?[\)\]]', '', cap).strip()
                if "무단전재" in clean_cap or "재배포" in clean_cap: continue
            else:
                clean_cap = None
            if src: return fix_newswire_url(urljoin(url, src)), clean_cap

        og = soup.select_one('meta[property="og:image"]')
        if og and og.get('content'):
            og_url = og.get('content')
            if not any(x in og_url.lower() for x in BLOCKED_IMAGE_PATTERNS):
                return fix_newswire_url(og_url), None
        return None, None
    except:
        return None, None

def find_best_image(article):
    rss_img = article.get("image", "").strip()
    rss_body = article.get("body", "")
    # 1순위: RSS media_content 이미지 — URL 패턴 체크만 (이미지 alt/캡션 저작권 체크는 2·3순위에서 처리)
    if rss_img:
        if not any(b in rss_img for b in BLOCKED_IMAGE_PATTERNS):
            return fix_newswire_url(rss_img), None
        else:
            print(f" [1순위 블록:{rss_img[:50]}]", end="")
    else:
        print(f" [1순위:RSS이미지없음]", end="")
    # 2순위: RSS summary/body HTML에 포함된 <img> 태그 (캡션 copyright 체크 포함)
    if rss_body and "<img" in rss_body.lower():
        hi, hc = extract_image_from_html(rss_body, article.get("url", ""))
        if hi and not any(b in hi for b in BLOCKED_IMAGE_PATTERNS):
            return hi, hc
        else:
            print(f" [2순위 실패]", end="")
    else:
        print(f" [2순위:body img없음]", end="")
    # 3순위: 기사 페이지 직접 접속하여 이미지 추출
    link = article.get("url", "").strip()
    if link:
        li, lc = extract_image_with_caption(link)
        if li and not any(b in li for b in BLOCKED_IMAGE_PATTERNS):
            return li, lc
        else:
            print(f" [3순위 실패:{str(li)[:50]}]", end="")
    return None, None

# ========================= [8. 메인 파이프라인] =========================

def collect_articles(ex_ids: set, ex_titles: set, limit: int) -> list:
    """RSS에서 기사를 수집하여 리스트로 반환 (시트 없이 메모리에서 직접 처리)"""
    today = datetime.now().date()
    current_hour = datetime.now().hour
    articles = []

    def fetch_feed(url, source_name, feed_limit, is_newswire=False):
        if feed_limit <= 0: return 0
        print(f"      📡 [{source_name}] 스캔 중 (목표: {feed_limit}건)...", end="", flush=True)
        count = 0
        try:
            resp = fetch_with_retry(url, timeout=20)
            resp.encoding = 'utf-8'
            f = feedparser.parse(resp.text)
            for e in f.entries:
                if count >= feed_limit: break
                if not hasattr(e, 'link'): continue
                curr_id = extract_unique_id(e.link)
                if curr_id in ex_ids: continue
                if not is_mainly_korean(e.title, threshold=0.5): continue
                if is_semantic_duplicate(e.title, ex_titles, threshold=0.9): continue
                dt = e.get('published_parsed') or e.get('updated_parsed')
                if not dt or datetime.fromtimestamp(calendar.timegm(dt)).date() != today: continue
                if is_newswire and not re.search('[가-힣]', e.title): continue

                img_link = ""
                if hasattr(e, 'media_content'):
                    for mc in e.media_content:
                        if 'image' in mc.get('type', ''): img_link = mc.get('url', ''); break

                articles.append({
                    "url": e.link,
                    "url_id": curr_id,
                    "title": e.title[:1000],
                    "body": e.get('summary', '')[:30000],
                    "image": img_link,
                })
                ex_ids.add(curr_id)
                ex_titles.add(e.title[:1000])
                count += 1
            print(f" {count}건 확보")
        except Exception as err:
            print(f" 오류({err})")
        return count

    total_remaining = limit

    def fetch_policy_feeds(lim):
        got = 0
        for feed_url in RSS_FEEDS[:-1]:
            feed_name = "정책브리핑-" + feed_url.split('/')[-1].replace('dept_', '').replace('.xml', '')
            found = fetch_feed(feed_url, feed_name, lim - got, is_newswire=False)
            got += found
            if got >= lim: break
        return got

    if current_hour < 18:
        print("      ☀️ [주간 모드] '정책브리핑'의 모든 부처를 수집합니다.")
        fetch_policy_feeds(total_remaining)
    else:
        print(f"      🌗 [야간 모드] '정책브리핑' 우선, 부족 시 '뉴스와이어'로 채웁니다.")
        got_policy = fetch_policy_feeds(total_remaining)
        total_remaining -= got_policy
        if total_remaining > 0:
            print(f"      👉 목표 미달({total_remaining}건 부족) -> 뉴스와이어 가동")
            fetch_feed(RSS_FEEDS[-1], "뉴스와이어", total_remaining, is_newswire=True)

    return articles


def process_article(article: dict, upload_counts: dict) -> bool:
    """기사 1건을 3개 매체에 재작성 + WP 발행. 성공 시 True"""
    print(f"\n▶ 기사 처리 시작: {article['title'][:40]}...")

    # 이미지 확인
    print(f"   🔎 이미지 탐색 중...", end="", flush=True)
    best_img, best_cap = find_best_image(article)
    if not best_img:
        print(" 실패 (이미지 없음/저작권). Skip.")
        return False
    print(f" 찾음.")

    if not is_valid_image(best_img):
        if "/data/" in best_img:
            best_img = best_img.replace("/data/", "/thumb_")
        if not is_valid_image(best_img):
            print("   ❌ 이미지 URL 접속 실패. Skip.")
            return False

    # 매체별 재작성 + 발행
    rewritten = {}
    for prefix in MEDIA_PREFIXES:
        print(f"      ✍️ [{prefix}] Gemini 기사 작성 중...", end="", flush=True)
        try:
            res = ask_gemini(PERSONA_DEFINITIONS[prefix], strip_html_tags(article["body"])[:10000])
            p = parse_gemini_response(res)
            is_valid, msg = validate_content_quality(p['title'], p['body'])
            if not is_valid:
                raise Exception(f"QA탈락: {msg}")

            # AI 품질검수+보완 (Flash 1회)
            print(" 작성완료.", flush=True)
            print(f"      🔍 [{prefix}] Flash 품질검수 중...", end="", flush=True)
            passed, fails, score, fixed = ai_quality_check(p['title'], p['body'], prefix)

            if not passed:
                print(f" {score}점(미달).", flush=True)
                if fixed:
                    print(f"      🔧 [{prefix}] 자동보완 적용...", end="", flush=True)
                    is_valid, msg = validate_content_quality(fixed['title'], fixed['body'])
                    if not is_valid:
                        raise Exception(f"보완 후 룰QA탈락: {msg}")
                    p = fixed
                    print(f" 완료.")
                else:
                    raise Exception(f"AI검수 최종미달(점수:{score})")
            else:
                print(f" {score}점 통과.")

            cat, tags = get_hybrid_meta(p['title'], p['body'], p['cat'], p['tags'])
            rewritten[prefix] = {"title": p['title'], "excerpt": p.get('excerpt', ''), "body": p['body'], "cat": cat, "tags": tags}

        except Exception as e:
            print(f" 실패({str(e)[:100]}).")
            rewritten[prefix] = None

    # 이미지 미리 다운로드 (원본 서버 접속 문제 방지)
    print(f"   📥 이미지 다운로드 중...", end="", flush=True)
    try:
        img_resp = fetch_with_retry(best_img, timeout=20)
        if not img_resp or img_resp.status_code != 200:
            print(" 실패. Skip.")
            return False
        img_bytes = img_resp.content
        if len(img_bytes) < MIN_IMAGE_BYTES:
            print(f" 건너뜀 (크기 {len(img_bytes)//1024}KB < {MIN_IMAGE_BYTES//1024}KB). Skip.")
            return False
        img_content_type = img_resp.headers.get("content-type", "image/jpeg")
        fn = re.sub(r'[^\w\.-]', '', best_img.split("/")[-1].split("?")[0])[-50:]
        if not fn: fn = "image.jpg"
        print(f" 완료 ({len(img_bytes)//1024}KB).")
    except Exception as e:
        print(f" 실패({str(e)[:80]}). Skip.")
        return False

    # WP 발행
    all_success = True
    for prefix in MEDIA_PREFIXES:
        rw = rewritten.get(prefix)
        if not rw:
            all_success = False
            continue
        print(f"      🚀 [{prefix}] 워드프레스 발행 중...", end="", flush=True)
        try:
            site = SITES[prefix]
            mid, _ = site.upload_image_bytes(img_bytes, fn, img_content_type, rw["title"], best_cap)
            if not mid:
                raise Exception("Img Upload Fail")
            author_id = IJ_CATEGORY_AUTHOR.get(rw["cat"]) if prefix == "IJ_" else None
            pid = site.create_post(rw["title"], rw["body"], site.get_cat_id(rw["cat"]), site.get_tag_ids(rw["tags"]), mid, excerpt=rw.get("excerpt", ""), author=author_id)
            upload_counts[prefix] += 1
            print(f" 성공 (ID:{pid}).")
            submit_sitemap_to_gsc(prefix)
            time.sleep(1)
        except Exception as e:
            print(f" 실패({str(e)[:100]}).")
            all_success = False

    return all_success


def run():
    print(f"\n🚀 AI 뉴스 엔진 (v24.0-GitHub_Actions) 가동: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # 오늘 발행 건수 확인
    today_count = db_get_today_count()
    remaining = DAILY_PUBLISH_LIMIT - today_count
    print(f"📊 금일 발행 현황: {today_count}/{DAILY_PUBLISH_LIMIT}건 (잔여: {remaining}건)")

    if remaining <= 0:
        print("🛑 금일 목표 달성. 종료.")
        return

    # DB에서 기존 발행 URL/제목 로드
    print("   ⏳ DB에서 기발행 데이터 로드 중...", end="", flush=True)
    ex_ids, ex_titles = db_get_existing_ids_and_titles()
    print(f" 완료 (URL {len(ex_ids)}건, 제목 {len(ex_titles)}개)")

    # RSS 수집
    print("   ⬇️ 신규 기사 수집(RSS) 시작...")
    articles = collect_articles(ex_ids, ex_titles, remaining)

    if not articles:
        print("👍 신규 기사 없음. 종료.")
        return

    print(f"✅ 처리할 기사: {len(articles)}건")

    # 기사 처리
    upload_counts = {p: 0 for p in MEDIA_PREFIXES}
    published = 0

    for article in articles:
        if published >= remaining:
            break
        success = process_article(article, upload_counts)
        if success:
            db_record_published(article["url_id"], article["title"], "ALL")
            published += 1
            print(f"   🎉 발행 완료! (금일 누적: {today_count + published}건)")

    # Zero-Sum Clean (이미지 정리)
    print("\n🧹 [Zero-Sum Clean] 구형 이미지 정리")
    for prefix, count in upload_counts.items():
        if count > 0:
            site = SITES[prefix]
            total = site.get_total_media_count()
            if total < MIN_MEDIA_LIMIT:
                print(f"   - [{prefix}] 현재 {total}개 (목표 미달) → 유지.")
            else:
                site.delete_oldest_media(count)

    # 결과 요약
    print(f"\n--- 실행 완료: {time.strftime('%H:%M:%S')} ---")
    print(f"📊 [작업 요약]")
    for p, c in upload_counts.items():
        print(f"   - {p} 발행 성공: {c}건")
    print(f"   - 금일 최종 누적: {today_count + published}/{DAILY_PUBLISH_LIMIT}건")
    print(f"──────────────────────────────────────────")


if __name__ == "__main__":
    run()

