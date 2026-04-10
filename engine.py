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
import hashlib
import base64
import json
import os
import difflib
import calendar
import html
from dataclasses import dataclass
from datetime import datetime, date, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urljoin, urlparse, parse_qs
from zoneinfo import ZoneInfo

import requests
import feedparser
import pymysql
from bs4 import BeautifulSoup
from google.oauth2 import service_account
from googleapiclient.discovery import build

def _load_env_file(path: str) -> None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None
else:
    try:
        load_dotenv()
    except Exception:
        pass
    local_env_path = os.path.expanduser("~/.env.erum_infra")
    if os.path.exists(local_env_path):
        try:
            load_dotenv(local_env_path, override=False)
        except Exception:
            _load_env_file(local_env_path)

if load_dotenv is None:
    local_env_path = os.path.expanduser("~/.env.erum_infra")
    if os.path.exists(local_env_path):
        _load_env_file(local_env_path)

# ========================= [1. 환경변수 로드] =========================

UPSTAGE_API_KEY = os.environ.get("UPSTAGE_API_KEY", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
DB_HOST = os.environ["DB_HOST"]
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]
DB_NAME = os.environ["DB_NAME"]

WP_CFG = {}  # WP 발행 완전 폐기 — 전 사이트 erum-one.com API 사용

# 전 사이트 erum-one.com API로 발행
ERUM_API_BASE = "https://erum-one.com"
# 배포 환경 호환:
# 1) ERUM_API_KEY
# 2) ADMIN_API_KEY
# 3) 레거시 기본값(임시 호환용)
ERUM_API_KEY = os.environ.get("ERUM_API_KEY") or os.environ.get("ADMIN_API_KEY") or "eRuM@AdminKey2026!"
ERUM_CFG = {
    "IJ_": {"site": "IJ", "gsc_site": "sc-domain:impactjournal.kr", "sitemap": "https://impactjournal.kr/sitemap-news.xml"},
    "NN_": {"site": "NN", "gsc_site": "sc-domain:neighbornews.kr", "sitemap": "https://neighbornews.kr/sitemap-news.xml"},
    "CB_": {"site": "CB", "gsc_site": "sc-domain:csrbriefing.kr", "sitemap": "https://csrbriefing.kr/sitemap-news.xml"},
}

# 카테고리별 기자 배정 (조직도: mgmt/03_operations/언론사_편집국_조직도.md)
JOURNALIST_MAP: dict[str, dict[str, str]] = {
    "IJ": {"정치": "오지현", "경제": "이성민", "사회": "윤성민", "IT/과학": "장예린", "문화/생활": "한재원", "국제": "서민준", "환경": "나혜진"},
    "NN": {"정치": "최지훈", "경제": "윤재원", "사회": "박서연", "IT/과학": "임태양", "문화/생활": "강미래", "국제": "송현아", "환경": "김도현"},
    "CB": {"정치": "김민서", "경제": "이준혁", "사회": "박지은", "IT/과학": "최현우", "문화/생활": "정수빈", "국제": "한다영", "환경": "오태준"},
}

# Cloudflare R2
R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "erum-news-images")
R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL", "https://pub-dd677a54d7cf4d8cabd2c3238f4558c9.r2.dev")
# [모델 설정]
UPSTAGE_API_BASE = os.environ.get("UPSTAGE_API_BASE", "https://api.upstage.ai/v1")
UPSTAGE_API_URL = os.environ.get("UPSTAGE_API_URL", f"{UPSTAGE_API_BASE.rstrip('/')}/chat/completions")
UPSTAGE_MODEL = os.environ.get("UPSTAGE_MODEL", "solar-pro3")
UPSTAGE_MODEL_REWRITE = os.environ.get("UPSTAGE_MODEL_REWRITE", UPSTAGE_MODEL)
UPSTAGE_MODEL_QA = os.environ.get("UPSTAGE_MODEL_QA", UPSTAGE_MODEL)
UPSTAGE_REWRITE_MAX_OUTPUT_TOKENS = int(os.environ.get("UPSTAGE_REWRITE_MAX_OUTPUT_TOKENS", "2500"))
UPSTAGE_QA_MAX_OUTPUT_TOKENS = int(os.environ.get("UPSTAGE_QA_MAX_OUTPUT_TOKENS", "2500"))
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-pro")
GEMINI_MODEL_REWRITE = os.environ.get("GEMINI_MODEL_REWRITE", GEMINI_MODEL)
GEMINI_MODEL_QA = os.environ.get("GEMINI_MODEL_QA", GEMINI_MODEL)
# thinking 모델(gemma-4-31b-it 등)은 thinking 토큰이 maxOutputTokens를 잡아먹으므로 별도 높은 한도 사용
GEMINI_THINKING_MAX_OUTPUT_TOKENS = int(os.environ.get("GEMINI_THINKING_MAX_OUTPUT_TOKENS", "8000"))
REWRITE_SOURCE_MAX_CHARS = int(os.environ.get("REWRITE_SOURCE_MAX_CHARS", "4000"))
MIN_REWRITTEN_BODY_CHARS = int(os.environ.get("MIN_REWRITTEN_BODY_CHARS", "300"))
SOFT_REWRITTEN_BODY_CHARS = int(os.environ.get("SOFT_REWRITTEN_BODY_CHARS", "4500"))
HARD_REWRITTEN_BODY_CHARS = int(os.environ.get("HARD_REWRITTEN_BODY_CHARS", "6500"))
QA_INPUT_MAX_CHARS = int(os.environ.get("QA_INPUT_MAX_CHARS", "2400"))
LLM_RESPONSE_MAX_CHARS = int(os.environ.get("LLM_RESPONSE_MAX_CHARS", "12000"))
MAX_REWRITTEN_BODY_CHARS = SOFT_REWRITTEN_BODY_CHARS  # backward compatibility for older helper code
MAX_ARTICLE_RETRY_ATTEMPTS = 2
BASE_RETRY_DELAY_MINUTES = 60
MAX_RETRY_DELAY_MINUTES = 240
SYSTEM_FAILURE_CODES = {"AUTH_401", "AUTH_403", "CONFIG_MISSING"}
RETRYABLE_FAILURE_CODES = {
    "SOURCE_FETCH_TIMEOUT",
    "SOURCE_FETCH_HTTP_5XX",
    "IMAGE_FETCH_TIMEOUT",
    "IMAGE_FETCH_HTTP_5XX",
    "IMAGE_UPLOAD_TIMEOUT",
    "IMAGE_UPLOAD_HTTP_5XX",
    "REWRITE_API_ERROR",
    "QA_API_ERROR",
    "PUBLISH_API_ERROR",
}

DAILY_PUBLISH_LIMIT = 50
PER_RUN_LIMIT = 15  # 1회 실행당 최대 발행 수
RETRY_DAYS = int(os.environ.get('RETRY_DAYS', '0'))  # 0=당일만, N=N일 전까지 재시도
REVIEW_ONLY = os.environ.get("REVIEW_ONLY", "0") == "1"
if not UPSTAGE_API_KEY and not (REVIEW_ONLY and GEMINI_API_KEY):
    raise RuntimeError("UPSTAGE_API_KEY가 없습니다. 리뷰 전용 모드에서는 GEMINI_API_KEY가 필요합니다.")
MEDIA_PREFIXES = ["IJ_", "NN_", "CB_"]
KST = ZoneInfo("Asia/Seoul")
TARGET_URL_IDS = {
    x.strip()
    for x in os.environ.get("TARGET_URL_IDS", "").split(",")
    if x.strip()
}
TARGET_URL_ID_LIST = [
    x.strip()
    for x in os.environ.get("TARGET_URL_IDS", "").split(",")
    if x.strip()
]


def now_kst() -> datetime:
    return datetime.now(tz=KST)


def to_kst(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST)


def to_kst_naive(dt: Optional[datetime]) -> Optional[datetime]:
    converted = to_kst(dt)
    return converted.replace(tzinfo=None) if converted else None


