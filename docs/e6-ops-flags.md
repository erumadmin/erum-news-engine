# E6 Ops Flags

| Flag | Default | Meaning |
|---|---|---|
| `PUBLISH_STATUS` | required | `DRAFT` or `PUBLISHED` (fail closed if unset) |
| `PER_RUN_LIMIT` | required | Max new drafts per invocation (W8 runner exact: `3`) |
| `DAILY_PUBLISH_LIMIT` | required | Max **unique `auto_news_drafts` created today** by `created_at` (incl. later PUBLISHED). W8 runner exact: `9` |
| `PER_SITE_PER_RUN_LIMIT` | required | Max drafts per media per run (W8 runner exact: `1`) |
| `ONE_SOURCE_ONE_SITE` | required for W8 | Must be `1` on W8 runner (no 3-media fanout) |
| `ENABLE_SITE_IJ` | `1` | Allow IJ |
| `ENABLE_SITE_NN` | `1` | Allow NN |
| `ENABLE_SITE_CB` | `1` | Allow CB |
| `REVIEW_ONLY` | `0` | `1` = no publish / no DB success |
| `HIDDEN_PUBLISH_TEST` | `0` | Must be `0` on W8 cron |
| `ENGINE_ENV_FILE` | required (cron) | Explicit env path; mode 600; owner = runner |
| `REVALIDATE_FAILURE_WEBHOOK_CONFIGURED` | required (cron) | Must be `1` or cron BLOCKED |

See `docs/w8-run-modes.md` and `configs/w8.env.example`.
