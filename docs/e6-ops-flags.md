# E6 Ops Flags

| Flag | Default | Meaning |
|---|---|---|
| `PUBLISH_STATUS` | required | `DRAFT` or `PUBLISHED` (fail closed if unset) |
| `PER_RUN_LIMIT` | required | Max articles processed per engine invocation (fail closed; W8 initial: `3`) |
| `DAILY_PUBLISH_LIMIT` | required | Max successful publishes/drafts counted per KST day (fail closed; W8 initial: `9`) |
| `PER_SITE_PER_RUN_LIMIT` | required | Max DRAFTs per media (IJ/NN/CB) within one run (fail closed; W8 initial: `1`) |
| `ONE_SOURCE_ONE_SITE` | `1` | Auto news routes to exactly one site (W8 cron requires `1`; no 3-media fanout) |
| `ENABLE_SITE_IJ` | `1` | Allow IJ publishing |
| `ENABLE_SITE_NN` | `1` | Allow NN publishing |
| `ENABLE_SITE_CB` | `1` | Allow CB publishing |
| `REVIEW_ONLY` | `0` | `1` = no publish / no DB success (dry-run inspection) |
| `HIDDEN_PUBLISH_TEST` | `0` | Staging-only hidden test; must be `0` for W8 cron |

## W8 run modes

| Mode | Flags | Script | DB / R2 |
|---|---|---|---|
| Dry-run / review | `REVIEW_ONLY=1`, `PUBLISH_STATUS=DRAFT` | `scripts/w8-dry-run.sh` | No article create, no R2 upload, no DB success |
| Operational DRAFT | `REVIEW_ONLY=0`, `PUBLISH_STATUS=DRAFT`, `PER_RUN_LIMIT=3`, `DAILY_PUBLISH_LIMIT=9`, `PER_SITE_PER_RUN_LIMIT=1` | `scripts/w8-cron-runner.sh` | Creates Portal DRAFTs + may upload images to R2; **no** auto PUBLISHED |

Customer-request 3-media fanout is **out of engine cron scope** (Portal customer publisher only) and must not be enabled via `ONE_SOURCE_ONE_SITE=0`.