def to_kst_iso(dt: Optional[datetime]) -> Optional[str]:
    converted = to_kst(dt)
    return converted.isoformat(timespec="seconds") if converted else None


def to_utc_iso(dt: Optional[datetime]) -> Optional[str]:
    converted = to_kst(dt)
    if not converted:
        return None
    return converted.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def feed_time_to_kst(dt: Optional[time.struct_time]) -> Optional[datetime]:
    if not dt:
        return None
    return datetime.fromtimestamp(calendar.timegm(dt), tz=timezone.utc).astimezone(KST)


def normalize_rule_text(text: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"[^\w가-힣]", "", (text or "").lower())).strip()


def hash_title_for_rule(text: str) -> str:
    normalized = normalize_rule_text(text)
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_url_for_rule(url: str) -> str:
    return (url or "").strip().split("#", 1)[0].rstrip("/")

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
MIN_IMAGE_BYTES = 20_000

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


@dataclass
class PipelineFailure(Exception):
    stage: str
    code: str
    message: str
    retryable: bool = False
    abort_run: bool = False
    partial_success: bool = False

    def __post_init__(self):
        super().__init__(self.message)


@dataclass
class ImageCandidate:
    url: str
    caption: Optional[str]
    source: str
    score: int = 0

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

# ========================= [2. Upstage / 프롬프트] =========================

PROMPT_USER_TEMPLATE = """원문 자료:
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

EDITOR_COMMON_PROMPT = load_skill("news_editor_common")
PERSONA_DEFINITIONS = {
    "IJ_": f"{EDITOR_COMMON_PROMPT}\n\n{load_skill('news_editor_ij')}",
    "NN_": f"{EDITOR_COMMON_PROMPT}\n\n{load_skill('news_editor_nn')}",
    "CB_": f"{EDITOR_COMMON_PROMPT}\n\n{load_skill('news_editor_cb')}",
}

def _llm_failure(stage: str, exc: Exception) -> PipelineFailure:
    status = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if response is not None and not status:
        status = getattr(response, "status_code", None)
    message = str(exc)
    if response is not None:
        try:
            message = response.text or message
        except Exception:
            pass
    lowered = message.lower()
    if status in (401, 403):
        return PipelineFailure(stage, f"{stage.upper()}_AUTH_{status}", message[:500], retryable=False, abort_run=True)
    if status in (429, 500, 502, 503, 504) or "rate limit" in lowered or "spending cap" in lowered:
        return PipelineFailure(stage, f"{stage.upper()}_API_ERROR", message[:500], retryable=True)
    if "timeout" in lowered or "connection" in lowered or "temporarily unavailable" in lowered:
        return PipelineFailure(stage, f"{stage.upper()}_API_ERROR", message[:500], retryable=True)
    return PipelineFailure(stage, f"{stage.upper()}_API_ERROR", message[:500], retryable=False)

def _ask_gemini_rest(persona, text, model=None, max_output_tokens=None, stage="rewrite"):
    use_model = model if (model and (str(model).startswith("gemini") or str(model).startswith("gemma"))) else (GEMINI_MODEL_QA if stage == "qa" else GEMINI_MODEL_REWRITE)
    # thinking 모델(gemma-4-31b-it 등)은 thinking 토큰이 maxOutputTokens를 소비하므로 별도 높은 한도 적용
    is_thinking_model = str(use_model).startswith("gemma")
    if max_output_tokens:
        output_tokens = max_output_tokens
    elif is_thinking_model:
        output_tokens = GEMINI_THINKING_MAX_OUTPUT_TOKENS
    else:
        output_tokens = UPSTAGE_QA_MAX_OUTPUT_TOKENS if stage == "qa" else UPSTAGE_REWRITE_MAX_OUTPUT_TOKENS
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{use_model}:generateContent"
    try:
        response = requests.post(
            url,
            params={"key": GEMINI_API_KEY},
            headers={
                "Content-Type": "application/json",
                "User-Agent": "erum-news-engine/1.0",
            },
            json={
                "systemInstruction": {"parts": [{"text": persona}]},
                "contents": [
                    {"role": "user", "parts": [{"text": PROMPT_USER_TEMPLATE.format(original_text=text)}]}
                ],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": output_tokens,
                },
            },
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise ValueError("Gemini 응답에 candidates가 없음")
        parts = ((candidates[0].get("content") or {}).get("parts") or [])
        # thinking 모델은 thought=True 파트를 필터링(내부 사고과정 제외)
        content = "".join(
            part.get("text", "")
            for part in parts
            if isinstance(part, dict) and not part.get("thought")
        )
        return content.strip()
    except PipelineFailure:
        raise
    except Exception as e:
        raise _llm_failure(stage, e)

def ask_llm(persona, text, model=None, max_output_tokens=None, stage="rewrite"):
    provider = "upstage"
    resolved_model = model or (UPSTAGE_MODEL_QA if stage == "qa" else UPSTAGE_MODEL_REWRITE)
    if REVIEW_ONLY and not UPSTAGE_API_KEY and GEMINI_API_KEY:
        provider = "gemini"
    elif GEMINI_API_KEY and (str(resolved_model).startswith("gemini") or str(resolved_model).startswith("gemma")):
        provider = "gemini"
    if provider == "gemini":
        return _ask_gemini_rest(persona, text, model=model, max_output_tokens=max_output_tokens, stage=stage)
    use_model = model or (UPSTAGE_MODEL_QA if stage == "qa" else UPSTAGE_MODEL_REWRITE)
    user_msg = PROMPT_USER_TEMPLATE.format(original_text=text)
    output_tokens = max_output_tokens or (UPSTAGE_QA_MAX_OUTPUT_TOKENS if stage == "qa" else UPSTAGE_REWRITE_MAX_OUTPUT_TOKENS)
    try:
        response = requests.post(
            UPSTAGE_API_URL,
            headers={
                "Authorization": f"Bearer {UPSTAGE_API_KEY}",
                "Content-Type": "application/json",
                "User-Agent": "erum-news-engine/1.0",
            },
            json={
                "model": use_model,
                "messages": [
                    {"role": "system", "content": persona},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.2,
                "max_tokens": output_tokens,
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("Upstage 응답에 choices가 없음")
        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        return (content or "").strip()
    except PipelineFailure:
        raise
    except Exception as e:
        raise _llm_failure(stage, e)

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
            cur.execute("SELECT url_id, title FROM published_articles WHERE COALESCE(media, '') <> 'FAILED'")
            rows = cur.fetchall()
        return {r["url_id"] for r in rows}, {r["title"] for r in rows if r["title"]}
    finally:
        conn.close()

def db_get_retry_blocked_ids() -> set:
    conn = get_db_connection()
    try:
        blocked_now = to_kst_naive(now_kst())
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT url_id
                FROM article_attempts
                WHERE status IN ('PERMANENT', 'SYSTEM')
                   OR (status = 'RETRYABLE' AND next_retry_at IS NOT NULL AND next_retry_at > %s)
                """,
                (blocked_now,),
            )
            rows = cur.fetchall()
        return {r["url_id"] for r in rows}
    finally:
        conn.close()

def db_get_today_count() -> int:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM published_articles WHERE DATE(published_at) = %s AND COALESCE(media, '') <> 'FAILED'",
                (now_kst().date(),),
            )
            return cur.fetchone()["cnt"]
    finally:
        conn.close()

def db_get_attempt_state(url_id: str) -> Optional[dict]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM article_attempts WHERE url_id = %s", (url_id,))
            return cur.fetchone()
    finally:
        conn.close()


