#!/usr/bin/env python3
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.pipeline.discovered_facts import (
    dedupe_discovered_facts,
    discovered_fact_reflected_in_plain,
    extract_discovered_facts,
)
from engine.pipeline.inject_discovered import inject_discovered_fact_anchors
from engine.pipeline.rewrite_validate import sanitize_editorial_action_paragraph
from engine.pipeline.research_depth import assess_research_gate, compute_research_depth
from engine.pipeline.target_engine import enrich_packet_target, should_skip_rewrite
import research_collector as rc


class TestTargetEngine(unittest.TestCase):
    def setUp(self):
        os.environ["IJ_TARGET_ENGINE"] = "1"
        os.environ["IJ_PUBLISH_V4"] = "0"

    def tearDown(self):
        os.environ["IJ_TARGET_ENGINE"] = "0"
        os.environ.pop("IJ_PUBLISH_V4", None)

    def test_discovered_excludes_source_substring(self):
        raw = {
            "title": "전기요금",
            "body": "6월부터 11월분까지 요금이 대상이다.",
            "url": "https://www.korea.kr/1",
        }
        evidence = [
            {
                "fetch_status": "ok",
                "url": "https://online.kepco.co.kr/",
                "body_excerpt": "한전ON 모바일 앱에서는 요금제 비교 시뮬레이션과 전기사용 패턴 분석 리포트를 무료로 제공한다. " * 2,
            }
        ]
        found = extract_discovered_facts(raw, evidence)
        self.assertTrue(found)
        self.assertNotIn("6월부터 11월", found[0]["fact"])

    def test_research_gate_passes_with_discovered(self):
        raw = {"body": "원문 본문", "url": "https://www.korea.kr/1"}
        evidence = [
            {
                "fetch_status": "ok",
                "url": "https://online.kepco.co.kr/",
                "body_excerpt": "x" * 90,
            },
            {
                "fetch_status": "ok",
                "url": "https://www.price.go.kr/",
                "body_excerpt": "y" * 90,
            },
        ]
        discovered = extract_discovered_facts(
            raw,
            [
                {
                    "fetch_status": "ok",
                    "url": "https://online.kepco.co.kr/",
                    "body_excerpt": "한전ON 모바일 앱에서는 요금제 비교 시뮬레이션을 제공한다. " * 3,
                }
            ],
        )
        packet = {
            "action_items": ["https://online.kepco.co.kr/"],
            "reader_utility": {"primary_links": [{"url": "https://online.kepco.co.kr/"}]},
            "who_is_affected": ["소상공인"],
            "key_facts": ["대상은 일반용(갑)Ⅱ"],
        }
        gate = assess_research_gate(evidence, discovered, packet)
        self.assertFalse(gate["research_insufficient"])
        self.assertGreaterEqual(gate["research_depth"], 7.0)

    def test_enrich_packet_sets_v3_fields(self):
        raw = {
            "title": "t",
            "body": "6월부터 시행한다.",
            "url": "https://www.korea.kr/1",
        }
        evidence = [
            {
                "fetch_status": "ok",
                "url": "https://online.kepco.co.kr/",
                "body_excerpt": "한전ON 모바일 앱에서는 요금제 비교 시뮬레이션을 제공한다. " * 3,
            },
            {
                "fetch_status": "ok",
                "url": "https://www.price.go.kr/",
                "body_excerpt": "참가격 에너지마켓플레이스에서는 LED 지원 신청 절차를 안내한다. " * 3,
            },
        ]
        packet = rc.build_research_packet(raw, [], assigned_site="IJ").to_dict()
        packet["action_items"] = ["https://online.kepco.co.kr/", "https://www.price.go.kr/"]
        out = enrich_packet_target(raw, packet, evidence)
        self.assertEqual((out.get("research_meta") or {}).get("packet_version"), 3)
        self.assertTrue(out.get("discovered_facts"))
        self.assertTrue(out.get("journalist_brief"))
        self.assertTrue(out.get("field_takeaways"))
        self.assertTrue((out.get("field_takeaways") or {}).get("who_line"))
        self.assertFalse(should_skip_rewrite(out))

    def test_discovered_reflect_detects_paraphrase_overlap(self):
        fact = (
            "참가격 누리집에서는 위생용품·생활용품별 용량·개수 변경 이력과 "
            "단위가격 비교표를 제공한다."
        )
        plain = (
            "참가격 누리집(https://www.price.go.kr)에서는 위생용품·생활용품별 "
            "용량·개수 변경 이력과 단위가격 비교표를 제공하며"
        )
        self.assertTrue(discovered_fact_reflected_in_plain(fact, plain))

    def test_inject_skips_when_fact_already_present(self):
        fact = "한전ON 모바일 앱에서는 요금제 비교 시뮬레이션을 무료로 제공한다."
        body = f"<p>리드</p><p>배경</p><p>{fact}</p><p>다만 조건이 있다.</p>"
        packet = {"discovered_facts": [{"fact": fact}]}
        out = inject_discovered_fact_anchors(body, packet)
        self.assertEqual(out.count("요금제 비교"), 1)

    def test_dedupe_overlapping_discovered(self):
        items = [
            {"fact": "참가격 누리집에서는 위생용품별 용량 변경 이력을 제공한다."},
            {
                "fact": (
                    "참가격 누리집에서는 위생용품별 용량 변경 이력을 제공한다. "
                    "소비자단체는 고시 일정을 열람할 수 있다."
                )
            },
        ]
        out = dedupe_discovered_facts(items)
        self.assertEqual(len(out), 1)
        self.assertIn("소비자단체", out[0]["fact"])

    def test_assess_briefing_ready_keeps_html_paras(self):
        from engine.pipeline.coalition_brief import assess_briefing_ready

        packet = {
            "who_is_affected": ["해외진출 기업"],
            "action_items": ["https://www.motie.go.kr/"],
            "journalist_brief": {
                "lead_question": "유턴?",
                "reader_tasks": ["파트너 해당 여부 확인"],
            },
            "field_takeaways": {
                "who_line": "NGO·사회적 기업·사회공헌 현장에서는 해외진출 기업 등 해당·영향 여부를 우선 점검할 필요가 있다.",
                "action_lines": ["현장에서는 파트너·수혜자 해당 여부 확인"],
                "caution_line": "연대·대외 안내 시 협상제 도입 초기 지원 불균형 가능성",
            },
        }
        paras = [
            "정부 발표. NGO·사회적 기업 현장 점검.",
            "배경과 유턴 우려.",
            "지원 절차 확인·안내.",
            "다만 시행 범위는 제한적이다.",
        ]
        plain = " ".join(paras)
        br = assess_briefing_ready(
            packet,
            [{"fact": "motie 유턴지원단 안내"}],
            body_plain=plain,
            paras=paras,
        )
        self.assertNotIn("coalition_takeaways_weak", br.get("fail_reasons") or [])

    def test_ensure_scorecard_slots_fills_rubric(self):
        from engine.pipeline.inject_scorecard_slots import ensure_scorecard_slots
        from engine.pipeline.editorial_originality import score_originality_dimension
        from engine.pipeline.reader_utility import score_reader_value_dimension

        source = (
            "산업통상부는 29일 경제관계장관회의에서 유턴 방안을 발표했다.\n"
            "반면, 미·일 등 주요국은 형식적 요건보다 첨단전략 분야의 생산역량 확보에 중점을 둔다.\n"
            "이를 위해 올해 중 법령 정비를 추진하고, 내년부터 본격 시행할 계획이다.\n"
            "기존 유턴보조금 체계는 일률적 보조비율로 운영되어 지방 유치에 한계가 있었다.\n"
        ) * 30
        packet = {
            "key_facts": [
                "경제관계장관회의에서 유턴 촉진방안이 발표됐다.",
                "올해 중 유턴법 법령 정비 후 내년 본격 시행 예정이다.",
            ],
            "discovered_facts": [
                {"fact": "유턴지원단 누리집에서 청산 절차 안내와 상담 예약 경로를 확인할 수 있다."}
            ],
            "reader_utility": {
                "as_of_date": "2026-06-01",
                "scenarios": [
                    {
                        "body": "반면, 미·일 등 주요국은 형식적 요건보다 첨단전략 분야의 생산역량 확보에 중점을 둔다."
                    }
                ],
                "checklist": [
                    {"step": "이를 위해 올해 중 법령 정비를 추진하고, 내년부터 본격 시행할 계획이다."},
                    {"step": "기존 유턴보조금 체계는 일률적 보조비율로 운영되어 지방 유치에 한계가 있었다."},
                ],
                "primary_links": [
                    {"label": "보도자료 원문", "url": "https://www.korea.kr/news/1"},
                    {"label": "공식 안내", "url": "https://www.motie.go.kr/x"},
                ],
                "evidence_quotes": [{"quote": "유턴지원단 누리집에서 청산 절차 안내와 상담 예약 경로를 확인할 수 있다."}],
            },
            "field_takeaways": {
                "who_line": "NGO·사회적 기업 현장에서는 파트너 해당 여부를 점검한다.",
                "action_lines": ["현장에서는 파트너·수혜자 해당 여부 확인"],
                "caution_line": "연대·대외 안내 시 시행 범위를 유의한다.",
            },
        }
        body = (
            "<p>산업통상부는 29일 경제관계장관회의에서 유턴 방안을 발표했다.</p>"
            "<p>배경 설명.</p>"
            "<p>지원 체계가 바뀐다.</p>"
            "<p>다만 시행 범위는 제한적이다.</p>"
        )
        out = ensure_scorecard_slots(body, packet, source)
        plain = " ".join(__import__("engine.pipeline.rewrite_validate", fromlist=["_paragraph_plain_blocks"])._paragraph_plain_blocks(out))
        rv, _ = score_reader_value_dimension(packet, plain)
        orig, _ = score_originality_dimension(packet, plain, source)
        self.assertGreaterEqual(rv, 8.0, plain[:200])
        self.assertGreaterEqual(orig, 8.0)

    def test_reorder_swapped_paragraph_roles(self):
        from engine.pipeline.ij_paragraph_roles import reorder_paragraph_roles_paras
        from engine.pipeline.rewrite_validate import _paragraph_plain_blocks

        body = (
            "<p>발표.</p>"
            "<p>지원 절차와 신청 경로가 바뀐다. 협상 방식 보조금.</p>"
            "<p>보호무역 강화로 유턴 한계가 있었다. 기존 체계 문제.</p>"
            "<p>다만 시행 범위는 제한적이다.</p>"
        )
        paras = reorder_paragraph_roles_paras(_paragraph_plain_blocks(body))
        self.assertIn("보호무역", paras[1])
        self.assertIn("신청", paras[2])

    def test_coalition_takeaways_inject_and_validate(self):
        from engine.pipeline.coalition_takeaways import (
            build_field_takeaways,
            coalition_takeaways_reflected_in_body,
            inject_coalition_field_takeaways,
        )
        from engine.pipeline.rewrite_validate import _paragraph_plain_blocks

        packet = {
            "who_is_affected": ["해외진출 기업", "유턴 검토 파트너"],
            "journalist_brief": {
                "lead_question": "유턴 — 현장에서 무엇이 바뀌나?",
                "reader_tasks": ["파트너·수혜자 해당 여부 확인", "조사 확인: 공식 지원 경로 안내"],
                "coalition_gaps": ["협상제 도입 초기 지원 불균형 가능성"],
            },
            "discovered_facts": [],
        }
        ft = build_field_takeaways({"title": "유턴", "body": "원문"}, packet, [])
        packet["field_takeaways"] = ft
        body = (
            "<p>정부가 유턴 방안을 발표했다.</p>"
            "<p>배경 설명.</p>"
            "<p>지원 체계가 바뀐다.</p>"
            "<p>다만 시행 범위는 제한적이다.</p>"
        )
        out = inject_coalition_field_takeaways(body, packet)
        paras = _paragraph_plain_blocks(out)
        ok, gaps = coalition_takeaways_reflected_in_body(" ".join(paras), packet, paras=paras)
        self.assertTrue(ok, gaps)
        self.assertTrue(any("NGO" in paras[0] or "파트너" in paras[0] for _ in [1]))

    def test_sanitize_removes_duplicate_url_tail(self):
        messy = (
            "본문 흐름이다. 보도자료 원문: https://www.korea.kr/news/1 "
            "https://www.motie.go.kr/x: https://www.motie.go.kr/x "
            "산업통상자원부 유턴지원단 누리집에서는 해외법인 청산 절차 안내와 "
            "지방 투자 연계 상담 예약, 복귀 기업 맞춤형 세제·보조금 신청 경로를 "
            "한눈에 확인할 수 있다. 이를 위해 올해 중 법령 정비를 추진한다."
        )
        fact = (
            "산업통상자원부 유턴지원단 누리집에서는 해외법인 청산 절차 안내와 "
            "지방 투자 연계 상담 예약, 복귀 기업 맞춤형 세제·보조금 신청 경로를 "
            "한눈에 확인할 수 있다."
        )
        packet = {"discovered_facts": [{"fact": fact}]}
        lead = (
            "본문 흐름이다. 산업통상부 유턴지원단 누리집에서 청산 절차를 안내한다. "
        )
        out = sanitize_editorial_action_paragraph(lead + messy.split("본문 흐름이다. ", 1)[1], packet)
        self.assertNotIn("motie.go.kr/x: https", out)
        self.assertEqual(out.count(fact), 1)
        self.assertNotIn("이를 위해 올해", out)

    def test_skip_rewrite_when_insufficient(self):
        packet = {
            "research_gate": {"research_insufficient": True, "research_depth": 2.0},
        }
        self.assertTrue(should_skip_rewrite(packet))

    def test_validate_para1_lead_fails_on_ireul_wihae_only(self):
        from engine.pipeline.rewrite_validate import validate_para1_lead

        packet = {
            "main_claim": "산업통상부는 29일 경제관계장관회의에서 유턴 촉진방안을 발표했다.",
            "key_facts": ["올해 중 유턴법 법령 정비 후 내년 본격 시행 예정이다."],
            "journalist_brief": {"lead_question": "유턴 — 현장에서 무엇이 바뀌나?"},
        }
        paras = [
            "이를 위해 올해 중 법령 정비를 추진하고 내년부터 본격 시행할 계획이다.",
            "배경",
            "조치",
            "다만 시행 범위는 제한적이다.",
        ]
        ok, msg = validate_para1_lead(paras, packet, None)
        self.assertFalse(ok)
        self.assertEqual(msg, "1문단 리드 부족")

    def test_caution_line_excludes_expansion_only_gaps(self):
        from engine.pipeline.coalition_takeaways import build_field_takeaways

        packet = {
            "journalist_brief": {
                "coalition_gaps": [
                    "정부는 협상제 도입을 뒷받침하고 지방 투자를 활성화해 유턴을 개선해 나갈 계획이다.",
                    "다만 시행 초기 지원 불균형 가능성이 있다.",
                ],
            },
            "who_is_affected": ["해외진출 기업"],
        }
        ft = build_field_takeaways({"title": "유턴", "body": "원문"}, packet, [])
        self.assertTrue(ft.get("caution_line"))
        self.assertIn("불균형", ft["caution_line"])
        self.assertNotIn("뒷받침", ft["caution_line"])

    def test_caution_line_prefers_shortest_limitation_gap(self):
        from engine.pipeline.coalition_takeaways import build_field_takeaways

        packet = {
            "journalist_brief": {
                "coalition_gaps": [
                    "유사성 판단 시 개선해 탄력적으로 운영할 예정이다. 이를 통해 투자 활성화를 뒷받침한다.",
                    "시행 초기 지원 불균형 가능성에 한계가 있다.",
                    "해외법인 청산 절차는 별도 확인이 필요하며 취소 조건이 달라질 수 있다.",
                ],
            },
            "who_is_affected": ["해외진출 기업"],
        }
        ft = build_field_takeaways({"title": "유턴", "body": "원문"}, packet, [])
        self.assertIn("한계", ft["caution_line"])
        self.assertNotIn("뒷받침", ft["caution_line"])

    def test_caution_line_skips_expansion_gap_with_weak_yejeong(self):
        from engine.pipeline.coalition_takeaways import build_field_takeaways

        packet = {
            "journalist_brief": {
                "coalition_gaps": [
                    "유사성 판단 시 개선해 탄력적으로 운영할 예정이다. "
                    "이를 통해, 기업의 신산업 진출과 사업구조 고도화를 위한 투자 활성화를 뒷받침한다.",
                    "기존 유턴보조금 체계는 기준표에 따라 보조비율이 일률적으로 적용되어 "
                    "지방 중심의 우수한 유턴기업 유치에는 한계가 있었다.",
                ],
            },
            "who_is_affected": ["해외진출 기업"],
        }
        ft = build_field_takeaways({"title": "유턴", "body": "원문"}, packet, [])
        self.assertIn("한계", ft["caution_line"])
        self.assertNotIn("뒷받침", ft["caution_line"])
        self.assertNotIn("활성화", ft["caution_line"])

    def test_inject_skips_expansion_caution_line(self):
        from engine.pipeline.coalition_takeaways import inject_coalition_field_takeaways
        from engine.pipeline.rewrite_validate import _paragraph_plain_blocks

        packet = {
            "field_takeaways": {
                "caution_line": (
                    "연대·대외 안내 시 개선해 탄력적으로 운영할 예정이다. "
                    "이를 통해 투자 활성화를 뒷받침한다."
                ),
            },
        }
        body = (
            "<p>리드</p><p>배경</p><p>조치</p>"
            "<p>다만 시행 범위는 제한적이다.</p>"
        )
        out = inject_coalition_field_takeaways(body, packet)
        p4 = _paragraph_plain_blocks(out)[3]
        self.assertNotIn("뒷받침", p4)
        self.assertIn("제한적", p4)

    def test_finalize_v4_uses_packet_limitation_not_default(self):
        from engine.pipeline.rewrite_validate import (
            DEFAULT_LIMITATION_SENTENCE,
            finalize_ij_editorial_body,
            _paragraph_plain_blocks,
        )

        expansion_p4 = (
            "다만 유사성 판단 시 개선해 탄력적으로 운영할 예정이다. "
            "이를 통해 기업의 신산업 진출을 위한 투자 활성화를 뒷받침한다."
        )
        pad = "적용 대상과 시행 시점은 원문 보도자료를 기준으로 확인한다."
        body = (
            f"<p>산업통상부는 29일 경제관계장관회의에서 유턴 촉진방안을 발표했다. {pad}</p>"
            f"<p>그동안 보호무역 강화로 유턴 정책의 한계가 제기됐다. {pad}</p>"
            f"<p>한전은 고지서에 표기한다. {pad}</p>"
            f"<p>{expansion_p4}</p>"
        )
        packet = {
            "main_claim": "산업통상부는 29일 경제관계장관회의에서 유턴 촉진방안을 발표했다.",
            "key_facts": ["올해 중 유턴법 법령 정비 후 내년 본격 시행 예정이다."],
            "journalist_brief": {
                "coalition_gaps": [
                    "기존 유턴보조금 체계는 일률적 보조비율로 지방 유치에 한계가 있었다.",
                ],
            },
            "reader_utility": {"as_of_date": "2026-06-01"},
        }
        os.environ["IJ_PUBLISH_V4"] = "1"
        try:
            out = finalize_ij_editorial_body(body, packet, {"body": "다음 달부터 시행한다."})
            paras = _paragraph_plain_blocks(out)
            self.assertGreaterEqual(len(paras), 4)
            p4 = paras[3]
            self.assertNotIn(DEFAULT_LIMITATION_SENTENCE[:20], p4)
            self.assertNotIn("보도·안내 내용은", p4)
            self.assertNotIn("뒷받침", p4)
            self.assertTrue(p4.startswith("다만"))
        finally:
            os.environ.pop("IJ_PUBLISH_V4", None)

    def test_finalize_replaces_expansion_only_para4(self):
        from engine.pipeline.rewrite_validate import (
            DEFAULT_LIMITATION_SENTENCE,
            finalize_ij_editorial_body,
            _paragraph_plain_blocks,
        )

        expansion_p4 = (
            "다만 유사성 판단 시 개선해 탄력적으로 운영할 예정이다. "
            "이를 통해 기업의 신산업 진출을 위한 투자 활성화를 뒷받침한다."
        )
        body = (
            "<p>산업통상부는 29일 경제관계장관회의에서 유턴 촉진방안을 발표했다.</p>"
            "<p>그동안 보호무역 강화로 유턴 정책의 한계가 제기됐다.</p>"
            "<p>한전은 고지서에 표기한다. https://www.motie.go.kr/x</p>"
            f"<p>{expansion_p4}</p>"
        )
        packet = {
            "main_claim": "산업통상부는 29일 경제관계장관회의에서 유턴 촉진방안을 발표했다.",
            "key_facts": ["올해 중 유턴법 법령 정비 후 내년 본격 시행 예정이다."],
            "risk_flags": ["official_evidence_missing"],
            "action_items": ["https://www.motie.go.kr/x"],
            "journalist_brief": {
                "coalition_gaps": [
                    "유사성 판단 시 개선해 탄력적으로 운영할 예정이다. "
                    "이를 통해 투자 활성화를 뒷받침한다.",
                ],
            },
            "field_takeaways": {
                "caution_line": (
                    "연대·대외 안내 시 개선해 탄력적으로 운영할 예정이다. "
                    "이를 통해 투자 활성화를 뒷받침한다."
                ),
            },
            "reader_utility": {
                "as_of_date": "2026-06-01",
                "scenarios": [],
                "checklist": [],
                "primary_links": [],
                "evidence_quotes": [],
            },
        }
        os.environ["IJ_PUBLISH_V4"] = "0"
        try:
            out = finalize_ij_editorial_body(body, packet, {"body": "다음 달부터 시행한다."})
            p4 = _paragraph_plain_blocks(out)[3]
            self.assertTrue(
                DEFAULT_LIMITATION_SENTENCE[:24] in p4
                or "본격 시행 예정" in p4
                or "유턴법" in p4
            )
            self.assertNotIn("뒷받침", p4)
            self.assertIn("다만", p4)
        finally:
            os.environ.pop("IJ_PUBLISH_V4", None)

    def test_p1_lead_line_prepended_discovered_only_in_p3(self):
        from engine.pipeline.coalition_takeaways import (
            build_field_takeaways,
            inject_coalition_field_takeaways,
        )
        from engine.pipeline.inject_scorecard_slots import ensure_scorecard_slots
        from engine.pipeline.rewrite_validate import _paragraph_plain_blocks

        main = "산업통상부는 29일 경제관계장관회의에서 유턴 촉진방안을 발표했다."
        discovered_fact = (
            "유턴지원단 누리집에서 청산 절차 안내와 상담 예약 경로를 확인할 수 있다."
        )
        packet = {
            "main_claim": main,
            "journalist_brief": {
                "lead_question": "유턴 — 현장에서 무엇이 바뀌나?",
                "who_should_care": ["해외진출 기업"],
                "reader_tasks": [],
                "coalition_gaps": [],
            },
            "discovered_facts": [{"fact": discovered_fact}],
            "reader_utility": {
                "scenarios": [],
                "checklist": [],
                "primary_links": [],
                "evidence_quotes": [],
            },
        }
        ft = build_field_takeaways({"title": "유턴", "body": "원문"}, packet, packet["discovered_facts"])
        packet["field_takeaways"] = ft
        self.assertTrue(ft.get("lead_line"))
        self.assertIn("유턴", ft["lead_line"])

        body = (
            "<p>짧은 리드.</p>"
            "<p>배경 설명.</p>"
            "<p>조치 요약.</p>"
            "<p>다만 시행 범위는 제한적이다.</p>"
        )
        out = inject_coalition_field_takeaways(body, packet)
        out = ensure_scorecard_slots(out, packet, "원문 본문")
        paras = _paragraph_plain_blocks(out)
        self.assertTrue(paras[0].startswith(ft["lead_line"][:40]))
        self.assertIn(discovered_fact[:30], paras[2])
        self.assertNotIn(discovered_fact[:30], paras[0])

    def test_p1_limitation_sentence_uses_hanje_gap(self):
        from engine.pipeline.coalition_takeaways import build_field_takeaways

        packet = {
            "journalist_brief": {
                "coalition_gaps": [
                    "정부는 협상제 도입을 뒷받침하고 지방 투자를 활성화해 유턴을 개선해 나갈 계획이다.",
                    "기존 유턴보조금 체계는 일률적 보조비율로 지방 유치에 한계가 있었다.",
                ],
            },
            "who_is_affected": ["해외진출 기업"],
        }
        ft = build_field_takeaways({"title": "유턴", "body": "원문"}, packet, [])
        lim = ft.get("limitation_sentence") or ""
        self.assertTrue(lim.startswith("다만"))
        self.assertIn("한계", lim)
        self.assertIn("일률", lim)

    def test_p2_limitation_avoids_para3_duplicate(self):
        from engine.pipeline.coalition_takeaways import refine_limitation_sentence_for_body

        p3 = (
            "기존에는 기준표에 따라 보조비율이 일률적으로 적용되어 "
            "지방 중심의 우수한 유턴기업 유치에 한계가 있었다."
        )
        packet = {
            "journalist_brief": {
                "coalition_gaps": [
                    "기존 유턴보조금 체계는 일률적 보조비율로 지방 유치에 한계가 있었다.",
                    "이를 위해 올해 중 유턴법 관련 법령 정비를 추진하고, 내년부터 본격 시행할 계획이다.",
                    "유턴기업 선정 이후 투자가 계획대로 이행되지 않아 지정이 취소되는 사례가 다수 발생해 왔다.",
                ],
            },
            "field_takeaways": {},
        }
        from engine.pipeline.coalition_takeaways import _gap_overlaps_para3

        lim = refine_limitation_sentence_for_body(packet, p3)
        self.assertTrue(lim.startswith("다만"))
        self.assertFalse(_gap_overlaps_para3(p3, lim))
        self.assertTrue("취소" in lim or "시행" in lim or "내년" in lim)

    def test_p2_sanitize_para1_strips_ireul_whae_and_title(self):
        from engine.pipeline.coalition_takeaways import sanitize_para1_coalition

        title = "해외 진출 기업, '유턴' 문턱 낮춰 국내 복귀·지방 투자 유도"
        lead = "해외 진출·국내 복귀(유턴)를 검토하는 NGO·연대 현장에는 지원 범위가 달라진다."
        p0 = (
            f"{title} 1. 산업통상부는 29일 발표했다. "
            "이를 위해 올해 중 유턴법 정비를 추진한다."
        )
        out = sanitize_para1_coalition(p0, lead, {"title": title})
        self.assertTrue(out.startswith(lead[:28]))
        self.assertNotIn("이를 위해", out)

    def test_p1_ensure_limitation_prefers_gap_over_generic_default(self):
        from engine.pipeline.coalition_takeaways import build_field_takeaways
        from engine.pipeline.rewrite_validate import (
            DEFAULT_LIMITATION_SENTENCE,
            ensure_valid_limitation_paragraph,
            _paragraph_plain_blocks,
        )

        packet = {
            "journalist_brief": {
                "coalition_gaps": [
                    "기존 유턴보조금 체계는 일률적 보조비율로 지방 유치에 한계가 있었다.",
                ],
            },
        }
        ft = build_field_takeaways({"title": "유턴", "body": "원문"}, packet, [])
        packet["field_takeaways"] = ft
        body = (
            "<p>리드.</p><p>배경.</p><p>조치.</p>"
            f"<p>{DEFAULT_LIMITATION_SENTENCE}</p>"
        )
        out = ensure_valid_limitation_paragraph(body, packet)
        p4 = _paragraph_plain_blocks(out)[3]
        self.assertIn("일률", p4)
        self.assertIn("한계", p4)
        self.assertNotIn("시행 범위·적용 조건", p4)

    def test_p1_who_line_uturn_msme_only_uses_field_template(self):
        from engine.pipeline.coalition_takeaways import build_field_takeaways

        packet = {
            "main_claim": "정부가 유턴 지원을 확대한다.",
            "journalist_brief": {"who_should_care": ["중소벤처기업"]},
        }
        ft = build_field_takeaways({"title": "유턴 정책", "body": "원문"}, packet, [])
        who = ft.get("who_line") or ""
        self.assertIn("유턴", who)
        self.assertIn("파트너·수혜자", who)
        self.assertNotRegex(who, r"중소벤처\s*등")

    def test_p1_who_line_uturn_no_generic_msme(self):
        from engine.pipeline.coalition_takeaways import build_field_takeaways

        packet_generic = {
            "main_claim": "정부가 유턴 지원을 확대한다.",
            "journalist_brief": {"who_should_care": ["기업", "소비자"]},
        }
        ft_generic = build_field_takeaways(
            {"title": "유턴 정책", "body": "원문"}, packet_generic, []
        )
        who_generic = ft_generic.get("who_line") or ""
        self.assertIn("유턴", who_generic)
        self.assertIn("파트너·수혜자", who_generic)
        self.assertNotIn("중소벤처", who_generic)

        packet_specific = {
            "main_claim": "정부가 유턴 지원을 확대한다.",
            "journalist_brief": {"who_should_care": ["해외진출 기업", "중소벤처기업"]},
        }
        ft_specific = build_field_takeaways(
            {"title": "유턴", "body": "원문"}, packet_specific, []
        )
        who = ft_specific.get("who_line") or ""
        self.assertIn("유턴", who)
        self.assertIn("해외진출", who)
        self.assertNotRegex(who, r"중소벤처\s*등")

    def test_discovered_inject_truncates_without_open_paren(self):
        fact = (
            "산업통상자원부 유턴지원단 누리집(www.motie.go.kr)에서는 해외법인 청산 절차 안내와 "
            "지방 투자 연계 상담 예약, 복귀 기업 맞춤형 세제·보조금 신청 경로를 "
            "한눈에 확인할 수 있다. 추가 안내는 공식 페이지를 참고한다."
        )
        body = "<p>리드</p><p>배경</p><p>짧은 3문단</p><p>다만 한계가 있다.</p>"
        packet = {"discovered_facts": [{"fact": fact}]}
        out = inject_discovered_fact_anchors(body, packet)
        from engine.pipeline.rewrite_validate import _paragraph_plain_blocks

        p3 = _paragraph_plain_blocks(out)[2]
        self.assertNotIn("(", p3[-3:])
        self.assertTrue(p3.endswith("다.") or p3.endswith("다"))


if __name__ == "__main__":
    unittest.main()
