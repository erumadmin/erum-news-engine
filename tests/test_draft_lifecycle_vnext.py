from erum_pipeline.draft_lifecycle import resolve_author_for_site, normalize_source_id
from erum_pipeline.publish_contract import build_article_payload


def test_build_payload_wires_vnext_fields():
    payload = build_article_payload(
        site_code="IJ",
        title="제목",
        body="<p>본문</p>",
        cat_id=1,
        status="DRAFT",
        author="오지현",
        author_slug="oh-jihyun",
        image_caption="캡션",
        image_credit="크레딧",
        source_url="https://example.com/src",
        idempotency_key="AUTO:abc",
        engine_commit="deadbeef",
        prompt_version="vnext-1",
        normalized_source_id="abc",
    )
    assert payload["authorSlug"] == "oh-jihyun"
    assert payload["imageCaption"] == "캡션"
    assert payload["imageCredit"] == "크레딧"
    assert payload["sourceUrl"] == "https://example.com/src"
    assert payload["idempotencyKey"] == "AUTO:abc"
    assert payload["engineCommit"] == "deadbeef"
    assert payload["promptVersion"] == "vnext-1"
    assert payload["normalizedSourceId"] == "abc"
    assert payload["status"] == "DRAFT"


def test_author_resolution_and_source_normalize():
    name, slug = resolve_author_for_site("IJ", "politics")
    assert name == "오지현"
    assert slug == "oh-jihyun"
    assert normalize_source_id("  abc  ") == "abc"
