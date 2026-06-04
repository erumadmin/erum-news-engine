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
UPSTAGE_REWRITE_MAX_OUTPUT_TOKENS = int(os.environ.get("UPSTAGE_REWRITE_MAX_OUTPUT_TOKENS", "1500"))
UPSTAGE_REWRITE_RETRY_MAX_OUTPUT_TOKENS = int(os.environ.get("UPSTAGE_REWRITE_RETRY_MAX_OUTPUT_TOKENS", "2200"))
UPSTAGE_QA_MAX_OUTPUT_TOKENS = int(os.environ.get("UPSTAGE_QA_MAX_OUTPUT_TOKENS", "900"))
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-pro")
GEMINI_MODEL_REWRITE = os.environ.get("GEMINI_MODEL_REWRITE", GEMINI_MODEL)
GEMINI_MODEL_QA = os.environ.get("GEMINI_MODEL_QA", GEMINI_MODEL)
REWRITE_SOURCE_MAX_CHARS = int(os.environ.get("REWRITE_SOURCE_MAX_CHARS", "4000"))
MIN_REWRITTEN_BODY_CHARS = int(os.environ.get("MIN_REWRITTEN_BODY_CHARS", "300"))
SHORT_FORM_MIN_REWRITTEN_BODY_CHARS = int(os.environ.get("SHORT_FORM_MIN_REWRITTEN_BODY_CHARS", "220"))
SHORT_FORM_MIN_SENTENCE_COUNT = int(os.environ.get("SHORT_FORM_MIN_SENTENCE_COUNT", "4"))
SHORT_FORM_MIN_PARAGRAPH_COUNT = int(os.environ.get("SHORT_FORM_MIN_PARAGRAPH_COUNT", "3"))
SOFT_REWRITTEN_BODY_CHARS = int(os.environ.get("SOFT_REWRITTEN_BODY_CHARS", "4500"))
HARD_REWRITTEN_BODY_CHARS = int(os.environ.get("HARD_REWRITTEN_BODY_CHARS", "6500"))
QA_INPUT_MAX_CHARS = int(os.environ.get("QA_INPUT_MAX_CHARS", "2400"))
QA_SOURCE_MAX_CHARS = int(os.environ.get("QA_SOURCE_MAX_CHARS", "1800"))
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
EDITORIAL_IMAGE_PROBE = os.environ.get("EDITORIAL_IMAGE_PROBE", "0") == "1"
EDITORIAL_IMAGE_PROBE_DOWNLOAD = os.environ.get("EDITORIAL_IMAGE_PROBE_DOWNLOAD", "0") == "1"
HIDDEN_PUBLISH_TEST = os.environ.get("HIDDEN_PUBLISH_TEST", "0") == "1"
PUBLISH_STATUS = (os.environ.get("PUBLISH_STATUS", "PUBLISHED").strip() or "PUBLISHED").upper()
if PUBLISH_STATUS not in {"PUBLISHED", "DRAFT"}:
    raise RuntimeError("PUBLISH_STATUS는 PUBLISHED 또는 DRAFT만 허용됩니다.")
if HIDDEN_PUBLISH_TEST:
    PUBLISH_STATUS = "DRAFT"
if not UPSTAGE_API_KEY and not (REVIEW_ONLY and GEMINI_API_KEY):
    raise RuntimeError("UPSTAGE_API_KEY가 없습니다. 리뷰 전용 모드에서는 GEMINI_API_KEY가 필요합니다.")
EDITORIAL_PIPELINE = os.environ.get("EDITORIAL_PIPELINE", "1") == "1"
# IJ + 편집 파이프라인: 수집 원문 전문 + 리서치 패킷·근거를 합쳐 재작성 (0이면 원문만)
# IJ 작성: 원문 전문 + 리서치 패킷 + 근거 (하이브리드 유저 메시지). 0 = GitHub main처럼 원문만.
IJ_PACKET_PIPELINE = os.environ.get("IJ_PACKET_PIPELINE", "1") != "0"
EDITORIAL_PERSIST = os.environ.get("EDITORIAL_PERSIST", "0") == "1"
MEDIA_PREFIXES = ["IJ_", "NN_", "CB_"]
SITE_PREFIX_BY_CODE = {"IJ": "IJ_", "NN": "NN_", "CB": "CB_"}
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

IMAGE_MASTER_MAX_WIDTH = int(os.environ.get("IMAGE_MASTER_MAX_WIDTH", "2000"))
IMAGE_MASTER_WEBP_QUALITY = int(os.environ.get("IMAGE_MASTER_WEBP_QUALITY", "89"))
IMAGE_THUMB_MAX_WIDTH = int(os.environ.get("IMAGE_THUMB_MAX_WIDTH", "640"))
IMAGE_THUMB_WEBP_QUALITY = int(os.environ.get("IMAGE_THUMB_WEBP_QUALITY", "80"))

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

CANONICAL_CATEGORY_SLUGS = {
    "정치": "politics",
    "사회": "society",
    "경제": "economy",
    "IT/과학": "it-science",
    "문화/생활": "culture-life",
    "국제": "international",
    "환경": "environment",
}

CATEGORY_ALIASES = {
    "정치": "정치",
    "politics": "정치",
    "사회": "사회",
    "society": "사회",
    "경제": "경제",
    "economy": "경제",
    "it/과학": "IT/과학",
    "it과학": "IT/과학",
    "it-science": "IT/과학",
    "문화/생활": "문화/생활",
    "문화생활": "문화/생활",
    "culture-life": "문화/생활",
    "국제": "국제",
    "international": "국제",
    "환경": "환경",
    "environment": "환경",
}


def normalize_category_name(name: Optional[str]) -> str:
    raw = (name or "").strip()
    if not raw:
        return DEFAULT_CATEGORY
    key = raw.lower().replace(" ", "")
    return CATEGORY_ALIASES.get(key, raw)


