"""Tests for layout_decision."""

from __future__ import annotations

import unittest

from engine.pipeline.layout_decision import decide_layout_type


class TestLayoutDecision(unittest.TestCase):
    def test_hero_with_download_ok(self):
        probe = {"status": "download_ok", "selected_url": "https://x/img.jpg"}
        self.assertEqual(
            decide_layout_type(probe, placement_slot="hero", publish_grade="A"),
            "hero",
        )

    def test_brief_without_image_on_secondary_lead(self):
        probe = {"status": "no_candidates"}
        self.assertEqual(
            decide_layout_type(probe, placement_slot="secondary_lead", publish_grade="B"),
            "brief",
        )

    def test_list_with_candidates(self):
        probe = {"status": "candidates_ok", "selected_url": "https://x/img.jpg"}
        self.assertEqual(
            decide_layout_type(probe, placement_slot="ledger", publish_grade="C"),
            "list",
        )


if __name__ == "__main__":
    unittest.main()
