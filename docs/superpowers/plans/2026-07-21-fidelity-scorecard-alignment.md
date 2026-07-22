# Fidelity Gate + Scorecard Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hard-fail unsupported norm claims, internal contradictions, and thin-source invented background; align IJ scorecard `passes` with `fidelity_ok`.

**Architecture:** Extend `validate_source_fidelity` with shared helpers; reuse those helpers in `score_editorial_rewrite` for soft penalties and `passes`. Keep NN/CB on the shared fidelity function only.

**Tech Stack:** Python 3, unittest/pytest, existing `engine.pipeline` modules.

**Spec:** `docs/superpowers/specs/2026-07-21-fidelity-scorecard-alignment-design.md`

---

### Task 1: Failing fidelity tests (A)

**Files:**
- Modify: `tests/test_source_fidelity.py`

- [ ] **Step 1: Add failing tests** for 의무화 without source stem, 시행일 공표↔미명시 contradiction, thin-source 슈링크플레이션, and dry-run article body; plus a positive case where source contains 의무화.

- [ ] **Step 2: Run tests — expect fail**

```bash
.venv/bin/python -m pytest tests/test_source_fidelity.py -q
```

### Task 2: Implement fidelity gates

**Files:**
- Modify: `engine/pipeline/rewrite_validate.py`
- Modify: `engine/pipeline/nn_rewrite_validate.py` (pass packet)
- Modify: `engine/pipeline/cb_rewrite_validate.py` (pass packet)

- [ ] **Step 1: Implement helpers + extend `validate_source_fidelity(..., packet=None)`**
- [ ] **Step 2: Wire packet through IJ/NN/CB validate call sites**
- [ ] **Step 3: Run `tests/test_source_fidelity.py` — expect pass**

### Task 3: Failing scorecard tests (B)

**Files:**
- Modify: `tests/test_editorial_scorecard.py`

- [ ] **Step 1: Add test** that dry-run-like rewrite gets `fidelity_ok is False` and `passes is False` even if structure looks complete; existing high-score test still `fidelity_ok True`.

- [ ] **Step 2: Run — expect new tests fail**

### Task 4: Scorecard + originality + report

**Files:**
- Modify: `engine/pipeline/editorial_scorecard.py`
- Modify: `engine/pipeline/editorial_originality.py`
- Modify: `engine/pipeline/editorial_report.py`
- Modify: `prompts/news_editor_common.md`, `prompts/news_editor_ij.md`

- [ ] **Step 1: Soft facts penalties, thin structure rule, form_score/fidelity meta, passes AND fidelity**
- [ ] **Step 2: Hallucination denylist term penalty**
- [ ] **Step 3: Compare markdown fidelity line**
- [ ] **Step 4: Prompt one-liners**
- [ ] **Step 5: Run targeted tests**

```bash
.venv/bin/python -m pytest tests/test_source_fidelity.py tests/test_editorial_scorecard.py tests/test_editorial_originality.py -q
```

### Task 5: Regression smoke

- [ ] **Step 1: Run**

```bash
.venv/bin/python -m pytest tests/test_source_fidelity.py tests/test_editorial_scorecard.py tests/test_rewrite_validate.py tests/test_publish_v4_scorecard.py tests/test_editorial_originality.py -q
```

- [ ] **Step 2: Confirm dry-run body fails and kepco-style fixture still scores well**