def db_get_active_article_rules() -> dict:
    conn = get_db_connection()
    try:
        active_now = to_kst_naive(now_kst())
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT url_id, source_url, title_hash, rule_type
                FROM article_rules
                WHERE expires_at IS NULL OR expires_at > %s
                """,
                (active_now,),
            )
            rows = cur.fetchall()
        blocked_ids, blocked_title_hashes, blocked_source_urls = set(), set(), set()
        allowed_ids, allowed_title_hashes, allowed_source_urls = set(), set(), set()
        for row in rows:
            rule_type = (row.get("rule_type") or "").upper()
            url_id = row.get("url_id")
            title_hash = (row.get("title_hash") or "").lower()
            source_url = normalize_url_for_rule(row.get("source_url") or "")
            if rule_type == "BLOCK":
                if url_id:
                    blocked_ids.add(url_id)
                if title_hash:
                    blocked_title_hashes.add(title_hash)
                if source_url:
                    blocked_source_urls.add(source_url)
            elif rule_type in {"ALLOW", "OVERRIDE"}:
                if url_id:
                    allowed_ids.add(url_id)
                if title_hash:
                    allowed_title_hashes.add(title_hash)
                if source_url:
                    allowed_source_urls.add(source_url)
        return {
            "blocked_ids": blocked_ids,
            "blocked_title_hashes": blocked_title_hashes,
            "blocked_source_urls": blocked_source_urls,
            "allowed_ids": allowed_ids,
            "allowed_title_hashes": allowed_title_hashes,
            "allowed_source_urls": allowed_source_urls,
        }
    finally:
        conn.close()

def db_store_attempt_state(
    url_id: str,
    title: str,
    media: str,
    status: str,
    stage: Optional[str] = None,
    code: Optional[str] = None,
    message: str = "",
    retry_count: int = 0,
    next_retry_at: Optional[datetime] = None,
    partial_success: bool = False,
    source_published_at: Optional[datetime] = None,
):
    conn = get_db_connection()
    try:
        attempt_at = to_kst_naive(now_kst())
        retry_at = to_kst_naive(next_retry_at)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO article_attempts
                    (url_id, title, media, source_published_at, status, fail_stage, fail_code, fail_message, retry_count, next_retry_at, partial_success, last_attempt_at, updated_at)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    title = VALUES(title),
                    media = VALUES(media),
                    source_published_at = VALUES(source_published_at),
                    status = VALUES(status),
                    fail_stage = VALUES(fail_stage),
                    fail_code = VALUES(fail_code),
                    fail_message = VALUES(fail_message),
                    retry_count = VALUES(retry_count),
                    next_retry_at = VALUES(next_retry_at),
                    partial_success = VALUES(partial_success),
                    last_attempt_at = VALUES(last_attempt_at),
                    updated_at = VALUES(updated_at)
                """,
                (
                    url_id,
                    title[:1000],
                    media[:50],
                    to_kst_naive(source_published_at),
                    status,
                    stage[:50] if stage else None,
                    code[:50] if code else None,
                    message[:1000],
                    retry_count,
                    retry_at,
                    1 if partial_success else 0,
                    attempt_at,
                    attempt_at,
                ),
            )
        conn.commit()
    finally:
        conn.close()

def db_record_success(url_id: str, title: str, media: str, source_published_at: Optional[datetime] = None, published_at: Optional[datetime] = None):
    conn = get_db_connection()
    try:
        published_kst = to_kst_naive(published_at or now_kst())
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO published_articles (url_id, title, media, source_published_at, published_at)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    title = VALUES(title),
                    media = VALUES(media),
                    source_published_at = VALUES(source_published_at),
                    published_at = VALUES(published_at)
                """,
                (url_id, title[:1000], media, to_kst_naive(source_published_at), published_kst),
            )
        conn.commit()
    finally:
        conn.close()

def db_ensure_table():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS published_articles (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    url_id VARCHAR(512) NOT NULL,
                    title VARCHAR(1000),
                    media VARCHAR(50),
                    source_published_at DATETIME DEFAULT NULL,
                    published_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_url_id (url_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS article_attempts (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    url_id VARCHAR(512) NOT NULL,
                    title VARCHAR(1000),
                    media VARCHAR(50),
                    source_published_at DATETIME DEFAULT NULL,
                    status VARCHAR(32) NOT NULL,
                    fail_stage VARCHAR(50),
                    fail_code VARCHAR(50),
                    fail_message TEXT,
                    retry_count INT NOT NULL DEFAULT 0,
                    next_retry_at DATETIME DEFAULT NULL,
                    partial_success TINYINT(1) NOT NULL DEFAULT 0,
                    last_attempt_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_attempt_url_id (url_id),
                    KEY idx_attempt_status_retry (status, next_retry_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS article_rules (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    url_id VARCHAR(512) DEFAULT NULL,
                    source_url VARCHAR(2048) DEFAULT NULL,
                    title_hash CHAR(64) DEFAULT NULL,
                    rule_type VARCHAR(20) NOT NULL,
                    expires_at DATETIME DEFAULT NULL,
                    note TEXT,
                    created_by VARCHAR(100) DEFAULT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    KEY idx_article_rules_url_id (url_id),
                    KEY idx_article_rules_title_hash (title_hash),
                    KEY idx_article_rules_type_expires (rule_type, expires_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    actor VARCHAR(100) NOT NULL,
                    action VARCHAR(100) NOT NULL,
                    target_url_id VARCHAR(512) DEFAULT NULL,
                    before_state LONGTEXT DEFAULT NULL,
                    after_state LONGTEXT DEFAULT NULL,
                    note TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    KEY idx_audit_logs_target_url_id (target_url_id),
                    KEY idx_audit_logs_created_at (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # 기존 테이블에는 새 컬럼이 없을 수 있으므로, 안전하게 보강한다.
            for table_name, column_name, column_def in [
                ("published_articles", "source_published_at", "DATETIME DEFAULT NULL"),
                ("article_attempts", "source_published_at", "DATETIME DEFAULT NULL"),
            ]:
                cur.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
                    """,
                    (DB_NAME, table_name, column_name),
                )
                if not cur.fetchone()["cnt"]:
                    cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
        conn.commit()
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
    if len(body) < MIN_REWRITTEN_BODY_CHARS:
        return False, f"본문 너무 짧음({len(body)}자)"
    if len(body) > HARD_REWRITTEN_BODY_CHARS:
        return False, f"본문 너무 김({len(body)}자)"

    # 라벨 잔재
    for label in ["제목:", "본문:", "내용:", "카테고리:", "태그:", "Title:", "Body:", "리드문:", "배경:", "과제:", "전망:", "솔루션:", "문제:", "해결책:", "임팩트:"]:
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
    if plain_for_check and plain_for_check[-1] not in ("다", ".", "!", "?", '"', "'", "〉", "》", ")", "]", "”", "’"):
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

