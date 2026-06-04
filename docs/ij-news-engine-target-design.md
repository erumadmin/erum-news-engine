# IJ 뉴스엔진 목표 설계 (Target Architecture)

**Status:** Superseded by product goal — see **[ij-news-engine-target-design-v4.md](./ij-news-engine-target-design-v4.md)** (Publish-First)  
**Date:** 2026-05-28  
**Repo:** `erum-news-engine`  
**Supersedes:** 제품 정의 관점에서 [ij-editorial-workflow-v3-design.md](./ij-editorial-workflow-v3-design.md)를 **구체화·통합** (v3 파이프라인 상세는 v3 문서 유지)  
**Related:** [editorial-pipeline.md](./editorial-pipeline.md), [ij-editorial-workflow-v2-design.md](./ij-editorial-workflow-v2-design.md), **[ij-news-engine-target-design-v4.md](./ij-news-engine-target-design-v4.md)**

---

## 0. 한 페이지 요약

| | |
|---|---|
| **North Star** | NGO·사회적 기업·사회공헌 업계가 **검증된 현장·연대 브리핑**으로 IJ를 인용·공유하게 한다. |
| **엔진이 하는 일** | 보도자료(신호) → **공식 자료 조사** → **조사 fact + 연대 렌즈**로 IJ 집필 → **조사 없으면 발행·통과 불가**. |
| **엔진이 하지 않는 일** | 보도자료 요약만, 점수 9.5만, LLM 상식 보강, 일반 대중 속보 경쟁. |
| **v2 대비** | v2 = 패킷·독자가치·채점. **Target = 조사·discovered·연대 brief·research 게이트**가 제품 핵심. |

---

## 1. 1차 독자 & 권위 정의

### 1.1 Primary audience

**NGO, 사회적 기업, 사회공헌(기업 CSR·재단·플랫폼) 업계 실무자.**

읽는 이유: 파트너·수혜자에게 **정책 변화를 설명**, 내부 보고·연대 공지·제안서에 **공식 근거**를 붙이기 위함.

### 1.2 “좋은 IJ 기사” = 현장·연대 브리핑 (5조건)

발행·통과의 **편집 정의** (점수와 별개):

1. **대상·예외** — 누가 해당/제외인지 원문·조사에 근거해 명시  
2. **현장 행동** — 확인 URL·문의·신청·고지·연계 창구 1~2개  
3. **추가 공식 1건+** — 원문에 없던 fact가 **fetch 발췌**와 함께 본문·번들에 표시 (`discovered_facts`)  
4. **한계·공백** — 자율·예정·미시행·범위 제한을 4문단 `다만`에  
5. **연대 렌즈** — `journalist_brief`가 “우리 현장·파트너에게 무엇이 열리는가”에 답 (invent 금지)

### 1.3 권위 지표 (엔진이 추적할 것)

| 지표 | 용도 |
|------|------|
| `briefing_ready` | 위 5조건 자동 판정 (bool) |
| `discovered_count` | 조사 기여 |
| `research_depth` | 조사 깊이 0–10 |
| `publish_grade` | A/B만 자동 발행 후보, C는 REVIEW_ONLY·수동 |
| Human sample | 분기 N편 “현장 브리핑 아님” 비율 (엔진 밖) |

**Anti-KPI:** total 9.5만, 월 발행 수만, 키워드 노출만.

---

## 2. 시스템 아키텍처

