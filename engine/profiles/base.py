from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

from engine.types import CandidateDecision, PlacementScore, RouteScore, SiteCode

# Shared drop patterns (event notices, awards, weak announcements)
DROP_TITLE_PATTERNS = (
    r"개최\s*안내",
    r"참가자\s*모집",
    r"수상",
    r"MOU\s*체결",
    r"협약\s*체결",
    r"포럼\s*개최",
    r"세미나\s*개최",
    r"박람회\s*개최",
)


class SiteProfile(ABC):
    name: SiteCode

    @abstractmethod
    def candidate_filter(self, raw_source: dict[str, Any]) -> CandidateDecision:
        ...

    @abstractmethod
    def route_score(self, raw_source: dict[str, Any]) -> RouteScore:
        ...

    def collect_evidence_plan(self, raw_source: dict[str, Any]) -> dict[str, Any]:
        """Returns kwargs for research_collector.build_evidence_plan."""
        return {"assigned_site": self.name, "max_fetch": 3}

    def placement_config(self) -> dict[str, int]:
        return {
            "hero": 85,
            "secondary_lead": 70,
            "proof_row": 50,
        }


def shared_drop_check(raw_source: dict[str, Any]) -> CandidateDecision | None:
    title = (raw_source.get("title") or "").strip()
    body = (raw_source.get("body") or raw_source.get("source_body") or "").strip()
    for pat in DROP_TITLE_PATTERNS:
        if re.search(pat, title, re.I):
            return CandidateDecision(False, f"drop_title:{pat}")
    if len(body) < 80 and not re.search(r"(시행|의무|지원|신청|변경)", body):
        return CandidateDecision(False, "thin_announcement")
    return None
