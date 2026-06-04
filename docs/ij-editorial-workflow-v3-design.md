# IJ 편집 파이프라인 v3 — 기자형 리서치·작성 설계

**Status:** Draft (설계만, 미구현)  
**Date:** 2026-05-28  
**Repo:** `erum-news-engine` (feature: `feat/ij-editorial-pipeline-test`)  
**Supersedes (부분):** [ij-editorial-workflow-v2-design.md](./ij-editorial-workflow-v2-design.md) — v2는 **패킷·독자가치·채점 번들**까지 구현; v3는 **제품 정의·리서치·작성 철학**을 바꾼다.  
**Related:** [editorial-pipeline.md](./editorial-pipeline.md), [research-pipeline-implementation-plan.md](./research-pipeline-implementation-plan.md), **[ij-news-engine-target-design.md](./ij-news-engine-target-design.md)** (통합 목표·아키텍처)

---

## 0.1 Primary audience (Target)

**1차 독자:** NGO, 사회적 기업, 사회공헌 업계 실무자.  
**편집 목표:** 검증된 **현장·연대 브리핑** — 상세는 [ij-news-engine-target-design.md §1](./ij-news-engine-target-design.md#1-1차-독자--권위-정의).

---

## 0. 한 문장 정의

**v3:** 정책브리핑 **원문을 출발점**으로 삼고, **관련 공식 자료를 조사해 추가 사실을 발견**한 뒤, **기자 관점으로 IJ 기사**를 쓴다.  
사실은 **원문 ∪ 조사에서 확인한 출처**에만 존재해야 하며, 조사 없이 원문만 다듬은 글은 **등급·통과에서 불리**하다.

---

## 1. v2와 v3의 차이 (왜 v3인가)

| 관점 | v2 (현재 구현) | v3 (목표) |
|------|----------------|-----------|
| **원문 역할** | 1차 근거 + fact 검증 기준 | **이슈 인지·판단 재료** (“파볼까?”) |
| **리서치** | 원문/HTML 링크 fetch 시도, 실패해도 진행 가능 | **관련 자료 조사** — 추가 fact **발견**이 목적 |
| **패킷** | 원문 요약 + `reader_utility` | + **`discovered_facts`** (출처 URL·발췌·역할) |
| **재작성** | “세 곳에 없는 사실 금지” (보수적) | “**조사에서 확인한 사실** + 기자 구성·관점” |
| **통과** | 형식 + reader_value + originality | + **`research_depth` 하한** (조사 깊이) |
| **실패 모드** | fetch 없음 → `official_evidence_missing`만 | 조사 부족 → **작성 보류·등급 C·루프 재시도** |

v2가 “원문 다듬기 엔진”처럼 느껴진 이유는 **리서치가 선택적**이고, **조사에서 온 사실과 원문 사실이 패킷에서 구분되지 않기 때문**이다. v3는 그 구분과 **조사 필수화**로 제품을 맞춘다.

---

## 2. 기자 워크플로 (제품 모델)

```
┌──────────────────────────────────────────────────────────────┐
│ 1. 인지 (INGEST)                                              │
│    보도자료/브리핑 전문 수집 → “무슨 일인지” 파악              │
└────────────────────────────┬─────────────────────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────────┐
│ 2. 판단 (ROUTE + FILTER)                                      │
│    IJ 후보인가? 파볼 가치 있는가?                             │
└────────────────────────────┬─────────────────────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────────┐
│ 3. 조사 (RESEARCH v3)  ★ v3 핵심                              │
│    원문 링크 + Tier C + (선택) 제한 검색                       │
│    → 공식 페이지에서 **원문에 없던 사실** 발췌·태깅            │
└────────────────────────────┬─────────────────────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────────┐
│ 4. 메모 (PACKET v3)                                           │
│    source_facts + discovered_facts + reader_utility           │
│    + journalist_brief (누구·왜 지금·독자 질문)                 │
└────────────────────────────┬─────────────────────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────────┐
│ 5. 집필 (REWRITE v3)                                          │
│    기자 시각: 선택·순서·강조 (사실 invent 아님)                │
└────────────────────────────┬─────────────────────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────────┐
│ 6. 교정 (FINALIZE + GATE + QA + BUNDLE)                       │
│    v2와 동일 + research_depth·discovered 반영 채점            │
└──────────────────────────────────────────────────────────────┘
```

**기자가 하지 않는 것 (여전히 금지):**

- 원문·조사 출처에 없는 **수치·일정·표·FAQ** 생성
- 익명 제보·소셜만으로 사실 단정
- 조사 없이 **보도자료 문장 순서만 바꾼** 기사를 “완성”으로 제출

---

## 3. 운영 규칙 (v2 계승)

| 규칙 | 내용 |
|------|------|
| **main 머지 금지** | feature 브랜치·`REVIEW_ONLY` 검증 |
| **환각 금지** | 본문 fact = `source_facts` ∪ `discovered_facts` (각각 출처 필수) |
| **번들 일치** | compare MD HTML = 채점·검증 HTML |

---

## 4. 조사 (Research) v3

### 4.1 조사 범위 (허용)

| Tier | 소스 | v3 역할 |
|------|------|---------|
| **A** | 원문 URL 본문 | `source_facts` |
| **B** | 원문 HTML 내 링크 | 1차 조사 타깃 |
| **C** | 본문·부처 힌트 기반 공식 URL (한전, 참가격, `.go.kr`) | **discovered_facts** 후보 |
| **C+** (선택) | `TIER_C_USE_LLM` URL 힌트 → **반드시 HTTP fetch 후** 발췌만 사용 | v2와 동일 원칙 |
| **D** (Phase 2) | allowlist 사이트 **내부 검색 API** (site:kepco.co.kr 등) | 원문 키워드로 페이지 찾기 → fetch |

**비목표 (v3 Phase 1):** 구글 전체 자유 검색, 뉴스 DB, 페이월 크롤, LLM이 “알고 있는 세계지식”으로 사실 보강.

### 4.2 “새 사실”의 정의

**discovered_fact** = 원문 본문에 **없던** 문장·수치·절차이며, **조사 URL fetch ok** 발췌에 **부분 문자열로 존재**하는 항목.

```json
{
  "fact": "12월부터 가장 유리한 요금을 선택해 적용받을 수 있다.",
  "source_url": "https://online.kepco.co.kr/...",
  "excerpt": "…발췌 80자 이상…",
  "role": "procedure|faq|statistics|deadline",
  "discovered_at": "2026-05-28T12:00:00+09:00"
}
```

- 원문에 이미 있는 문장은 `source_facts` / `key_facts` — **discovered가 아님** (중복 태깅 금지).
- 발췌에 없으면 **discovered로 등록 불가** (LLM 요약 금지, Phase 1).

### 4.3 조사 파이프라인 (알고리즘)

| Step | 처리 | 모듈 (예정) |
|------|------|-------------|
| R1 | v2와 동일: `build_evidence_plan` + fetch | `research_collector.py` |
| R2 | fetch ok 발췌에서 **원문 미포함** 문장 추출 | `discovered_facts.py` (신규) |
| R3 | Tier C **필수 실행** (v3): `official_evidence_missing`이면 **최소 N건 fetch 재시도** | `tier_c.py` |
| R4 | `research_depth` 산출 (0–10) | `research_depth.py` (신규) |
| R5 | depth &lt; 하한 → `risk_flags: research_insufficient` | orchestrator |

**환경변수 (안):**

| Variable | Default | Meaning |
|----------|---------|---------|
| `RESEARCH_MIN_OK_EVIDENCE` | `2` | fetch ok + 발췌 80자+ 최소 건수 |
| `RESEARCH_MIN_DISCOVERED_FACTS` | `1` | discovered_facts 최소 건수 (원문에 없는 fact) |
| `RESEARCH_DEPTH_MIN` | `7.0` | 작성·통과 허용 하한 |
| `RESEARCH_FETCH_RETRIES` | `2` | URL fetch 재시도 |

### 4.4 research_depth (0–10) — 조사 깊이

| 점수 | 조건 (예) |
|------|-----------|
| +2 | fetch ok **≥ RESEARCH_MIN_OK_EVIDENCE** |
| +2 | **discovered_facts ≥ RESEARCH_MIN_DISCOVERED_FACTS** |
| +2 | reader_action URL(한전·참가격 등) **fetch ok** 1건 이상 |
| +2 | 발췌가 본문 **인용**에 사용될 수준 (길이·도메인) |
| +2 | 원문 대비 **고유 호스트** 2개 이상 조사 성공 |

**통과:** `research_depth ≥ RESEARCH_DEPTH_MIN` (기본 7).  
조사가 약하면 **재작성 전**에 Tier C 재실행 또는 **등급 C + 품질 루프 실패** (정책 선택).

---

## 5. 패킷 (ResearchPacket v3)

v2 필드 **전부 유지** + 아래 추가.

### 5.1 신규 필드

```json
{
  "research_meta": {
    "packet_version": 3,
    "ingest_source": "full_page",
    "research_depth": 8.5
  },
  "source_facts": [
    { "fact": "…", "source": "lead_article", "url": "https://www.korea.kr/…" }
  ],
  "discovered_facts": [
    { "fact": "…", "source_url": "https://online.kepco.co.kr/…", "excerpt": "…", "role": "faq" }
  ],
  "journalist_brief": {
    "lead_question": "소규모 사업자 전기요금이 어떻게 바뀌나?",
    "why_now": "다음 달 시행",
    "who_should_care": ["일반용(갑)Ⅱ", "…"],
    "reader_tasks": ["6~11월 고지서 비교", "12월 요금 선택", "한전ON 확인"]
  },
  "reader_utility": { }
}
```

- **`journalist_brief`:** LLM(선택) 또는 규칙 — **원문·discovered에서만** 추출. invent 금지.
- **`source_facts` vs `key_facts`:** `key_facts`는 v2 호환; v3에서는 `source_facts`에 출처 태그 명시.

### 5.2 publish_grade (v3 조정)

| Grade | 조건 (개념) |
|-------|-------------|
| **A** | research_depth ≥ 8, discovered ≥ 2, substantive official ≥ 2 |
| **B** | research_depth ≥ 7, discovered ≥ 1 |
| **C** | 원문만 충실, 조사 약함 — **발행·통과 제한** |
| **D** | 본문·사실 부족 — DROP |

`announcement_only_risk` + `research_insufficient` → **최대 C**.

---

## 6. 재작성 (Rewrite) v3

### 6.1 프롬프트 철학 변경

**v2:**

> 아래 [수집 원문], [리서치 패킷], [추가 근거]에 있는 사실만 사용…

**v3:**

> 당신은 정책 데스크 기자다. [수집 원문]으로 이슈를 파악했고, [조사에서 확인한 사실]을 추가로 확보했다.  
> **원문과 조사 발췌에 있는 사실만**으로 독자가 행동할 수 있는 IJ 기사를 작성한다.  
> 조사에서 확인하지 못한 내용은 쓰지 않는다. **기자 관점**은 사실 선택·순서·강조·독자 질문에 답하는 구조다.

### 6.2 입력 블록

| 블록 | 내용 |
|------|------|
| [수집 원문] | v2 동일 |
| [조사에서 확인한 사실] | `discovered_facts` + evidence 발췌 (신규) |
| [기자 브리프] | `journalist_brief` (신규) |
| [리서치 패킷] | v2 JSON |
| [독자 가치] | `reader_utility` |
| [독창성 가치] | v2 `originality` 힌트 — **discovered 반영**으로 갱신 |
| [추가 근거] | fetch ok evidence |

### 6.3 본문 규칙 (v2 유지 + v3)

- 4문단 IJ, 700~1100자, 환각 금지
- **discovered_facts 1건 이상** 본문에 반영 (발췌 substring 매칭 — 채점)
- **기준일 + 원문·독자 URL** (v2 reader_utility)
- **“다만”** + 한계 (v2)

### 6.4 Finalize (v2 + v3)

- v2: `inject_reader_utility_anchors`, `inject_originality_anchors`
- v3 추가: `inject_discovered_fact_anchors` — **미반영 discovered 1건**을 3문단에 발췌 일부 삽입 (원문 문자열)

---

## 7. 품질 게이트 (v3)

### 7.1 검증 (`validate_ij_editorial_rewrite`)

v2 전부 +

- `discovered_facts`가 패킷에 있으면: **최소 1건**이 본문에 발췌·fact 반영
- `research_insufficient` in risk_flags → **경고** 또는 hard fail (env `RESEARCH_DEPTH_HARD_FAIL=1`)

### 7.2 채점 (`score_editorial_rewrite`)

| 차원 | 가중치 (안) | v3 |
|------|-------------|-----|
| structure | 20% | v2 |
| facts | 20% | v2 + discovered 누락 감점 |
| utility | 12% | v2 |
| editorial | 12% | v2 |
| reader_value | 8% | v2 |
| originality | 8% | **discovered·기자 재구성** 반영 (루브릭 개정) |
| **research_depth** | **10%** | 패킷 `research_depth` 환산 |
| qa_proxy | 10% | v2 |

**통과 (안):**

- `total ≥ 9.5`
- `reader_value ≥ 9.0`
- `originality ≥ 9.0`
- **`research_depth ≥ 7.0`** (패킷·채점 이중)
- `validation_ok`

### 7.3 originality v3 (의미 개정)

v2 originality = 원문 **재구성** 체크리스트.  
v3 originality = v2 **+**

| 추가 | 점수 |
|------|------|
| discovered fact **1건 이상** 본문 반영 | +2 |
| 원문 첫 80자 **복붙** 아님 (v2 reframe) | (유지) |
| **journalist_brief.reader_tasks** 2개 이상 반영 | +2 |

**originality 10의 의미 (v3):** “원문만 잘 다듬음”이 아니라 **조사로 확인한 사실을 넣고 기자 관점으로 구성함** (여전히 **Google 독창 콘텐츠 보장 아님**).

---

## 8. 산출물 (Bundle v3)

v2 파일 + compare MD 섹션 추가:

```markdown
## 조사 요약 (research_depth: 8.5)

### discovered_facts
- [faq] https://online.kepco.co.kr/… : "…발췌…"

### fetch ok 증거
- …
```

`editorial_quality_{ts}.json`에 `research_depth`, `discovered_facts[]` 포함.

---

## 9. 구현 단계 (v2 위에 쌓기)

### Phase 1 — 조사·패킷 (오프라인·mock 가능)

- [ ] `docs/ij-editorial-workflow-v3-design.md` (본 문서) 리뷰
- [ ] `engine/pipeline/discovered_facts.py` — 발췌 → discovered 추출 + substring 검증
- [ ] `ResearchPacket` v3 필드 + `packet_version: 3`
- [ ] `research_depth.py` + unit tests
- [ ] orchestrator: depth &lt; min → `research_insufficient`

### Phase 2 — 작성·게이트

- [ ] `packet_writer` — [조사에서 확인한 사실], [기자 브리프]
- [ ] `validate` + `scorecard` — research_depth 차원·통과 조건
- [ ] `originality` v3 루브릭
- [ ] `editorial_report` — discovered 섹션

### Phase 3 — 조사 안정화

- [ ] fetch 재시도·타임아웃
- [ ] Tier C **필수** + `RESEARCH_MIN_*` env
- [ ] 품질 루프: 전기요금 + 위생용품 + **제3 주제** fixture

### Phase 4 — (선택) Tier D

- [ ] allowlist site search → fetch only
- [ ] 설계·보안 리뷰 후 feature flag

### Phase 5 — 배포

- [ ] v2/v3 env 문서, sign-off, `main` 별도 승인

**v2 완료 항목은 유지·재사용.** v3는 **삭제가 아니라 확장**.

---

## 10. 성공 기준 (Acceptance)

1. **서로 다른 주제 3건**에서 `discovered_facts ≥ 1` + compare MD에 출처 표시.
2. 조사 fetch ok **0건**인 실행은 `research_insufficient` → **품질 루프 미통과** (또는 grade C only).
3. 본문에 있는 **discovered** 주장은 전건 발췌 substring 매칭 (자동 테스트).
4. 원문에 없는 **억·월·표** 환각 0건 (샘플 감사).
5. 기자 관점 **수동 리뷰** 3건: “원문만 읽은 것보다 조사한 티가 난다” (정성).

---

## 11. 리스크

| 리스크 | 완화 |
|--------|------|
| fetch 실패 다수 | 재시도·fixture·REVIEW_ONLY; depth 하한으로 “가짜 조사” 방지 |
| discovered = 원문 중복 | substring dedup against source body |
| finalize 주입 과다 | v2와 동일 — **발췌만** 주입 |
| 기자 관점 = LLM 환각 | brief·본문 모두 출처 태그·검증기 |
| v2 점수 하락 | 가중치·하한 튜닝; v2 번들 regression 비교 |

---

## 12. 용어

| 용어 | 의미 |
|------|------|
| **원문** | ingest한 보도자료 본문 |
| **조사** | 원문 밖 공식 URL fetch + 발췌 |
| **discovered_fact** | 조사에서만 확인된 사실 (출처 필수) |
| **research_depth** | 조사 깊이 0–10 |
| **기자 관점** | 사실 선택·구성·독자 질문 (새 사실 invent 아님) |

---

## 13. 변경 이력

| 날짜 | 변경 |
|------|------|
| 2026-05-28 | v3 초안: 기자형 워크플로, discovered_facts, research_depth, 패킷·프롬프트·게이트 |
