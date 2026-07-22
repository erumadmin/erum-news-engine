"""Rewrite prompt slim-packet + desk-aligned structure."""
from __future__ import annotations

import unittest

from engine.pipeline.packet_writer import (
    EDITORIAL_REWRITE_TEMPLATE,
    slim_packet_for_rewrite,
)


class TestRewritePromptSlim(unittest.TestCase):
    def test_slim_drops_coalition_noise(self):
        packet = {
            "main_claim": "지표 도입",
            "key_facts": ["a", "b", "c", "d", "e", "f", "g"],
            "field_takeaways": {"who": "NGO"},
            "journalist_brief": {"lead_question": "연대?"},
            "reader_utility": {"checklist": [{"step": "확인"}]},
            "risk_flags": [],
        }
        slim = slim_packet_for_rewrite(packet)
        self.assertIn("main_claim", slim)
        self.assertNotIn("field_takeaways", slim)
        self.assertNotIn("journalist_brief", slim)
        self.assertEqual(len(slim["key_facts"]), 6)
        self.assertIn("reader_utility", slim)

    def test_ij_template_puts_mechanism_in_para2(self):
        self.assertIn("2번째 <p>: **해법 작동**", EDITORIAL_REWRITE_TEMPLATE)
        self.assertNotIn("2번째 <p>: 배경·문제", EDITORIAL_REWRITE_TEMPLATE)


if __name__ == "__main__":
    unittest.main()
