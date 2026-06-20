# Multi-Brand Editorial Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `news-engine-test` 브랜치에서 IJ/NN/CB가 같은 편집 코어를 공유하면서도 각자 전용 rewrite/publish 경로를 가지게 만든다.

**Architecture:** 기존 `engine.py`와 `engine/pipeline/*` 구조는 유지한다. 새 작업은 `CB` 전용 packet writer, rewrite validator, publish-body helper를 추가하고, `engine.py` 분기와 테스트를 최소 범위로 연결하는 방식으로 진행한다.

**Tech Stack:** Python 3.12, pytest, existing `engine.py` editorial pipeline, erum publish API

---

## File Map

| File | Responsibility |
|------|----------------|
| `engine.py` | `CB_PACKET_PIPELINE` 환경 변수 로드, rewrite/publish 분기 연결 |
| `engine/pipeline/cb_packet_writer.py` | CB 하이브리드 rewrite 입력 생성 |
| `engine/pipeline/cb_rewrite_validate.py` | CB 전용 finalize + validation |
| `engine/pipeline/publish_body.py` | `prepare_cb_publish_body` 추가 |
| `tests/test_cb_editorial_pipeline.py` | CB packet writer / validator / toggle tests |
| `tests/test_publish_body.py` | CB publish body gate tests |
| `docs/cb-complete-workflow.md` | CB 실행 플래그와 운영 흐름 문서 |

## Task 1: Add failing CB editorial tests

**Files:**
- Create: `erum-news-engine/tests/test_cb_editorial_pipeline.py`
- Modify: `erum-news-engine/tests/test_publish_body.py`

- [ ] **Step 1: Write the failing test file**

```python
from engine.pipeline.cb_packet_writer import build_rewrite_user_message_for_cb
from engine.pipeline.cb_rewrite_validate import (
    finalize_cb_editorial_body,
    validate_cb_editorial_rewrite,
)


def test_cb_packet_toggle_on():
    ...


def test_cb_rewrite_message_contains_compliance_axes():
    ...


def test_cb_finalize_and_validate_body():
    ...
```

- [ ] **Step 2: Run CB tests to verify import failure**

Run:

```bash
cd /Users/leegyeongsub/Documents/Playground/erum-news-engine
python3 -m pytest tests/test_cb_editorial_pipeline.py -v
```

Expected: `ModuleNotFoundError` for `engine.pipeline.cb_packet_writer` or `cb_rewrite_validate`

- [ ] **Step 3: Add failing publish-body test for CB**

```python
def test_prepare_cb_publish_body_strips_inline_urls_and_appends_footer():
    ...
```

- [ ] **Step 4: Run publish-body target test**

Run:

```bash
python3 -m pytest tests/test_publish_body.py -k cb -v
```

Expected: FAIL because `prepare_cb_publish_body` is missing

## Task 2: Implement minimal CB packet writer

**Files:**
- Create: `erum-news-engine/engine/pipeline/cb_packet_writer.py`
- Test: `erum-news-engine/tests/test_cb_editorial_pipeline.py`

- [ ] **Step 1: Add minimal env helpers and rewrite template**

```python
def is_cb_publish_v4_enabled() -> bool:
    ...


def is_cb_target_engine_enabled() -> bool:
    ...


def build_rewrite_user_message_for_cb(article, packet, evidence=None, *, max_original_chars=MAX_ORIGINAL_CHARS) -> str:
    ...
```

- [ ] **Step 2: Run CB tests**

Run:

```bash
python3 -m pytest tests/test_cb_editorial_pipeline.py -k packet -v
```

Expected: packet tests PASS, validator tests still FAIL

## Task 3: Implement minimal CB rewrite validator

**Files:**
- Create: `erum-news-engine/engine/pipeline/cb_rewrite_validate.py`
- Test: `erum-news-engine/tests/test_cb_editorial_pipeline.py`

- [ ] **Step 1: Implement four-paragraph validator**

