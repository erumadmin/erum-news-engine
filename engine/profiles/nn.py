from __future__ import annotations

import re
from typing import Any

from engine.profiles.base import SiteProfile, shared_drop_check
from engine.types import CandidateDecision, RouteScore


class NNProfile(SiteProfile):
    name = "NN"

    _NN_SIGNALS = (
        "생활",
        "이용",
        "신청",
        "할인",
        "요금",
        "가구",
        "주민",
        "지역",
        "체감",
        "편의",
    )

    def candidate_filter(self, raw_source: dict[str, Any]) -> CandidateDecision:
        dropped = shared_drop_check(raw_source)
        if dropped:
            return dropped
        return CandidateDecision(True, "nn_candidate_ok")

    def route_score(self, raw_source: dict[str, Any]) -> RouteScore:
        text = f"{raw_source.get('title', '')} {raw_source.get('body', '')}"
        hits = sum(1 for s in self._NN_SIGNALS if s in text)
        score = 30.0 + hits * 10.0
        if raw_source.get("source_type") == "newswire":
            score += 15.0
        return RouteScore("NN", score, f"nn_signals={hits}")