```
                    ┌─────────────────────────────────────┐
                    │         INGEST (Tier A)              │
                    │  korea.kr / fixture / full page      │
                    └──────────────────┬──────────────────┘
                                       ▼
                    ┌─────────────────────────────────────┐
                    │  ROUTE + FILTER (IJ profile)         │
                    │  정책·제도·지원 신호만 IJ 후보        │
                    └──────────────────┬──────────────────┘
                                       ▼
┌──────────────────────────────────────────────────────────────────┐
│  RESEARCH CORE (Target — v3)                                      │
│  B: 원문 링크  C: .go.kr·한전·참가격·NGO 관련 공식 URL (필수 시도) │
│  → evidence[] (fetch ok + excerpt)                                │
│  → discovered_facts[] (원문 ⊄ excerpt)                          │
│  → research_depth, risk_flags                                     │
│  → gate: depth < min OR discovered < min → research_insufficient │
└──────────────────┬───────────────────────────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────────────────────┐
│  PACKET v3                                                        │
│  key_facts, reader_utility (v2)                                   │
│  + source_facts, discovered_facts, journalist_brief (연대)        │
│  + coalition_gaps[] (원문·발췌에 있는 미비·한계만)                 │
│  publish_grade A|B|C|D                                            │
└──────────────────┬───────────────────────────────────────────────┘
                   ▼
        research_insufficient? ──yes──► SKIP rewrite (Target 기본)
                   │ no
                   ▼
┌──────────────────────────────────────────────────────────────────┐
│  REWRITE                                                          │
│  system: news_editor_ij + news_editor_common (유지)               │
│  user: packet_writer Target template                              │
│    [연대 브리프] [조사 확인 사실] [원문] [패킷] [증거]              │
└──────────────────┬───────────────────────────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────────────────────┐
│  FINALIZE + VALIDATE + SCORE                                      │
│  inject: reader, originality, discovered (발췌만)                 │
│  pass: validation_ok AND briefing_ready AND research_depth≥7      │
└──────────────────┬───────────────────────────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────────────────────┐
│  BUNDLE (REVIEW_ONLY / 운영)                                      │
│  editorial_compare: 원문 | discovered | coalition | IJ 본문      │
│  editorial_quality.json: briefing_ready, dimensions               │
└──────────────────────────────────────────────────────────────────┘
```

**기본 정책:** `research_insufficient`이면 **LLM 재작성 호출 안 함** (보도자료 다듬기 방지).  
`REVIEW_ONLY=1` 품질 루프에서는 compare MD에 **“조사 실패 — 브리핑 미생성”** 기록.

---

## 3. 데이터 모델 (ResearchPacket v3 + 연대)

### 3.1 `journalist_brief` (연대 필드)

```json
{
  "lead_question": "우리 파트너·수혜자에게 이번 제도가 무엇을 바꾸나?",
  "why_now": "시행·고지 시점 (원문·조사만)",
  "who_should_care": ["협력 NGO", "소상공인 SE", "..."],
  "reader_tasks": ["대상 여부 확인", "공식 FAQ URL", "연대 공지 초안용 체크"],
  "coalition_gaps": ["아직 의무 아님", "특정 업종 제외", "..."]
}
```

- 생성: **규칙 우선** (원문·패킷·discovered에서 추출), LLM 보조 시 **substring 검증**  
- `coalition_gaps`: 원문·발췌에 있는 한계 문장만; 없으면 빈 배열

### 3.2 `discovered_fact`

```json
{
  "fact": "…",
  "source_url": "https://…",
  "excerpt": "80자+",
  "role": "eligibility|procedure|deadline|faq|contact|statistics",
  "audience_tag": "field_partner|grantee|coalition"
}
```

### 3.3 `briefing_ready` (산출 메타)

```json
{
  "briefing_ready": true,
  "checks": {
    "eligibility_clear": true,
    "field_action_urls": true,
    "discovered_min": true,
    "limits_paragraph": true,
    "coalition_framing": true
  },
  "fail_reasons": []
}
```

`score_editorial_rewrite` 통과에 **`briefing_ready` 필수** (Target).

---

## 4. 조사 (Research) — Target 동작

### 4.1 Tier 정책

| Tier | | Target |
|------|---|--------|
| A | 원문 | 필수 |
| B | 원문 내 링크 | max_fetch 내 우선 |
| C | tier_c (한전, .go.kr, 참가격 등) | **IJ 후보는 항상 1회 이상** (`TIER_C_ENABLED=1`) |
| D | site-limited search | Phase 4, feature flag |

### 4.2 discovered 추출