def ai_quality_check(title: str, body: str, media_prefix: str, source_len: int = 0) -> Tuple[bool, List[str], int, Optional[dict]]:
    media_tone = MEDIA_TONE_DESC.get(media_prefix, "일반 뉴스")
    min_chars = int(source_len * 0.8) if source_len > 0 else 0
    system_prompt = QA_SYSTEM_PROMPT.format(media_tone=media_tone, source_chars=source_len, min_chars=min_chars)
    # HTML 태그 제거 후 검수 — qa_checker는 HTML 태그를 포맷 오염으로 즉시 탈락 처리함
    plain_body = re.sub(r'<[^>]+>', ' ', body).strip()
    plain_body = re.sub(r'\s+', ' ', plain_body)
    plain_body = limit_rewritten_body_text(plain_body, QA_INPUT_MAX_CHARS)
    article_text = f"제목: {title}\n\n본문: {plain_body}"
    raw = ask_llm(system_prompt, article_text, model=UPSTAGE_MODEL_QA, max_output_tokens=UPSTAGE_QA_MAX_OUTPUT_TOKENS, stage="qa")
    try:
        parts = raw.split("---", 1)
        json_part = parts[0]
        clean = re.sub(r"```json\s*", "", json_part)
        clean = re.sub(r"```\s*", "", clean).strip()
        decoder = json.JSONDecoder()
        result, _ = decoder.raw_decode(clean)
        total = int(result.get("total", 0))
        passed = result.get("pass", False) and total >= 72
        fails = result.get("fails", [])
        if not fails and not passed:
            fails = [f"총점 {total}점 미달"]
        fixed = None
        if not passed and len(parts) > 1:
            fixed = parse_llm_response(parts[1].strip())

        # 분량 미달이면 강제 탈락 (원문 분량의 80% 기준, source_len이 없으면 300자)
        body_char_count = len(plain_body)
        min_body = int(source_len * 0.8) if source_len > 0 else 300
        if body_char_count < min_body:
            passed = False
            if "분량 미달" not in str(fails):
                fails = fails + [f"분량 미달({body_char_count}자, 기준 {min_body}자)"]

        # QA 미통과 시 fixed 없거나 fixed도 분량 미달이면 fallback
        if not passed and not fixed:
            retry_user = (
                f"다음 기사가 검수에서 탈락했다: {', '.join(str(f) for f in fails)}.\n"
                f"탈락 사유를 모두 수정한 완성 기사를 출력하라. "
                f"제목은 30자 이내, 쉼표 없이. 본문은 원문({source_len}자) 분량의 90~100% 수준으로.\n\n"
                f"제목: {title}\n\n본문: {plain_body}"
            )
            retry_raw = ask_llm(
                QA_SYSTEM_PROMPT.format(media_tone=MEDIA_TONE_DESC.get(media_prefix, "일반 뉴스"), source_chars=source_len, min_chars=min_body),
                retry_user, model=UPSTAGE_MODEL_QA, max_output_tokens=UPSTAGE_QA_MAX_OUTPUT_TOKENS, stage="qa"
            )
            parts3 = retry_raw.split("---", 1)
            if len(parts3) > 1:
                candidate = parse_llm_response(parts3[1].strip())
                if len(candidate.get('title', '')) < 60 and len(candidate.get('body', '')) > 200:
                    fixed = candidate

        return passed, fails, total, fixed
    except Exception as e:
        print(f"      ⚠️ [AI검수] 파싱 실패({str(e)[:50]}), 실패 처리")
        return False, ["AI검수 파싱 실패"], 0, None

def _strip_model_fences(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()

def _trim_to_sentence_boundary(text: str, max_chars: int) -> str:
    if not text or len(text) <= max_chars:
        return text.strip()
    cutoff = text[:max_chars].rstrip()
    boundaries = [m.end() for m in re.finditer(r'(?<=[.!?다요])\s+', cutoff)]
    if boundaries:
        return cutoff[:boundaries[-1]].strip()
    last_space = cutoff.rfind(" ")
    if last_space > int(max_chars * 0.6):
        return cutoff[:last_space].strip()
    return cutoff.strip()

def limit_rewritten_body_text(text: str, max_chars: int = SOFT_REWRITTEN_BODY_CHARS) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) <= max_chars:
        return text

    kept_lines = []
    used = 0
    for line in [line.strip() for line in text.splitlines()]:
        if not line:
            continue
        if used + len(line) <= max_chars:
            kept_lines.append(line)
            used += len(line)
            continue

        remaining = max_chars - used
        if remaining > 80:
            trimmed = _trim_to_sentence_boundary(line, remaining)
            if trimmed:
                kept_lines.append(trimmed)
        break

    if not kept_lines:
        return _trim_to_sentence_boundary(text, max_chars)
    return "\n".join(kept_lines).strip()

def clean_body_html(text):
    if not text: return ""
    text = text.replace("본문:", "").replace("본문 :", "").replace("내용:", "").replace("내용 :", "")
    text = text.replace("Body:", "").replace("Body :", "").replace("Title:", "").replace("제목:", "")
    text = re.sub(r'^(본문|Body|내용)[:\s-]*', '', text, flags=re.IGNORECASE).strip()
    text = limit_rewritten_body_text(text)
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

def parse_llm_response(text):
    text = _strip_model_fences(text)
    if len(text) > LLM_RESPONSE_MAX_CHARS:
        text = text[:LLM_RESPONSE_MAX_CHARS].rstrip()
    lines = [line.rstrip() for line in text.splitlines()]
    title = ""
    excerpt = ""
    cat = ""
    tags = []
    body_lines: List[str] = []
    current = None
    label_re = re.compile(r'^(제목|Title|헤드라인|리드문|Excerpt|요약|본문|Body|내용|카테고리|Category|태그|Tags)\s*[:：]\s*(.*)$', re.IGNORECASE)

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        m = label_re.match(line)
        if m:
            label = m.group(1).lower()
            value = m.group(2).strip()
            if label in ("제목", "title", "헤드라인"):
                title = value
                current = "title"
            elif label in ("리드문", "excerpt", "요약"):
                excerpt = value
                current = "excerpt"
            elif label in ("본문", "body", "내용"):
                current = "body"
                if value:
                    body_lines.append(value)
            elif label in ("카테고리", "category"):
                cat = value
                current = "cat"
            elif label in ("태그", "tags"):
                current = "tags"
                if value:
                    tags = [t.strip() for t in re.split(r'[,/]', value) if t.strip()]
            continue
        if current == "body":
            body_lines.append(line)
        elif current == "title" and not title:
            title = line
        elif current == "excerpt" and not excerpt:
            excerpt = line
        elif current == "cat" and not cat:
            cat = line
        elif current == "tags" and not tags:
            tags = [t.strip() for t in re.split(r'[,/]', line) if t.strip()]

    if not title and lines:
        title = lines[0].strip()
    title = re.sub(r"[#\*\[\]`]", "", title).strip().strip('"')
    title = title.replace(',', '').replace('，', '')  # 제목 쉼표 금지 후처리
    # 제목이 영어로만 구성된 경우 제거 (모델이 원문을 echo하는 오류 방지)
    if title and re.match(r'^[A-Za-z0-9 :,.\'"!?()-]+$', title):
        title = ""
    excerpt = re.sub(r"[#\*\[\]`]", "", excerpt).strip()
    excerpt = html.unescape(excerpt) if excerpt else ""
    body_raw = limit_rewritten_body_text("\n".join(body_lines).strip(), HARD_REWRITTEN_BODY_CHARS)
    final_body = clean_body_html(body_raw)
    # 리드문이 비어 있으면 본문 첫 2문장으로 자동 생성
    if not excerpt and final_body:
        plain = re.sub(r'<[^>]+>', ' ', final_body).strip()
        plain = re.sub(r'\s+', ' ', plain)
        sentences = re.split(r'(?<=[다요])\. *', plain)
        excerpt = '. '.join(s.strip() for s in sentences[:2] if s.strip())
        excerpt = html.unescape(excerpt) if excerpt else ""
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


def _extract_first_date(text: str) -> Optional[datetime]:
    if not text:
        return None
    m = re.search(r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})', text)
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=KST)
    except Exception:
        return None


def load_review_articles_from_targets(target_ids: List[str]) -> List[dict]:
    articles = []
    for url_id in target_ids:
        source_url = url_id if url_id.startswith("http") else f"https://{url_id}"
        db_title = ""
        db_source_published_at = None
        try:
            conn = get_db_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT title, source_published_at FROM published_articles WHERE url_id = %s LIMIT 1", (url_id,))
                    row = cur.fetchone()
                    if row:
                        db_title = row.get("title") or ""
                        db_source_published_at = row.get("source_published_at")
                    if not db_title:
                        cur.execute("SELECT title, source_published_at FROM article_attempts WHERE url_id = %s LIMIT 1", (url_id,))
                        row = cur.fetchone()
                        if row:
                            db_title = row.get("title") or ""
                            db_source_published_at = row.get("source_published_at") or db_source_published_at
            finally:
                conn.close()
        except Exception:
            pass

        resp = fetch_with_retry(source_url, timeout=20)
        if not resp or resp.status_code != 200:
            print(f"   ⚠️ [리뷰 원문] 직접 fetch 실패: {url_id} (HTTP {getattr(resp, 'status_code', 'none')})")
            continue
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        title = ""
        h1 = soup.select_one("h1")
        if h1:
            title = h1.get_text(" ", strip=True)
        if not title:
            og_title = soup.find("meta", attrs={"property": "og:title"}) or soup.find("meta", attrs={"name": "og:title"})
            if og_title and og_title.get("content"):
                title = og_title.get("content", "").strip()
        if not title:
            title = db_title or url_id

        body_node = (
            soup.select_one(".view_cont")
            or soup.select_one(".article-content")
            or soup.select_one("#articleBody")
            or soup.select_one("article")
            or soup.select_one(".content")
            or soup.select_one(".view_cont")
        )
        body_text = body_node.get_text(separator="\n", strip=True) if body_node else strip_html_tags(resp.text)
        main_node = soup.select_one("main.main") or soup.select_one("section.area_contents") or soup.select_one("main")
        if not db_source_published_at and main_node:
            db_source_published_at = _extract_first_date(main_node.get_text(" ", strip=True)[:1200])
        if not db_source_published_at:
            db_source_published_at = _extract_first_date(soup.get_text(" ", strip=True)[:1200])

        articles.append({
            "url": source_url,
            "url_id": url_id,
            "title": title[:1000],
            "body": body_text[:40000],
            "image": "",
            "source_published_at": db_source_published_at,
        })
    return articles

