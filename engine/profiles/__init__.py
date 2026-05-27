from __future__ import annotations

from typing import Any

from engine.profiles.base import SiteProfile
from engine.profiles.cb import CBProfile
from engine.profiles.ij import IJProfile
from engine.profiles.nn import NNProfile
from engine.types import RouteScore, SiteCode

_PROFILES: dict[SiteCode, SiteProfile] = {
    "IJ": IJProfile(),
    "NN": NNProfile(),
    "CB": CBProfile(),
}


def get_profile(site: SiteCode) -> SiteProfile:
    if site == "DROP":
        raise ValueError("DROP has no profile")
    return _PROFILES[site]


def route_primary(raw_source: dict[str, Any]) -> RouteScore:
    """1 raw -> 1 site: pick highest route score among profiles that accept candidate."""
    candidates: list[RouteScore] = []
    for site in ("IJ", "NN", "CB"):
        profile = _PROFILES[site]
        decision = profile.candidate_filter(raw_source)
        if not decision.accept:
            continue
        candidates.append(profile.route_score(raw_source))
    if not candidates:
        return RouteScore("DROP", 0.0, "no_profile_accepted")
    best = max(candidates, key=lambda r: r.score)
    if best.score < 35.0:
        return RouteScore("DROP", best.score, f"below_threshold:{best.reason}")
    return best
