from __future__ import annotations

import re
from typing import Any

from engine.pipeline.desk_fit import cb_enterprise_hit_count, cb_is_nonfit
from engine.profiles.base import SiteProfile, shared_drop_check
from engine.types import CandidateDecision, RouteScore


class CBProfile(SiteProfile):
    name = "CB"

    _CB_SIGNALS = (
        "규제",
        "비용",
        "일정",
        "공시",
        "공급",
        "계약",
        "리스크",
        "컴플라이언스",
        "ESG",
        "의무",
        "조달",
        "과태료",
        "사업주",
        "사업장",
    )

    def candidate_filter(self, raw_source: dict[str, Any]) -> CandidateDecision:
        dropped = shared_drop_check(raw_source)
        if dropped:
            return dropped
        nonfit, reason = cb_is_nonfit(raw_source)
        if nonfit:
            return CandidateDecision(False, reason)
        if cb_enterprise_hit_count(raw_source) < 1 and not re.search(
            r"(투자|수요|인력|인프라|업종)",
            f"{raw_source.get('title') or ''} {raw_source.get('body') or ''}",
        ):
            return CandidateDecision(False, "cb_nonfit_weak_signal")
        return CandidateDecision(True, "cb_candidate_ok")

    def route_score(self, raw_source: dict[str, Any]) -> RouteScore:
        text = f"{raw_source.get('title', '')} {raw_source.get('body', '')}"
        hits = sum(1 for s in self._CB_SIGNALS if s in text)
        ent = cb_enterprise_hit_count(raw_source)
        score = 25.0 + hits * 11.0 + ent * 3.0
        if raw_source.get("source_type") == "newswire":
            score += 20.0
        return RouteScore("CB", score, f"cb_signals={hits},ent={ent}")
