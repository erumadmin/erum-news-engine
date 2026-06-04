# IJ Full Pipeline Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Unify text quality loop (v4) with image probe + layout decision + publish preflight manifest — without production deploy or API publish.

**Architecture:** Keep `REVIEW_ONLY=1` for all editorial loops. Add `EDITORIAL_IMAGE_PROBE=1` to run `find_best_image` / optional download in-process, record results in compare JSON/MD, and emit `publish_preflight` (what would happen if `REVIEW_ONLY=0`). Image failure does not fail text gate (research-pipeline policy).

**Tech Stack:** Python 3, existing `engine.py` image helpers, `editorial_report.py`, pytest.

---

### Task 1: Image probe module

**Files:**
- Create: `engine/pipeline/image_probe.py`
- Test: `tests/test_image_probe.py`

- [ ] `probe_article_images(article, *, download=False)` → status, candidates, selected, bytes_kb, error code (soft, no raise)

### Task 2: Layout decision

**Files:**
- Create: `engine/pipeline/layout_decision.py`
- Test: `tests/test_layout_decision.py`

- [ ] `decide_layout_type(image_probe, placement_slot)` → `hero` | `card` | `list` | `brief`

### Task 3: Publish preflight manifest

**Files:**
- Create: `engine/pipeline/publish_preflight.py`
- Test: `tests/test_publish_preflight.py`

- [ ] `build_publish_preflight(...)` → would_publish, blocked_reasons, layout_type, image_status

### Task 4: Wire into process_article + editorial report

**Files:**
- Modify: `engine.py` (`process_article`, env `EDITORIAL_IMAGE_PROBE`)
- Modify: `engine/pipeline/editorial_report.py`
- Modify: `scripts/run_editorial_quality_loop.py` (setdefault probe=1)

### Task 5: Preflight E2E script + docs

**Files:**
- Create: `scripts/run_editorial_preflight_e2e.py`
- Modify: `docs/editorial-pipeline.md`

**No deploy:** `REVIEW_ONLY=1`, no `HIDDEN_PUBLISH_TEST` unless user explicitly runs it later.
