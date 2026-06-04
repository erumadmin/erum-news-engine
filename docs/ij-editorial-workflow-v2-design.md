# IJ 편집 파이프라인 v2 — 범용 워크플로우 설계

**Status:** Implemented on `feat/ij-editorial-pipeline-test` (packet v2, reader_value scoring; E2E는 fixture 권장)  
**Date:** 2026-05-28  
**Repo:** `erum-news-engine` (feature: `feat/ij-editorial-pipeline-test`)  
**Related:** [editorial-pipeline.md](./editorial-pipeline.md), [research-pipeline-implementation-plan.md](./research-pipeline-implementation-plan.md), [2026-05-27 IJ implementation plan](https://github.com/erum/erum-company-website/blob/main/docs/superpowers/plans/2026-05-27-erum-news-engine-ij-editorial-pipeline.md) (company-website)

---

## 0. 운영 규칙 (변경 없음)

| 규칙 | 내용 |
|------|------|
| **main 머지 금지** | 프로덕션·Actions 전환 전까지 feature 브랜치에서만 작업 |
| **REVIEW_ONLY 기본** | 로컬·CI 검증은 `REVIEW_ONLY=1`, 발행·`REVIEW_ONLY=0`은 별도 승인 |
| **환각 금지** | 재작성·패킷·독자 가치 블록 모두 **원문 ∪ 증거 발췌** 밖 사실 추가 금지 |

---

## 1. 문제 정의

### 1.1 v1이 해결한 것

- 정책브리핑 **전문 수집** (`ingest.py`)
- IJ 라우팅·후보 필터 (`engine/profiles/ij.py`)
- 리서치 패킷 + Tier C 증거 fetch 시도 (`research_collector.py`)
- 원문 + 패킷 + 근거 **하이브리드 재작성** (`packet_writer.py`)
- 4문단·URL·한계 **검증/후처리** (`rewrite_validate.py`)
- 가중 **채점** + 품질 루프 산출물 번들 (`editorial_scorecard.py`, `editorial_report.py`)

### 1.2 v1의 한계 (기사 무관하게 반복되는 구조적 문제)

| 문제 | 결과 |
|------|------|
| 패킷 = 원문 **요약·링크 목록** | “조사했다”기보다 “정리했다”에 가까움 |
| `reader_utility` 슬롯 없음 | 시나리오·체크리스트·기준일·FAQ 발췌를 **재작성이 invent** 하거나 **생략** |
| 증거 fetch 불안정·활용 약함 | `official_evidence_missing` 빈번, E-E-A-T 약함 |
| 통과 = 형식·fact 위주 | **독창성·독자 가치**와 채점·검증 불일치 |
| 산출물·채점 불일치 (과거) | compare MD 평문만 저장 → 재채점 불가 (v1.1에서 번들로 완화) |
| **특정 기사 튜닝 착시** | 전기요금 1건 9.5 통과 ≠ 모든 IJ 후보에 동일 품질 |

### 1.3 제품 판단

**“원문을 IJ 4문단으로 다듬기만”** 할 거면 기존 뉴스엔진(원문 → 재작성 → QA)으로 충분하다.  
IJ 전용 엔진을 유지할 이유는 **리서치 패킷을 통해 독자 행동·확인 경로·공식 발췌를 구조화해 넣는 것**이다.

---

## 2. 목표 / 비목표

### 2.1 목표

1. **어떤 IJ 후보 원문**이든 동일 단계·동일 스키마·동일 산출물로 처리한다.
2. 패킷에 **`reader_utility`** 를 두고, 재작성은 그 범위 안에서만 “독자 가치”를 추가한다.
3. **통과 조건** = 검증 OK + 채점 ≥ 9.5 + (v2) reader_value 하한 충족.
4. 실행마다 **채점에 사용한 HTML**과 compare MD를 **한 타임스탬프 번들**로 저장한다.
5. 도메인 하드코딩(전기위원회 문장 등)을 **원문 fact 그룹 기반** 규칙으로 일반화한다.

### 2.2 비목표 (이 설계 범위 밖)

- `main` 머지·GitHub Actions 프로덕션 env 변경
- NN/CB 편집 파이프라인 전면 교체 (IJ만 v2 적용)
- 프로액티브 웹 검색으로 원문에 없는 신규 사실 수집
- **프로덕션 API 발행**·IJ 홈 슬롯 API (별도 승인 트랙)

### 2.3 프리플라이트 E2E (2026-06-02, 배포 없음)

리뷰 모드에서 **텍스트 v4 + 이미지 프로브 + 발행 체크리스트**를 한 번에 돌린다 (`REVIEW_ONLY=1` 유지).

| 단계 | 구현 |
|------|------|
| 수집·조사·재작성·v4 게이트 | 기존 품질 루프 |
| 이미지 | `EDITORIAL_IMAGE_PROBE=1` → `image_probe.py` |
| 편성 | `layout_decision.py` (이미지 없으면 `brief`/`list`) |
| 발행 dry-run | `publish_preflight.py` → `would_publish_api` (API 호출 없음) |

스크립트: `scripts/run_editorial_preflight_e2e.py` · 산출물: compare MD §이미지·발행 프리플라이트, `editorial_preflight_latest.json`

---

## 3. 범용 워크플로우 (기사 독립)

```
┌─────────────┐
│ 1. INGEST   │  URL/RSS → full body (또는 승인된 fallback)
└──────┬──────┘
       ▼
┌─────────────┐
│ 2. ROUTE    │  IJ | NN | CB | DROP (profile 공통)
└──────┬──────┘
       ▼ (assigned == IJ)
┌─────────────┐
│ 3. RESEARCH │  Tier A/B/C evidence fetch + 발췌
└──────┬──────┘
       ▼
┌─────────────┐
│ 4. PACKET   │  ResearchPacket v2 (+ reader_utility)
└──────┬──────┘
       ▼
┌─────────────┐
│ 5. REWRITE  │  LLM (원문 + 패킷 + evidence + reader_utility)
└──────┬──────┘
       ▼
┌─────────────┐
│ 6. FINALIZE │  4<p>, fact 주입, 반복·시점 정규화 (규칙)
└──────┬──────┘
       ▼
┌─────────────┐
│ 7. GATE     │  validate_ij + score_editorial (≥9.5)
└──────┬──────┘
       ▼
┌─────────────┐
│ 8. QA       │  ai_quality_check (기존)
└──────┬──────┘
       ▼
┌─────────────┐
│ 9. BUNDLE   │  compare MD + JSON + body HTML
└──────┬──────┘
       ▼
   REVIEW_ONLY 종료  또는  (승인 후) 발행
```

**입력 변형 (환경변수만 다름, 로직 동일):**

| 입력 | `EDITORIAL_REQUIRE_FULL_SOURCE` | `article.body` |
|------|--------------------------------|----------------|
| Live URL | `1` | fetch로 채움 |
| 캐시 원문 (테스트) | `0` | `FIXTURE_SOURCE_MD` 등으로 사전 주입 |

---

## 4. 데이터 모델 — ResearchPacket v2

### 4.1 기존 필드 (유지)

`research_collector.ResearchPacket` / `packet.to_dict()`:

- `main_claim`, `why_now`, `who_is_affected`, `effective_date`
- `conditions`, `exceptions`, `key_facts`, `action_items`
- `source_refs`, `risk_flags`, `publish_grade`, `placement_hint`
- `evidence_count`, `official_evidence_count`

### 4.2 신규: `reader_utility`

모든 IJ 기사에 **동일 JSON shape**. 내용만 원문·증거에 따라 채움.

```json
{
  "reader_utility": {
    "scenarios": [
      {
        "label": "낮 시간대 전기 사용이 많은 업종",
        "body": "카페·음식점 등은 시간대별 요금이 유리할 수 있다.",
        "source": "raw_body",
        "source_ref": "원문 예시 문단"
      }
    ],
    "checklist": [
      {
        "step": "6~11월 고지서에서 두 요금 비교 확인",
        "source": "raw_body"
      },
      {
        "step": "12월부터 유리한 요금 선택 적용",
        "source": "raw_body"
      }
    ],
    "primary_links": [
      {
        "label": "보도자료 원문",
        "url": "https://www.korea.kr/...",
        "role": "announcement"
      },
      {
        "label": "한전ON",
        "url": "https://online.kepco.co.kr/",
        "role": "official_reader",
        "fetch_status": "ok"
      }
    ],
    "as_of_date": "2026-05-28",
    "evidence_quotes": [
      {
        "url": "https://online.kepco.co.kr/...",
        "quote": "발췌 80자 이상 ...",
        "used_for": "reader_confirmation"
      }
    ]
  },
  "research_meta": {
    "ingest_source": "full_page",
    "packet_version": 2
  }
}
```

### 4.3 채우는 규칙 (도메인 무관)

| 슬롯 | 소스 | 비어 있어도 됨 |
|------|------|----------------|
| `scenarios` | 원문의 **예시·비유·“예를 들어”** 문장; 증거 페이지 예시(발췌 인용) | ✅ (0개면 독자가치 점수만 감점) |
| `checklist` | 원문·증거의 **행동+시점** (“신청”, “확인”, “선택”, “시행”, “~부터”) | ✅ |
| `primary_links` | 원문 URL + `action_items` URL (+ fetch 성공 시 role 태깅) | ❌ 원문 URL 최소 1 |
| `as_of_date` | 수집 시각 KST (시스템) | ❌ |
| `evidence_quotes` | `evidence[].fetch_status==ok` 발췌 | ✅ (0이면 `official_evidence_missing`) |

**금지:** 위 소스에 없는 수치·표·FAQ 문구 생성.

---

## 5. 리서치 단계 (Research) — 알고리즘

### 5.1 Evidence plan (기존 확장)

`IJProfile.collect_evidence_plan` → `max_fetch` (기본 4).

1. 원문 HTML/본문에서 URL 추출 → `action_items`
2. Tier C: 정부·공식·원문 도메인 우선 (`tier_c.py`)
3. fetch → `title`, `body_excerpt`, `fetch_status`, `evidence_type`

### 5.2 Packet build v2 (신규 모듈)

**파일 (예정):** `engine/pipeline/reader_utility.py` + `research_collector` 연동

| Step | 처리 |
|------|------|
| A | `key_facts`, `action_items` — 기존 추출 유지 |
| B | `scenarios` — 원문에서 “예를 들어”, “반면”, “~업종”, “~경우” 패턴 + LLM 보조(선택, 원문 인용만) |
| C | `checklist` — 날짜·절차 문장 분리 (규칙 + LLM, source 태그 필수) |
| D | `primary_links` — 원문 URL + action URL merge, fetch 메타 |
| E | `evidence_quotes` — ok evidence에서 1~3발췌 |
| F | `risk_flags` — `official_evidence_count==0` → `official_evidence_missing` |

**LLM 사용 시:** 출력은 JSON only, 각 항목에 `source` / `quote` 필수, 검증기가 원문 substring 매칭.

---

## 6. 재작성 (Rewrite)

### 6.1 입력 (`packet_writer`)

기존 블록 유지 + 추가:

```text
[독자 가치 — 패킷 reader_utility만 사용, 없으면 생략]
시나리오: ...
체크리스트: ...
기준일(as_of): ...
공식 인용: ...
```

### 6.2 본문 규칙 (모든 기사 공통)

- HTML `<p>` **정확히 4개**
- 1: 변화·수혜 / 2: 배경·문제 / 3: 작동·URL / 4: **다만** + 한계
- 700~1100자, 동일 fact 반복 ≤2회
- `reader_utility.checklist`가 있으면 3 또는 4문단에 **번호 없이** 2~3행동 녹임
- `scenarios`가 있으면 3문단에 **1개만** 짧게

### 6.3 Finalize (규칙 엔진)

`finalize_ij_editorial_body` — v2 변경 방향:

- `flatten_nested_paragraph_tags` → `enforce_four_paragraph_structure`
- `inject_missing_source_anchors` → **`editorial_facts.fact_groups_from_source(원문)`** 기반 일반 주입 (도메인 키워드 테이블 축소)
- `cap_watch_phrase_repetition`, `pad_paragraph_min_length`

---

## 7. 품질 게이트 (Validate + Score)

### 7.1 검증 (`validate_ij_editorial_rewrite`)

- 4문단·역할·URL·반복·`missing_fact_labels(원문)` (기존 `editorial_facts`)
- v2: `reader_utility`가 비어 있지 않으면 **최소 1개 primary_links.url** 본문 포함

### 7.2 채점 (`score_editorial_rewrite`)

| 차원 | 가중치 | v2 메모 |
|------|--------|---------|
| structure | 28% | 논리 4문단, 중첩 p 감점 |
| facts | 28% | 원문 fact 그룹 + key_facts |
| utility | 18% | action_items URL |
| editorial | 18% | 시점·반복·한계 |
| qa_proxy | 8% | QA 점수 환산 |
| **reader_value** | **9%** | scenarios/checklist/as_of/evidence 인용 |
| **originality** (신규) | **9%** | 시나리오 대비·체크리스트 3단·링크 묶음·원문 비교 (환각 감점) |

**reader_value 예시 루브릭 (0–10):**

- +2: scenario 1개 이상 본문 반영
- +2: checklist 2개 이상 반영
- +2: `as_of_date` 또는 “기준” 문구
- +2: evidence_quote 또는 공식 발췌 인용
- +2: primary_links 2개 이상 본문 URL

**originality 루브릭 (0–10, `editorial_originality.py`):**

- +2: 시나리오 대비 1줄 (예: 카페 vs 업종별 유리 요금 — 원문 예시 반영)
- +2: 체크리스트 3단계 (6~11월·12월 선택 등 원문 시점)
- +2: 기준일 + 보도자료·독자 확인 링크 묶음
- +2: 원문 비교·표기·고지 서술 (원문에 있을 때만)
- 감점: 원문 없는 「억」·월·표 등 환각 의심

**통과:** `total ≥ 9.5` **AND** `validation_ok` **AND** `reader_value ≥ 9.0` **AND** `originality ≥ 9.0`.

### 7.3 품질 루프

**스크립트:** `scripts/run_editorial_quality_loop.py`

- `EDITORIAL_QUALITY_MAX_ATTEMPTS` (기본 3)
- 매 시도 `write_editorial_quality_bundle`
- `passes`는 위 통합 조건

---

## 8. 산출물 (Artifact Bundle)

**모듈:** `engine/pipeline/editorial_report.py`

| 파일 | 내용 |
|------|------|
| `editorial_compare_{ts}.md` | 원문, 패킷, **채점 HTML**, 평문 4문단, 점수 |
| `editorial_quality_{ts}.json` | score + body_html + metadata |
| `editorial_ij_body_{ts}.html` | 발행/미리보기용 본문 |
| `editorial_quality_score.json` | 최신 시도 요약 |

**원칙:** compare MD에 있는 HTML = 채점·검증에 사용한 HTML (`normalize_ij_body_html`).

---

## 9. 진입점

| 용도 | 명령 |
|------|------|
| 품질 루프 (권장) | `REVIEW_ONLY=1 EDITORIAL_PIPELINE=1 IJ_PACKET_PIPELINE=1 .venv/bin/python scripts/run_editorial_quality_loop.py` |
| 단일 리뷰 | `... run_editorial_review_fixture.py --purpose [--url URL]` |
| 캐시 원문 테스트 | `FIXTURE_SOURCE_MD=review_outputs/editorial_compare_*.md EDITORIAL_REQUIRE_FULL_SOURCE=0 ...` |
| 단위 테스트 | `.venv/bin/python -m pytest tests/ -q --ignore=tests/fixtures` |

**운영 배치 (미래):** `engine.py` + `EDITORIAL_PIPELINE=1`, IJ만 `editorial_ctx` — v2 패킷은 `run_pre_publish_pipeline` 내부에서 생성.

---

## 10. v1 → v2 구현 단계

### Phase A — 설계·문서 (현재)

- [x] 본 설계 문서
- [ ] `editorial-pipeline.md`에 v2 링크·env 추가

### Phase B — 패킷 v2 (오프라인 가능)

- [ ] `ResearchPacket` + `to_dict()`에 `reader_utility`, `research_meta`
- [ ] `reader_utility.py` 규칙 추출 + unit tests (fixture JSON)
- [ ] 패킷 빌드 후 **원문 substring 검증기**

### Phase C — 프롬프트·재작성

- [ ] `packet_writer`에 `[독자 가치]` 블록
- [ ] LLM 패킷 빌드(선택) — 인용만

### Phase D — 게이트·채점

- [ ] `reader_value` 차원 + 가중치 재정의
- [ ] `passes` = score + validate + reader_value
- [ ] finalize 주입 fact-group 일반화

### Phase E — E2E·회귀

- [ ] evidence fetch 안정화 (타임아웃·재시도·mock tests)
- [ ] 품질 루프 2종 URL fixture (정책브리핑 + 다른 도메인 1건)
- [ ] 222605 대비 v2 번들 diff 체크리스트 (수동)

### Phase F — 배포 (별도 계획)

- [ ] `main` 머지 금지 유지 until sign-off
- [ ] Actions env·`REVIEW_ONLY=0` 스모크

---

## 11. 성공 기준 (Acceptance)

1. **서로 다른 주제** IJ 후보 2건 이상에서 동일 스크립트로 번들 생성.
2. 각 번들에서 `reader_utility`가 비어 있지 않거나, 비어 있으면 **reader_value < 7로 통과 불가**.
3. compare MD의 HTML을 오프라인 재채점 시 **저장된 score와 ±0.2 이내**.
4. 원문에 없는 수치·날짜가 본문에 없음 (샘플 10건 수동 감사).
5. pytest editorial 관련 전부 PASS.

---

## 12. 리스크

| 리스크 | 완화 |
|--------|------|
| korea.kr fetch 실패 | fallback 정책 문서화; 테스트는 `FIXTURE_SOURCE_MD` |
| finalize 주입이 “인공적” | reader_value는 **패킷에 있는 문장만**; 주입은 fact 라벨 기반 |
| LLM 패킷 환각 | substring / source 태그 검증 필수 |
| 뉴스엔진과 차별 모호 | reader_utility 없으면 **발행 등급 C 제한** 또는 IJ 스킵 검토 |

---

## 13. 용어

| 용어 | 의미 |
|------|------|
| **원문** | ingest后的 `article.body` |
| **패킷** | `ResearchPacket` v2 dict |
| **증거** | Tier A/B/C `evidence[]` |
| **독자 가치** | `reader_utility` — 행동·확인·예시·기준일 |
| **번들** | 동일 `ts`의 compare + json + html |
| **통과** | validate + score + reader_value 하한 |

---

## 14. 변경 이력

| 날짜 | 변경 |
|------|------|
| 2026-05-28 | 초안: 범용 워크플로우, packet v2, reader_utility, 게이트·번들·단계 |
