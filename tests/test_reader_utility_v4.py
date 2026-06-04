#!/usr/bin/env python3
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline.reader_utility import score_reader_value_dimension


class TestReaderUtilityV4(unittest.TestCase):
    def setUp(self):
        os.environ["IJ_PUBLISH_V4"] = "1"

    def tearDown(self):
        os.environ.pop("IJ_PUBLISH_V4", None)

    def test_v4_scores_footer_not_body_url(self):
        plain = "한전 고지서에서 확인한다. 기준 2026-05-28."
        packet = {
            "sources_footer": [{"url": "https://online.kepco.co.kr/", "label": "한전ON"}],
            "reader_utility": {"as_of_date": "2026-05-28", "primary_links": []},
        }
        score, gaps = score_reader_value_dimension(packet, plain)
        self.assertGreaterEqual(score, 4.0, gaps)


if __name__ == "__main__":
    unittest.main()
