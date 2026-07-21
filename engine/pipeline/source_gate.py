"""Newswire source gate: local filter/score + DeepSeek (OpenRouter) LLM routing.

Newswire is treated as a screened candidate pool, not a peer publish source.
Flow: local hard DROP -> local site scores -> auto DROP/ROUTE thresholds ->
optional LLM for ambiguous band -> ROUTE to exactly one of IJ/NN/CB.

Tightening notes (2026-07-12):
- Award/citation titles: default DROP; never IJ; CB only with strong business signals
- Threshold/site_cap use overall preferred site (max IJ/NN/CB), not allowed-only fallback
- site_cap preferred site → DROP site_cap:{site} (no below_threshold disguise); skip LLM
- Weak NN lifestyle promo: no local_auto_route; hard DROP when NN would
  auto-route; heavy rank penalty; public/policy bonus for NN/IJ keepers
- Cohort recruit promo (교육생·N기 모집 / 미디어 커리어): hard DROP recruit_promo
- Soft CB promo (partner-program / product-launch / ETF·fund 출시 PR without
  EPC·공급망·공시·M&A substance): hard DROP soft_cb_promo; no CB local_auto_route;
  revalidate DROP any site; rank −40
- CB ops substance (EPC/공급망/재생에너지/복합단지/건설…): local CB + ranking boost vs mid soft-ESG
- LLM empty/invalid JSON: fallback ROUTE via llm_fallback_local when local is strong; else parse_fail DROP
- IJ≫CB fidelity: if local IJ−CB ≥ 15, revalidate CB→IJ (or DROP if IJ capped)
- LLM IJ results revalidated locally
- Missing image is soft for CB-leaning copy; hard DROP otherwise
- CB-first selection order; stricter IJ per-run cap
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import requests

from engine.pipeline.article_images import BLOCKED_IMAGE_PATTERNS

SiteCode = str  # IJ | NN | CB | DROP

IJ_BOOST = ("정책", "제도", "안전", "복지", "노동", "환경", "공공기관", "취약계층", "사회문제")
NN_BOOST = ("지역", "주민", "생활", "건강", "교육", "문화", "관광", "소상공인", "소비자")
CB_BOOST = ("ESG", "CSR", "탄소", "공급망", "공시", "규제", "투자", "AI", "보안", "금융", "지속가능성")
CB_STRONG = CB_BOOST + ("IRA", "EPC", "컴플라이언스", "의무", "시행", "계약", "공급")
PR_PENALTY = ("최초", "최고", "혁신", "출시", "수상", "선정", "이벤트", "프로모션", "브랜드 캠페인")

PROMO_TITLE_PATTERNS = (
    r"할인",
    r"쿠폰",
    r"프로모션",
    r"이벤트\s*(개최|안내|진행)",
    r"특가",
    r"사은품",
    r"경품",
    r"무료\s*체험",
)
AWARD_TITLE_PATTERNS = (
    r"수상",
    r"표창",
    r"선정",
    r"인증\s*(획득|선정|수상)?",
    r"어워드",
    r"대상\s*수상",
    r"1위",
)
# Lifestyle/program promo cues that inflate NN local scores without public value
WEAK_NN_PROMO_TITLE_PATTERNS = (
    r"인기",
    r"신규\s*프로그램",
    r"프로그램\s*(모집|안내|개설|운영)",
    r"(참가자|수강생|회원)\s*모집",
    r"모집",
    r"출시",
    r"오픈",
)
# Sports / lifestyle program markers (title or body) — aerobics/yoga class PR etc.
WEAK_NN_LIFESTYLE_PATTERNS = (
    r"에어로빅",
    r"스텝박스",
    r"요가",
    r"필라테스",
    r"헬스장",
    r"줌바",
    r"생활체육",
    r"체육센터\s*(프로그램|신규|모집)?",
    r"문화체육센터",
    r"GX\s*프로그램",
    r"다이어트\s*(교실|프로그램|반)",
)
# Strong public/welfare/policy signals that keep NN legitimate (exemption + rank bonus).
# Keep this set strict: incidental 행정/안전 in lifestyle copy must NOT clear weak promo.
PUBLIC_POLICY_SIGNALS = (
    "복지",
    "정책",
    "고립은둔",
    "고립",
    "은둔",
    "학교밖",
    "취약계층",
    "취약",
    "조례",
    "예산",
    "공모사업",
    "돌봄",
    "시책",
    "공익",
    "사회문제",
    "공공기관",
    "지원센터",
)
# Back-compat alias used by older call sites / docs
PUBLIC_NN_SIGNALS = PUBLIC_POLICY_SIGNALS
# Cohort / career-program recruitment PR (D-Bridge 교육생 모집 등).
# Prefer specific frames — bare `모집` alone is too broad (already in weak NN).
RECRUIT_COHORT_PATTERNS = (
    r"교육생\s*모집",
    r"수강생\s*모집",
    r"\d+\s*[·･⋅\-~～]?\s*\d*\s*기\s*모집",
    r"[0-9]+\s*기\s*(교육생|수강생|참가자)?\s*모집",
    r"기\s*교육생\s*모집",
)
RECRUIT_CAREER_FRAMES = (
    r"미디어\s*커리어",
    r"커리어\s*빌드업",
    r"빌드업",
    r"파트너\s*프로그램",
    r"일경험\s*프로그램",
)
# Title-only civic signals that can clear title-strong recruit (not body 고립/은둔 alone).
RECRUIT_TITLE_CIVIC_EXEMPT_PATTERNS = (
    r"고립은둔",
    r"학교밖",
    r"복지\s*정책",
    r"지원센터",
)
# Soft CB: partner-program / product-feature PR (BitGo·Elliptic-class) without real ops.
SOFT_CB_PARTNER_PATTERNS = (
    r"디자인\s*파트너",
    r"파트너\s*프로그램",
    r"에이전틱.{0,24}파트너",
    r"design\s*partner",
    r"partner\s*program",
)
SOFT_CB_PRODUCT_LAUNCH_PATTERNS = (
    r"기능\s*출시",
    r"(월렛|지갑).{0,30}(출시|기능|론칭)",
    r"(새로운|신규).{0,16}(기능|솔루션)\s*(출시|론칭)",
    r"양자\s*위험\s*관리",
    r"(제품|솔루션|서비스)\s*(출시|론칭)",
)
SOFT_CB_CRYPTO_VENDOR_PATTERNS = (
    r"비트코인",
    r"암호화폐",
    r"디지털\s*자산",
    r"월렛",
    r"지갑",
    r"블록체인",
    r"크립토",
)
# Defiance-class ETF / fund product launch (UCITS ETF 출시 등) — soft without ops substance.
# Treat like partner path (no CB_STRONG fluff escape): tech/AI/공급망 narrative must not clear.
SOFT_CB_ETF_FUND_LAUNCH_PATTERNS = (
    r"UCITS\s*ETF",
    r"\bETFs?\b",
    r"\bETNs?\b",
    r"상장지수\s*펀드",
    r"상장지수펀드",
    r"신규\s*ETF",
    r"펀드\s*출시",
    r"(ETF|ETN|UCITS|상장지수\s*펀드|상장지수펀드).{0,30}(출시|론칭|상장)",
    r"(출시|론칭|상장).{0,30}(ETF|ETN|UCITS|상장지수\s*펀드|상장지수펀드)",
    r"유럽\s*최초.{0,48}(ETF|ETN|UCITS)",
)
# Narrow substance that clears soft-CB (not AI/보안/금융/투자 fluff alone).
SOFT_CB_SUBSTANCE_KEEP = (
    "EPC",
    "IRA",
    "공급망",
    "공시",
    "탄소",
    "의무",
    "시행",
    "계약",
    "공급",
    "에너지 복합단지",
    "복합단지",
    "재생에너지",
    "건설",
    "공장",
    "인수",
    "합병",
    "장기 주주",
    "지분",
)
# Soft CB hard-DROP when substance keep hits are below this (partner/product markers present).
SOFT_CB_SUBSTANCE_MIN = 2
# Real-ops CB substance (EPC/infra/M&A) — lifts local CB + ranking vs mid soft-ESG fluff.
# Deliberately omits bare ESG/CSR/탄소/지속가능성 so partner-program PR is not boosted.
CB_OPS_SUBSTANCE = (
    "EPC",
    "공급망",
    "재생에너지",
    "에너지 복합단지",
    "복합단지",
    "건설",
    "공장",
    "IRA",
    "계약",
    "공급",
    "인수",
    "합병",
    "장기 주주",
    "지분",
    "공시",
)
CB_OPS_SUBSTANCE_MIN = 2
CB_OPS_LOCAL_PER_HIT = 8.0
CB_OPS_LOCAL_HIT_CAP = 6
CB_OPS_RANK_BONUS_MIN3 = 14.0
CB_OPS_RANK_BONUS_MIN2 = 7.0
# After LLM empty/invalid JSON: fallback to local ROUTE at/above this (slightly above auto_drop).
LLM_FALLBACK_LOCAL_MIN = 40.0
# When local IJ dominates CB by this margin, do not ship as CB (재검증 → IJ or DROP).
IJ_CB_FIDELITY_MARGIN = 15.0
BOILERPLATE_MARKERS = (
    "회사소개",
    "회사 소개",
    "문의처",
    "문의:",
    "연락처",
    "면책",
    "본 보도자료",
    "보도자료 문의",
    "홍보 담당",
    "대표이사",
    "본사 주소",
)

SOURCE_GATE_SYSTEM_PROMPT = """당신은 이룸컴퍼니 뉴스엔진의 소스 게이트다.
뉴스와이어 PR 원문을 평가해 ROUTE 또는 DROP만 결정한다.
출력은 JSON만 허용한다.

