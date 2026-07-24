# PR-E1 Integration Branch Inventory

version: `e1-2026-07-23`
base: `origin/main` @ `f45d67c`
integration origin tip: `cfdb09c` (23 commits ahead / 23 behind)
local WIP worktree tip (preserve, do not reset): `5e3146f` (+28 vs origin integration)

## Decision legend

- **PORT**: cherry-pick / re-apply onto `release/news-engine-vnext`
- **REWRITE**: keep intent, reimplement against main
- **DEFER**: needed later (E2+)
- **DROP**: do not bring

## Commits on integration not in main

| SHA | Subject | Bucket | Decision |
|---|---|---|---|
| 6472bd5 | feat: IJ editorial pipeline | IJ | REWRITE into E3 after E2 common path |
| 34f60d4 | fix: P0 editorial quality | IJ | PORT selectively with IJ fixtures |
| 58e6170 | fix: P1 IJ rewrite validation | IJ | PORT |
| 4b6e536 | fix: flatten nested p tags | common/IJ | PORT |
| 3794df0 | feat: IJ editorial v4 + image probe | IJ | REWRITE (large); extract image gate to common |
| 6f83ad6 | assemble IJ publish body v4 | IJ | PORT after sanitizer contract |
| 22e81f5 | article_images require gate | common | PORT to E2 image rights |
| d804936 | restore image_probe candidates | IJ | PORT with 22e81f5 |
| 054e41a | IJ image gate before research | IJ | PORT |
| af32695 | wire image_required / skip report | common | PORT |
| 6fd76d7 | v4 publish body footer gate | common | REWRITE vs portal sanitizer allowlist |
| 9db117a | run_ij_full_pipeline CLI | ops | PORT as non-prod tool |
| cda459e | GHA IJ editorial review | ops/CI | REWRITE into merge-blocking unit + separate live job |
| ce2f3df | IJ operator runbook | docs | PORT |
| 58a1798 | evaluation gaps / tests | common | PORT tests (mocked) |
| 9b5de89 | engine/utils/http + call-order test | common | PORT |
| e0b864f | NN and CB editorial packet pipelines | NN/CB | REWRITE into E4/E5 (do not wholesale) |
| ae78dae | harden CB review artifacts | CB | PORT selectively |
| f400ec3 | korea policy web crawler in test branch | ops | DROP vs main (main already has crawler lineage) |
| d9fd1f8 | port main security onto test | security | DROP (main already has security merges) |
| 7bdee83 | ci install pytest | CI | PORT pattern |
| 6848802 | ci supply import env | CI | PORT pattern |
| cfdb09c | ci dry-run from fixture JSON | CI | PORT — golden fixture path |

## Commits on main not in integration (must remain / rebase onto)

Security + korea crawler + gemini fallback + short-source safety (`3ec1909`…`f45d67c`).  
**Rule:** `release/news-engine-vnext` starts from **main**, then selective PORT/REWRITE. Never merge integration tip as one PR.

## File bucket summary (`main...integration`, 131 files)

| Bucket | Approx files | Release target |
|---|---:|---|
| common pipeline | 43 | E1/E2 |
| IJ | 13 | E3 |
| NN | 10 | E5 |
| CB | 8 | E4 |
| ops/docs/CI | 14 | E1/E6 |
| other | 43 | triage per file during PORT |

## E1 deliverables on this branch

1. This inventory (decision table)
2. Merge-blocking GitHub Actions unit workflow (no live LLM)
3. Separate non-blocking workflow stub for live-provider jobs
4. Golden fixture placeholder used by unit tests