def _review_output_dir() -> str:
    configured = os.environ.get("REVIEW_OUTPUT_DIR", "review_outputs").strip() or "review_outputs"
    if os.path.isabs(configured):
        return configured
    return os.path.join(script_dir, configured)


def _review_safe_slug(text: str, fallback: str = "article") -> str:
    slug = re.sub(r"[^0-9A-Za-z가-힣]+", "_", (text or "").strip()).strip("_")
    if not slug:
        slug = fallback
    return slug[:60]


def _format_review_report(records: List[dict]) -> str:
    created_at = now_kst().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# 기사 재작성 리뷰",
        "",
        f"- 생성 시각(KST): {created_at}",
        f"- 리뷰 모드: {'ON' if REVIEW_ONLY else 'OFF'}",
        f"- 대상 기사 수: {len(records)}",
    ]
    if TARGET_URL_IDS:
        lines.append(f"- 대상 URL 필터: {len(TARGET_URL_IDS)}건")
    lines.append("")

    for idx, record in enumerate(records, 1):
        title = (record.get("source_title") or record.get("title") or "").strip() or "(제목 없음)"
        source_url = record.get("source_url") or record.get("url") or "-"
        source_published_at = record.get("source_published_at")
        if isinstance(source_published_at, datetime):
            source_published_at = to_kst_iso(source_published_at) or "-"
        source_chars = record.get("source_chars")
        source_body = record.get("source_body")
        if source_chars is None and isinstance(source_body, str):
            source_chars = len(source_body)

        lines.extend([
            f"## {idx}. {title}",
            f"- 원문 URL: {source_url}",
            f"- 원문 시각(KST): {source_published_at or '-'}",
            f"- 원문 길이: {source_chars if source_chars is not None else '-'}자",
        ])

        if record.get("status"):
            lines.append(f"- 상태: {record.get('status')}")
        if record.get("message"):
            lines.append(f"- 사유: {record.get('message')}")
        if record.get("stage") or record.get("code"):
            stage = record.get("stage") or "-"
            code = record.get("code") or "-"
            lines.append(f"- 실패 코드: {stage}/{code}")

        variants = record.get("variants") or []
        if not variants:
            lines.append("")
            continue

        success_count = sum(1 for v in variants if v.get("status") == "SUCCESS" or v.get("qa_pass"))
        failed_count = len(variants) - success_count
        lines.extend([
            f"- 변형 성공: {success_count}건",
            f"- 변형 실패: {failed_count}건",
            "",
        ])

        for variant in variants:
            prefix = (variant.get("prefix") or "").rstrip("_") or "?"
            lines.append(f"### {prefix}")
            lines.append(f"- 상태: {variant.get('status') or ('통과' if variant.get('qa_pass') else '실패')}")
            if variant.get("qa_score") is not None:
                lines.append(f"- QA 점수: {variant.get('qa_score')}")
            if variant.get("qa_fails"):
                lines.append(f"- QA 지적: {', '.join(variant.get('qa_fails'))}")
            if variant.get("fixed_applied"):
                lines.append("- 자동보완: 적용")
            if variant.get("failure"):
                lines.append(f"- 실패: {variant.get('failure')}")
            lines.append(f"- 제목: {variant.get('title', '')}")
            lines.append(f"- 리드문: {variant.get('excerpt', '')}")
            lines.append(f"- 카테고리: {variant.get('cat', '')}")
            tags = variant.get("tags") or []
            lines.append(f"- 태그: {', '.join(tags) if tags else '-'}")
            lines.append("- 본문:")
            body = (variant.get("body") or "").rstrip()
            if body:
                lines.append("")
                lines.append(body)
            else:
                lines.append("없음")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_review_report(records: List[dict]) -> str:
    output_dir = _review_output_dir()
    os.makedirs(output_dir, exist_ok=True)
    filename = f"rewrite_review_{now_kst().strftime('%Y%m%d_%H%M%S')}.md"
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(_format_review_report(records))
    return path

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
            status = getattr(getattr(e, "response", None), "status_code", 0)
            if hasattr(e, 'response') and e.response is not None:
                err_msg = e.response.text or err_msg
            print(f"\n      ❌ [이미지 업로드 에러]: {err_msg[:200]}")
            if status in (401, 403):
                raise PipelineFailure("publish", f"IMAGE_UPLOAD_HTTP_{status}", err_msg[:200], retryable=False, abort_run=True)
            if status in (429, 500, 502, 503, 504):
                raise PipelineFailure("publish", f"IMAGE_UPLOAD_HTTP_{status}", err_msg[:200], retryable=True)
            raise PipelineFailure("publish", "IMAGE_UPLOAD_ERROR", err_msg[:200], retryable=True)

    def create_post(self, title, body, cat, tags, mid=None, excerpt="", author=None, published_at: Optional[datetime] = None, source_published_at: Optional[datetime] = None):
        publish_dt = to_kst(published_at) or now_kst()
        d = {
            "title": title,
            "content": body,
            "status": "publish",
            "categories": [cat] if cat else [],
            "tags": tags,
            "date": to_kst_iso(publish_dt),
            "date_gmt": to_utc_iso(publish_dt),
        }
        if mid: d["featured_media"] = mid
        if excerpt: d["excerpt"] = excerpt
        if author: d["author"] = author
        r = self.sess.post(f"{self.base}/wp-json/wp/v2/posts", json=d, timeout=30)
        r.raise_for_status()
        return self._safe_json(r)["id"]



def upload_to_r2(img_bytes: bytes, filename: str, content_type: str) -> Optional[str]:
    """이미지를 WebP로 변환 후 Cloudflare R2에 업로드하고 퍼블릭 URL 반환. 실패 시 None."""
    if not R2_ACCESS_KEY_ID or not R2_SECRET_ACCESS_KEY:
        return None
    # WebP 변환 (1200px 이하 리사이즈, quality 82)
    try:
        from PIL import Image
        import io as _io
        img = Image.open(_io.BytesIO(img_bytes))
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        if img.width > 1200:
            ratio = 1200 / img.width
            img = img.resize((1200, int(img.height * ratio)), Image.LANCZOS)
        buf = _io.BytesIO()
        img.save(buf, format="WEBP", quality=82)
        img_bytes = buf.getvalue()
        content_type = "image/webp"
        filename = filename.rsplit(".", 1)[0] + ".webp"
    except Exception:
        pass  # 변환 실패 시 원본 사용
    try:
        import boto3
        from botocore.config import Config
        s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
        key = f"news/{now_kst().strftime('%Y/%m')}/{filename}"
        s3.put_object(Bucket=R2_BUCKET_NAME, Key=key, Body=img_bytes, ContentType=content_type)
        return f"{R2_PUBLIC_URL}/{key}"
    except Exception as e:
        print(f"\n      ⚠️ [R2 업로드 실패]: {str(e)[:100]}")
        return None


