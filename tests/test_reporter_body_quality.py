"""Reporter roster + reader-body meta-label hard gates (byline supplement).

Desk-fit remains covered by tests/test_desk_fit.py (Test2 engine.pipeline.desk_fit).
Editorial core remains engine/pipeline/* — these gates are supplements, not substitutes.
"""
from erum_pipeline.body_quality import evaluate_reader_body, find_banned_meta_labels
from erum_pipeline.reporter_roster import (
    AUTHOR_SLUG_BY_SITE_CAT,
    CATEGORIES,
    all_roster_entries,
    assert_person_name_slug_pair,
    normalize_category_slug,
    resolve_author,
)


CANONICAL = {
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


def test_reporter_map_all_sites_categories():
    assert set(AUTHOR_SLUG_BY_SITE_CAT) == {"IJ", "NN", "CB"}
    for site in ("IJ", "NN", "CB"):
        assert set(AUTHOR_SLUG_BY_SITE_CAT[site]) == set(CATEGORIES)
        for cat in CATEGORIES:
            name, slug = AUTHOR_SLUG_BY_SITE_CAT[site][cat]
            assert (name, slug) == CANONICAL[site][cat]
            resolved = resolve_author(site, cat)
            assert resolved.mapped and resolved.is_person
            assert resolved.name == name and resolved.slug == slug
            assert assert_person_name_slug_pair(resolved.name, resolved.slug)


def test_korean_category_aliases_resolve():
    r = resolve_author("IJ", "사회")
    assert r.name == "윤성민" and r.slug == "yun-sungmin"
    assert normalize_category_slug("IT/과학") == "it-science"


def test_no_cross_site_slug_mix():
    ij_slugs = {slug for _, slug in AUTHOR_SLUG_BY_SITE_CAT["IJ"].values()}
    nn_slugs = {slug for _, slug in AUTHOR_SLUG_BY_SITE_CAT["NN"].values()}
    cb_slugs = {slug for _, slug in AUTHOR_SLUG_BY_SITE_CAT["CB"].values()}
    assert ij_slugs.isdisjoint(nn_slugs)
    assert ij_slugs.isdisjoint(cb_slugs)
    assert nn_slugs.isdisjoint(cb_slugs)


def test_unknown_category_fail_closed_desk():
    r = resolve_author("IJ", "unknown-beat")
    assert not r.mapped
    assert r.author_type == "Organization"
    assert r.slug is None
    assert "편집국" in r.name
    assert assert_person_name_slug_pair(r.name, r.slug)


def test_roster_entry_count_21():
    assert len(all_roster_entries()) == 21


def test_meta_label_ban_and_soft_score_cannot_override():
    dirty = "<p>【사실·정부 발표】 정부가 발표했다.</p><p>【매체 해석·IJ】 파급이 크다.</p>"
    assert find_banned_meta_labels(dirty)
    gate = evaluate_reader_body(
        title="제목",
        excerpt="리드",
        body=dirty,
        soft_score=0.99,
    )
    assert gate["publish_ready"] is False
    assert gate["soft_score_overridden"] is True


def test_daman_daman_and_clean_body():
    bad = "<p>다만 다만, 효과가 제한적이다.</p>"
    gate_bad = evaluate_reader_body(title="t", excerpt="e", body=bad)
    assert gate_bad["publish_ready"] is False
    clean = "<p>정부는 시행령을 개정했다. 사업장 의무가 구체화된다.</p>"
    gate_ok = evaluate_reader_body(
        title="시행령 개정",
        excerpt="의무가 구체화된다.",
        body=clean,
        source_text="정부는 시행령을 개정했다. 사업장 의무가 구체화된다.",
    )
    assert gate_ok["publish_ready"] is True
