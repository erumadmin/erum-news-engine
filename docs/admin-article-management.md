# 관리자 기사 관리 설계

## 목표

- 기사 중복 수집을 관리자가 직접 제어할 수 있게 한다.
- 발행 시각과 원문 시각을 분리해서 KST 기준으로 보여준다.
- 실패 기사도 재시도/영구차단/수동예외로 관리한다.

## 기준 시간

- 저장 기준은 KST를 사용한다.
- 화면 표시는 모두 `Asia/Seoul` 기준으로 통일한다.
- 관리자 화면에는 최소한 아래 두 시각을 분리해서 보여준다.
  - `published_at`: 엔진이 실제로 발행/기록한 시각
  - `source_published_at`: 원문 RSS/기사의 발행 시각

## DB 모델

### `published_articles`

- 최종 발행 성공만 저장하는 append-only 로그
- 주요 컬럼
  - `url_id`
  - `title`
  - `media`
  - `source_published_at`
  - `published_at`

### `article_attempts`

- 실패, 보류, 재시도 상태 저장
- 주요 컬럼
  - `url_id`
  - `title`
  - `media`
  - `source_published_at`
  - `status`
  - `fail_stage`
  - `fail_code`
  - `fail_message`
  - `retry_count`
  - `next_retry_at`
  - `partial_success`
  - `last_attempt_at`
  - `updated_at`

### 권장 추가 테이블

### `article_rules`

- 중복 예외/차단을 관리한다.
- 예시 컬럼
  - `url_id`
  - `source_url`
  - `title_hash`
  - `rule_type` (`ALLOW`, `BLOCK`, `OVERRIDE`)
  - `expires_at`
  - `note`
  - `created_by`
  - `created_at`

### `audit_logs`

- 관리자 작업 이력을 남긴다.
- 예시 컬럼
  - `actor`
  - `action`
  - `target_url_id`
  - `before_state`
  - `after_state`
  - `created_at`

## 관리자 API

- `GET /api/admin/articles`
  - 필터: `site`, `status`, `q`, `date_from`, `date_to`
- `GET /api/admin/articles/:url_id`
  - 상세 보기
- `PATCH /api/admin/articles/:url_id`
  - 액션 예시
    - `allow_retry`
    - `block`
    - `override`
    - `restore`
- `POST /api/admin/articles/:url_id/note`
  - 메모 추가
- `GET /api/admin/metrics`
  - 일별 발행 수, 실패 수, 재시도 수

## 관리자 UI

- 목록 컬럼
  - 제목
  - 상태
  - 카테고리
  - 원문일(KST)
  - 발행일(KST)
  - 마지막 시도(KST)
  - 실패 코드
  - 재시도 횟수
- 상세 패널
  - 원문 URL
  - 원문일(KST)
  - 발행일(KST)
  - 이미지 후보
  - 실패 사유
  - 관리자 메모
- 액션 버튼
  - 재시도 허용
  - 영구 차단
  - 수동 예외
  - 복원

## 정책

- `published_articles`는 삭제보다 조회 중심으로 사용한다.
- 재시도 가능 여부는 `article_attempts.status`로 판단한다.
- 일시 장애는 `RETRYABLE`, 구조적 실패는 `PERMANENT`, 시스템 오류는 `SYSTEM`으로 분리한다.
- 관리자 화면에서 삭제보다 상태 변경을 우선한다.
- `BLOCK`은 `url_id`, `source_url`, `title_hash` 중 하나로 매칭될 수 있다.
- `ALLOW`와 `OVERRIDE`는 엔진의 재시도 차단만 완화하고, 성공 발행 기록을 자동으로 다시 쓰지 않는다.
