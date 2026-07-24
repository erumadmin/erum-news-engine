"""1원문=1매체 routing heuristics (LLM-free)."""
from __future__ import annotations

import re
from typing import Optional

IJ_CUES = ["법률", "개정", "국회", "제도", "조례", "시행령", "정책", "고용보험", "복지부", "기재부"]
NN_CUES = ["가구", "시민", "노동자", "이용자", "수급", "바우처", "지원금", "부담", "생활비", "가정"]
CB_CUES = ["ESG", "CSR", "공시", "공급망", "상장", "지속가능", "기업", "산업", "규제", "실사"]
DROP_CUES = ["열애설", "연예인", "가십", "광고", "할인쿠폰", "맛집추천"]


def _score(text: str, cues: list[str]) -> int:
    t = text.lower()
    return sum(1 for c in cues if c.lower() in t)


def route_primary(article: dict) -> Optional[str]:
    title = str(article.get("title") or "")
    body = str(article.get("body") or article.get("content") or article.get("summary") or "")
    text = f"{title}\n{body}"
    if _score(text, DROP_CUES) > 0 and _score(text, IJ_CUES + NN_CUES + CB_CUES) == 0:
        return None
    scores = {
        "IJ": _score(text, IJ_CUES),
        "NN": _score(text, NN_CUES),
        "CB": _score(text, CB_CUES),
    }
    best = max(scores.values())
    if best <= 0:
        return None
    winners = [k for k, v in scores.items() if v == best]
    if len(winners) == 1:
        return winners[0]
    # tie-break: statute/policy -> IJ; enterprise/ESG -> CB; household -> NN
    if any(c in text for c in ["법률", "개정", "시행령", "제도"]):
        return "IJ"
    if any(c in text for c in ["ESG", "공시", "공급망", "상장"]):
        return "CB"
    if any(c in text for c in ["가구", "시민", "이용자", "바우처"]):
        return "NN"
    return "IJ"


def build_one_site_media_plan(assigned_site: Optional[str], enable_flags: dict | None = None) -> dict:
    flags = enable_flags or {"IJ": True, "NN": True, "CB": True}
    plan = {f"{s}_": {"enabled": False, "mode": "skip", "reason": "not-assigned"} for s in ("IJ", "NN", "CB")}
    if not assigned_site:
        return plan
    if not flags.get(assigned_site, True):
        plan[f"{assigned_site}_"] = {"enabled": False, "mode": "skip", "reason": "feature-flag-off"}
        return plan
    plan[f"{assigned_site}_"] = {"enabled": True, "mode": "primary", "reason": "one-source-one-site"}
    return plan


_METRIC_PAT = re.compile(r"(매출|영업이익|시가총액|주가)\s*\d")


def assert_no_ungrounded_metrics(text: str) -> bool:
    return _METRIC_PAT.search(text or "") is None


def assert_no_lifestyle_howto(text: str) -> bool:
    bad = ["이용 방법은", "신청 꿀팁", "쉽게 따라하기", "생활팁"]
    return not any(b in (text or "") for b in bad)


def assert_no_fake_field_reporting(text: str) -> bool:
    bad = ["현장에서 확인한 결과", "직접 취재한 결과", "취재진이 만난"]
    return not any(b in (text or "") for b in bad)
