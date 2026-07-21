"""Tests for HTML sanitization in clean_body_html and publish path (stored XSS prevention)."""
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _load_engine_py():
    spec = importlib.util.spec_from_file_location("erum_news_engine_main", REPO_ROOT / "engine.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


eng = _load_engine_py()
clean_body_html = eng.clean_body_html


def test_script_tag_removed():
    output = clean_body_html("<script>alert(1)</script>")
    assert "<script>" not in output.lower()
    assert "alert(1)" not in output


def test_img_onerror_removed():
    output = clean_body_html('<img src="x" onerror="alert(1)">')
    assert "onerror" not in output.lower()


def test_iframe_removed():
    output = clean_body_html("<iframe src=\"evil\"></iframe>")
    assert "<iframe" not in output.lower()


def test_allowed_tags_preserved():
    output = clean_body_html("<p>hello</p><strong>bold</strong>")
    assert "<p>hello</p>" in output
    assert "<strong>bold</strong>" in output


def test_existing_markdown_conversion_still_works():
    bold_output = clean_body_html("**bold**")
    assert "<strong>bold</strong>" in bold_output

    heading_output = clean_body_html("## Heading")
    assert "<h3>Heading</h3>" in heading_output


def test_a_href_preserved():
    output = clean_body_html('<a href="https://example.com">link</a>')
    assert '<a href="https://example.com">' in output


def test_javascript_href_removed():
    output = clean_body_html('<a href="javascript:alert(1)">x</a>')
    assert "javascript:" not in output.lower()


def test_publish_sanitize_body_strips_script():
    from engine.pipeline.publish_validate import publish_sanitize_body

    cleaned, _ = publish_sanitize_body(
        "<p>정부는 제도를 시행한다. <script>alert(1)</script>대상은 국민이다.</p>"
        "<p>그동안 부담 우려가 있었다.</p>"
        "<p>한전 고지서에 표기된다.</p>"
        "<p>다만 조건과 한계를 유의해야 한다.</p>",
        {},
    )
    assert "<script>" not in cleaned.lower()
    assert "alert(1)" not in cleaned