class ErumSite:
    """erum-one.com REST API를 통해 NN/CB 기사를 발행"""
    def __init__(self, site_code: str):
        self.site_code = site_code
        self.api_base = ERUM_API_BASE
        self.headers = {"x-api-key": ERUM_API_KEY, "Content-Type": "application/json"}

    def get_cat_id(self, name: str) -> Optional[int]:
        if not name: return None
        clean = re.sub(r'[^\w\s가-힣]', '', name).strip()[:30]
        if not clean: return None
        try:
            r = requests.post(f"{self.api_base}/api/categories",
                              json={"site": self.site_code, "name": clean},
                              headers=self.headers, timeout=10)
            r.raise_for_status()
            return r.json()["category"]["id"]
        except: return None

    def get_tag_ids(self, tags): return []

    def create_post(self, title, body, cat_id, tag_ids, img_url=None, excerpt="", author=None, published_at: Optional[datetime] = None, source_published_at: Optional[datetime] = None):
        publish_dt = to_kst(published_at) or now_kst()
        payload = {
            "site": self.site_code,
            "title": title,
            "content": body,
            "excerpt": excerpt or "",
            "status": "PUBLISHED",
            "categoryId": cat_id,
            "featuredImageUrl": img_url,
            "publishedAt": to_kst_iso(publish_dt),
            "sourcePublishedAt": to_kst_iso(source_published_at) if source_published_at else None,
        }
        if payload["sourcePublishedAt"] is None:
            payload.pop("sourcePublishedAt")
        if author:
            payload["author"] = author
        r = requests.post(f"{self.api_base}/api/articles",
                          json=payload, headers=self.headers, timeout=30)
        r.raise_for_status()
        return r.json()["id"]

SITES: dict = {k: Site(v['base'], v['user'], v['app_pw']) for k, v in WP_CFG.items()}
for _prefix, _cfg in ERUM_CFG.items():
    SITES[_prefix] = ErumSite(_cfg["site"])

# ========================= [6. GSC 사이트맵 제출] =========================

def submit_sitemap_to_gsc(prefix):
    cfg = WP_CFG.get(prefix) or ERUM_CFG.get(prefix)
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

def fetch_with_retry(url, max_retries=2, timeout=15, stream=False, retry_statuses=(429, 500, 502, 503, 504)):
    last_response = None
    for attempt in range(max_retries + 1):
        try:
            r = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout, stream=stream)
            last_response = r
            if r.status_code in retry_statuses and attempt < max_retries:
                time.sleep(1 + attempt)
                continue
            return r
        except (requests.exceptions.ConnectionError, ConnectionResetError):
            if attempt < max_retries:
                time.sleep(1 + attempt)
                continue
            return None
    return last_response

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
    if not url: return False
    # korea.kr 공식 첨부 이미지는 GitHub Actions IP에서 접속 차단됨 → URL 패턴으로 신뢰
    if 'korea.kr/newsWeb/resources/attaches' in url:
        return True
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
    except:
        return None, None

def find_best_image(article):
    rss_img = article.get("image", "").strip()
    rss_body = article.get("body", "")
    link = article.get("url", "").strip()
    candidates: list[ImageCandidate] = []
    seen = set()
    page_retryable = False

    # 1순위: RSS media_content 이미지
    if rss_img and not _is_blocked_image_url(rss_img):
        _add_image_candidate(candidates, seen, rss_img, None, "rss:media", 100, "")
    elif rss_img:
        print(f" [1순위 블록:{rss_img[:50]}]", end="")
    else:
        print(f" [1순위:RSS이미지없음]", end="")

    # 2순위: RSS summary/body HTML에 포함된 이미지 후보
    if rss_body and "<img" in rss_body.lower():
        candidates.extend(_extract_candidates_from_html(rss_body, article.get("url", ""), "rss"))
    else:
        print(f" [2순위:body img없음]", end="")

    # 3순위: 기사 페이지 직접 접속하여 이미지 후보를 더 수집
    if link:
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
            raise PipelineFailure("image", "SOURCE_FETCH_HTTP_5XX", "기사 본문 조회 실패", retryable=True)
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
    retryable_seen = False
    blocked_seen = False
    for cand in candidates:
        try:
            if _is_blocked_image_url(cand.url):
                blocked_seen = True
                continue

            is_korea_kr = 'korea.kr/newsWeb/resources/attaches' in cand.url
            if is_korea_kr:
                kr_headers = dict(REQUEST_HEADERS)
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

            filename = re.sub(r'[^\w\.-]', '', cand.url.split("/")[-1].split("?")[0])[-50:]
            if not filename:
                filename = f"img_{hash(cand.url) & 0xFFFFFF:06x}.jpg"
            return candidate_bytes, ct if 'image' in ct.lower() else "image/jpeg", filename, cand.caption, cand.url
        except Exception:
            retryable_seen = True
            continue

    if retryable_seen:
        raise PipelineFailure("image", "IMAGE_FETCH_HTTP_5XX", "이미지 다운로드 실패", retryable=True)
    raise PipelineFailure("image", "NO_USABLE_IMAGE", "사용 가능한 이미지 없음", retryable=False)

def classify_attempt_state(failure: PipelineFailure, prior_state: Optional[dict] = None) -> Tuple[str, int, Optional[datetime]]:
    prior_retry_count = int((prior_state or {}).get("retry_count") or 0)
    retry_count = prior_retry_count + 1

    if failure.abort_run or failure.code in SYSTEM_FAILURE_CODES:
        return "SYSTEM", retry_count, None

    if failure.partial_success:
        return "PERMANENT", retry_count, None

    if failure.code in RETRYABLE_FAILURE_CODES or failure.retryable:
        if retry_count >= MAX_ARTICLE_RETRY_ATTEMPTS:
            return "PERMANENT", retry_count, None
        delay_minutes = min(MAX_RETRY_DELAY_MINUTES, BASE_RETRY_DELAY_MINUTES * (2 ** (retry_count - 1)))
        return "RETRYABLE", retry_count, now_kst() + timedelta(minutes=delay_minutes)

    return "PERMANENT", retry_count, None

# ========================= [8. 메인 파이프라인] =========================

def collect_articles(ex_ids: set, ex_titles: set, blocked_ids: set, limit: int, rules: Optional[dict] = None, review_mode: bool = False) -> list:
    """RSS에서 기사를 수집하여 리스트로 반환 (시트 없이 메모리에서 직접 처리)"""
    current_kst = now_kst()
    today = current_kst.date()
    current_hour = current_kst.hour
    articles = []
    rule_blocked_ids = (rules or {}).get("blocked_ids", set())
    rule_blocked_title_hashes = (rules or {}).get("blocked_title_hashes", set())
    rule_blocked_source_urls = (rules or {}).get("blocked_source_urls", set())
    rule_allowed_ids = (rules or {}).get("allowed_ids", set())
    rule_allowed_title_hashes = (rules or {}).get("allowed_title_hashes", set())
    rule_allowed_source_urls = (rules or {}).get("allowed_source_urls", set())

    def fetch_feed(url, source_name, feed_limit, is_newswire=False):
        if feed_limit <= 0: return 0
        print(f"      📡 [{source_name}] 스캔 중 (목표: {feed_limit}건)...", end="", flush=True)
        count = 0
        try:
            resp = fetch_with_retry(url, timeout=20)
            if not resp or resp.status_code != 200:
                print(f" 오류(HTTP {getattr(resp, 'status_code', 'none')})")
                return 0
            resp.encoding = 'utf-8'
            f = feedparser.parse(resp.text)
            for e in f.entries:
                if count >= feed_limit: break
                if not hasattr(e, 'link'): continue
                curr_id = extract_unique_id(e.link)
                if not review_mode and curr_id in ex_ids: continue
                if TARGET_URL_IDS and curr_id not in TARGET_URL_IDS:
                    continue
                if not is_mainly_korean(e.title, threshold=0.5): continue
                if not review_mode:
                    title_hash = hash_title_for_rule(e.title)
                    source_url_key = normalize_url_for_rule(e.link)
                    rule_allowed = (
                        curr_id in rule_allowed_ids
                        or title_hash in rule_allowed_title_hashes
                        or source_url_key in rule_allowed_source_urls
                    )
                    if (
                        curr_id in rule_blocked_ids
                        or title_hash in rule_blocked_title_hashes
                        or source_url_key in rule_blocked_source_urls
                    ):
                        if not rule_allowed:
                            continue
                    if not rule_allowed and curr_id in blocked_ids:
                        continue
                    if is_semantic_duplicate(e.title, ex_titles, threshold=0.9): continue
                dt = e.get('published_parsed') or e.get('updated_parsed')
                source_published_at = feed_time_to_kst(dt)
                if not source_published_at: continue
                article_date = source_published_at.date()
                if RETRY_DAYS > 0:
                    if article_date < today - timedelta(days=RETRY_DAYS) or article_date > today:
                        continue
                else:
                    if article_date != today: continue
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
                    "source_published_at": source_published_at,
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


