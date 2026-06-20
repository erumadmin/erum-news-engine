# Multi-Brand Editorial Parity Design

**Date:** 2026-06-20
**Branch target:** `news-engine-test` only
**Status:** Draft for implementation in test branch, not for direct merge to `main`

## Goal

`news-engine-test`에 이미 들어간 IJ 편집 파이프라인을 공용 멀티브랜드 편집 코어로 고정하고, `IJ`, `NN`, `CB`가 같은 엔진 구조 위에서 각자 다른 편집 규칙과 발행 검증을 통과하도록 만든다.

이번 설계의 완료 기준은 다음이다.

1. `IJ`, `NN`, `CB` 모두 `1원문 = 1사이트` 규칙으로 라우팅된다.
2. 세 사이트 모두 전용 rewrite 입력, 전용 rewrite 검증, 전용 publish body 검증 경로를 가진다.
3. 세 사이트 모두 `dry-run`, `review-only`, `hidden-publish` 검토 경로를 유지한다.
4. 작업은 `news-engine-test`에서만 진행하고 `main` 병합은 별도 배포 계획으로 분리한다.

## Current State

현재 브랜치 기준 상태는 다음과 같다.

- `IJ`는 하이브리드 packet rewrite, target engine, publish v4 gate, 이미지 게이트, 전용 validator까지 연결돼 있다.
- `NN`는 `NN_PACKET_PIPELINE`, `NN_TARGET_ENGINE`, `NN_PUBLISH_V4`, `nn_packet_writer`, `nn_rewrite_validate`, `nn_community_brief`가 들어가 있어 전용 편집 경로가 상당 부분 구현돼 있다.
- `CB`는 `profiles/cb.py`에 라우팅 시그널만 있고, `cb_packet_writer`, `cb_rewrite_validate`, `CB_PACKET_PIPELINE`, `CB_TARGET_ENGINE` 같은 동등한 전용 경로는 없다.
- `engine.py`의 rewrite/publish 분기 역시 `IJ`와 `NN`까지만 전용 분기가 있으며 `CB`는 기본 `build_rewrite_user_message(article)` 경로로 남아 있다.

즉 현재 구조는 `IJ 완성 + NN 부분 완성 + CB 미구현` 상태다.

## Decision

이번 작업에서는 `CB`를 `NN`과 같은 수준의 전용 편집 경로로 올린다. 다만 `IJ`의 NGO/연대 브리핑 성격을 복제하지 않고, `CB`는 기업 실무 독자를 위한 별도 각도로 정의한다.

`CB`의 편집 성격은 아래처럼 고정한다.

- 1문단: 기업, 기관, 공급망, 실무 담당자에게 무엇이 바뀌는지
- 2문단: 왜 중요한지, 어떤 규제/일정/비용 배경이 있는지
- 3문단: 기업이 실제로 확인하거나 준비해야 할 절차, 범위, 예외
- 4문단: `다만`으로 시작하는 제한, 유예, 적용 범위, 미확정 요소

## Architecture

### Shared core

공용 코어는 그대로 유지한다.

- ingest
- route/filter
- research pipeline
- placement
- review-only / hidden-publish / dry-run
- media plan
- erum publish API

### Site-specific layer

사이트별 차이는 아래 인터페이스에만 넣는다.

- profile: 후보 필터, route score, evidence fetch plan, placement threshold
- rewrite input builder
- rewrite validator/finalizer
- publish-body preparation
- optional target-engine enrichment

이번 작업에서 새로 채워야 하는 사이트 레이어는 `CB`다.

## CB Design

### Flags

`CB`는 `NN`과 같은 수준의 명시적 플래그를 가진다.

- `CB_PACKET_PIPELINE`
- `CB_TARGET_ENGINE`
- `CB_PUBLISH_V4`

기본값은 아래처럼 둔다.

- `CB_PACKET_PIPELINE=0`
- `CB_TARGET_ENGINE=0`
- `CB_PUBLISH_V4=1`

이 기본값은 기존 운영 경로를 깨지 않으면서, 명시적으로 `CB` 전용 파이프를 켰을 때만 새 동작을 타게 한다.

### Packet writer

`cb_packet_writer.py`는 `NN` 구조를 그대로 복제하지 않고 `CB` 독자에 맞는 rewrite 입력을 만든다.

포함해야 하는 축은 다음이다.

- 누가 영향받는가: 기업, 협회, 공급망, ESG/CSR 실무자
- 무엇이 달라지는가: 공시, 규제, 의무, 기준, 일정, 비용
- 무엇을 확인해야 하는가: 제출, 고지, 점검, 신고, 적용 대상
- 무엇이 아직 남아 있는가: 유예, 예외, 세부지침, 해석 여지

### Rewrite validation

`cb_rewrite_validate.py`는 다음을 강제한다.

- 제목/본문이 기업 실무 관점으로 유지된다.
- 본문은 정확히 4문단이다.
- 1문단은 기업/실무 영향이 드러난다.
- 3문단에는 확인 절차, 일정, 범위, 조건 중 최소 하나가 들어간다.
- 4문단은 `다만`으로 시작하고 제한·예외·유의가 들어간다.
- 본문에 URL과 전화번호를 직접 노출하지 않는다.

### Publish body

기존 `prepare_ij_publish_body`, `prepare_nn_publish_body`에 이어 `prepare_cb_publish_body`를 추가한다.

규칙은 v4 publish gate를 공통으로 쓰되, footer class와 실무형 안내 문구만 `CB`에 맞게 다룬다.

## Engine Integration

`engine.py`와 `engine/pipeline/orchestrator.py`에서 `CB` 전용 경로를 아래처럼 연결한다.

1. `CB_PACKET_PIPELINE` 환경 변수를 로드한다.
2. `editorial_ctx.use_packet_writing`이 `CB`이고 flag가 켜져 있으면 `cb_packet_writer`를 사용한다.
3. rewrite validation 단계에서 `cb_rewrite_validate`를 호출한다.
4. publish 단계에서 `prepare_cb_publish_body`를 호출한다.
5. 로그/summary 출력에도 `CB packet` 상태가 보이게 한다.

## Testing Strategy

테스트는 `CB`를 추가하는 방향으로 확장한다.

- unit: `cb_packet_writer`
- unit: `cb_rewrite_validate`
- integration: `engine.py` rewrite branch selection
- integration: `publish_body.py` CB publish gate
- regression: existing IJ/NN tests keep passing

핵심은 `CB` 테스트를 먼저 쓰고 실패를 확인한 뒤, 최소 구현으로 통과시키는 것이다.

## Non-Goals

이번 작업에서 하지 않는다.

- `main` 병합
- 프로덕션 env 변경
- GHA 배포 활성화
- 프론트엔드 사이트 코드 변경
- 홈 슬롯 알고리즘 재설계
- CB 전용 research collector 대규모 분기

## Deliverables

완료 시점에는 아래 산출물이 있어야 한다.

- `cb_packet_writer.py`
- `cb_rewrite_validate.py`
- `CB_*` env wiring
- `prepare_cb_publish_body`
- `tests/test_cb_editorial_pipeline.py`
- `tests/test_publish_body.py` 또는 별도 publish gate test의 CB 케이스
- `docs/cb-complete-workflow.md` 또는 동등한 운영 문서

