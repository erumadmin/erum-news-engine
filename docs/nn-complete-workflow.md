# NN Complete Workflow — Operator Runbook

**Branch:** `news-engine-test` only.

## Pipeline (IJ와 동일 순서)

```mermaid
flowchart LR
  A[수집] --> B[이미지 필수]
  B --> C[리서치]
  C --> D[community_brief]
  D --> E[패킷 재작성]
  E --> F[발행본 v4]
  F --> G[ERUM API DRAFT]
```

| Step | Module |
|------|--------|
| 이미지 (필수) | `editorial_stages` → `require_article_image` |
| 리서치 | `research_collector` (공유) |
| 재작성 | `nn_packet_writer` + `nn_rewrite_validate` |
| 발행본 | `prepare_nn_publish_body` |
| 품질 루프 | `run_nn_editorial_quality_loop.py` |

## 실행

```bash
cd erum-news-engine   # news-engine-test

# dry-run (3 attempts)
FIXTURE_URL='https://www.korea.kr/news/policyNewsView.do?newsId=148965573&call_from=rsslink' \
  .venv/bin/python scripts/run_nn_full_pipeline.py --mode dry-run

# review (12 attempts, image download strict)
FIXTURE_URL='https://www.korea.kr/news/policyNewsView.do?newsId=148965573&call_from=rsslink' \
  .venv/bin/python scripts/run_nn_full_pipeline.py --mode review

# review — 네트워크 없을 때 (원문 MD + 캐시 featured)
FIXTURE_SOURCE_MD='review_outputs/editorial_compare_20260605_091959.md' \
FIXTURE_CACHED_IMAGE='review_outputs/featured_20260605_091959.jpg' \
  .venv/bin/python scripts/run_nn_full_pipeline.py --mode review

# hidden-publish (DRAFT, 홈 미노출)
TARGET_URL_IDS='https://www.korea.kr/news/policyNewsView.do?newsId=148965573&call_from=rsslink' \
  .venv/bin/python scripts/run_nn_full_pipeline.py --mode hidden-publish
```

## Env flags

| Variable | Default | Meaning |
|----------|---------|---------|
| `NN_PACKET_PIPELINE` | `1` (via CLI) | 패킷+community_brief 재작성 |
| `NN_TARGET_ENGINE` | `1` | community_brief 생성 |
| `NN_PUBLISH_V4` | `1` | 본문 무URL + footer |
| `EDITORIAL_FORCE_SITE` | `NN` | 라우팅 강제 |
| `MIN_IMAGE_WIDTH` | `720` | korea.kr og:image |
| `IJ_TARGET_ENGINE` | `0` (NN CLI) | IJ research gate 비활성 (NN 오판 방지) |
| `FIXTURE_SOURCE_MD` | — | compare MD에서 원문 주입 (오프라인) |
| `FIXTURE_CACHED_IMAGE` | — | 사전 다운로드 featured jpg |

## 통과 기준

- 총점 ≥ **9.5**
- `community_axes` ≥ 7.0
- `article_publish_ready` (v4)
- `would_publish_api` (review preflight, REVIEW_ONLY 제외 시)

산출물: `review_outputs/editorial_compare_*.md`, `editorial_quality_*.json`