def process_article(article: dict, upload_counts: dict, review_mode: bool = REVIEW_ONLY) -> dict:
    """기사 1건을 3개 매체에 재작성 + 발행."""
    print(f"\n▶ 기사 처리 시작: {article['title'][:40]}...")
    source_published_at = article.get("source_published_at")
    published_at = now_kst()
    review_record = {
        "source_title": article.get("title", ""),
        "source_url": article.get("url", ""),
        "source_published_at": source_published_at,
        "source_chars": len(article.get("body", "") or ""),
        "variants": [],
    }

    if review_mode:
        print("   🧪 리뷰 전용 모드: 이미지/발행 단계 생략")
    else:
        # 이미지 확인
        print(f"   🔎 이미지 탐색 중...", end="", flush=True)
        image_candidates = find_best_image(article)
        if not image_candidates:
            print(" 실패 (이미지 없음/저작권).")
            raise PipelineFailure("image", "NO_USABLE_IMAGE", "이미지 후보 없음", retryable=False)
        print(f" 찾음.")

        print(f"   📥 이미지 다운로드 중...", end="", flush=True)
        img_bytes, img_content_type, fn, best_cap, best_img = download_best_image(image_candidates)
        print(f" 완료 ({len(img_bytes)//1024}KB).")

    rewritten = {}
    published_prefixes = []
    failures: List[PipelineFailure] = []
    for prefix in MEDIA_PREFIXES:
        print(f"      ✍️ [{prefix}] Solar Pro 3 기사 작성 중...", end="", flush=True)
        try:
            source_text = strip_html_tags(article["body"])[:REWRITE_SOURCE_MAX_CHARS]
            res = ask_llm(
                PERSONA_DEFINITIONS[prefix],
                source_text,
                model=UPSTAGE_MODEL_REWRITE,
                max_output_tokens=UPSTAGE_REWRITE_MAX_OUTPUT_TOKENS,
                stage="rewrite",
            )
            p = parse_llm_response(res)
            is_valid, msg = validate_content_quality(p['title'], p['body'])
            if not is_valid:
                raise PipelineFailure("rewrite", "REWRITE_VALIDATION_FAIL", msg, retryable=False)

            # AI 품질검수+보완 (Solar Pro 3 1회)
            print(" 작성완료.", flush=True)
            print(f"      🔍 [{prefix}] Solar Pro 3 품질검수 중...", end="", flush=True)
            passed, fails, score, fixed = ai_quality_check(p['title'], p['body'], prefix, source_len=len(source_text))
            final_pass = passed

            if not passed:
                print(f" {score}점(미달).", flush=True)
                if fixed:
                    print(f"      🔧 [{prefix}] 자동보완 적용...", end="", flush=True)
                    is_valid, msg = validate_content_quality(fixed['title'], fixed['body'])
                    if not is_valid:
                        raise PipelineFailure("qa", "QA_FIXED_VALIDATION_FAIL", msg, retryable=False)
                    p = fixed
                    final_pass = True
                    print(f" 완료.")
                else:
                    raise PipelineFailure("qa", "QA_HARD_FAIL", f"AI검수 최종미달(점수:{score})", retryable=False)
            else:
                print(f" {score}점 통과.")

            cat, tags = get_hybrid_meta(p['title'], p['body'], p['cat'], p['tags'])
            rw = {"title": p['title'], "excerpt": p.get('excerpt', ''), "body": p['body'], "cat": cat, "tags": tags}
            rewritten[prefix] = rw

            variant_review = {
                "prefix": prefix,
                "status": "SUCCESS",
                "qa_pass": final_pass,
                "qa_score": score,
                "qa_fails": fails,
                "fixed_applied": bool(fixed),
                "title": rw["title"],
                "excerpt": rw["excerpt"],
                "body": rw["body"],
                "cat": rw["cat"],
                "tags": rw["tags"],
            }

            if review_mode:
                review_record["variants"].append(variant_review)
                published_prefixes.append(prefix)
                continue

            # 발행 단계: 매체별로 독립 실행
            try:
                is_erum = prefix in ERUM_CFG
                print(f"      🚀 [{prefix}] {'erum API' if is_erum else '워드프레스'} 발행 중...", end="", flush=True)
                site = SITES[prefix]
                if is_erum:
                    # R2에 업로드 후 CF URL 사용, 실패 시 원본 URL fallback
                    r2_url = upload_to_r2(img_bytes, fn, img_content_type)
                    mid = r2_url if r2_url else best_img
                else:
                    mid, _ = site.upload_image_bytes(img_bytes, fn, img_content_type, rw["title"], best_cap)
                    if not mid:
                        raise PipelineFailure("publish", "IMAGE_UPLOAD_FAIL", "이미지 업로드 실패", retryable=True)
                # 카테고리 기반 기자 배정
                site_code = ERUM_CFG[prefix]["site"] if is_erum else None
                journalist = JOURNALIST_MAP.get(site_code, {}).get(rw["cat"]) if site_code else None
                pid = site.create_post(
                    rw["title"],
                    rw["body"],
                    site.get_cat_id(rw["cat"]),
                    site.get_tag_ids(rw["tags"]),
                    mid,
                    excerpt=rw.get("excerpt", ""),
                    author=journalist,
                    published_at=published_at,
                    source_published_at=source_published_at,
                )
                upload_counts[prefix] += 1
                published_prefixes.append(prefix)
                variant_review["publish_id"] = pid
                print(f" 성공 (ID:{pid}).")
                submit_sitemap_to_gsc(prefix)
                time.sleep(1)
            except requests.HTTPError as e:
                status = getattr(getattr(e, "response", None), "status_code", 0)
                retryable = status in (429, 500, 502, 503, 504)
                failure = PipelineFailure("publish", f"PUBLISH_HTTP_{status or 'ERROR'}", str(e), retryable=retryable, abort_run=status in (401, 403))
                print(f" 실패 ({failure.stage}/{failure.code}).")
                failures.append(failure)
                if review_mode:
                    variant_review["status"] = "FAILED"
                    variant_review["failure"] = f"{failure.stage}/{failure.code}: {failure.message[:200]}"
                    review_record["variants"].append(variant_review)
                continue

            if review_mode:
                review_record["variants"].append(variant_review)

        except PipelineFailure as e:
            if e.abort_run and e.stage in ("rewrite", "qa"):
                raise
            print(f" 실패 ({e.stage}/{e.code}).")
            failures.append(e)
            if review_mode:
                review_record["variants"].append({
                    "prefix": prefix,
                    "status": "FAILED",
                    "qa_pass": False,
                    "qa_score": 0,
                    "qa_fails": [e.message] if e.message else [],
                    "fixed_applied": False,
                    "title": "",
                    "excerpt": "",
                    "body": "",
                    "cat": "",
                    "tags": [],
                    "failure": f"{e.stage}/{e.code}: {e.message[:200]}",
                })
            continue
        except Exception as e:
            failure = PipelineFailure("publish", "PUBLISH_RUNTIME_ERROR", str(e), retryable=True)
            print(f" 실패 ({failure.stage}/{failure.code}).")
            failures.append(failure)
            if review_mode:
                review_record["variants"].append({
                    "prefix": prefix,
                    "status": "FAILED",
                    "qa_pass": False,
                    "qa_score": 0,
                    "qa_fails": [str(e)[:200]],
                    "fixed_applied": False,
                    "title": "",
                    "excerpt": "",
                    "body": "",
                    "cat": "",
                    "tags": [],
                    "failure": f"{failure.stage}/{failure.code}: {failure.message[:200]}",
                })
            continue

    if review_mode:
        review_record["success_media"] = [p.rstrip("_") for p in published_prefixes]
        review_record["partial_success"] = len(published_prefixes) < len(MEDIA_PREFIXES)
        review_record["failure_count"] = len(failures)
        review_record["status"] = "SUCCESS" if published_prefixes else "FAILED"
        if failures and not published_prefixes:
            primary = failures[0]
            details = " | ".join(f"{f.stage}/{f.code}" for f in failures[:3])
            review_record["message"] = f"모든 변형 실패: {details}"
            review_record["stage"] = primary.stage
            review_record["code"] = primary.code
        return review_record

    if published_prefixes:
        return {
            "success_media": [p.rstrip("_") for p in published_prefixes],
            "partial_success": len(published_prefixes) < len(MEDIA_PREFIXES),
            "failure_count": len(failures),
        }

    if failures:
        retryable = any(f.retryable for f in failures)
        abort_run = any(f.abort_run for f in failures)
        primary = failures[0]
        details = " | ".join(f"{f.stage}/{f.code}" for f in failures[:3])
        raise PipelineFailure(
            primary.stage,
            primary.code,
            f"모든 매체 실패: {details}",
            retryable=retryable,
            abort_run=abort_run,
        )

    raise PipelineFailure("run", "NO_MEDIA_PUBLISHED", "모든 매체 발행 실패", retryable=False)


