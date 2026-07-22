# Fidelity Gate + Scorecard Alignment Design

**Date:** 2026-07-21  
**Branch target:** `integration/news-engine-test-main-stabilization` (test branch only)  
**Status:** Approved for implementation

## Goal

자동 editorial 채점이 형식(슬롯·문단·키워드)만 보고 높게 나오고, 사람이 보면 사실·프레임·내부 모순으로 낮게 나오는 갭을 줄인다.

성공 기준:

1. 2026-07-21 dry-run 재작성본(의무화 / 슈링크플레이션 / 시행일 모순)이 **자동으로 fidelity fail** 된다.
2. 점수 번들에 `form_score`(기존 total)와 `fidelity_ok` / `fidelity_gaps`가 분리되어 보인다.
3. `passes`는 기존 형식 조건 **AND** `fidelity_ok`이다.
4. 원문에 근거가 있는 정상 기사는 회귀 없이 통과한다.

## Non-goals

- LLM 2차 재판관(C)
- 채점 가중치 전면 재튜닝
- NN/CB 전용 루브릭 개편 (공통 `validate_source_fidelity`만 공유; IJ scorecard를 우선)

## Problem

현재 자동 루브릭은 다음만 본다.

- structure: 4문단, 2문단「기존/우려」키워드, 4문단「다만」
- facts: 원문 키워드 **누락**만 감점 (추가 사실은 거의 미검사)
- originality hallucination: `억` / `월` / `표` 정도
- `validate_source_fidelity`: 수치 + 에너지 정책용 고정 금지어

사람이 깎는「의무화 과장」「원문 없는 배경」「본문 내부 모순」은 점수·게이트 밖에 있다.  
오히려 structure는 2문단 배경 키워드를 **가점**해 창작 배경을 보상한다.

## Decision: A + B

### A — Hard fail gates (expand `validate_source_fidelity`)

허용 근거 텍스트(allow corpus):

- article: `title` + plain `body` + `list_text` + `source_published_at`
- optional packet: `key_facts` 문자열, `discovered_facts[].fact`, `main_claim`

| Gate | Rule | Fail message prefix |
|------|------|---------------------|
| Strong norm verbs | Rewrite title/excerpt/body contains `의무화|강제화|법제화|처벌` (and close variants) **and** none of those stems appear in allow corpus | `원문에 없는 규범 주장` |
| Internal contradiction | Paired claims both present in rewrite (title+excerpt+body) | `본문 내부 모순` |
| Thin-source invented background | Source plain length &lt; 500 **or** `thin_source_body` in `packet.risk_flags`; paragraph 2 (or whole body if &lt;2 paras) contains a **blocked background term** absent from allow corpus | `얇은 원문 배경 창작` |

Initial contradiction pairs (compact Korean match):

- `시행일`+`공표` ↔ `시행일`+(`명시되지`|`명시되지않`|`밝히지`)
- `의무`+(`화`|`사항`) in title/lead sense vs body `자발` / `협약` alone is **not** auto-fail unless strong verb gate already covers 의무화; prefer strong-verb + explicit pair:
  - title/excerpt has `의무화` and body has `자발적` → contradiction (optional secondary)

Initial thin-source background denylist (absent from corpus → fail):

- `슈링크플레이션`
- `인플레이션` (unless in corpus)
- `물가 급등` / `물가급등`

Strong norm stems to detect in rewrite vs corpus:

- `의무화`, `강제화`, `법제화`, `처벌`  
  Note: bare `의무 사항` in source should **not** unlock `의무화` (different stem). Matching is substring on compact text for the full stem list above.

Signature change (backward compatible):

```python
def validate_source_fidelity(
    title, body, article=None, *, excerpt="", packet=None
) -> tuple[bool, str]:
```

Call sites that already have packet (IJ/NN/CB validate) must pass `packet=`.

### B — Scorecard adjustments (IJ `editorial_scorecard` + originality)

1. **structure**  
   - Keep requiring some background/mechanism role signals.  
   - Do **not** treat bare `기존|우려` as sufficient if those cues (and nearby claim tokens) are absent from allow corpus when source is thin (&lt;500) or `thin_source_body`.  
   - On thin source: if para2 uses BG keys but no allow-corpus overlap for the “problem claim”, subtract the same 1.5 that “2문단 배경·문제 약함” would (i.e. treat unsupported background as weak/missing).

2. **facts**  
   - Keep missing-source-fact penalties.  
   - Soft-score: if fidelity gaps would fire (same helpers as A), subtract up to 3.0 and append gap strings. Soft score alone does not replace hard fail.

3. **originality `_hallucination_penalty`**  
   - Keep numeric/table penalties.  
   - Add +2.0 if any thin-source background denylist term appears in plain but not in source_body (and not in packet facts if passed — keep signature; use source_body only here, scorecard can pass richer check via facts).

4. **Bundle / passes**  
   - `score["form_score"] = total` (alias of existing total before fidelity gate).  
   - `score["fidelity_ok"]`, `score["fidelity_gaps"]` from running the same fidelity checks (non-throwing collector).  
   - `passes = passes_score AND fidelity_ok`.  
   - Compare markdown: show fidelity line under score header.

### Prompt (minimal)

`prompts/news_editor_common.md` / `news_editor_ij.md`: one line — 원문에 없는 배경 개념·「의무화」 등 규범 과장 금지; 같은 본문에서 상충 주장 금지.

## Files

| File | Change |
|------|--------|
| `engine/pipeline/rewrite_validate.py` | Gates A; helpers; packet kwarg |
| `engine/pipeline/editorial_scorecard.py` | B structure/facts/passes/meta |
| `engine/pipeline/editorial_originality.py` | hallucination denylist |
| `engine/pipeline/editorial_report.py` | compare line for fidelity |
| `engine/pipeline/nn_rewrite_validate.py` / `cb_rewrite_validate.py` | pass packet |
| `prompts/news_editor_common.md`, `news_editor_ij.md` | one safety line |
| `tests/test_source_fidelity.py` | A cases + dry-run fixture body |
| `tests/test_editorial_scorecard.py` | B passes/fidelity meta |

## Verification

```bash
.venv/bin/python -m pytest tests/test_source_fidelity.py tests/test_editorial_scorecard.py -q
```

Fixture body from `review_outputs/editorial_compare_20260721_130851.md` must fail fidelity.  
Existing pass cases in `test_source_fidelity` / high-score scorecard must still pass.
