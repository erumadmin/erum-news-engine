# IJ 뉴스엔진 목표 설계 v4 (Publish-First)

**Status:** Draft for approval — **v3 North Star를 대체하는 방향**  
**Date:** 2026-06-01  
**Repo:** `erum-news-engine`  
**Supersedes (제품 목표):** [ij-news-engine-target-design.md](./ij-news-engine-target-design.md) (v3 Target)  
**Keeps (파이프라인 상세):** [ij-editorial-workflow-v3-design.md](./ij-editorial-workflow-v3-design.md), [editorial-pipeline.md](./editorial-pipeline.md) — v4에 맞게 단계·게이트만 갱신 예정  
**Related:** [ij-editorial-workflow-v2-design.md](./ij-editorial-workflow-v2-design.md)

---

## 0. v3에서 v4로 바꾸는 이유 (한 페이지)

| | v3 (현재 문서·코드 쏠림) | **v4 (재설정)** |
|---|-------------------------|-----------------|
| **North Star** | NGO·SE가 **연대 브리핑**으로 인용 | **권위 있는 완성 기사**로 읽히고 인용 |
| **통과의 정의** | `briefing_ready` + 본문 URL + 9.5 | **`article_publish_ready`** + (내부) 조사·근거 번들 |
| **본문 링크** | `https://…` 노출이 검증·채점에 필요 | **발행 본문에는 링크 금지(노출 URL)** → 출처는 각주/하단 박스/CMS |
| **톤** | “연대·보고 관점에서…” 시사점 주입 | **정책·제도 뉴스** 톤 (솔루션 저널리즘, IJ 4문단) |
| **엔진이 만든 것** | compare MD + 브리핑형 본문 | **사이트에 올릴 기사 1편** + (부록) 검증 번들 |

**v3가 틀렸다는 뜻이 아님.** 조사·`discovered_facts`·연대 질문은 **유지**하되, **발행물이 아니라 내부 패킷·번들·편집 메모**로 격하한다.

---

## 1. 제1원칙 (처음부터 말한 목표 — 최우선)

> **산출물의 정체성은 “완성된 IJ 기사 1편”이다.**  
> 독자·동료 언론·정책 당사자가 **권위 있는 매체의 기사**로 읽을 수 있어야 한다.

### 1.1 “권위 있는 기사”란 (발행 기준)

아래를 **모두** 만족할 때만 발행·품질 루프 통과로 본다.

| # | 발행 기준 | 설명 |
|---|-----------|------|
| P1 | **완성도** | 제목·리드·4문단이 한 편의 정책 기사로 읽힘. 초안·메모·체크리스트 느낌이 아님 |
| P2 | **언론 톤** | 보도자료 문장 복붙·홍보체·“연대·보고 관점에서” 반복 오프너 없음 |
| P3 | **본문 무URL** | 본문 4문단 안에 `http://`, `https://`, `www.` **노출 없음** |
| P4 | **출처는 격리** | 확인 경로는 **기사 하단 「관련 링크」** 또는 CMS 하이퍼링크(앵커 문구만) |
| P5 | **리드=뉴스** | 무엇이·언제·누가 바뀌는지. NGO 업무 메모 리드가 아님 |
| P6 | **다만=한계** | 4문단은 진짜 한계·유의. 정책 확장·홍보 문장이 아님 |

**금지 예 (v3 파이프라인이 자주 만드는 패턴):**

- `보도자료 원문: https://www.korea.kr/...`
- `3. 단위 사양 축소 정보는…` (문단 번호 잔여)
- `연대·보고 관점에서 … 연대·보고 관점에서 …` (오프너 반복)
- 타 기사 fact 잔여 (예: 유턴지원단이 AI 기사에 등장)

### 1.2 v3의 “좋은 글 5조건”의 위치

v3 §1.2(대상·URL·discovered·다만·연대)는 **내부 편집·연대 활용**에는 유효하다.  
**발행 통과 조건이 되어서는 안 된다.** → §4 `internal_brief`로 이동.

---

## 2. North Star & 1차 독자 (v4)

### 2.1 North Star (한 문장)

> **정책·제도 변화를 IJ가 **완성된 기사**로 전달하고, 독자와 업계가 **언론사 기사**로 신뢰·인용한다.**

### 2.2 1차 독자 (발행)

| 독자 | 읽는 이유 |
|------|-----------|
| **정책·제도 관심 일반 독자** | 무엇이 바뀌는지, 내게 해당하는지 |
| **언론·정책 업계** | 사실 확인·맥락·비교 (동료 매체) |
| **NGO·SE·사회공헌** (2차) | 기사를 **인용**하되, 기사 자체는 브리핑 문서가 아님 |

**핵심:** NGO가 쓰는 것은 **부수 효과**이지, 글의 **장르 정의**가 아니다.

