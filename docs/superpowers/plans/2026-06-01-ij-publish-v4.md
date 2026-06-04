# IJ Publish-First v4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement v4 publish-first gates (`validate_publish_article`, `publish_sanitize_body`, v4 scorecard) so quality loop passes mean a publishable article, not a briefing.

**Architecture:** New `publish_validate.py` module; wire into `finalize_ij_editorial_body`, `validate_ij_editorial_rewrite`, `editorial_scorecard`, `inject_scorecard_slots` behind `IJ_PUBLISH_V4=1` (default on).

**Tech Stack:** Python 3, unittest/pytest, existing pipeline modules

---

### Task 1: publish_validate core (TDD)

**Files:**
- Create: `engine/pipeline/publish_validate.py`
- Create: `tests/test_publish_v4.py`

- [ ] Failing tests for sanitize + validate
- [ ] Minimal implementation
- [ ] Green tests

### Task 2: Pipeline integration

**Files:**
- Modify: `engine/pipeline/rewrite_validate.py`
- Modify: `engine/pipeline/editorial_scorecard.py`
- Modify: `engine/pipeline/inject_scorecard_slots.py`

### Task 3: Batch evaluation loop

**Files:**
- Modify: `scripts/run_editorial_quality_loop.py` (article_publish_ready in output)