규칙:
- decision은 ROUTE 또는 DROP.
- ROUTE인 경우 site는 IJ, NN, CB 중 하나만.
- 단순 홍보/수상/출시/이벤트는 DROP.
- ETF·UCITS·ETN·상장지수펀드·펀드 출시/신규 ETF 등 펀드 상품 출시 PR은 DROP (CB 금지).
- 제목에 수상·표창·선정·어워드가 있으면 원칙적으로 DROP. IJ로 보내지 않는다.
- 기업 실무·규제·ESG·공시·공급망 의미가 있으면 주로 CB.
- 시민 생활·지역·소비자 정보는 NN.
- 공공성·사회적 영향이 강해도 수상/행사 PR 프레임이면 IJ 금지, DROP 또는 CB만 검토.
- 뉴스와이어 PR은 무조건 통과시키지 않는다.
- score는 0~100 정수.
- 허용 site 목록이 주어지면 그 중에서만 고른다.
"""


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass
class SourceGateConfig:
    daytime_mode: str = "screened"
    max_selected_per_run: int = 5
    max_daily_share_pct: int = 30
    max_per_site_per_run: int = 3
    max_ij_per_run: int = 2
    max_per_org_per_run: int = 2
    provider: str = "openrouter"
    model: str = "deepseek/deepseek-v4-flash"
    input_max_chars: int = 3000
    max_output_tokens: int = 500
    temperature: float = 0.0
    auto_drop_below: float = 35.0
    auto_route_above: float = 82.0
    llm_min_score: float = 35.0
    llm_max_score: float = 81.0
    min_body_chars: int = 800
    korean_ratio_threshold: float = 0.5
    openrouter_api_key: str = ""
    openrouter_api_base: str = "https://openrouter.ai/api/v1"
    llm_retry: int = 1
    soft_image_for_cb: bool = True

    @classmethod
    def from_env(cls) -> "SourceGateConfig":
        return cls(
            daytime_mode=(os.environ.get("NEWSWIRE_DAYTIME_MODE", "screened") or "screened").strip().lower(),
            max_selected_per_run=max(0, _env_int("NEWSWIRE_MAX_SELECTED_PER_RUN", 5)),
            max_daily_share_pct=max(0, min(100, _env_int("NEWSWIRE_MAX_DAILY_SHARE", 30))),
            max_per_site_per_run=max(1, _env_int("NEWSWIRE_MAX_PER_SITE_PER_RUN", 3)),
            max_ij_per_run=max(0, _env_int("NEWSWIRE_MAX_IJ_PER_RUN", 2)),
            max_per_org_per_run=max(1, _env_int("NEWSWIRE_MAX_PER_ORG_PER_RUN", 2)),
            provider=(os.environ.get("SOURCE_GATE_PROVIDER", "openrouter") or "openrouter").strip().lower(),
            model=(os.environ.get("SOURCE_GATE_MODEL", "deepseek/deepseek-v4-flash") or "deepseek/deepseek-v4-flash").strip(),
            input_max_chars=max(500, _env_int("SOURCE_GATE_INPUT_MAX_CHARS", 3000)),
            max_output_tokens=max(100, _env_int("SOURCE_GATE_MAX_OUTPUT_TOKENS", 500)),
            temperature=_env_float("SOURCE_GATE_TEMPERATURE", 0.0),
            auto_drop_below=_env_float("SOURCE_GATE_AUTO_DROP_BELOW", 35.0),
            auto_route_above=_env_float("SOURCE_GATE_AUTO_ROUTE_ABOVE", 82.0),
            llm_min_score=_env_float("SOURCE_GATE_LLM_MIN_SCORE", 35.0),
            llm_max_score=_env_float("SOURCE_GATE_LLM_MAX_SCORE", 81.0),
            openrouter_api_key=(os.environ.get("OPENROUTER_API_KEY", "") or "").strip(),
            openrouter_api_base=(
                os.environ.get("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1") or "https://openrouter.ai/api/v1"
            ).rstrip("/"),
            llm_retry=max(0, _env_int("SOURCE_GATE_LLM_RETRY", 1)),
            soft_image_for_cb=os.environ.get("SOURCE_GATE_SOFT_IMAGE_CB", "1") != "0",
        )

    def site_limit(self, site: str) -> int:
        if site == "IJ":
            return min(self.max_per_site_per_run, self.max_ij_per_run)
        return self.max_per_site_per_run


@dataclass
class GateDecision:
    decision: str  # ROUTE | DROP
    site: Optional[str] = None
    score: float = 0.0
    reason: str = ""
    rewrite_angle: Optional[str] = None
    risk_flags: list[str] = field(default_factory=list)
    must_avoid: list[str] = field(default_factory=list)
    stage: str = "local"  # local_drop | local_route | llm | llm_fallback | parse_fail
    scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "site": self.site,
            "score": self.score,
            "reason": self.reason,
            "rewrite_angle": self.rewrite_angle,
            "risk_flags": list(self.risk_flags),
            "must_avoid": list(self.must_avoid),
            "stage": self.stage,
            "scores": dict(self.scores),
        }


@dataclass
class SourceGateStats:
    input_candidates: int = 0
    local_drop: int = 0
    local_route: int = 0
    llm_calls: int = 0
    llm_route: int = 0
    llm_drop: int = 0
    final_selected: int = 0
    site_counts: Counter = field(default_factory=Counter)
    drop_reasons: Counter = field(default_factory=Counter)
    pr_risk_flags: int = 0
    parse_fail_drops: int = 0
    llm_skipped_site_cap: int = 0

    def record_decision(self, decision: GateDecision) -> None:
        if decision.decision == "DROP":
            key = (decision.reason or "unknown").split(":")[0][:80]
            self.drop_reasons[key] += 1
            if decision.stage.startswith("llm"):
                self.llm_drop += 1
            elif decision.stage == "parse_fail":
                self.parse_fail_drops += 1
                self.local_drop += 1
            else:
                self.local_drop += 1
        else:
            if decision.stage.startswith("llm"):
                self.llm_route += 1
            else:
                self.local_route += 1
            if decision.site:
                self.site_counts[decision.site] += 1
        for flag in decision.risk_flags:
            if "PR" in flag.upper():
                self.pr_risk_flags += 1

    def format_report(self) -> str:
        top_reasons = ", ".join(f"{k}={v}" for k, v in self.drop_reasons.most_common(5)) or "(없음)"
        return "\n".join(
            [
                "📊 [뉴스와이어 source gate]",
                f"  RSS 입력 후보: {self.input_candidates}",
                f"  로컬 DROP: {self.local_drop}",
                f"  로컬 ROUTE: {self.local_route}",
                f"  LLM gate 호출: {self.llm_calls}",
                f"  LLM 스킵(site_cap): {self.llm_skipped_site_cap}",
                f"  LLM ROUTE: {self.llm_route}",
                f"  LLM DROP: {self.llm_drop}",
                f"  최종 발행 후보: {self.final_selected}",
                f"  매체 분포: IJ={self.site_counts.get('IJ', 0)} / "
                f"NN={self.site_counts.get('NN', 0)} / CB={self.site_counts.get('CB', 0)}",
                f"  DROP 주요 사유 top5: {top_reasons}",
                f"  PR_RISK 플래그: {self.pr_risk_flags}",
                f"  JSON 파싱실패 DROP: {self.parse_fail_drops}",
            ]
        )


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "")


def plain_text(article: dict[str, Any]) -> str:
    body = article.get("body") or article.get("rss_summary") or ""
    return re.sub(r"\s+", " ", strip_html(str(body))).strip()


def korean_ratio(text: str) -> float:
    clean = re.sub(r"[^가-힣a-zA-Z]", "", text or "")
    if not clean:
        return 0.0
    return len(re.findall(r"[가-힣]", clean)) / len(clean)


def extract_org_key(title: str) -> str:
    """Best-effort org key for same-day per-org caps."""
    t = re.sub(r"\s+", " ", (title or "").strip())
    if not t:
        return ""
    m = re.match(r"^([^,，/|]+?)(?:주식회사|㈜|\(주\)|유한회사|재단|협회|센터)?\s*[,，]", t)
    if m:
        return re.sub(r"[^\w가-힣]", "", m.group(1))[:40]
    m = re.match(r"^\[([^\]]{2,40})\]", t)
    if m:
        return re.sub(r"[^\w가-힣]", "", m.group(1))[:40]
    tokens = re.findall(r"[가-힣A-Za-z0-9]{2,}", t)
    return tokens[0][:40] if tokens else ""


def is_award_title(title: str) -> bool:
    return any(re.search(pat, title or "", re.I) for pat in AWARD_TITLE_PATTERNS)


def is_public_policy_signal(article: dict[str, Any]) -> bool:
    """True when title/body carry strong public·welfare·policy framing."""
    title = (article.get("title") or "").strip()
    body = plain_text(article)[:3000]
    text = f"{title} {body}"
    title_hits = _keyword_hits(title, PUBLIC_POLICY_SIGNALS)
    if title_hits:
        return True
    text_hits = set(_keyword_hits(text, PUBLIC_POLICY_SIGNALS))
    return len(text_hits) >= 2


def is_weak_nn_promo(article: dict[str, Any]) -> bool:
    """True when copy is lifestyle/program promo that should not NN auto-route.

    Catches 신규 프로그램·인기·에어로빅/요가류 without strong public·policy
    signals. Public exemption uses title-first / strict signals so incidental
    body words (행정, 안전) cannot clear aerobics-class PR.
    """
    title = (article.get("title") or "").strip()
    body = plain_text(article)[:3000]
    text = f"{title} {body}"

    title_promo = any(re.search(pat, title, re.I) for pat in WEAK_NN_PROMO_TITLE_PATTERNS)
    lifestyle = any(re.search(pat, text, re.I) for pat in WEAK_NN_LIFESTYLE_PATTERNS)
    recruit_sports = bool(
        re.search(r"모집", title, re.I) and re.search(r"생활체육|체육센터|헬스|요가|필라테스", text, re.I)
    )
    if not (title_promo or lifestyle or recruit_sports):
        return False

    # Strong public/policy framing → not a weak lifestyle promo
    if is_public_policy_signal(article):
        return False
    return True


def is_recruit_promo(article: dict[str, Any]) -> bool:
    """True for cohort/career enrollment PR (교육생·N기 모집) without public-policy frame.

    Targets D-Bridge-class 미디어 커리어 / 교육생 모집. Does not treat bare
    ``모집`` alone as recruit.

    Title-strong path (cohort patterns or title 모집 + title career frames)
    sticks unless the *title itself* has narrow civic signals — body-only
    public keywords (고립/은둔/복지) must not clear it. Weaker path (title
    bare 모집 + career only in body) may still use ``is_public_policy_signal``.
    """
    title = (article.get("title") or "").strip()
    body = plain_text(article)[:3000]
    text = f"{title} {body}"

    title_cohort = any(re.search(pat, title, re.I) for pat in RECRUIT_COHORT_PATTERNS)
    title_career = any(re.search(pat, title, re.I) for pat in RECRUIT_CAREER_FRAMES)
    title_strong = title_cohort or (
        bool(re.search(r"모집", title, re.I)) and title_career
    )
    if title_strong:
        # Narrow title-only civic exemption — not body public-policy hits.
        if any(re.search(pat, title, re.I) for pat in RECRUIT_TITLE_CIVIC_EXEMPT_PATTERNS):
            return False
        return True

    # Weaker path: title bare 모집 + career/partner framing in body
    has_recruit = bool(re.search(r"모집", title, re.I))
    career = any(re.search(pat, text, re.I) for pat in RECRUIT_CAREER_FRAMES)
    partner = bool(re.search(r"파트너\s*(프로그램|사|기관)", text, re.I))
    if not (has_recruit and (career or partner)):
        return False
    if is_public_policy_signal(article):
        return False
    return True


def is_soft_cb_promo(article: dict[str, Any]) -> bool:
    """True for soft partner-program / product-launch / ETF-fund CB PR without real ops.

    Targets BitGo-class 기능 출시·월렛 PR, Elliptic-class 디자인 파트너 프로그램
    참여 발표, and Defiance-class UCITS ETF / 펀드 출시. Clears when
    SOFT_CB_SUBSTANCE_KEEP hits ≥ SOFT_CB_SUBSTANCE_MIN (EPC/공급망/공시/탄소/IRA/
    건설/M&A·장기 주주 등) — AI·보안·금융·투자 fluff alone does not. ETF/fund
    launch uses the partner-style path (no CB_STRONG fluff escape).
    """
    title = (article.get("title") or "").strip()
    body = plain_text(article)[:3000]
    text = f"{title} {body}"

    partner = any(re.search(pat, text, re.I) for pat in SOFT_CB_PARTNER_PATTERNS)
    title_product = any(re.search(pat, title, re.I) for pat in SOFT_CB_PRODUCT_LAUNCH_PATTERNS)
    body_product = any(re.search(pat, body, re.I) for pat in SOFT_CB_PRODUCT_LAUNCH_PATTERNS)
    crypto = any(re.search(pat, text, re.I) for pat in SOFT_CB_CRYPTO_VENDOR_PATTERNS)
    product = title_product or (body_product and crypto)
    etf_fund = any(re.search(pat, text, re.I) for pat in SOFT_CB_ETF_FUND_LAUNCH_PATTERNS)
    # ETF/fund markers alone are soft only with a launch/list frame (출시·론칭·상장·신규).
    if etf_fund and not re.search(r"출시|론칭|상장|신규\s*ETF|펀드\s*출시|UCITS", text, re.I):
        etf_fund = False
    if not (partner or product or etf_fund):
        return False

    substance = set(_keyword_hits(text, SOFT_CB_SUBSTANCE_KEEP))
    # "공급" is a substring of "공급망" — one 공급망 mention must not count as two keep hits
    # (Defiance-class ETF PR often name-drops 공급망 in a tech narrative).
    if "공급망" in substance:
        substance.discard("공급")
    if len(substance) >= SOFT_CB_SUBSTANCE_MIN:
        return False

    # Partner-program / ETF·fund product launch: soft unless substance keep clears.
    # No CB_STRONG fluff escape — LLM tech/AI/공급망 narrative must not clear Defiance-class.
    if partner or etf_fund:
        return True

    # Product-launch / crypto-vendor feature PR: also require weak CB_STRONG (<3).
    cb_strong = set(_keyword_hits(text, CB_STRONG))
    # Exclude soft fluff that crypto PR always carries so CB_STRONG isn't gamed.
    fluff = {"AI", "보안", "금융", "투자"}
    strong_ops = cb_strong - fluff
    if len(strong_ops) >= 3:
        return False
    return True


def cb_ops_substance_hits(article: dict[str, Any]) -> set[str]:
    """Unique real-ops CB substance keywords (EPC/공급망/복합단지/건설/M&A …)."""
    title = (article.get("title") or "").strip()
    body = plain_text(article)[:5000]
    return set(_keyword_hits(f"{title} {body}", CB_OPS_SUBSTANCE))


def cb_ops_substance_boost(article: dict[str, Any]) -> float:
    """Local CB score lift for substantive EPC/infra/M&A copy (not soft ESG fluff)."""
    n = len(cb_ops_substance_hits(article))
    if n < CB_OPS_SUBSTANCE_MIN:
        return 0.0
    return CB_OPS_LOCAL_PER_HIT * float(min(n, CB_OPS_LOCAL_HIT_CAP))


def _is_blocked_image(url: str) -> bool:
    if not url:
        return True
    lowered = url.lower()
    return any(x in lowered for x in BLOCKED_IMAGE_PATTERNS)


def _keyword_hits(text: str, keywords: tuple[str, ...]) -> list[str]:
    hits = []
    for kw in keywords:
        if kw.lower() in text.lower() or kw in text:
            hits.append(kw)
    return hits


def _recover_image(article: dict[str, Any]) -> str:
    image = (article.get("image") or "").strip()
    if not _is_blocked_image(image):
        return image
    html = article.get("raw_html") or ""
    m = re.search(
        r'https://file\.newswire\.co\.kr/[^"\']+\.(?:jpg|jpeg|png|webp)',
        html,
        re.I,
    )
    if m and not _is_blocked_image(m.group(0)):
        article["image"] = m.group(0)
        return article["image"]
    return image


def available_sites(site_counts: Optional[Counter], cfg: SourceGateConfig) -> list[str]:
    counts = site_counts or Counter()
    out = []
    for site in ("CB", "NN", "IJ"):
        if counts.get(site, 0) < cfg.site_limit(site):
            out.append(site)
    return out


def local_hard_drop(
    article: dict[str, Any],
    *,
    cfg: SourceGateConfig,
    org_counts: Optional[Counter] = None,
    seen_titles: Optional[set[str]] = None,
) -> Optional[GateDecision]:
    title = (article.get("title") or "").strip()
    body = plain_text(article)
    compact_title = re.sub(r"\s+", "", title.lower())

    if len(body) < cfg.min_body_chars:
        return GateDecision("DROP", score=0, reason=f"short_body:{len(body)}", stage="local_drop")

    ratio = korean_ratio(f"{title} {body[:2000]}")
    if ratio < cfg.korean_ratio_threshold:
        return GateDecision("DROP", score=0, reason=f"low_korean_ratio:{ratio:.2f}", stage="local_drop")

    if seen_titles is not None and compact_title in seen_titles:
        return GateDecision("DROP", score=0, reason="duplicate_title", stage="local_drop")
    if title and title in body[: max(len(title) * 3, 200)] and body.count(title) >= 2:
        return GateDecision("DROP", score=0, reason="title_body_duplicate", stage="local_drop")

    org = extract_org_key(title)
    if org and org_counts is not None and org_counts[org] >= cfg.max_per_org_per_run:
        return GateDecision("DROP", score=0, reason=f"org_cap:{org}", stage="local_drop", risk_flags=["ORG_CAP"])

    for pat in PROMO_TITLE_PATTERNS:
        if re.search(pat, title, re.I):
            return GateDecision(
                "DROP",
                score=5,
                reason=f"promo_title:{pat}",
                stage="local_drop",
                risk_flags=["PR_TONE", "PROMO"],
            )

    # Cohort / career enrollment PR (D-Bridge 교육생 모집 등) — hard DROP
    if is_recruit_promo(article):
        return GateDecision(
            "DROP",
            score=8,
            reason="recruit_promo",
            stage="local_drop",
            risk_flags=["PR_TONE", "RECRUIT_PROMO"],
        )

    # Soft CB partner/product PR (BitGo·Elliptic) without EPC/supply/M&A substance
    if is_soft_cb_promo(article):
        return GateDecision(
            "DROP",
            score=12,
            reason="soft_cb_promo",
            stage="local_drop",
            risk_flags=["PR_TONE", "SOFT_CB_PROMO"],
        )

    boiler_hits = sum(1 for m in BOILERPLATE_MARKERS if m in body)
    if boiler_hits >= 3 and len(body) < 1500:
        return GateDecision(
            "DROP",
            score=10,
            reason=f"boilerplate_heavy:{boiler_hits}",
            stage="local_drop",
            risk_flags=["PR_TONE"],
        )

    # Award frame: default DROP. Strong CB-only exception; never IJ later.
    if is_award_title(title):
        cb_hits = _keyword_hits(body, CB_STRONG)
        article["_award_frame"] = True
        if len(cb_hits) < 3:
            return GateDecision(
                "DROP",
                score=15,
                reason="award_frame",
                stage="local_drop",
                risk_flags=["AWARD_ONLY", "PR_TONE"],
            )
        article["_award_cb_exception"] = True

    image = _recover_image(article)
    if _is_blocked_image(image):
        cb_hits = len(_keyword_hits(body, CB_BOOST))
        if cfg.soft_image_for_cb and cb_hits >= 2:
            article["_no_image_soft"] = True
            article.setdefault("_pending_risk_flags", [])
            if "NO_IMAGE" not in article["_pending_risk_flags"]:
                article["_pending_risk_flags"].append("NO_IMAGE")
        else:
            return GateDecision(
                "DROP",
                score=0,
                reason="no_usable_image",
                stage="local_drop",
                risk_flags=["NO_IMAGE"],
            )

    return None


def compute_local_scores(article: dict[str, Any]) -> dict[str, float]:
    title = article.get("title") or ""
    body = plain_text(article)[:5000]
    text = f"{title} {body}"
    ij = 20.0 + 12.0 * len(_keyword_hits(text, IJ_BOOST))
    nn = 20.0 + 12.0 * len(_keyword_hits(text, NN_BOOST))
    cb = 25.0 + 12.0 * len(_keyword_hits(text, CB_BOOST))
    # EPC/공급망/복합단지/건설 등 실무 substance — mid soft-ESG CB_BOOST fluff보다 올리기
    cb += cb_ops_substance_boost(article)
    pr = 8.0 * len(_keyword_hits(text, PR_PENALTY))
    scores = {
        "IJ": max(0.0, ij - pr * 1.2),
        "NN": max(0.0, nn - pr),
        "CB": max(0.0, cb - pr * 0.7),
        "pr_penalty": pr,
    }
    # Award frame cannot route to IJ locally
    if article.get("_award_frame") or is_award_title(title):
        scores["IJ"] = 0.0
    return scores


def best_local_route(scores: dict[str, float], allowed: Optional[list[str]] = None) -> tuple[str, float]:
    pool = allowed or ["CB", "NN", "IJ"]
    if not pool:
        return "CB", 0.0
    best_site = max(pool, key=lambda s: scores.get(s, 0.0))
    if "CB" in pool and scores.get("CB", 0) >= scores.get(best_site, 0) - 2:
        best_site = "CB"
    if best_site == "NN" and "NN" in pool:
        rivals = [scores.get(s, 0) for s in pool if s != "NN"]
        if rivals and scores.get("NN", 0) < max(rivals) + 5:
            best_site = max((s for s in pool if s != "NN"), key=lambda s: scores.get(s, 0.0))
    if best_site == "IJ" and scores.get("IJ", 0) < 70:
        alts = [s for s in pool if s != "IJ"]
        if alts:
            alt = max(alts, key=lambda s: scores.get(s, 0.0))
            if scores.get(alt, 0) >= 40:
                best_site = alt
    return best_site, float(scores.get(best_site, 0.0))


def _strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def parse_llm_gate_json(text: str) -> GateDecision:
    raw = _strip_fences(text)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            raise
        data = json.loads(m.group(0))

    decision = str(data.get("decision") or "").strip().upper()
    site = data.get("site")
    site = str(site).strip().upper() if site not in (None, "", "null") else None
    score = float(data.get("score") or 0)
    reason = str(data.get("reason") or "").strip()
    rewrite_angle = data.get("rewrite_angle")
    if rewrite_angle in ("", "null"):
        rewrite_angle = None
    risk_flags = [str(x) for x in (data.get("risk_flags") or [])]
    must_avoid = [str(x) for x in (data.get("must_avoid") or [])]

    if decision not in ("ROUTE", "DROP"):
        raise ValueError(f"invalid decision: {decision}")
    if decision == "ROUTE":
        if site not in ("IJ", "NN", "CB"):
            raise ValueError(f"invalid site for ROUTE: {site}")
    else:
        site = None

    return GateDecision(
        decision=decision,
        site=site,
        score=score,
        reason=reason or ("llm_route" if decision == "ROUTE" else "llm_drop"),
        rewrite_angle=str(rewrite_angle) if rewrite_angle else None,
        risk_flags=risk_flags,
        must_avoid=must_avoid,
        stage="llm",
    )


def revalidate_route_decision(
    article: dict[str, Any],
    decision: GateDecision,
    scores: dict[str, float],
    *,
    allowed: Optional[list[str]] = None,
) -> GateDecision:
    """Local post-check so LLM cannot bypass award/IJ strictness."""
    if decision.decision != "ROUTE" or not decision.site:
        return decision

    title = article.get("title") or ""
    flags = list(decision.risk_flags)
    pending = list(article.get("_pending_risk_flags") or [])
    for f in pending:
        if f not in flags:
            flags.append(f)

    # Award frame: never IJ; prefer DROP unless CB still allowed and strong
    if article.get("_award_frame") or is_award_title(title):
        if decision.site == "IJ" or decision.site == "NN":
            if allowed and "CB" in allowed and scores.get("CB", 0) >= 40:
                decision = GateDecision(
                    "ROUTE",
                    site="CB",
                    score=decision.score,
                    reason=f"award_reclass_cb:{decision.reason}",
                    rewrite_angle=decision.rewrite_angle,
                    risk_flags=flags + ["AWARD_ONLY", "PR_TONE"],
                    must_avoid=decision.must_avoid,
                    stage=decision.stage,
                    scores=scores,
                )
            else:
                return GateDecision(
                    "DROP",
                    score=decision.score,
                    reason="award_ij_blocked",
                    stage="local_drop" if decision.stage != "llm" else "llm",
                    risk_flags=flags + ["AWARD_ONLY", "PR_TONE"],
                    scores=scores,
                )

    if decision.site == "IJ":
        # IJ strict: local IJ score must be strong and not award-framed.
        # Exception: IJ clearly dominates CB (fidelity margin) — keep IJ even
        # if absolute score is a bit under 60 (e.g. 밀리언드림즈 IJ~58 vs CB~31).
        ij_score = float(scores.get("IJ", 0.0) or 0.0)
        cb_score = float(scores.get("CB", 0.0) or 0.0)
        ij_dominates_cb = ij_score - cb_score >= IJ_CB_FIDELITY_MARGIN
        if (ij_score < 60 and not ij_dominates_cb) or article.get("_award_frame"):
            if allowed and "CB" in allowed and scores.get("CB", 0) >= scores.get("NN", 0):
                decision.site = "CB"
                decision.reason = f"ij_reclass_cb:{decision.reason}"
                flags = flags + ["IJ_DOWNGRADE"]
            elif allowed and "NN" in allowed and scores.get("NN", 0) >= 50:
                decision.site = "NN"
                decision.reason = f"ij_reclass_nn:{decision.reason}"
                flags = flags + ["IJ_DOWNGRADE"]
            else:
                return GateDecision(
                    "DROP",
                    score=decision.score,
                    reason="ij_strict_reject",
                    stage="local_drop" if decision.stage != "llm" else "llm",
                    risk_flags=flags + ["IJ_STRICT"],
                    scores=scores,
                )

    # Weak NN lifestyle promo must not survive as NN ROUTE (LLM or local)
    if decision.site == "NN" and is_weak_nn_promo(article):
        return GateDecision(
            "DROP",
            score=decision.score,
            reason="weak_nn_promo",
            stage="local_drop" if decision.stage != "llm" else "llm",
            risk_flags=flags + ["PR_TONE", "WEAK_NN_PROMO"],
            scores=scores,
        )

    # Cohort recruit PR must not survive as any ROUTE (LLM bypass safety)
    if is_recruit_promo(article):
        return GateDecision(
            "DROP",
            score=decision.score,
            reason="recruit_promo",
            stage="local_drop" if decision.stage != "llm" else "llm",
            risk_flags=flags + ["PR_TONE", "RECRUIT_PROMO"],
            scores=scores,
        )

    # Soft CB partner/product/ETF-fund PR must not survive as any ROUTE (LLM bypass).
    # Especially blocks Defiance-class ETF 출시 rationalized as CB tech/infra narrative.
    if is_soft_cb_promo(article):
        return GateDecision(
            "DROP",
            score=decision.score,
            reason="soft_cb_promo",
            stage="local_drop" if decision.stage != "llm" else "llm",
            risk_flags=flags + ["PR_TONE", "SOFT_CB_PROMO"],
            scores=scores,
        )

    # IJ ≫ CB fidelity: local IJ clearly dominates → do not ship as CB
    if decision.site == "CB":
        ij_score = float(scores.get("IJ", 0.0) or 0.0)
        cb_score = float(scores.get("CB", 0.0) or 0.0)
        if ij_score - cb_score >= IJ_CB_FIDELITY_MARGIN and not article.get("_award_frame"):
            ij_allowed = allowed is None or "IJ" in allowed
            if ij_allowed:
                decision.site = "IJ"
                decision.reason = f"ij_fidelity_from_cb:{decision.reason}"
                flags = flags + ["IJ_FIDELITY"]
                decision.must_avoid = [
                    x for x in (decision.must_avoid or []) if str(x).strip().upper() != "IJ"
                ]
            else:
                return GateDecision(
                    "DROP",
                    score=decision.score,
                    reason="ij_fidelity_cb_blocked",
                    stage="local_drop" if decision.stage != "llm" else "llm",
                    risk_flags=flags + ["IJ_FIDELITY"],
                    scores=scores,
                )

    if allowed is not None and decision.site not in allowed:
        return GateDecision(
            "DROP",
            score=decision.score,
            reason=f"site_cap:{decision.site}",
            stage="local_drop",
            risk_flags=flags,
            scores=scores,
        )

    decision.risk_flags = flags
    decision.scores = scores
    return decision


def build_llm_user_message(
    article: dict[str, Any],
    scores: dict[str, float],
    cfg: SourceGateConfig,
    *,
    allowed: Optional[list[str]] = None,
) -> str:
    title = (article.get("title") or "").strip()
    body = plain_text(article)[: cfg.input_max_chars]
    url = (article.get("url") or "").strip()
    allowed_txt = ",".join(allowed) if allowed else "IJ,NN,CB"
    notes = []
    if article.get("_award_frame"):
        notes.append("수상/표창 프레임: IJ 금지, 원칙 DROP 또는 CB만")
    if article.get("_no_image_soft"):
        notes.append("이미지 미확보(CB soft): 실무성 없으면 DROP")
    return "\n".join(
        [
            "후보 원문 (뉴스와이어)",
            f"제목: {title}",
            f"URL: {url}",
            f"허용 site: {allowed_txt}",
            f"로컬점수: IJ={scores.get('IJ', 0):.1f} NN={scores.get('NN', 0):.1f} "
            f"CB={scores.get('CB', 0):.1f} PR감점={scores.get('pr_penalty', 0):.1f}",
            f"주의: {'; '.join(notes) if notes else '없음'}",
            "본문:",
            body,
            "",
            "JSON 스키마:",
            '{"decision":"ROUTE|DROP","site":"IJ|NN|CB|null","score":0,'
            '"reason":"...","rewrite_angle":"...|null","risk_flags":[],"must_avoid":[]}',
        ]
    )


def should_llm_fallback_local(
    article: dict[str, Any],
    scores: dict[str, float],
    *,
    cfg: SourceGateConfig,
    allowed: Optional[list[str]] = None,
) -> Optional[tuple[str, float]]:
    """If LLM JSON is empty/invalid, optionally ROUTE from strong local scores.

    Fail-closed when local is weak. Prefer public NN/IJ or ops-strong CB; use a
    slightly higher floor (``LLM_FALLBACK_LOCAL_MIN``) for generic mid-band.
    Soft/recruit/weak-NN promo never fallback-route (revalidate would DROP anyway).
    """
    site, score = best_local_route(scores, allowed=allowed or ["CB", "NN", "IJ"])
    if is_recruit_promo(article) or is_soft_cb_promo(article):
        return None
    if site == "NN" and is_weak_nn_promo(article):
        return None

    strong_public = site in ("NN", "IJ") and is_public_policy_signal(article)
    strong_cb = site == "CB" and len(cb_ops_substance_hits(article)) >= CB_OPS_SUBSTANCE_MIN
    threshold = float(cfg.auto_drop_below)
    if not (strong_public or strong_cb):
        threshold = max(threshold, LLM_FALLBACK_LOCAL_MIN)
    if score < threshold:
        return None
    return site, score


def call_openrouter_gate(
    article: dict[str, Any],
    scores: dict[str, float],
    cfg: SourceGateConfig,
    *,
    http_post: Optional[Callable[..., Any]] = None,
    allowed: Optional[list[str]] = None,
) -> GateDecision:
    if not cfg.openrouter_api_key:
        return GateDecision(
            "DROP",
            score=0,
            reason="missing_openrouter_api_key",
            stage="local_drop",
            risk_flags=["CONFIG"],
            scores=scores,
        )

    post = http_post or requests.post
    url = f"{cfg.openrouter_api_base}/chat/completions"
    payload = {
        "model": cfg.model,
        "messages": [
            {"role": "system", "content": SOURCE_GATE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_llm_user_message(article, scores, cfg, allowed=allowed),
            },
        ],
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_output_tokens,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {cfg.openrouter_api_key}",
        "Content-Type": "application/json",
        "User-Agent": "erum-news-engine-source-gate/1.0",
    }

    last_err = ""
    for _attempt in range(cfg.llm_retry + 1):
        try:
            resp = post(url, headers=headers, json=payload, timeout=90)
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                raise ValueError("empty choices")
            content = ((choices[0].get("message") or {}).get("content")) or ""
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part) for part in content
                )
            decision = parse_llm_gate_json(str(content))
            decision.scores = scores
            decision.stage = "llm"
            return decision
        except Exception as exc:  # noqa: BLE001 — gate must fail closed when local is also weak
            last_err = str(exc)
            continue

    fallback = should_llm_fallback_local(article, scores, cfg=cfg, allowed=allowed)
    if fallback:
        site, score = fallback
        return GateDecision(
            "ROUTE",
            site=site,
            score=score,
            reason=f"llm_fallback_local:{site}",
            stage="llm_fallback",
            risk_flags=["LLM_FAIL", "LOCAL_FALLBACK"],
            scores=scores,
        )

    return GateDecision(
        "DROP",
        score=0,
        reason=f"llm_parse_or_call_fail:{last_err[:120]}",
        stage="parse_fail",
        risk_flags=["LLM_FAIL"],
        scores=scores,
    )


def decide_article(
    article: dict[str, Any],
    *,
    cfg: Optional[SourceGateConfig] = None,
    stats: Optional[SourceGateStats] = None,
    org_counts: Optional[Counter] = None,
    seen_titles: Optional[set[str]] = None,
    site_counts: Optional[Counter] = None,
    llm_enabled: bool = True,
    http_post: Optional[Callable[..., Any]] = None,
    record: bool = True,
    enforce_site_cap: bool = True,
) -> GateDecision:
    """Qualify one article.

    When ``enforce_site_cap=False`` (ranked fill phase-1), preferred-site
    caps are ignored so all viable ROUTEs can compete by score.
    """
    cfg = cfg or SourceGateConfig.from_env()

    def _commit(decision: GateDecision) -> GateDecision:
        if stats and record:
            stats.record_decision(decision)
        return decision

    hard = local_hard_drop(article, cfg=cfg, org_counts=org_counts, seen_titles=seen_titles)
    if hard:
        return _commit(hard)

    scores = compute_local_scores(article)
    allowed = available_sites(site_counts, cfg) if enforce_site_cap else ["CB", "NN", "IJ"]
    if enforce_site_cap and not allowed:
        decision = GateDecision(
            "DROP",
            score=0,
            reason="site_cap:all",
            stage="local_drop",
            scores=scores,
        )
        if stats:
            stats.llm_skipped_site_cap += 1
        return _commit(decision)

    # Threshold / preferred-site cap use ALL media scores — never disguise
    # a capped preferred site as below_threshold via weak allowed fallback.
    overall_site, overall_score = best_local_route(scores, allowed=["CB", "NN", "IJ"])

    if overall_score < cfg.auto_drop_below:
        decision = GateDecision(
            "DROP",
            score=overall_score,
            reason=f"local_below_threshold:{overall_site}:{overall_score:.1f}",
            stage="local_drop",
            scores=scores,
            risk_flags=["LOW_SCORE"] + (["PR_TONE"] if scores.get("pr_penalty", 0) >= 16 else []),
        )
        return _commit(decision)

    if enforce_site_cap and overall_site not in allowed:
        decision = GateDecision(
            "DROP",
            score=overall_score,
            reason=f"site_cap:{overall_site}",
            stage="local_drop",
            scores=scores,
        )
        if stats:
            stats.llm_skipped_site_cap += 1
        return _commit(decision)

    best_site, best_score = best_local_route(scores, allowed=allowed)

    if best_score >= cfg.auto_route_above:
        if best_site == "IJ" and best_score < cfg.auto_route_above + 5:
            pass  # fall through to LLM
        elif best_site == "NN" and is_weak_nn_promo(article):
            # Weak lifestyle/program promo must not auto-route or steal NN slots.
            # Hard DROP when it would have auto-routed (no CB/IJ public path).
            decision = GateDecision(
                "DROP",
                score=best_score,
                reason="weak_nn_promo",
                stage="local_drop",
                scores=scores,
                risk_flags=["PR_TONE", "WEAK_NN_PROMO"],
            )
            return _commit(decision)
        elif best_site == "CB" and is_soft_cb_promo(article):
            # Soft partner/product CB must not auto-route or steal scarce CB slots.
            decision = GateDecision(
                "DROP",
                score=best_score,
                reason="soft_cb_promo",
                stage="local_drop",
                scores=scores,
                risk_flags=["PR_TONE", "SOFT_CB_PROMO"],
            )
            return _commit(decision)
        else:
            decision = GateDecision(
                "ROUTE",
                site=best_site,
                score=best_score,
                reason=f"local_auto_route:{best_site}",
                stage="local_route",
                scores=scores,
                risk_flags=["PR_TONE"] if scores.get("pr_penalty", 0) >= 8 else [],
            )
            decision = revalidate_route_decision(article, decision, scores, allowed=allowed)
            return _commit(decision)

    # Ambiguous band -> LLM (preferred site still has a slot)
    if not llm_enabled or not (cfg.llm_min_score <= best_score <= cfg.llm_max_score):
        if best_score < cfg.auto_route_above:
            # Lifestyle-only NN with LLM off / out of band stays DROP
            if best_site == "NN" and is_weak_nn_promo(article):
                decision = GateDecision(
                    "DROP",
                    score=best_score,
                    reason="weak_nn_promo",
                    stage="local_drop",
                    scores=scores,
                    risk_flags=["PR_TONE", "WEAK_NN_PROMO"],
                )
                return _commit(decision)
            if best_site == "CB" and is_soft_cb_promo(article):
                decision = GateDecision(
                    "DROP",
                    score=best_score,
                    reason="soft_cb_promo",
                    stage="local_drop",
                    scores=scores,
                    risk_flags=["PR_TONE", "SOFT_CB_PROMO"],
                )
                return _commit(decision)
            decision = GateDecision(
                "DROP",
                score=best_score,
                reason=f"ambiguous_no_llm:{best_site}:{best_score:.1f}",
                stage="local_drop",
                scores=scores,
            )
            return _commit(decision)

    if stats is not None:
        stats.llm_calls += 1
    decision = call_openrouter_gate(
        article, scores, cfg, http_post=http_post, allowed=allowed
    )
    decision = revalidate_route_decision(article, decision, scores, allowed=allowed)
    return _commit(decision)


def apply_gate_to_article(article: dict[str, Any], decision: GateDecision) -> dict[str, Any]:
    out = dict(article)
    out["source_type"] = out.get("source_type") or "newswire"
    out["_source_gate"] = decision.to_dict()
    if decision.decision == "ROUTE" and decision.site in ("IJ", "NN", "CB"):
        out["_source_gate_site"] = decision.site
        out["_source_gate_reason"] = decision.reason
        if decision.rewrite_angle:
            out["_source_gate_rewrite_angle"] = decision.rewrite_angle
        if decision.must_avoid:
            out["_source_gate_must_avoid"] = list(decision.must_avoid)
        if out.get("_no_image_soft"):
            out["_source_gate_needs_image"] = True
    return out


def ranking_score(article: dict[str, Any], decision: GateDecision) -> float:
    """Higher is better. Fill per-run / per-site caps by quality, not arrival order."""
    scores = decision.scores or compute_local_scores(article)
    base = float(decision.score or 0.0)
    site = decision.site or ""
    site_local = float(scores.get(site, 0.0)) if site else 0.0
    bonus = {"CB": 8.0, "NN": 0.0, "IJ": -3.0}.get(site, 0.0)
    if site == "NN" and is_weak_nn_promo(article):
        bonus -= 45.0
    if is_recruit_promo(article):
        bonus -= 50.0
    if site == "CB" and is_soft_cb_promo(article):
        bonus -= 40.0
    if site == "CB":
        ops_n = len(cb_ops_substance_hits(article))
        if ops_n >= 3:
            bonus += CB_OPS_RANK_BONUS_MIN3
        elif ops_n >= CB_OPS_SUBSTANCE_MIN:
            bonus += CB_OPS_RANK_BONUS_MIN2
    if site in ("NN", "IJ") and is_public_policy_signal(article):
        bonus += 18.0
    if article.get("_award_frame"):
        bonus -= 15.0
    if article.get("_no_image_soft"):
        bonus -= 3.0
    return base + site_local * 0.25 + bonus


def screen_newswire_candidates(
    candidates: list[dict[str, Any]],
    *,
    cfg: Optional[SourceGateConfig] = None,
    llm_enabled: bool = True,
    http_post: Optional[Callable[..., Any]] = None,
    daily_published: int = 0,
    daily_limit: int = 50,
) -> tuple[list[dict[str, Any]], SourceGateStats, list[dict[str, Any]]]:
    """Screen candidates; return (selected_articles, stats, all_decisions).

    Two-phase fill:
    1) Qualify every candidate without per-site caps
    2) Rank ROUTE results and fill run/site/org caps in rank order
    """
    cfg = cfg or SourceGateConfig.from_env()
    stats = SourceGateStats(input_candidates=len(candidates))
    selected: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    max_by_share = cfg.max_selected_per_run
    if daily_limit > 0 and cfg.max_daily_share_pct >= 0:
        allowed_total = int(daily_limit * (cfg.max_daily_share_pct / 100.0))
        remaining_share = max(0, allowed_total)
        remaining_budget = max(0, daily_limit - daily_published)
        max_by_share = min(
            cfg.max_selected_per_run,
            remaining_share,
            remaining_budget or cfg.max_selected_per_run,
        )

    provisional: list[tuple[float, dict[str, Any], GateDecision]] = []

    # Phase 1 — qualify (no site/org cap enforcement; those apply in rank fill)
    for article in candidates:
        decision = decide_article(
            article,
            cfg=cfg,
            stats=stats,
            org_counts=None,
            seen_titles=seen_titles,
            site_counts=None,
            llm_enabled=llm_enabled,
            http_post=http_post,
            record=False,
            enforce_site_cap=False,
        )
        title_key = re.sub(r"\s+", "", (article.get("title") or "").lower())
        if title_key:
            seen_titles.add(title_key)

        if decision.decision == "ROUTE" and decision.site:
            provisional.append((ranking_score(article, decision), article, decision))
            continue

        stats.record_decision(decision)
        decisions.append(
            {
                "title": article.get("title", ""),
                "url": article.get("url", ""),
                **decision.to_dict(),
            }
        )

    # Phase 2 — rank fill
    provisional.sort(key=lambda row: (-row[0], -(row[2].score or 0)))
    site_counts: Counter = Counter()
    org_counts: Counter = Counter()

    for rank_score, article, decision in provisional:
        site = decision.site or ""
        org = extract_org_key(article.get("title") or "")
        over_run = len(selected) >= max_by_share
        over_site = bool(site) and site_counts[site] >= cfg.site_limit(site)
        over_org = bool(org) and org_counts[org] >= cfg.max_per_org_per_run
        if over_run or over_site or over_org:
            if over_run:
                reason = "site_cap:run"
            elif over_site:
                reason = f"site_cap:{site}"
            else:
                reason = f"org_cap:{org}"
            capped = GateDecision(
                "DROP",
                score=decision.score,
                reason=f"{reason}:rank",
                stage="local_drop",
                scores=decision.scores,
                risk_flags=list(decision.risk_flags) + ["RANK_CAP"],
            )
            stats.record_decision(capped)
            if over_run or over_site:
                stats.llm_skipped_site_cap += 1
            decisions.append(
                {
                    "title": article.get("title", ""),
                    "url": article.get("url", ""),
                    "rank_score": rank_score,
                    **capped.to_dict(),
                }
            )
            continue

        if org:
            org_counts[org] += 1
        site_counts[site] += 1
        stats.record_decision(decision)
        selected.append(apply_gate_to_article(article, decision))
        decisions.append(
            {
                "title": article.get("title", ""),
                "url": article.get("url", ""),
                "rank_score": rank_score,
                **decision.to_dict(),
            }
        )

    stats.final_selected = len(selected)
    stats.site_counts = Counter(a.get("_source_gate_site") for a in selected if a.get("_source_gate_site"))
    return selected, stats, decisions


def is_newswire_article(article: dict[str, Any]) -> bool:
    if (article.get("source_type") or "").lower() == "newswire":
        return True
    url = (article.get("url") or "") + " " + (article.get("feed_url") or "")
    return "newswire" in url.lower()
