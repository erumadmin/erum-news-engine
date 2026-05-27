from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

SiteCode = Literal["IJ", "NN", "CB", "DROP"]
PublishGrade = Literal["A", "B", "C", "D"]
PlacementSlot = Literal["hero", "secondary_lead", "proof_row", "ledger"]


@dataclass
class CandidateDecision:
    accept: bool
    reason: str = ""


@dataclass
class RouteScore:
    site: SiteCode
    score: float
    reason: str = ""


@dataclass
class PlacementScore:
    total: int
    social_clarity: int = 0
    headline_strength: int = 0
    summary_strength: int = 0
    image_trust: int = 0
    fact_density: int = 0
    timeliness: int = 0
    slot: PlacementSlot = "ledger"
    hard_failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "social_clarity": self.social_clarity,
            "headline_strength": self.headline_strength,
            "summary_strength": self.summary_strength,
            "image_trust": self.image_trust,
            "fact_density": self.fact_density,
            "timeliness": self.timeliness,
            "slot": self.slot,
            "hard_failures": self.hard_failures,
        }


@dataclass
class EditorialContext:
    """Output of pre-publish pipeline passed into engine.py rewrite/publish."""

    assigned_site: SiteCode
    routing_reason: str
    publish_grade: PublishGrade
    placement: PlacementScore
    packet: dict[str, Any]
    evidence: list[dict[str, Any]]
    use_packet_writing: bool
    raw_source_id: Optional[int] = None
    research_packet_id: Optional[int] = None