- 모듈: `engine/pipeline/discovered_facts.py`  
- 입력: fetch ok `evidence[].excerpt`, 원문 plain text  
- 규칙: excerpt 문장 중 원문에 **부분 문자열 없음** → 후보 → 길이·역할 태깅  
- LLM 요약으로 discovered 생성 **금지** (Phase 1)

### 4.3 `research_depth` & 게이트

| Env | Default |
|-----|---------|
| `RESEARCH_MIN_OK_EVIDENCE` | 1 |
| `RESEARCH_MIN_DISCOVERED_FACTS` | 1 |
| `RESEARCH_DEPTH_MIN` | 7.0 |
| `RESEARCH_INSUFFICIENT_SKIP_REWRITE` | 1 |
| `RESEARCH_FETCH_RETRIES` | 2 |

`research_insufficient` → `publish_grade` 최대 **C**, `briefing_ready` false.

### 4.4 NGO 관점 URL 우선순위 (Tier C 힌트)

`tier_c` URL 후보 가중:

1. 본문 `action_items` / reader URL (한전ON, 부처 포털)  
2. 본문 부처·제도 키워드 → `.go.kr`  
3. (Phase 2) 복지·고용·중기부 등 **협약·지원 FAQ** 패턴

---

## 5. 재작성 (Rewrite) — Target 템플릿

### 5.1 역할 분리

| 층 | 담당 |
|----|------|
| System | `news_editor_ij` — 솔루션 저널리즘·4문단·환각 금지 (유지) |
| User | Target template — **연대 독자·조사 fact·브리프** |

### 5.2 User 메시지 블록 (순서)

1. **[연대 브리프]** — `journalist_brief`  
2. **[조사에서 확인한 사실]** — `discovered_facts` + evidence 발췌  
3. **[수집 원문]** — 전문 (cap)  
4. **[리서치 패킷]** — JSON  
5. **[독자 가치]** — `reader_utility` (v2)  
6. **[독창성·재구성]** — originality guidance (discovered 반영)  
7. **[독자 확인 경로]** — action_items  
8. **[추가 근거]** — evidence  

### 5.3 집필 규칙 (추가)

- **1문단:** `lead_question`에 답; 수혜·변화  
- **2문단:** 배경·문제 (연대 맥락)  
- **3문단:** 작동·**discovered 1건 이상**·URL  
- **4문단:** `다만` + `coalition_gaps`  
- 톤: **현장 브리핑** (보도자료 복사·홍보체 금지)

### 5.4 Finalize

v2 유지 + `inject_discovered_fact_anchors` (발췌 substring만).

---

## 6. 품질 게이트

### 6.1 통과 조건 (Target)

모두 만족:

- `validate_ij_editorial_rewrite` OK  
- `research_depth ≥ RESEARCH_DEPTH_MIN`  
- `discovered_facts` 패킷에 ≥ `RESEARCH_MIN_DISCOVERED_FACTS` 이면 본문 반영  
- **`briefing_ready == true`**  
- `publish_grade` ∈ {A, B} (자동 발행 경로)

### 6.2 채점 가중치 (안)

| 차원 | % | 비고 |
|------|---|------|
| structure | 18 | 4p IJ |
| facts | 18 | + discovered 누락 |
| utility | 10 | |
| editorial | 10 | |
| reader_value | 8 | v2 |
| originality | 8 | + reader_tasks, discovered |
| **coalition_briefing** | **10** | briefing_ready 세부 |
| **research_depth** | **10** | |
| qa_proxy | 8 | |

`TARGET_SCORE=9.5`, `TARGET_RESEARCH_DEPTH=7`, `TARGET_BRIEFING=9` (coalition 차원).

### 6.3 v2와의 호환

- `packet_version` 2 → 기존 루프 동작; env `IJ_TARGET_ENGINE=0`  
- `IJ_TARGET_ENGINE=1` (기본 Target 배포 시): v3 게이트 전부 적용

---

## 7. 산출물 (Bundle)

### 7.1 `editorial_compare_*.md` 섹션

