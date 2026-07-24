"""Canonical IJ/NN/CB reporter roster — single source of truth for Engine.

Frontends/portal keep parallel copies; parity tests must stay in sync.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Desk Organization labels — fail-closed fallback only when mapping is impossible.
DESK_BY_SITE = {
    "IJ": "임팩트저널 편집국",
    "NN": "이웃뉴스 편집국",
    "CB": "CSR브리핑 편집국",
}

AUTHOR_SLUG_BY_SITE_CAT: dict[str, dict[str, tuple[str, str]]] = {
    "IJ": {
        "politics": ("오지현", "oh-jihyun"),
        "economy": ("이성민", "lee-sungmin"),
        "society": ("윤성민", "yun-sungmin"),
        "it-science": ("장예린", "jang-yerin"),
        "culture-life": ("한재원", "han-jaewon"),
        "international": ("서민준", "seo-minjun"),
        "environment": ("나혜진", "na-hyejin"),
    },
    "NN": {
        "politics": ("최지훈", "choi-jihun"),
        "economy": ("윤재원", "yun-jaewon"),
        "society": ("박서연", "park-seoyeon"),
        "it-science": ("임태양", "im-taeyang"),
        "culture-life": ("강미래", "kang-mirae"),
        "international": ("송현아", "song-hyuna"),
        "environment": ("김도현", "kim-dohyun"),
    },
    "CB": {
        "politics": ("김민서", "kim-minseo"),
        "economy": ("이준혁", "lee-junhyuk"),
        "society": ("박지은", "park-jieun"),
        "it-science": ("최현우", "choi-hyunwoo"),
        "culture-life": ("정수빈", "jeong-subin"),
        "international": ("한다영", "han-dayoung"),
        "environment": ("오태준", "oh-taejun"),
    },
}

CATEGORIES = (
    "politics",
    "economy",
    "society",
    "it-science",
    "culture-life",
    "international",
    "environment",
)

# Korean display names / aliases → canonical slug (rewrite path uses Korean cats).
CATEGORY_SLUG_ALIASES: dict[str, str] = {
    "politics": "politics",
    "정치": "politics",
    "economy": "economy",
    "경제": "economy",
    "society": "society",
    "사회": "society",
    "it-science": "it-science",
    "it/과학": "it-science",
    "it과학": "it-science",
    "IT/과학": "it-science",
    "culture-life": "culture-life",
    "문화/생활": "culture-life",
    "문화생활": "culture-life",
    "international": "international",
    "국제": "international",
    "environment": "environment",
    "환경": "environment",
}


def normalize_category_slug(category: str | None) -> Optional[str]:
    raw = (category or "").strip()
    if not raw:
        return None
    if raw in CATEGORY_SLUG_ALIASES:
        return CATEGORY_SLUG_ALIASES[raw]
    key = raw.lower().replace(" ", "")
    return CATEGORY_SLUG_ALIASES.get(key) or CATEGORY_SLUG_ALIASES.get(raw)


@dataclass(frozen=True)
class ResolvedAuthor:
    name: str
    slug: Optional[str]
    author_type: str  # "Person" | "Organization"
    site: str
    category: Optional[str]
    mapped: bool

    @property
    def is_person(self) -> bool:
        return self.author_type == "Person"


def is_desk_name(name: Optional[str]) -> bool:
    if not name:
        return True
    return "편집국" in name.replace(" ", "")


def name_to_slug_for_site(site: str, name: str) -> Optional[str]:
    """Exact site+name → slug. No global name-only mapping."""
    table = AUTHOR_SLUG_BY_SITE_CAT.get(site, {})
    target = (name or "").strip()
    for _cat, (n, slug) in table.items():
        if n == target:
            return slug
    return None


def resolve_author_for_site(site: str, category_slug: str | None) -> tuple[Optional[str], Optional[str]]:
    """Back-compat: (name, slug) for known category; (None, None) if unmapped."""
    resolved = resolve_author(site, category_slug)
    if resolved.mapped and resolved.is_person:
        return resolved.name, resolved.slug
    return None, None


def resolve_author(site: str, category_slug: str | None, *, allow_desk_fallback: bool = True) -> ResolvedAuthor:
    """
    Resolve personal byline for site+category.

    Normal path: Person with name+slug together.
    Unknown/missing category: Organization desk only when allow_desk_fallback=True
    (fail-closed). Never invent reporters; never return personal name without slug.
    """
    site_key = (site or "").strip().upper()
    cat = normalize_category_slug(category_slug)
    table = AUTHOR_SLUG_BY_SITE_CAT.get(site_key, {})
    if cat and cat in table:
        name, slug = table[cat]
        return ResolvedAuthor(
            name=name,
            slug=slug,
            author_type="Person",
            site=site_key,
            category=cat,
            mapped=True,
        )
    desk = DESK_BY_SITE.get(site_key, "편집국")
    if allow_desk_fallback:
        return ResolvedAuthor(
            name=desk,
            slug=None,
            author_type="Organization",
            site=site_key,
            category=cat,
            mapped=False,
        )
    return ResolvedAuthor(
        name=desk,
        slug=None,
        author_type="Organization",
        site=site_key,
        category=cat,
        mapped=False,
    )


def assert_person_name_slug_pair(name: Optional[str], slug: Optional[str]) -> bool:
    """Personal bylines must carry name and slug together."""
    if is_desk_name(name):
        return slug is None or slug == ""
    return bool(name and slug)


def all_roster_entries() -> list[tuple[str, str, str, str]]:
    """(site, category, name, slug) for parity tests."""
    rows: list[tuple[str, str, str, str]] = []
    for site, cats in AUTHOR_SLUG_BY_SITE_CAT.items():
        for cat, (name, slug) in cats.items():
            rows.append((site, cat, name, slug))
    return rows
