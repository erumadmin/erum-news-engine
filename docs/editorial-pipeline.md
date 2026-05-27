# IJ Editorial Pipeline (local test)

**⛔ Do not merge to `main` without explicit deploy approval.**

## Env flags

| Variable | Default | Meaning |
|----------|---------|---------|
| `EDITORIAL_PIPELINE` | `1` | Ingest → route → research → placement |
| `IJ_PACKET_PIPELINE` | `1` | Hybrid user message (source + packet + evidence) |
| `REVIEW_ONLY` | `0` | `1` = no publish, review outputs only |
| `TIER_C_ENABLED` | `1` | Extra evidence when facts thin |
| `TIER_C_USE_LLM` | `0` | `1` + `GEMINI_API_KEY` for URL hints |
| `EDITORIAL_PERSIST` | `0` | Requires `sql/editorial_pipeline.sql` on DB |

## Tests

```bash
cd erum-news-engine
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest tests/ -v --ignore=tests/fixtures
```

## Fixture E2E (no publish)

```bash
EDITORIAL_PIPELINE=1 IJ_PACKET_PIPELINE=1 REVIEW_ONLY=1 \
  .venv/bin/python scripts/run_editorial_review_fixture.py
```

Output: `review_outputs/editorial_compare_*.md`

**Do not run** `REVIEW_ONLY=0` on production until deploy plan.
