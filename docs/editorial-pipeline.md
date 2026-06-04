# IJ Editorial Pipeline (local test)

**⛔ Do not merge to `main` without explicit deploy approval.**

**설계 (v2, 구현됨):** [ij-editorial-workflow-v2-design.md](./ij-editorial-workflow-v2-design.md) — 패킷 `reader_utility`, reader_value·originality 채점, artifact bundle.

**목표 설계 (권장):** **[ij-news-engine-target-design-v4.md](./ij-news-engine-target-design-v4.md)** — **권위 있는 완성 기사(발행본) 1순위**, 본문 무URL·출처 하단, `article_publish_ready`.  
(레거시 v3 Target: [ij-news-engine-target-design.md](./ij-news-engine-target-design.md) — 연대 브리핑 North Star, 구현 잔존)

**설계 (v3, 기자형 리서치·작성):** [ij-editorial-workflow-v3-design.md](./ij-editorial-workflow-v3-design.md) — 파이프라인·패킷·채점 상세.

## Env flags

| Variable | Default | Meaning |
|----------|---------|---------|
| `EDITORIAL_PIPELINE` | `1` | Ingest → route → research → placement |
| `IJ_PACKET_PIPELINE` | `1` | Hybrid user message (source + packet + evidence) |
| `IJ_TARGET_ENGINE` | `0` | `1` = NGO·SE 연대 브리핑 Target (discovered, `field_takeaways`, briefing_ready, research gate) |
| `RESEARCH_INSUFFICIENT_SKIP_REWRITE` | `1` | 조사 부족 시 IJ LLM 재작성 스킵 |
| `RESEARCH_DEPTH_MIN` | `7.0` | Target 통과 조사 깊이 하한 |
| `RESEARCH_MIN_DISCOVERED_FACTS` | `1` | 원문에 없는 discovered 최소 건수 |
| `REVIEW_ONLY` | `0` | `1` = no publish, review outputs only |
| `EDITORIAL_IMAGE_PROBE` | `0` | `1` = in review mode, run `find_best_image` (no API publish) |
| `EDITORIAL_IMAGE_PROBE_DOWNLOAD` | `0` | `1` + probe = also try `download_best_image` (network) |
| `TIER_C_ENABLED` | `1` | Extra evidence when facts thin |
| `TIER_C_USE_LLM` | `0` | `1` + `GEMINI_API_KEY` for URL hints |
| `EDITORIAL_PERSIST` | `0` | Requires `sql/editorial_pipeline.sql` on DB |

## Tests

```bash
cd erum-news-engine
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest tests/ -v --ignore=tests/fixtures
```

## Fixture E2E (no publish)

```bash
EDITORIAL_PIPELINE=1 IJ_PACKET_PIPELINE=1 REVIEW_ONLY=1 \
  .venv/bin/python scripts/run_editorial_review_fixture.py
```

Output: `review_outputs/editorial_compare_*.md` (includes **이미지·발행 프리플라이트** when `EDITORIAL_IMAGE_PROBE=1`)

### Full preflight E2E (text + image probe, no deploy)

```bash
FIXTURE_URL='https://www.korea.kr/news/policyNewsView.do?newsId=148965108&call_from=rsslink' \
  .venv/bin/python scripts/run_editorial_preflight_e2e.py
```

Writes `review_outputs/editorial_preflight_latest.json` with `would_publish_api`, `layout_type`, `image_status`.

**Do not run** `REVIEW_ONLY=0` on production until deploy plan.

### Target 워크플로 (NGO·SE 시사점)

`IJ_TARGET_ENGINE=1` 일 때:

1. **조사** → `discovered_facts`, `research_gate`
2. **패킷** → `journalist_brief` + `field_takeaways` (누구 / 할 일 / 유의)
3. **재작성 프롬프트** → `[NGO·SE 현장 시사점]` 블록 + 1·3·4문단 체크리스트
4. **finalize** (`finalize_ij_editorial_body`) — 순서:
   - `flatten_nested_paragraph_tags` → `normalize_temporal_in_body`
   - `enforce_four_paragraph_structure` → `fix_para1_lead_opener` (이를 위해 리드 보정)
   - `inject_missing_source_anchors` → `append_limitation_paragraph_if_needed`
   - `inject_reader_utility_anchors` → `inject_originality_anchors`
   - `inject_discovered_fact_anchors` → `sanitize_editorial_body`
   - (Target) `inject_coalition_field_takeaways` → `sanitize_editorial_body`
   - `ensure_scorecard_slots` (리드·루브릭 슬롯) → `inject_discovered_fact_anchors` (재시도)
   - `sanitize_editorial_body` → `split_limitation_paragraph` → `ensure_valid_limitation_paragraph`
   - `fix_para1_lead_opener` → `pad_paragraph_min_length` → `cap_watch_phrase_repetition`
5. **검증·채점** → `validate_para1_lead`, `validate_limitation_paragraph`, `coalition_takeaways_weak`, `briefing_ready`

품질 루프: `scripts/run_editorial_quality_loop.py` — `EDITORIAL_QUALITY_MAX_ATTEMPTS` 기본 **12**.

픽스처 E2E: `run_editorial_review_fixture.py`는 동일 기사에 대해 **dual-fetch** 조사(원문+Tier C) 후 비교 리포트를 쓴다.

**Do not run** `REVIEW_ONLY=0` on production until deploy plan.

### North Star P1 (Target 시사점·리드)

`field_takeaways` / finalize 단계에서 NGO·SE 브리핑 품질을 맞춘다.

| 항목 | 동작 |
|------|------|
| **리드** | `build_field_takeaways` → `lead_line` (lead_question 답 한 문장, `— 현장·연대…` 꼬리 제거, 길면 `main_claim`, 최대 200자). `inject_coalition_field_takeaways`가 1문단 앞에 prepend. `validate_para1_lead`는 `lead_line` 앵커 인정. |
| **discovered·인용** | `ensure_scorecard_slots`는 2·3문단만 사용 (1문단 리드 재구성 제거). |
| **다만** | `limitation_sentence` = coalition gap 중 `한계\|취소\|지정 취소\|일률` 최단 문장. `ensure_valid_limitation_paragraph`가 DEFAULT 전에 시도. |
| **누구** | 유턴·해외·진출·복귀 라벨 → 유턴 현장 템플릿; 그 외 → 연대·보고 현장 템플릿. generic `who` + 유턴 주제면 who_line 생략. 1문단에 WHO 마커·라벨 있으면 중복 주입 안 함. |