```markdown
## 브리핑 적합성
- briefing_ready: true/false
- research_depth: 8.5
- discovered: 2건

## 조사에서 확인 (원문에 없음)
- [procedure] https://… — "발췌…"

## 연대 브리프
- lead_question: …
- reader_tasks: …

## 원문 vs IJ …
```

### 7.2 발행 정책

| Grade | REVIEW_ONLY | Production (미래) |
|-------|-------------|-------------------|
| A, B + briefing_ready | compare 저장, 통과 표시 | 발행 허용 |
| C | compare + “수동 검토” | 기본 미발행 |
| D / research_insufficient | rewrite skip 로그 | DROP |

---

## 8. 모듈 맵 (구현)

| 모듈 | 상태 | Target 변경 |
|------|------|-------------|
| `orchestrator.py` | v2 | research gate → skip rewrite |
| `research_collector.py` | v2 | packet v3 fields, call discovered |
| `discovered_facts.py` | **신규** | |
| `research_depth.py` | **신규** | |
| `coalition_brief.py` | **신규** | journalist_brief + briefing_ready |
| `tier_c.py` | v2 | IJ mandatory pass |
| `packet_writer.py` | v2 | Target template |
| `rewrite_validate.py` | v2 | discovered + briefing checks |
| `editorial_scorecard.py` | v2 | coalition + research dims |
| `editorial_report.py` | v2 | compare sections |
| `prompts/news_editor_ij.md` | v2 | 1차 독자 한 줄 (NGO·SE) |

---

## 9. 구현 Phase

### Phase 0 — 설계 고정 (지금)

- [x] 본 문서  
- [ ] v3 design §1 Primary audience 링크

### Phase 1 — 조사·패킷 (2주 목표)

- [ ] `discovered_facts.py`, `research_depth.py`  
- [ ] `run_research_pipeline` v3 packet  
- [ ] orchestrator: `research_insufficient` + skip rewrite  
- [ ] tests + fixture (전기요금 + 위생 1건)

### Phase 2 — 연대 brief & rewrite (1주)

- [ ] `coalition_brief.py`  
- [ ] `packet_writer` Target template  
- [ ] `news_editor_ij.md` 독자 명시

### Phase 3 — 게이트·번들 (1주)

- [ ] `briefing_ready` validator + scorecard  
- [ ] compare MD 섹션  
- [ ] `IJ_TARGET_ENGINE=1` 품질 루프 3주제 회귀

### Phase 4 — 운영

- [ ] fetch 안정화, Tier D optional  
- [ ] human briefing audit 워크플로 (스프레드시트)  
- [ ] main 머지 별도 승인

---

## 10. 성공 기준 (Launch)

1. **3주제** fixture에서 `briefing_ready=true`, `discovered≥1`, compare에 조사 섹션.  
2. **조사 0건** 실행 시 rewrite **미호출** + 루프 **fail**.  
3. 편집자 5편 샘플: “NGO·SE 현장 브리핑으로 공유 가능” **≥ 4/5**.  
4. `094315` 유형(증거 0, 9.92)은 Target env에서 **통과 불가**.

---

## 11. 명시적 비목표

- NN/CB Target화 (IJ만)  
- 실시간 전체 웹 검색  
- LLM이 “알고 있는” 사실 보강  
- 일반 독자용 클릭베이트 제목  
- 점수만 올리는 finalize 주입 확대 (discovered는 **발췌만**)

---

## 12. 용어

| 용어 | 정의 |
|------|------|
| **현장·연대 브리핑** | NGO·SE가 인용·공지에 쓸 수 있는 검증된 IJ 기사 |
| **discovered** | 원문에 없고 공식 URL 발췌에 있는 fact |
| **briefing_ready** | §1.2 다섯 조건 자동 판정 |
| **research_insufficient** | depth/discovered 미달 — Target에서 rewrite 금지 |

---

## 변경 이력

| 날짜 | 내용 |
|------|------|
| 2026-05-28 | Target 설계: North Star, NGO·SE 1차 독자, briefing_ready, skip rewrite, 모듈·Phase |
