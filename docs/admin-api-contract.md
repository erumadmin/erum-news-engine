# Admin Article API Contract

This document defines the backend contract for the ERUM admin article-management screen.

## Timezone Rules

- All human-facing timestamps are displayed in `Asia/Seoul`.
- The database stores `DATETIME` values without timezone metadata, but the engine writes them as KST-naive values.
- The admin backend must treat `published_at`, `source_published_at`, `last_attempt_at`, and `next_retry_at` as KST.

## Article List

`GET /api/admin/articles`

### Query parameters

- `site`: `IJ`, `NN`, or `CB`
- `status`: `SUCCESS`, `RETRYABLE`, `PERMANENT`, `SYSTEM`
- `q`: title or URL search term
- `date_from`: `YYYY-MM-DD`
- `date_to`: `YYYY-MM-DD`
- `page`: default `1`
- `page_size`: default `20`

### Response

```json
{
  "items": [
    {
      "url_id": "022338",
      "title": "경영위기 소상공인 최대 20만 명...",
      "site": "IJ",
      "category": "경제",
      "status": "SUCCESS",
      "source_published_at": "2026-03-27T09:00:00+09:00",
      "published_at": "2026-03-28T00:15:12+09:00",
      "last_attempt_at": "2026-03-28T00:15:12+09:00",
      "next_retry_at": null,
      "fail_stage": null,
      "fail_code": null,
      "retry_count": 0,
      "partial_success": false,
      "has_rule": false
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 123
}
```

## Article Detail

`GET /api/admin/articles/:url_id`

### Response fields

- `published_article`
  - success record from `published_articles`
- `attempt`
  - current or most recent row from `article_attempts`
- `rule`
  - current matching row from `article_rules`
- `audit_logs`
  - recent actions for the article

## State Transitions

`PATCH /api/admin/articles/:url_id`

### Actions

- `allow_retry`
  - sets the attempt state to `RETRYABLE`
  - may set `next_retry_at`
- `block`
  - sets or updates the rule to `BLOCK`
  - marks the attempt as `PERMANENT`
- `override`
  - inserts or updates a `ALLOW` or `OVERRIDE` rule
  - may expire automatically after a chosen date
- `restore`
  - clears a block/override rule

### Example request

```json
{
  "action": "allow_retry",
  "note": "이미지 차단 이슈가 해소된 뒤 재처리",
  "next_retry_at": "2026-04-02T15:00:00+09:00"
}
```

## Notes

- `published_articles` should stay append-only in normal operation.
- Admin actions should update `article_attempts`, `article_rules`, and `audit_logs`.
- Deleting from `published_articles` should be reserved for emergency cleanup.
- The UI must show both `source_published_at` and `published_at` so the source date and ERUM processing date do not get confused.
- `article_rules` may match on `url_id`, normalized `source_url`, or normalized `title_hash`.
- `ALLOW` and `OVERRIDE` only bypass retry/attempt blocking; they should not silently rewrite already published success records.
