# 3매체 데스크 정체성 개선 루프

**Date:** 2026-07-21  
**Goal:** 각 언론사 특성에 맞는 기사 작성이 가능하도록 데스크 정체성 `.md`를 확정·개선한다.

## North Star (고정)

| 매체 | North Star |
|------|------------|
| **IJ** | 제도 변화의 구조·대상·한계가 보이는 **권위 있는 정책 기사**. 연대/NGO 시사점은 **내부 번들만**. |
| **NN** | 해당자가 바로 판단하는 **생활 안내 기사**. |
| **CB** | 기업이 당장 확인할 **의무·비용·일정 브리핑**. 없으면 **미배정(비적합)**. |

## 루프 구조 (반복)

```
Draft → Review(갭) → Patch → Verify → (다음 Cycle)
```

| Cycle | 입력 | 출력 | 상태 |
|-------|------|------|------|
| **1** | 기존 prompts + v4 설계 | `desks/{ij,nn,cb}.md` 초안 | ✅ 완료 |
| **2** | Cycle1 검토 갭 | 실원문 3사 대비, Hard-Fail 매핑, Self-Check 강화 | ✅ 완료 |
| **3** | desks 정본 | `news_editor_*.md` 이식 + 라우팅 Fit 게이트 | ✅ 완료 |
| **4** | 엔진 검증 | Hard-Fail → validator / dry-run 재평가 | ✅ 진행(H1+CB fit) |

## Cycle 1 작성 루프 (매체당)

```
1. Identity Lock   → North Star 1문장 + 1차 독자 + 논조
2. Angle Rules     → 반드시 답할 질문 / 금지 질문
3. Story Shape     → 제목·리드·4문단 역할
4. Fit Gate        → 이 원문을 이 데스크가 맡을지
5. Self-Check      → 발행 전 기자 체크리스트
6. Anti-Patterns   → 하지 말 것
7. Mini Example    → 데스크답게 한 줄 예시
```

## Cycle 2 개선 갭 (검토에서 확정)

| ID | 갭 | 수정 |
|----|-----|------|
| G1 | IJ 미니 예시가 가상 | 실 dry-run 원문(중환자실 부하지수) before/after |
| G2 | 3사 비교가 파일마다 분산 | `compare_example_icu.md` 공통 원문 대비 |
| G3 | Self-Check가 soft | Hard-Fail 조건 표 (검증 게이트와 1:1) |
| G4 | 공통 사실규칙 중복 | desks는 관점만, 공통은 common 참조 한 줄 |
| G5 | 엔진 미연결 | Cycle3: 프롬프트 이식 + CB Fit 라우팅 |

## Cycle 2 검증

- [x] 같은 ICU 원문으로 IJ/NN 각도 + CB 비적합이 한 문서에서 보임 (`compare_example_icu.md`)
- [x] 각 desk에 Hard-Fail 섹션 있음
- [x] IJ 예시가 실제 원문 기준 요약형 vs 구조형 구분
- [x] README에 Cycle 상태·다음 단계 표시

## Cycle 3 검증

- [x] `news_editor_{ij,nn,cb}.md`에 North Star + Hard-Fail 이식 (v10/v8/v7)
- [x] `engine/pipeline/desk_fit.py` + CB `candidate_filter` — ICU 성과보상 비적합 거부
- [x] IJ korea.kr 가산점 완화(+30→+18), NN life cue 가중
- [x] `tests/test_desk_fit.py` 통과

## Cycle 4 검증

- [x] IJ `validate_paragraph_roles` / scorecard: desk v10(2문단=작동) + legacy(2=배경·3=작동) 병행
- [x] `assess_cb_article_fit`에 `cb_is_nonfit` 선게이트
- [x] `MEDIA_TONE_DESC` North Star 정렬
- [x] 라이브 dry-run: IJ pass(구조 보임), NN pass(패드 수정 후), CB DROP(`cb_nonfit_health_performance`)
- [x] v4에서도 `pad_paragraph_min_length` 동작 (NN 짧은 문단 실패 해소)
- [x] `reorder_paragraph_roles_paras` no-op (desk v10 2문단=작동 보존)

## 산출물

| 파일 | 역할 |
|------|------|
| `prompts/desks/ij.md` | IJ 데스크 규약 |
| `prompts/desks/nn.md` | NN 데스크 규약 |
| `prompts/desks/cb.md` | CB 데스크 규약 |
| `prompts/desks/compare_example_icu.md` | 공통 원문 3사 대비 (Cycle2) |
| `prompts/desks/README.md` | 루프·사용법 |
| `engine/pipeline/desk_fit.py` | CB/NN Fit 헬퍼 (Cycle3) |
| `engine/profiles/{cb,nn,ij}.py` | 라우팅·후보 필터 |
| `engine/pipeline/ij_paragraph_roles.py` | MECH_STRUCTURE_KEYS (Cycle4) |

## 성공 기준

1. 세 파일을 읽고 같은 원문으로 세 기자가 서로 다른 기사를 쓸 수 있다.
2. Fit/비적합이 분명하다 (특히 CB).
3. IJ는 구조 축이 본문에 남고, 연대는 본문에 없다.
4. Cycle2 갭 G1–G4가 문서에 반영된다.
5. Cycle3: 엔진 라우팅이 CB 비적합(ICU)을 DROP/타매체에 넘기고, 물류 안전은 CB 수락.