```python
def finalize_cb_editorial_body(body, packet, article=None) -> str:
    ...


def validate_cb_editorial_rewrite(title, body, packet, article=None) -> tuple[bool, str]:
    ...
```

- [ ] **Step 2: Run CB validator tests**

Run:

```bash
python3 -m pytest tests/test_cb_editorial_pipeline.py -k validate -v
```

Expected: PASS

## Task 4: Add CB publish-body helper

**Files:**
- Modify: `erum-news-engine/engine/pipeline/publish_body.py`
- Test: `erum-news-engine/tests/test_publish_body.py`

- [ ] **Step 1: Add `prepare_cb_publish_body`**

```python
def prepare_cb_publish_body(...):
    return _prepare_site_publish_body(..., footer_class="cb-sources-footer", ...)
```

- [ ] **Step 2: Run CB publish-body tests**

Run:

```bash
python3 -m pytest tests/test_publish_body.py -k cb -v
```

Expected: PASS

## Task 5: Wire CB into engine rewrite branch

**Files:**
- Modify: `erum-news-engine/engine.py`
- Modify: `erum-news-engine/tests/test_cb_editorial_pipeline.py`

- [ ] **Step 1: Add `CB_PACKET_PIPELINE` env load near IJ/NN flags**

```python
CB_PACKET_PIPELINE = os.environ.get("CB_PACKET_PIPELINE", "0") == "1"
```

- [ ] **Step 2: Add CB rewrite-input branch**

```python
elif editorial_ctx and editorial_ctx.use_packet_writing and prefix == "CB_" and CB_PACKET_PIPELINE:
    ...
```

- [ ] **Step 3: Add CB validator branch**

```python
if is_valid and cb_editorial:
    ...
```

- [ ] **Step 4: Run CB targeted tests**

Run:

```bash
python3 -m pytest tests/test_cb_editorial_pipeline.py -v
```

Expected: PASS

## Task 6: Wire CB into publish path

**Files:**
- Modify: `erum-news-engine/engine.py`
- Modify: `erum-news-engine/tests/test_publish_body.py`

- [ ] **Step 1: Add CB publish branch**

```python
elif prefix == "CB_" and editorial_ctx and CB_PACKET_PIPELINE:
    from engine.pipeline.publish_body import prepare_cb_publish_body
    ...
```

- [ ] **Step 2: Run publish-body tests**

Run:

```bash
python3 -m pytest tests/test_publish_body.py -v
```

Expected: PASS

## Task 7: Add CB operator doc

**Files:**
- Create: `erum-news-engine/docs/cb-complete-workflow.md`

- [ ] **Step 1: Document flags and run modes**

Include:

```text
CB_PACKET_PIPELINE
CB_TARGET_ENGINE
CB_PUBLISH_V4
EDITORIAL_FORCE_SITE=CB
REVIEW_ONLY=1
HIDDEN_PUBLISH_TEST=1
```

- [ ] **Step 2: Sanity-check doc references**

Run:

```bash
rg -n "CB_PACKET_PIPELINE|CB_TARGET_ENGINE|CB_PUBLISH_V4" docs/cb-complete-workflow.md engine.py engine/pipeline
```

Expected: all flags found in code and doc

## Task 8: Run regression suite

**Files:**
- Test: `erum-news-engine/tests/test_cb_editorial_pipeline.py`
- Test: `erum-news-engine/tests/test_nn_editorial_pipeline.py`
- Test: `erum-news-engine/tests/test_ij_pipeline.py`
- Test: `erum-news-engine/tests/test_publish_body.py`

- [ ] **Step 1: Run targeted multi-brand regression**

```bash
cd /Users/leegyeongsub/Documents/Playground/erum-news-engine
python3 -m pytest \
  tests/test_cb_editorial_pipeline.py \
  tests/test_nn_editorial_pipeline.py \
  tests/test_ij_pipeline.py \
  tests/test_publish_body.py -v
```

Expected: all PASS

- [ ] **Step 2: Record results in branch notes**

Capture:

- current branch
- tested commands
- pass/fail summary
- known gaps if any

