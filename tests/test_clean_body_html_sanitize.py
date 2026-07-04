"""Tests for HTML sanitization in clean_body_html (stored XSS prevention)."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine import clean_body_html


def test_script_tag_removed():
    output = clean_body_html('<script>alert(1)</script>')
    assert "<script>" not in output.lower()
    assert "alert(1)" not in output


def test_img_onerror_removed():
    output = clean_body_html('<img src="x" onerror="alert(1)">')
    assert "onerror" not in output.lower()


def test_iframe_removed():
    output = clean_body_html('<iframe src="evil"></iframe>')
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