def get_canonical_category_pair(name: Optional[str]) -> Tuple[str, str]:
    canonical_name = normalize_category_name(name)
    canonical_slug = CANONICAL_CATEGORY_SLUGS.get(canonical_name, canonical_name.lower())
    return canonical_name, canonical_slug


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

REWRITE_USER_TEMPLATE = """원문 메타데이터
제목: {source_title}
출처 URL: {source_url}
원문 발행시각: {source_published_at}

원문 본문
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

def build_rewrite_user_message(article: dict) -> str:
    source_title = re.sub(r"\s+", " ", (article.get("title") or "").strip()) or "미상"
    source_url = (article.get("url") or "").strip() or "미상"
    source_published_at = to_kst_iso(article.get("source_published_at")) or "미상"
    original_text = strip_html_tags(article.get("body", ""))[:REWRITE_SOURCE_MAX_CHARS]
    return REWRITE_USER_TEMPLATE.format(
        source_title=source_title,
        source_url=source_url,
        source_published_at=source_published_at,
        original_text=original_text,
    )

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

def _ask_gemini_rest(persona, user_text, model=None, max_output_tokens=None, stage="rewrite"):
    use_model = model if (model and str(model).startswith("gemini")) else (GEMINI_MODEL_QA if stage == "qa" else GEMINI_MODEL_REWRITE)
    output_tokens = max_output_tokens or (UPSTAGE_QA_MAX_OUTPUT_TOKENS if stage == "qa" else UPSTAGE_REWRITE_MAX_OUTPUT_TOKENS)
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
                    {"role": "user", "parts": [{"text": user_text}]}
                ],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": output_tokens,
                },
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise ValueError("Gemini 응답에 candidates가 없음")
        parts = ((candidates[0].get("content") or {}).get("parts") or [])
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in parts
        )
        return content.strip()
    except PipelineFailure:
        raise
    except Exception as e:
        raise _llm_failure(stage, e)

def ask_llm(persona, user_text, model=None, max_output_tokens=None, stage="rewrite"):
    provider = "upstage"
    if REVIEW_ONLY and not UPSTAGE_API_KEY and GEMINI_API_KEY:
        provider = "gemini"
    if provider == "gemini":
        return _ask_gemini_rest(persona, user_text, model=model, max_output_tokens=max_output_tokens, stage=stage)
    use_model = model or (UPSTAGE_MODEL_QA if stage == "qa" else UPSTAGE_MODEL_REWRITE)
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
                    {"role": "user", "content": user_text},
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
            from engine.services.db_editorial import ensure_editorial_tables

            ensure_editorial_tables(lambda sql: cur.execute(sql))
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

def split_plain_sentences(text: str) -> List[str]:
    if not text:
        return []
    normalized = re.sub(r'\s+', ' ', text).strip()
    if not normalized:
        return []
    return [
        part.strip()
        for part in re.split(r'(?<=[.!?])\s+|(?<=다)\s+(?=[가-힣A-Z0-9“"\'\(\[])', normalized)
        if part.strip()
    ]

def auto_paragraphize_text(text: str) -> str:
    if not text:
        return ""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ""

    nonempty_lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    structural_prefixes = ("##", "###", "<h", "<p", "<ul", "<ol", "<li", "- ", "* ")
    if len(nonempty_lines) >= 2 or any(line.startswith(structural_prefixes) for line in nonempty_lines):
        return "\n".join(nonempty_lines)

    plain_line = re.sub(r'\s+', ' ', nonempty_lines[0]).strip()
    sentences = split_plain_sentences(plain_line)
    if len(sentences) < 3:
        return plain_line

    minimum_paragraphs = 3 if len(sentences) >= SHORT_FORM_MIN_SENTENCE_COUNT else 2
    target_paragraphs = min(5, max(minimum_paragraphs, (len(sentences) + 2) // 3))
    base_size = len(sentences) // target_paragraphs
    extras = len(sentences) % target_paragraphs

    paragraphs: List[str] = []
    cursor = 0
    for idx in range(target_paragraphs):
        chunk_size = base_size + (1 if idx < extras else 0)
        chunk = sentences[cursor:cursor + chunk_size]
        if chunk:
            paragraphs.append(" ".join(chunk))
        cursor += chunk_size
    return "\n\n".join(paragraphs).strip()

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
    plain_body = strip_html_tags(body)
    plain_body = re.sub(r'\s+', ' ', plain_body).strip()
    plain_body_len = len(plain_body)
    paragraph_count = len(re.findall(r'<p\b', body, flags=re.IGNORECASE))
    if not paragraph_count and plain_body:
        paragraph_count = max(1, len([p for p in re.split(r'\n{2,}', plain_body) if p.strip()]))
    sentence_count = len([part for part in split_plain_sentences(plain_body) if len(part) >= 12])

    # 제목
    if not title or len(title) < 5:
        return False, "제목 누락 또는 너무 짧음"

    # 본문 길이
    complete_short_form = (
        plain_body_len >= SHORT_FORM_MIN_REWRITTEN_BODY_CHARS
        and sentence_count >= SHORT_FORM_MIN_SENTENCE_COUNT
        and paragraph_count >= SHORT_FORM_MIN_PARAGRAPH_COUNT
    )
    if plain_body_len < MIN_REWRITTEN_BODY_CHARS and not complete_short_form:
        return False, f"본문 너무 짧음({plain_body_len}자, {sentence_count}문장)"
    if plain_body_len > HARD_REWRITTEN_BODY_CHARS:
        return False, f"본문 너무 김({plain_body_len}자)"
    if plain_body_len >= SHORT_FORM_MIN_REWRITTEN_BODY_CHARS and sentence_count >= SHORT_FORM_MIN_SENTENCE_COUNT and paragraph_count < 2:
        return False, f"문단 수 부족({paragraph_count}개)"

    # 라벨 잔재
    for label in ["제목:", "본문:", "내용:", "카테고리:", "태그:", "Title:", "Body:", "리드문:", "배경:", "과제:", "전망:", "솔루션:", "문제:", "해결책:", "임팩트:", "해석:"]:
        if label in body:
            return False, f"라벨 잔재 발견({label})"
    if re.search(r'<p>\s*(배경|과제|전망|솔루션|문제|해결책|임팩트|해석)\s*</p>', body, flags=re.IGNORECASE):
        return False, "라벨 잔재 발견(단독 소제목)"

    # 포맷 오염
    if "**" in body or "##" in body:
        return False, "마크다운(**, ##) 잔재 발견"
    if re.search(r"<p[^>]*>\s*<p", body, flags=re.IGNORECASE):
        return False, "중첩 p 태그 발견"
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


def should_retry_rewrite_validation(message: str) -> bool:
    if not message:
        return False
    return any(
        token in message
        for token in (
            "본문 너무 짧음",
            "라벨 잔재 발견",
            "본문 마지막 문자 비정상",
            "문단 수 부족",
            "시점 표기 불일치",
            "독자 확인 URL 누락",
            "반복 과다",
            "한계·조건 서술 부족",
            "IJ 4문단",
            "중첩 p 태그",
            "배경·문제",
            "작동 방식",
            "너무 짧음",
            "원문 핵심 누락",
            "1문단 리드",
            "coalition_takeaways",
            "briefing_not_ready",
            "2문단 배경",
            "4문단 한계",
            "한계·유의 부족",
            "경어체",
            "말줄임표",
            "discovered_fact",
            "미완성 문단",
            "절차 안내",
            "보도 인용",
            "원문 확인",
        )
    )

CB_DIRECT_KEYWORDS: Tuple[str, ...] = (
    "과징금", "가산세", "감면", "지원금", "보조금", "수출바우처", "바우처", "수의계약",
    "입찰", "조달", "공급망", "물류비", "인허가", "특례", "규제특례", "규제특구",
    "네거티브", "시행령", "입법예고", "매점매석", "사업재편", "펀드", "계약 제한",
    "계약 체결", "자격", "경력 요건", "지원 요건", "대부료", "사용료", "유예 조항",
)
CB_SIGNAL_KEYWORDS: Tuple[str, ...] = (
    "공공주택", "착공", "인구유입", "지방소멸", "재생에너지", "전력망", "철도", "중련운행",
    "좌석", "스타트업", "인플루언서", "관광", "콘텐츠", "예능", "IP", "브랜드",
    "K-푸드", "K-컬처", "기술인재", "거점국립대", "AI", "바이오", "메가특구",
)
CB_BUSINESS_CONTEXT_KEYWORDS: Tuple[str, ...] = (
    "기업", "업계", "산업", "시장", "중소기업", "소상공인", "창업", "협력사", "제조",
    "수출", "투자", "관광객", "콘텐츠", "공급", "수요",
)
CB_SKIP_SHAPE_KEYWORDS: Tuple[str, ...] = (
    "행사", "캠페인", "기념식", "축사", "담화", "간담회", "홍보", "초청", "체험", "방한",
)


def _keyword_hits(text: str, compact: str, keywords: Tuple[str, ...]) -> List[str]:
    tokens = re.findall(r"[0-9A-Za-z가-힣-]+", text)
    hits: List[str] = []
    for keyword in keywords:
        lowered = keyword.lower().strip()
        compact_keyword = re.sub(r"\s+", "", lowered)
        if " " in lowered:
            if lowered in text or compact_keyword in compact:
                hits.append(keyword)
            continue
        token_hit = any(
            token == lowered
            or token.startswith(lowered)
            or token.endswith(lowered)
            for token in tokens
        )
        if token_hit:
            hits.append(keyword)
    return hits


def assess_cb_article_fit(article: dict) -> Tuple[str, str]:
    title = re.sub(r"\s+", " ", (article.get("title") or "").strip())
    body = strip_html_tags(article.get("body", ""))[:5000]
    text = re.sub(r"\s+", " ", f"{title} {body}".lower()).strip()
    compact = re.sub(r"\s+", "", text)

    direct_hits = _keyword_hits(text, compact, CB_DIRECT_KEYWORDS)
    if direct_hits:
        return "direct", f"직접 영향 키워드: {', '.join(direct_hits[:3])}"

    signal_hits = _keyword_hits(text, compact, CB_SIGNAL_KEYWORDS)
    if signal_hits:
        return "signal", f"시장 신호 키워드: {', '.join(signal_hits[:3])}"

    business_hits = _keyword_hits(text, compact, CB_BUSINESS_CONTEXT_KEYWORDS)
    if business_hits:
        return "signal", f"기업 맥락 키워드: {', '.join(business_hits[:3])}"

    skip_hits = _keyword_hits(text, compact, CB_SKIP_SHAPE_KEYWORDS)
    if skip_hits:
        return "skip", "행사·발언·홍보 성격은 있으나 기업 직접 영향이나 시장 신호가 약함"

    return "skip", "기업 독자 기준 직접 영향과 시장 신호가 약함"

# [v23.0] AI 품질검수 시스템
MEDIA_TONE_DESC = {
    "IJ_": "솔루션 저널리즘 - 사회 문제의 구조적 해결책 제시, 수요자 중심 관점",
    "NN_": "커뮤니티 저널리즘 - 어려운 뉴스를 쉽고 품격 있게, 지역·공동체 소식 중심",
    "CB_": "비즈니스 분석 - 산업 트렌드와 ESG 시사점, 경영 전략 관점",
}

QA_SYSTEM_PROMPT = load_skill("qa_checker")

def build_qa_user_message(
    source_article: Optional[dict],
    title: str,
    excerpt: str,
    body: str,
    packet: Optional[dict] = None,
) -> str:
    plain_body = re.sub(r'<[^>]+>', ' ', body).strip()
    plain_body = re.sub(r'\s+', ' ', plain_body)
    plain_body = limit_rewritten_body_text(plain_body, QA_INPUT_MAX_CHARS)
    excerpt = re.sub(r'\s+', ' ', (excerpt or '').strip())
    excerpt = excerpt[:240]
    lines = []
    if source_article:
        source_title = re.sub(r'\s+', ' ', (source_article.get("title") or "").strip()) or "미상"
        source_url = (source_article.get("url") or "").strip() or "미상"
        source_published_at = to_kst_iso(source_article.get("source_published_at")) or "미상"
        source_plain = strip_html_tags(source_article.get("body", ""))
        source_plain = re.sub(r'\s+', ' ', source_plain).strip()[:QA_SOURCE_MAX_CHARS]
        lines.extend([
            "원문 기사",
            f"제목: {source_title}",
            f"출처 URL: {source_url}",
            f"원문 발행시각: {source_published_at}",
            f"본문: {source_plain}",
            "",
        ])
    from engine.pipeline.qa_input import append_packet_block

    append_packet_block(lines, packet)
    lines.extend([
        "재작성 기사",
        f"제목: {title}",
        f"리드문: {excerpt}",
        f"본문: {plain_body}",
    ])
    return "\n".join(lines)


def ai_quality_check(
    title: str,
    excerpt: str,
    body: str,
    media_prefix: str,
    source_article: Optional[dict] = None,
    research_packet: Optional[dict] = None,
) -> Tuple[bool, List[str], int, Optional[dict]]:
    media_tone = MEDIA_TONE_DESC.get(media_prefix, "일반 뉴스")
    system_prompt = QA_SYSTEM_PROMPT.format(media_tone=media_tone)
    article_text = build_qa_user_message(
        source_article, title, excerpt, body, packet=research_packet
    )
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
    for label in (
        "리드문:", "배경:", "과제:", "전망:", "솔루션:", "문제:", "해결책:", "임팩트:", "해석:",
        "리드문 :", "배경 :", "과제 :", "전망 :",
    ):
        text = text.replace(label, "")
    text = re.sub(
        r"<p>\s*(배경|과제|전망|솔루션|문제|해결책|임팩트|해석)\s*:?\s*</p>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r'^(본문|Body|내용)[:\s-]*', '', text, flags=re.IGNORECASE).strip()
    text = limit_rewritten_body_text(text)
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'^##\s+(.*?)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^###\s+(.*?)$', r'<h4>\1</h4>', text, flags=re.MULTILINE)
    text = auto_paragraphize_text(text)
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
    label_re = re.compile(r'^(제목|Title|헤드라인|리드문|Excerpt|요약|본문|Body|내용|카테고리|Category|태그|Tags)\s*[:：]?\s*(.*)$', re.IGNORECASE)
    bare_labels = {
        "제목": "title",
        "title": "title",
        "헤드라인": "title",
        "리드문": "excerpt",
        "excerpt": "excerpt",
        "요약": "excerpt",
        "본문": "body",
        "body": "body",
        "내용": "body",
        "카테고리": "cat",
        "category": "cat",
        "태그": "tags",
        "tags": "tags",
    }

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        lower_line = line.lower()
        if lower_line in bare_labels:
            current = bare_labels[lower_line]
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
    cat = normalize_category_name(ai_cat.replace('[', '').replace(']', '').strip())
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
    if not R2_ACCOUNT_ID or not R2_ACCESS_KEY_ID or not R2_SECRET_ACCESS_KEY:
        print("\n      ⚠️ [R2 업로드 불가]: R2 환경변수 누락")
        return None
    variants: Dict[str, Tuple[bytes, str, str]]
    try:
        variants = build_r2_variants(img_bytes, filename)
    except Exception:
        variants = {"master": (img_bytes, content_type, filename)}
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
        uploaded_urls: Dict[str, str] = {}
        for variant_name, (variant_bytes, variant_content_type, variant_filename) in variants.items():
            key = f"news/{now_kst().strftime('%Y/%m')}/{variant_filename}"
            s3.put_object(Bucket=R2_BUCKET_NAME, Key=key, Body=variant_bytes, ContentType=variant_content_type)
            uploaded_urls[variant_name] = f"{R2_PUBLIC_URL}/{key}"
        return uploaded_urls.get("master")
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
        clean_name, clean_slug = get_canonical_category_pair(name)
        if not clean_name or not clean_slug: return None
        try:
            r = requests.post(f"{self.api_base}/api/categories",
                              json={"site": self.site_code, "name": clean_name, "slug": clean_slug},
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
            "status": PUBLISH_STATUS,
            "categoryId": cat_id,
            "featuredImageUrl": img_url,
            "publishedAt": to_kst_iso(publish_dt),
            "sourcePublishedAt": to_kst_iso(source_published_at) if source_published_at else None,
        }
        if payload["sourcePublishedAt"] is None:
            payload.pop("sourcePublishedAt")
        r = requests.post(f"{self.api_base}/api/articles",
                          json=payload, headers=self.headers, timeout=30)
        r.raise_for_status()
        return r.json()["id"]

SITES: dict = {k: Site(v['base'], v['user'], v['app_pw']) for k, v in WP_CFG.items()}
for _prefix, _cfg in ERUM_CFG.items():
    SITES[_prefix] = ErumSite(_cfg["site"])

# ========================= [6. GSC 사이트맵 제출] =========================

def submit_sitemap_to_gsc(prefix):
    if PUBLISH_STATUS != "PUBLISHED":
        return
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

from engine.pipeline.article_images import (
    BLOCKED_IMAGE_PATTERNS,
    MIN_IMAGE_BYTES,
    MIN_IMAGE_WIDTH,
    MIN_IMAGE_ASPECT_RATIO,
    MAX_IMAGE_ASPECT_RATIO,
    CONTACT_ALT_RE,
    ImageCandidate,
    ImageInspection,
    find_best_image,
    download_best_image,
    require_article_image,
    fix_newswire_url,
    extract_image_from_html,
    extract_image_with_caption,
    is_valid_image,
    inspect_image_bytes,
    assess_image_quality,
)


def build_r2_variants(img_bytes: bytes, filename: str) -> Dict[str, Tuple[bytes, str, str]]:
    from PIL import Image
    import io as _io

    img = Image.open(_io.BytesIO(img_bytes))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    stem = filename.rsplit(".", 1)[0] or f"img_{hash(filename) & 0xFFFFFF:06x}"

    def render_variant(max_width: int, quality: int, suffix: str) -> Tuple[bytes, str, str]:
        variant = img.copy()
        if variant.width > max_width:
            ratio = max_width / variant.width
            variant = variant.resize((max_width, int(variant.height * ratio)), Image.LANCZOS)
        buf = _io.BytesIO()
        variant.save(buf, format="WEBP", quality=quality)
        return buf.getvalue(), "image/webp", f"{stem}{suffix}.webp"

    return {
        "master": render_variant(IMAGE_MASTER_MAX_WIDTH, IMAGE_MASTER_WEBP_QUALITY, ""),
        "thumb": render_variant(IMAGE_THUMB_MAX_WIDTH, IMAGE_THUMB_WEBP_QUALITY, "__thumb"),
    }


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
    stats = {
        "feed_entries": 0,
        "skipped_missing_link": 0,
        "skipped_existing_id": 0,
        "skipped_target_filter": 0,
        "skipped_non_korean_title": 0,
        "skipped_rule_blocked": 0,
        "skipped_global_blocked": 0,
        "skipped_semantic_duplicate": 0,
        "skipped_missing_date": 0,
        "skipped_out_of_range": 0,
        "skipped_non_korean_newswire": 0,
        "kept": 0,
    }
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
                stats["feed_entries"] += 1
                if count >= feed_limit: break
                if not hasattr(e, 'link'):
                    stats["skipped_missing_link"] += 1
                    continue
                curr_id = extract_unique_id(e.link)
                if not review_mode and curr_id in ex_ids:
                    stats["skipped_existing_id"] += 1
                    continue
                if TARGET_URL_IDS and curr_id not in TARGET_URL_IDS:
                    stats["skipped_target_filter"] += 1
                    continue
                if not is_mainly_korean(e.title, threshold=0.5):
                    stats["skipped_non_korean_title"] += 1
                    continue
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
                            stats["skipped_rule_blocked"] += 1
                            continue
                    if not rule_allowed and curr_id in blocked_ids:
                        stats["skipped_global_blocked"] += 1
                        continue
                    if is_semantic_duplicate(e.title, ex_titles, threshold=0.9):
                        stats["skipped_semantic_duplicate"] += 1
                        continue
                dt = e.get('published_parsed') or e.get('updated_parsed')
                source_published_at = feed_time_to_kst(dt)
                if not source_published_at:
                    stats["skipped_missing_date"] += 1
                    continue
                article_date = source_published_at.date()
                if RETRY_DAYS > 0:
                    if article_date < today - timedelta(days=RETRY_DAYS) or article_date > today:
                        stats["skipped_out_of_range"] += 1
                        continue
                else:
                    if article_date != today:
                        stats["skipped_out_of_range"] += 1
                        continue
                if is_newswire and not re.search('[가-힣]', e.title):
                    stats["skipped_non_korean_newswire"] += 1
                    continue

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
                stats["kept"] += 1
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

    if review_mode or TARGET_URL_IDS:
        print(
            "      🧮 [수집 필터] "
            f"입력 {stats['feed_entries']} / 유지 {stats['kept']} / "
            f"중복 {stats['skipped_semantic_duplicate']} / 대상필터 {stats['skipped_target_filter']} / "
            f"날짜 {stats['skipped_out_of_range']} / 비한글제목 {stats['skipped_non_korean_title']} / "
            f"ID중복 {stats['skipped_existing_id']} / 규칙차단 {stats['skipped_rule_blocked']} / "
            f"전역차단 {stats['skipped_global_blocked']} / 날짜누락 {stats['skipped_missing_date']} / "
            f"뉴스와이어비한글 {stats['skipped_non_korean_newswire']}"
        )

    if articles and EDITORIAL_PIPELINE and os.environ.get("EDITORIAL_ENRICH_ON_COLLECT", "1") != "0":
        from engine.pipeline.ingest import enrich_articles_batch

        print(f"   📥 [원문보강] RSS {len(articles)}건 → 전문 페이지 fetch 시도...")
        articles = enrich_articles_batch(articles, fetch_with_retry)

    return articles


def _editorial_db_hooks() -> Optional[dict]:
    if not EDITORIAL_PERSIST:
        return None
    from engine.services import db_editorial as edb

    def save_raw_source(raw: dict, research: dict) -> int:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                return edb.insert_raw_source(cur, raw, research)
        finally:
            conn.close()

    def save_research_packet(raw_id: int, site: str, packet: dict, publish_grade: str, placement) -> int:
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                return edb.insert_research_packet(cur, raw_id, site, packet, publish_grade, placement)
        finally:
            conn.close()

    return {"save_raw_source": save_raw_source, "save_research_packet": save_research_packet}


def process_article(
    article: dict,
    upload_counts: dict,
    review_mode: bool = REVIEW_ONLY,
    editorial_ctx=None,
) -> dict:
    """기사 1건 처리. editorial_ctx가 있으면 1원문=1사이트 라우팅."""
    print(f"\n▶ 기사 처리 시작: {article['title'][:40]}...")
    source_published_at = article.get("source_published_at")
    published_at = now_kst()
    if editorial_ctx:
        from engine.pipeline.media_plan import build_media_plan_for_editorial

        media_plan = build_media_plan_for_editorial(
            editorial_ctx,
            assess_cb_article_fit=assess_cb_article_fit,
            article=article,
        )
        active_prefixes = [p for p in MEDIA_PREFIXES if media_plan[p].get("enabled")]
    else:
        media_plan = {
            prefix: {"enabled": True, "mode": "default", "reason": ""}
            for prefix in MEDIA_PREFIXES
        }
        cb_mode, cb_reason = assess_cb_article_fit(article)
        media_plan["CB_"] = {
            "enabled": cb_mode != "skip",
            "mode": cb_mode,
            "reason": cb_reason,
        }
        active_prefixes = [p for p in MEDIA_PREFIXES if media_plan[p].get("enabled")]
    expected_media_count = len(active_prefixes)
    review_record = {
        "source_title": article.get("title", ""),
        "source_url": article.get("url", ""),
        "source_published_at": source_published_at,
        "source_chars": len(article.get("body", "") or ""),
        "editorial": {
            "assigned_site": getattr(editorial_ctx, "assigned_site", None),
            "publish_grade": getattr(editorial_ctx, "publish_grade", None),
            "placement": editorial_ctx.placement.to_dict() if editorial_ctx else None,
            "use_packet_writing": getattr(editorial_ctx, "use_packet_writing", False),
        } if editorial_ctx else None,
        "media_plan": {
            prefix.rstrip("_"): {
                "enabled": plan.get("enabled", True),
                "mode": plan.get("mode", "default"),
                "reason": plan.get("reason", ""),
            }
            for prefix, plan in media_plan.items()
        },
        "variants": [],
    }
    img_bytes = None
    img_content_type = ""
    fn = ""
    best_cap = None
    best_img = ""
    review_record["image_status"] = "skipped:review_mode" if review_mode else "pending"
    review_record["image_probe"] = None
    review_record["layout_type"] = None
    review_record["publish_preflight"] = None

    if review_mode and not EDITORIAL_IMAGE_PROBE:
        print("   🧪 리뷰 전용 모드: 이미지/발행 단계 생략")
    elif review_mode and EDITORIAL_IMAGE_PROBE:
        print("   🧪 리뷰 모드 + 이미지 프로브...", end="", flush=True)
        from engine.pipeline.image_probe import probe_article_images
        from engine.pipeline.layout_decision import decide_layout_type

        review_record["image_probe"] = probe_article_images(
            article, download=EDITORIAL_IMAGE_PROBE_DOWNLOAD
        )
        review_record["image_status"] = review_record["image_probe"].get("status", "probe")
        review_record["layout_type"] = decide_layout_type(
            review_record["image_probe"],
            placement_slot=getattr(getattr(editorial_ctx, "placement", None), "slot", "ledger")
            if editorial_ctx
            else "ledger",
            publish_grade=getattr(editorial_ctx, "publish_grade", "C") if editorial_ctx else "C",
        )
        print(
            f" {review_record['image_status']}"
            f" layout={review_record['layout_type']}"
            f" url={(review_record['image_probe'].get('selected_url') or '')[:60]}"
        )
    else:
        print(f"   🔎 이미지 탐색 중...", end="", flush=True)
        image_candidates = find_best_image(article)
        if not image_candidates:
            print(" 실패 (이미지 없음/저작권).")
            raise PipelineFailure("image", "NO_USABLE_IMAGE", "이미지 후보 없음", retryable=False)
        print(f" 찾음.")

        print(f"   📥 이미지 다운로드 중...", end="", flush=True)
        img_bytes, img_content_type, fn, best_cap, best_img = download_best_image(image_candidates)
        review_record["image_status"] = f"ok:{len(img_bytes)//1024}KB"
        print(f" 완료 ({len(img_bytes)//1024}KB).")

    rewritten = {}
    published_prefixes = []
    published_items: List[dict] = []
    failures: List[PipelineFailure] = []
    for prefix in active_prefixes:
        plan = media_plan.get(prefix, {"enabled": True, "mode": "default", "reason": ""})
        if not plan.get("enabled", True):
            print(f"      ⏭️ [{prefix}] 스킵 ({plan.get('reason', 'CB 비적합')}).")
            if review_mode:
                review_record["variants"].append({
                    "prefix": prefix,
                    "status": "SKIPPED",
                    "qa_pass": False,
                    "qa_score": 0,
                    "qa_fails": [],
                    "fixed_applied": False,
                    "title": "",
                    "excerpt": "",
                    "body": "",
                    "cat": "",
                    "tags": [],
                    "failure": f"skip/{plan.get('mode', 'skip')}: {plan.get('reason', 'CB 비적합')}",
                })
            continue
        if prefix == "CB_" and plan.get("mode") in ("direct", "signal"):
            print(f"      🧭 [CB_] {plan.get('mode')} 앵글 ({plan.get('reason')}).")
        print(f"      ✍️ [{prefix}] Solar Pro 3 기사 작성 중...", end="", flush=True)
        try:
            if (
                editorial_ctx
                and getattr(editorial_ctx, "skip_rewrite", False)
                and prefix == "IJ_"
            ):
                reason = getattr(editorial_ctx, "skip_rewrite_reason", "research_insufficient")
                print(f" 스킵(Target: {reason})", flush=True)
                if review_mode:
                    review_record["variants"].append({
                        "prefix": prefix,
                        "status": "SKIPPED",
                        "qa_pass": False,
                        "qa_score": 0,
                        "qa_fails": [reason],
                        "fixed_applied": False,
                        "title": "",
                        "excerpt": "",
                        "body": "",
                        "cat": "",
                        "tags": [],
                        "failure": f"target/{reason}",
                    })
                continue
            if (
                editorial_ctx
                and editorial_ctx.use_packet_writing
                and prefix == "IJ_"
                and IJ_PACKET_PIPELINE
            ):
                from engine.pipeline.packet_writer import build_rewrite_user_message_from_editorial

                rewrite_input = build_rewrite_user_message_from_editorial(
                    article,
                    editorial_ctx.packet,
                    editorial_ctx.evidence,
                )
                from engine.pipeline.packet_writer import build_editorial_quality_retry_suffix

                rewrite_input += build_editorial_quality_retry_suffix(
                    article.get("editorial_score_gaps")
                )
                print(" [원문+리서치]", end="", flush=True)
            else:
                rewrite_input = build_rewrite_user_message(article)
            rewrite_token_budgets = [UPSTAGE_REWRITE_MAX_OUTPUT_TOKENS]
            if UPSTAGE_REWRITE_RETRY_MAX_OUTPUT_TOKENS not in rewrite_token_budgets:
                rewrite_token_budgets.append(UPSTAGE_REWRITE_RETRY_MAX_OUTPUT_TOKENS)

            p = None
            msg = ""
            best_rewrite_candidate: dict | None = None
            best_rewrite_body_len = 0
            ij_editorial = (
                editorial_ctx
                and editorial_ctx.use_packet_writing
                and prefix == "IJ_"
                and IJ_PACKET_PIPELINE
            )
            validation_attempts = int(os.environ.get("IJ_REWRITE_VALIDATION_ATTEMPTS", "3"))
            current_input = rewrite_input
            for attempt_idx in range(validation_attempts):
                max_tokens = rewrite_token_budgets[min(attempt_idx, len(rewrite_token_budgets) - 1)]
                res = ask_llm(
                    PERSONA_DEFINITIONS[prefix],
                    current_input,
                    model=UPSTAGE_MODEL_REWRITE,
                    max_output_tokens=max_tokens,
                    stage="rewrite",
                )
                p = parse_llm_response(res)
                if ij_editorial:
                    from engine.pipeline.rewrite_validate import fix_ij_llm_body_markup

                    p["body"] = fix_ij_llm_body_markup(p.get("body") or "")
                plain_body_len = len(re.sub(r"<[^>]+>", "", p.get("body") or ""))
                if plain_body_len > best_rewrite_body_len:
                    best_rewrite_body_len = plain_body_len
                    best_rewrite_candidate = dict(p)
                is_valid, msg = validate_content_quality(p["title"], p["body"])
                if is_valid and ij_editorial:
                    from engine.pipeline.rewrite_validate import (
                        finalize_ij_editorial_body,
                        validate_ij_editorial_rewrite,
                    )

                    p["body"] = finalize_ij_editorial_body(
                        p["body"], editorial_ctx.packet, article
                    )
                    is_valid, msg = validate_ij_editorial_rewrite(
                        p["title"],
                        p["body"],
                        editorial_ctx.packet,
                        article,
                    )
                if is_valid:
                    break
                if (
                    ij_editorial
                    and attempt_idx + 1 >= validation_attempts
                    and any(
                        tok in msg
                        for tok in (
                            "한계·조건",
                            "한계·유의",
                            "4문단",
                        )
                    )
                ):
                    from engine.pipeline.rewrite_validate import (
                        finalize_ij_editorial_body,
                        validate_ij_editorial_rewrite,
                    )

                    p["body"] = finalize_ij_editorial_body(
                        p["body"], editorial_ctx.packet, article
                    )
                    is_valid, msg = validate_ij_editorial_rewrite(
                        p["title"],
                        p["body"],
                        editorial_ctx.packet,
                        article,
                    )
                if is_valid:
                    break
                if (
                    best_rewrite_candidate
                    and best_rewrite_body_len >= 120
                    and plain_body_len < 50
                ):
                    p = dict(best_rewrite_candidate)
                    plain_body_len = best_rewrite_body_len
                    if ij_editorial:
                        from engine.pipeline.rewrite_validate import (
                            finalize_ij_editorial_body,
                            validate_ij_editorial_rewrite,
                        )

                        p["body"] = finalize_ij_editorial_body(
                            p["body"], editorial_ctx.packet, article
                        )
                        is_valid, msg = validate_ij_editorial_rewrite(
                            p["title"],
                            p["body"],
                            editorial_ctx.packet,
                            article,
                        )
                        if is_valid:
                            break
                if attempt_idx + 1 >= validation_attempts or not should_retry_rewrite_validation(msg):
                    raise PipelineFailure("rewrite", "REWRITE_VALIDATION_FAIL", msg, retryable=False)
                from engine.pipeline.rewrite_validate import build_rewrite_correction_suffix

                current_input = rewrite_input + build_rewrite_correction_suffix(msg)
                next_tokens = rewrite_token_budgets[min(attempt_idx + 1, len(rewrite_token_budgets) - 1)]
                print(f" 재시도({msg}, {max_tokens}->{next_tokens} 토큰)...", end="", flush=True)

            if p is None:
                raise PipelineFailure("rewrite", "REWRITE_VALIDATION_FAIL", msg or "재작성 결과 없음", retryable=False)

            # AI 품질검수+보완 (Solar Pro 3 1회)
            print(" 작성완료.", flush=True)
            print(f"      🔍 [{prefix}] Solar Pro 3 품질검수 중...", end="", flush=True)
            passed, fails, score, fixed = ai_quality_check(
                p['title'],
                p.get('excerpt', ''),
                p['body'],
                prefix,
                source_article=article,
                research_packet=editorial_ctx.packet if editorial_ctx else None,
            )
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
                    # ERUM 프론트는 외부 원본 이미지 hotlink에 의존하면 깨질 수 있으므로 R2 URL만 발행한다.
                    r2_url = upload_to_r2(img_bytes, fn, img_content_type)
                    if not r2_url:
                        raise PipelineFailure("publish", "R2_UPLOAD_REQUIRED", "R2 업로드 실패로 발행 중단", retryable=True)
                    mid = r2_url
                else:
                    mid, _ = site.upload_image_bytes(img_bytes, fn, img_content_type, rw["title"], best_cap)
                    if not mid:
                        raise PipelineFailure("publish", "IMAGE_UPLOAD_FAIL", "이미지 업로드 실패", retryable=True)
                pid = site.create_post(
                    rw["title"],
                    rw["body"],
                    site.get_cat_id(rw["cat"]),
                    site.get_tag_ids(rw["tags"]),
                    mid,
                    excerpt=rw.get("excerpt", ""),
                    published_at=published_at,
                    source_published_at=source_published_at,
                )
                upload_counts[prefix] += 1
                published_prefixes.append(prefix)
                publish_meta = {}
                if editorial_ctx:
                    from engine.pipeline.publish_meta import build_publish_extras

                    publish_meta = build_publish_extras(editorial_ctx)
                published_items.append({
                    "prefix": prefix.rstrip("_"),
                    "site": ERUM_CFG.get(prefix, {}).get("site", prefix.rstrip("_")),
                    "id": pid,
                    "title": rw["title"],
                    "status": PUBLISH_STATUS,
                    "preview_url": f"{ERUM_API_BASE}/preview/articles/{pid}",
                    **publish_meta,
                })
                variant_review["publish_id"] = pid
                print(f" 성공 (ID:{pid}).")
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
        review_record["partial_success"] = len(published_prefixes) < expected_media_count
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
            "partial_success": len(published_prefixes) < expected_media_count,
            "failure_count": len(failures),
            "published_items": published_items,
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
    print(f"\n🚀 AI 뉴스 엔진 (v26.0-EditorialPipeline_KST) 가동: {now_kst().strftime('%Y-%m-%d %H:%M:%S')}")
    if EDITORIAL_PIPELINE:
        print(
            f"   📰 편집 파이프라인: ON (1원문=1사이트, IJ패킷={'ON' if IJ_PACKET_PIPELINE else 'OFF'}, "
            f"DB영속={'ON' if EDITORIAL_PERSIST else 'OFF'})"
        )
    if TARGET_URL_IDS:
        print(f"🎯 대상 URL 필터 활성화: {len(TARGET_URL_IDS)}건")

    if HIDDEN_PUBLISH_TEST:
        if not TARGET_URL_ID_LIST:
            raise RuntimeError("HIDDEN_PUBLISH_TEST 모드에서는 TARGET_URL_IDS가 필요합니다.")
        remaining = len(TARGET_URL_ID_LIST)
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
        print(f"🕶️ 숨김 발행 테스트 모드: {remaining}건, 상태 {PUBLISH_STATUS}, DB/GSC 기록 없음")
    elif REVIEW_ONLY:
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
    if (REVIEW_ONLY or HIDDEN_PUBLISH_TEST) and TARGET_URL_ID_LIST:
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
    hidden_publish_results: List[dict] = []
    editorial_hooks = _editorial_db_hooks() if EDITORIAL_PIPELINE and EDITORIAL_PERSIST else None
    if EDITORIAL_PIPELINE:
        from engine.pipeline.orchestrator import run_pre_publish_pipeline

    for article in articles:
        if published >= remaining:
            break
        editorial_ctx = None
        if EDITORIAL_PIPELINE:
            try:
                # 리뷰 모드도 TARGET 직접 로드·purpose 테스트는 전문 fetch 필요
                fetcher = fetch_with_retry
                editorial_ctx = run_pre_publish_pipeline(
                    article,
                    fetcher=fetcher,
                    persist=bool(editorial_hooks),
                    db_hooks=editorial_hooks,
                )
            except Exception as pipe_err:
                print(f"   ⚠️ 편집 파이프라인 오류: {pipe_err}")
                if os.environ.get("EDITORIAL_PIPELINE_STRICT", "0") == "1":
                    raise
                editorial_ctx = None
            if editorial_ctx is None:
                print("   ⏭️ 편집 파이프라인 DROP — 다음 기사")
                continue
        try:
            result = process_article(
                article,
                upload_counts,
                review_mode=REVIEW_ONLY,
                editorial_ctx=editorial_ctx,
            )
            if result:
                if REVIEW_ONLY:
                    review_records.append(result)
                    published += 1
                    continue
                if HIDDEN_PUBLISH_TEST:
                    hidden_publish_results.append({
                        "source_title": article.get("title", ""),
                        "source_url": article.get("url", ""),
                        "published_items": result.get("published_items", []),
                        "partial_success": result.get("partial_success", False),
                        "failure_count": result.get("failure_count", 0),
                    })
                    published += 1
                    print(f"   🕶️ 숨김 발행 완료! ({published}/{remaining})")
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
            if HIDDEN_PUBLISH_TEST:
                hidden_publish_results.append({
                    "source_title": article.get("title", ""),
                    "source_url": article.get("url", ""),
                    "status": "FAILED",
                    "stage": failure.stage,
                    "code": failure.code,
                    "message": failure.message,
                    "published_items": [],
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
            if HIDDEN_PUBLISH_TEST:
                hidden_publish_results.append({
                    "source_title": article.get("title", ""),
                    "source_url": article.get("url", ""),
                    "status": "FAILED",
                    "stage": failure.stage,
                    "code": failure.code,
                    "message": failure.message,
                    "published_items": [],
                })
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
                partial_success=False,
                source_published_at=article.get("source_published_at"),
            )

    # 결과 요약
    if REVIEW_ONLY:
        report_path = write_review_report(review_records)
        print(f"\n📝 리뷰 리포트 저장: {report_path}")
        print("   (발행/DB 기록 없음)")
        return

    if HIDDEN_PUBLISH_TEST:
        print(f"\n--- 숨김 발행 테스트 완료(KST): {now_kst().strftime('%H:%M:%S')} ---")
        print("📊 [작업 요약]")
        for p, c in upload_counts.items():
            print(f"   - {p} 발행 성공: {c}건")
        for record in hidden_publish_results:
            items = record.get("published_items", []) or []
            if not items:
                print(f"   - 실패: {record.get('source_title', '')} ({record.get('stage')}/{record.get('code')})")
                continue
            for item in items:
                print(
                    "   - "
                    f"{item.get('site')} ID:{item.get('id')} "
                    f"상태:{item.get('status')} "
                    f"프리뷰:{item.get('preview_url')}"
                )
        print("──────────────────────────────────────────")
        return hidden_publish_results

    print(f"\n--- 실행 완료(KST): {now_kst().strftime('%H:%M:%S')} ---")
    print(f"📊 [작업 요약]")
    for p, c in upload_counts.items():
        print(f"   - {p} 발행 성공: {c}건")
    for prefix, count in upload_counts.items():
        if count > 0:
            submit_sitemap_to_gsc(prefix)
    print(f"   - 금일 최종 누적: {today_count + published}/{DAILY_PUBLISH_LIMIT}건")
    print(f"──────────────────────────────────────────")


if __name__ == "__main__":
    run()