def run():
    print(f"\n🚀 AI 뉴스 엔진 (v25.1-Upstage_SolarPro3_KST) 가동: {now_kst().strftime('%Y-%m-%d %H:%M:%S')}")
    if TARGET_URL_IDS:
        print(f"🎯 대상 URL 필터 활성화: {len(TARGET_URL_IDS)}건")

    if REVIEW_ONLY:
        remaining = len(TARGET_URL_IDS) if TARGET_URL_IDS else PER_RUN_LIMIT
        ex_ids, ex_titles = set(), set()
        blocked_ids = set()
        article_rules = {
            "blocked_ids": set(),
            "blocked_title_hashes": set(),
            "blocked_source_urls": set(),
            "allowed_ids": set(),
            "allowed_title_hashes": set(),
            "allowed_source_urls": set(),
        }
        print(f"🧪 리뷰 전용 모드: 발행/DB 기록 없음, 후보 상한 {remaining}건")
    else:
        # 테이블 자동 생성 (없을 경우)
        db_ensure_table()

        # 오늘 발행 건수 확인
        today_count = db_get_today_count()
        remaining = min(DAILY_PUBLISH_LIMIT - today_count, PER_RUN_LIMIT)
        print(f"📊 금일 발행 현황: {today_count}/{DAILY_PUBLISH_LIMIT}건 (잔여: {remaining}건)")

        if remaining <= 0:
            print("🛑 금일 목표 달성. 종료.")
            return

        # DB에서 기존 발행 URL/제목 로드
        print("   ⏳ DB에서 기발행 데이터 로드 중...", end="", flush=True)
        ex_ids, ex_titles = db_get_existing_ids_and_titles()
        print(f" 완료 (URL {len(ex_ids)}건, 제목 {len(ex_titles)}개)")

        blocked_ids = db_get_retry_blocked_ids()
        article_rules = db_get_active_article_rules()

    # 기사 수집
    if REVIEW_ONLY and TARGET_URL_ID_LIST:
        print("   ⬇️ 리뷰 대상 원문 직접 수집 시작...")
        articles = load_review_articles_from_targets(TARGET_URL_ID_LIST)
    else:
        print("   ⬇️ 신규 기사 수집(RSS) 시작...")
        articles = collect_articles(ex_ids, ex_titles, blocked_ids, remaining, article_rules, review_mode=REVIEW_ONLY)

    if not articles:
        print("👍 신규 기사 없음. 종료.")
        if REVIEW_ONLY:
            report_path = write_review_report([])
            print(f"📝 리뷰 리포트 저장: {report_path}")
        return

    print(f"✅ 처리할 기사: {len(articles)}건")

    # 기사 처리
    upload_counts = {p: 0 for p in MEDIA_PREFIXES}
    published = 0
    review_records: List[dict] = []
    for article in articles:
        if published >= remaining:
            break
        try:
            result = process_article(article, upload_counts, review_mode=REVIEW_ONLY)
            if result:
                if REVIEW_ONLY:
                    review_records.append(result)
                    published += 1
                    continue
                success_media = result.get("success_media", [])
                media_value = ",".join(success_media) if success_media else "ALL"
                db_record_success(
                    article["url_id"],
                    article["title"],
                    media_value,
                    source_published_at=article.get("source_published_at"),
                    published_at=now_kst(),
                )
                db_store_attempt_state(
                    article["url_id"],
                    article["title"],
                    media_value,
                    "SUCCESS",
                    retry_count=0,
                    partial_success=result.get("partial_success", False),
                    source_published_at=article.get("source_published_at"),
                )
                published += 1
                print(f"   🎉 발행 완료! (금일 누적: {today_count + published}건)")
        except PipelineFailure as failure:
            if REVIEW_ONLY:
                review_records.append({
                    "source_title": article.get("title", ""),
                    "source_url": article.get("url", ""),
                    "source_published_at": article.get("source_published_at"),
                    "source_chars": len(article.get("body", "") or ""),
                    "status": "FAILED",
                    "stage": failure.stage,
                    "code": failure.code,
                    "message": failure.message,
                    "variants": [],
                })
                if failure.abort_run:
                    raise
                continue
            status, retry_count, next_retry_at = classify_attempt_state(failure, db_get_attempt_state(article["url_id"]))
            db_store_attempt_state(
                article["url_id"],
                article["title"],
                "FAILED",
                status,
                stage=failure.stage,
                code=failure.code,
                message=failure.message,
                retry_count=retry_count,
                next_retry_at=next_retry_at,
                partial_success=failure.partial_success,
                source_published_at=article.get("source_published_at"),
            )
            if failure.abort_run:
                raise
        except Exception as e:
            failure = PipelineFailure("run", "UNHANDLED_EXCEPTION", str(e), retryable=False)
            status, retry_count, next_retry_at = classify_attempt_state(failure, db_get_attempt_state(article["url_id"]))
            db_store_attempt_state(
                article["url_id"],
                article["title"],
                "FAILED",
                status,
                stage=failure.stage,
                code=failure.code,
                message=failure.message,
                retry_count=retry_count,
                next_retry_at=next_retry_at,
                partial_success=False,
                source_published_at=article.get("source_published_at"),
            )

    # 결과 요약
    if REVIEW_ONLY:
        report_path = write_review_report(review_records)
        print(f"\n📝 리뷰 리포트 저장: {report_path}")
        print("   (발행/DB 기록 없음)")
        return

    print(f"\n--- 실행 완료(KST): {now_kst().strftime('%H:%M:%S')} ---")
    print(f"📊 [작업 요약]")
    for p, c in upload_counts.items():
        print(f"   - {p} 발행 성공: {c}건")
    print(f"   - 금일 최종 누적: {today_count + published}/{DAILY_PUBLISH_LIMIT}건")
    print(f"──────────────────────────────────────────")


if __name__ == "__main__":
    run()
