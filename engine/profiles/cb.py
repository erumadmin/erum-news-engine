from __future__ import annotations

import re
from typing import Any

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
    )

    def candidate_filter(self, raw_source: dict[str, Any]) -> CandidateDecision:
        dropped = shared_drop_check(raw_source)
        if dropped:
            return dropped
        return CandidateDecision(True, "cb_candidate_ok")

    def route_score(self, raw_source: dict[str, Any]) -> RouteScore:
        text = f"{raw_source.get('title', '')} {raw_source.get('body', '')}"
        hits = sum(1 for s in self._CB_SIGNALS if s in text)
        score = 25.0 + hits * 11.0
        if raw_source.get("source_type") == "newswire":
            score += 20.0
        return RouteScore("CB", score, f"cb_signals={hits}")
