from __future__ import annotations

import re
from typing import Any

from engine.profiles.base import SiteProfile, shared_drop_check
from engine.types import CandidateDecision, RouteScore


class IJProfile(SiteProfile):
    name = "IJ"

    _IJ_SIGNALS = (
        "정책",
        "제도",
        "법",
        "규제",
        "의무",
        "시행",
        "공공",
        "국민",
        "소비자",
        "기업",
        "지원",
        "개편",
    )

    def candidate_filter(self, raw_source: dict[str, Any]) -> CandidateDecision:
        dropped = shared_drop_check(raw_source)
        if dropped:
            return dropped
        body = (raw_source.get("body") or "")[:8000]
        korean_chars = len(re.findall(r"[가-힣]", body))
        if korean_chars < 40:
            return CandidateDecision(False, "insufficient_korean_body")
        return CandidateDecision(True, "ij_candidate_ok")

    def route_score(self, raw_source: dict[str, Any]) -> RouteScore:
        text = f"{raw_source.get('title', '')} {raw_source.get('body', '')}"
        hits = sum(1 for s in self._IJ_SIGNALS if s in text)
        source_type = raw_source.get("source_type") or ""
        score = 40.0 + hits * 8.0
        if source_type == "policy_briefing" or "korea.kr" in (raw_source.get("url") or ""):
            score += 18.0  # was +30; leave room for NN/CB desk fit
        reason = f"ij_signals={hits}"
        return RouteScore("IJ", score, reason)

    def collect_evidence_plan(self, raw_source: dict[str, Any]) -> dict[str, Any]:
        return {"assigned_site": "IJ", "max_fetch": 4}

    def placement_config(self) -> dict[str, int]:
        return {"hero": 85, "secondary_lead": 70, "proof_row": 50}
