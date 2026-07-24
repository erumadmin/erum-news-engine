"""Routing + publish contract unit tests (no LLM)."""
import json
from pathlib import Path

from erum_pipeline.routing_vnext import (
    assert_no_fake_field_reporting,
    assert_no_lifestyle_howto,
    assert_no_ungrounded_metrics,
    build_one_site_media_plan,
    route_primary,
)
from erum_pipeline.publish_contract import build_article_payload, should_record_published_success

FIXTURE = Path(__file__).resolve().parent / "golden" / "routing_golden_v0.json"


def test_golden_routing_matches_expected_sites():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for case in data["cases"]:
        site = route_primary({"title": case["title"], "body": case.get("notes", "")})
        if case["expected_action"] == "DROP":
            assert site is None
        else:
            assert site == case["expected_site"]


def test_one_site_media_plan():
    plan = build_one_site_media_plan("NN")
    assert plan["NN_"]["enabled"] is True
    assert plan["IJ_"]["enabled"] is False
    assert plan["CB_"]["enabled"] is False


def test_publish_payload_includes_vnext_fields():
    payload = build_article_payload(
        site_code="IJ",
        title="t",
        body="<p>b</p>",
        cat_id=1,
        status="DRAFT",
        author="오지현",
        author_slug="oh-jihyun",
        image_caption="캡션",
        source_url="https://example.com/src",
        idempotency_key="AUTO:abc",
    )
    assert payload["authorSlug"] == "oh-jihyun"
    assert payload["idempotencyKey"] == "AUTO:abc"
    assert payload["provenanceChannel"] == "AUTO_NEWS"
    assert should_record_published_success("DRAFT") is False
    assert should_record_published_success("PUBLISHED") is True


def test_quality_gates():
    assert assert_no_ungrounded_metrics("제도 변화를 설명합니다.") is True
    assert assert_no_ungrounded_metrics("매출 123억 돌파") is False
    assert assert_no_lifestyle_howto("시민 부담이 줄었다.") is True
    assert assert_no_lifestyle_howto("이용 방법은 다음과 같다") is False
    assert assert_no_fake_field_reporting("공시 자료를 바탕으로 정리했다.") is True
    assert assert_no_fake_field_reporting("현장에서 확인한 결과") is False