### 2.3 IJ 페르소나 (유지)

- 솔루션 저널리즘, 4문단, 사실·원문·조사 발췌만  
- 환각·상식 보강 금지  
- **추가:** “인용 가능한 정책 기사” 문체 (한겨레·연합 정책면·전문지 수준의 **간결함**)

---

## 3. 산출물 2층 (발행 vs 내부)

```
┌─────────────────────────────────────────────────────────┐
│  A. PUBLISH ARTICLE (유일한 “기사”)                      │
│  - title, excerpt, body_html (4p)                        │
│  - sources_footer[] 또는 CMS links (본문 밖)             │
│  - 독자에게 보이는 최종본                                 │
└─────────────────────────────────────────────────────────┘
                          ▲
                          │ publish_layer (strip URL, tone, lead)
┌─────────────────────────────────────────────────────────┐
│  B. INTERNAL BUNDLE (편집·검증용 — 사이트 본문 아님)        │
│  - discovered_facts, evidence excerpts                   │
│  - journalist_brief, coalition_gaps, reader_tasks        │
│  - editorial_compare.md (원문 | 조사 | 연대 메모 | A)     │
│  - briefing_ready (내부 QA만)                            │
└─────────────────────────────────────────────────────────┘
                          ▲
                          │ research + packet v3 fields
┌─────────────────────────────────────────────────────────┐
│  C. RESEARCH CORE (유지)                                 │
│  - evidence fetch, discovered_facts, research_depth      │
│  - research_insufficient → rewrite skip (유지 가능)        │
└─────────────────────────────────────────────────────────┘
```

**규칙:** 채점·검증이 **A를 망가뜨려서** B를 채우면 **실패**. (v3의 구조적 오류)

---

## 4. 내부 품질 (v3 유산 — `internal_brief`)

발행과 **분리**된 편집 체크리스트. compare MD·패킷에만 기록.

| # | 내부 기준 | 용도 |
|---|-----------|------|
| I1 | 대상·예외 | 패킷·편집 메모 |
| I2 | discovered ≥1 + 발췌 URL | 조사 기여 |
| I3 | reader_tasks / coalition_gaps | 연대 활용 시 |
| I4 | `research_depth` ≥ 7 | 조사 게이트 |
| I5 | `briefing_ready` (연대 5조건) | **내부** “연대용으로도 쓸 수 있는가” |

**`briefing_ready`는 v4에서 `passes`에 포함하지 않는다** (기본안).

---

## 5. 재작성·Finalize (v4 규칙)

### 5.1 Rewrite 프롬프트 1순위 지시

```
당신이 쓰는 것은 사이트에 게시될 완성 기사다.
- 정책·제도 뉴스 문체. 브리핑 메모·내부 공유 문서 아님.
- 본문에 URL을 넣지 말 것. 출처는 [관련 링크] 블록에만.
- "연대·보고 관점에서"로 문단을 시작하지 말 것.
- 4문단, 마지막은 다만 + 실질적 한계·유의.
```

연대 브리프·조사 fact는 **참고 자료**로만 넣고, **문장 그대로 끼워 넣지 않음**.

### 5.2 Finalize 2단계

| 단계 | 함수(개념) | 하는 일 |
|------|------------|---------|
| **Draft finalize** | (기존) 사실·4문단·discovered **문장** 반영 | 조사·사실 정합 |
| **Publish finalize** | **`publish_sanitize_body`** (신규) | 본문 URL 제거→`sources_footer`, 오프너·번호 정리, 리드 정규화 |

### 5.3 출처 표기 (발행 표준)

**본문:** 앵커만 허용 — 예: “한전 누리집”, “참가격”, “산업통상부 보도자료”

**하단 (필수):**

```markdown
## 관련 링크
- 보도자료 원문 (대한민국 정책브리핑)
- 한전 요금 안내
- …
```

또는 CMS `related_links[]` — **독자 UI는 매체 스타일가이드** 따름.

---

## 6. 품질 게이트 (v4)

### 6.1 발행 통과 (`article_publish_ready`)

**모두** 만족 시 품질 루프 exit 0:

| 게이트 | 검사 |
|--------|------|
| `validate_publish_article` | P1–P6 (§1.1) |
| `validate_ij_editorial_rewrite` | 4문단·사실·환각 (기존, **단 URL-in-body 검사 제거**) |
| `research_depth` ≥ 7 | 조사 부족 시 스킵 정책 유지 가능 |
| discovered | 패킷·번들에 ≥1; **본문에는 자연스러운 문장**으로만 |
| **`TARGET_SCORE` ≥ 9.5** | **v4 가중치** (§6.2) |

### 6.2 채점 v4 (안)

