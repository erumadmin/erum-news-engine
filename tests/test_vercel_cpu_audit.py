import unittest

from engine.utils.vercel_cpu_audit import (
    classify_http_probe,
    extract_team_softblock,
    summarize_article_api_result,
)


class TestVercelCpuAudit(unittest.TestCase):
    def test_extract_team_softblock_returns_matching_team_state(self):
        payload = {
            "teams": [
                {
                    "slug": "other-team",
                    "billing": {"status": "active"},
                    "softBlock": None,
                },
                {
                    "slug": "erums-projects-cfc8699e",
                    "billing": {"status": "active"},
                    "softBlock": {
                        "reason": "FAIR_USE_LIMITS_EXCEEDED",
                        "blockedDueToOverageType": "fluidCpuDuration",
                    },
                },
            ]
        }

        state = extract_team_softblock(payload, "erums-projects-cfc8699e")
        self.assertEqual(state["slug"], "erums-projects-cfc8699e")
        self.assertEqual(state["billing_status"], "active")
        self.assertEqual(state["soft_block_reason"], "FAIR_USE_LIMITS_EXCEEDED")
        self.assertEqual(state["soft_block_overage_type"], "fluidCpuDuration")

    def test_extract_team_softblock_returns_missing_when_team_absent(self):
        state = extract_team_softblock({"teams": []}, "missing-team")
        self.assertEqual(state["slug"], "missing-team")
        self.assertEqual(state["status"], "missing")

    def test_classify_http_probe_marks_deployment_disabled(self):
        probe = classify_http_probe(
            "https://erum-one.com",
            402,
            {"x-vercel-error": "DEPLOYMENT_DISABLED"},
            "Payment required\nDEPLOYMENT_DISABLED",
        )
        self.assertEqual(probe["status"], "blocked")
        self.assertEqual(probe["reason"], "DEPLOYMENT_DISABLED")

    def test_classify_http_probe_marks_ok_response(self):
        probe = classify_http_probe(
            "https://impactjournal.kr",
            200,
            {"content-type": "text/html"},
            "<html></html>",
        )
        self.assertEqual(probe["status"], "ok")

    def test_summarize_article_api_result_detects_json_success(self):
        result = summarize_article_api_result(
            "https://erum-one.com/api/articles?site=IJ&status=PUBLISHED&page=1&limit=1",
            200,
            {"content-type": "application/json"},
            '{"articles":[],"total":0,"page":1,"limit":1}',
        )
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["json_ok"])

    def test_summarize_article_api_result_detects_blocked_text(self):
        result = summarize_article_api_result(
            "https://erum-one.com/api/articles?site=IJ&status=PUBLISHED&page=1&limit=1",
            402,
            {"x-vercel-error": "DEPLOYMENT_DISABLED"},
            "Payment required\nDEPLOYMENT_DISABLED",
        )
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["json_ok"])
