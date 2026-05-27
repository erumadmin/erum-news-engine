#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline.qa_input import append_packet_block
from engine.pipeline.publish_meta import build_publish_extras
from engine.types import EditorialContext, PlacementScore


class TestQaEditorial(unittest.TestCase):
    def test_qa_message_includes_packet_block(self):
        lines: list[str] = []
        packet = {"main_claim": "c", "key_facts": ["f1"], "source_refs": []}
        append_packet_block(lines, packet)
        msg = "\n".join(lines)
        self.assertIn("리서치 패킷", msg)
        self.assertIn("main_claim", msg)

    def test_build_publish_extras(self):
        ctx = EditorialContext(
            assigned_site="IJ",
            routing_reason="test",
            publish_grade="B",
            placement=PlacementScore(total=68, slot="ledger"),
            packet={},
            evidence=[],
            use_packet_writing=True,
        )
        extras = build_publish_extras(ctx)
        self.assertEqual(extras["publish_grade"], "B")
        self.assertEqual(extras["placement_slot"], "ledger")