**발행 품질이 대부분.** 연대·URL 반영 점수는 **내부 차원**으로만.

| 차원 | % | 비고 |
|------|---|------|
| **article_voice** | 22 | 언론 톤, 오프너·반복·메모체 |
| **lead_quality** | 15 | 제목·리드=뉴스 |
| structure | 12 | 4p IJ |
| facts | 15 | 원문·discovered 정합 |
| **prose_cleanliness** | 12 | **본문 무URL**, 번호 잔여, 문단 역할 |
| editorial | 8 | 솔루션 저널리즘 |
| utility | 8 | 독자 행동은 **문장**으로 (URL 아님) |
| originality | 8 | 재구성 (본문 URL 점수 **삭제**) |
| research_depth | 5 | 내부·가중치 축소 |
| qa_proxy | 5 | |

**제거·강등:** `coalition_briefing` 본문 점수화, `primary_links` 본문 반영 점수.

`TARGET_SCORE=9.5` 유지 가능하나, **의미가 “발행 기사 9.5”**로 바뀜.

### 6.3 Anti-KPI (v4)

- 본문에 URL 넣어서 `reader_value`·`originality` 채우기  
- `briefing_ready=true`인데 발행 기사로 못 읽힘  
- 9.5 통과 = 성공 (단독)  
- compare MD만 좋고 publish body는 브리핑체  

---

## 7. 아키텍처 (v4 흐름)

```
INGEST → ROUTE → RESEARCH CORE (동일)
       → PACKET (v3 필드 + internal_brief)
       → research_insufficient? → skip
       → REWRITE (publish-first prompt)
       → DRAFT FINALIZE (facts, 4p, discovered prose)
       → PUBLISH FINALIZE (strip URLs, sources_footer, lead fix)
       → validate_publish_article + validate_ij (no body URL rule)
       → SCORE (v4 weights)
       → BUNDLE: compare = 원문 | internal brief | PUBLISH article
```

**환경 변수 (안):**

| Env | 의미 |
|-----|------|
| `IJ_TARGET_ENGINE=1` | research + packet v3 |
| `IJ_PUBLISH_V4=1` | publish-first gates + sanitize (**v4 기본**) |

---

## 8. v3 코드와의 대응 (이후 구현 Phase)

| v3 동작 | v4 조치 |
|---------|---------|
| `inject_scorecard_slots` 본문 URL append | **금지** → `sources_footer`만 |
| `inject_coalition_field_takeaways` 1문단 오프너 | **옵션** / publish에서 제거 |
| `_url_reflected_in_plain` → pass | **본문 검사 제거**; 번들·footer만 |
| `score_reader_value` URL 2점 | **본문 무URL** 시 문장·as_of·행동으로 대체 |
| `briefing_ready` in `passes` | **제거** (로그·compare만) |
| 품질 루프 9.5 = 통과 | **`article_publish_ready` 필수** |

### Phase 0 (지금)

- [x] v4 목표 문서 초안  
- [x] 사용자 승인 (구현 진행)  

### Phase 1

- [x] `validate_publish_article` + `publish_sanitize_body`  
- [x] Rewrite / packet_writer 프롬프트 publish-first (`prompts/news_editor_ij.md` v9)  

### Phase 2

- [x] `editorial_scorecard` v4 가중치 (`IJ_PUBLISH_V4=1`)  
- [x] `finalize_ij_editorial_body` publish sanitize 단계 (draft finalize 후 sanitize)  

### Phase 3

- [x] 5건 배치 **재기준** (v4 통과 = `article_publish_ready`) — `editorial_batch_summary_*` (`gate: article_publish_ready_v4`)  
- [x] v3 통과본(`editorial_batch_summary_20260601_140808.json` 등)은 **레거시(v3 briefing gate)** 로 구분  

---

## 9. 성공 정의 (12–18개월)

| 지표 | 목표 |
|------|------|
| **발행 기사 블라인드 테스트** | 편집자·외부 10편 중 “완성 기사” ≥ 8/10 |
| **본문 무URL 준수율** | 자동 발행 경로 100% |
| **동료·NGO 인용** | “브리핑”이 아닌 **“기사”**로 인용 사례 |
| 조사 기여 | discovered 건수·번들 품질 (내부) |

---

## 10. 한 줄 (팀 공유용)

**v4 = 조사·연대는 엔진 안에서만 쓰고, 밖으로 나가는 것은 권위 있는 완성 기사뿐이다.**

---

## 부록: v3 문서와의 관계

- [ij-news-engine-target-design.md](./ij-news-engine-target-design.md): **역사적 참고 (v3 Target)**. North Star·통과 정의는 v4 우선.  
- 구현 중인 `briefing_ready`, `coalition_briefing` 차원: **v4에서 발행 게이트에서 하차**, compare·패킷 유지.
