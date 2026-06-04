# Research-Based News Pipeline Implementation Plan

## 1. 목적

이 문서는 현재 `원문 RSS -> AI 재작성 -> QA -> 발행` 구조를 `원문 수집 -> 후보 선별 -> 리서치팩 생성 -> 기사 작성 -> QA -> 발행` 구조로 전환하기 위한 구현 계획이다.

핵심 목표는 아래 4가지다.

- 정책브리핑과 뉴스와이어를 `기사 원문`이 아니라 `lead source`로 취급한다.
- 기사 입력을 raw body에서 `research packet`으로 바꾼다.
- `IJ`, `NN`, `CB`가 같은 원문을 병렬 재작성하지 않게 한다.
- 이미지 실패가 발행 실패로 이어지지 않도록 발행과 편성을 분리한다.

## 2. 현재 구조와 한계

현재 엔진은 대략 아래 순서로 동작한다.

1. RSS 수집
2. 중복 체크
3. AI 재작성
4. QA 검수
5. 발행

현재 구조의 한계는 명확하다.

- 정책브리핑, 뉴스와이어 원문 하나만으로 기사를 만든다.
- 여러 출처를 결합한 검증 단계가 없다.
- 매체별 라우팅이 `원문 적합도`보다 `재작성 프롬프트`에 더 의존한다.
- 이미지가 없거나 품질이 낮으면 기사 자체가 실패한다.
- 같은 이슈를 3개 사이트에 각각 재가공하면서 도메인 간 차별성이 약해진다.

## 3. 목표 구조

목표 파이프라인은 아래와 같다.

1. `Raw Source Ingestion`
2. `Candidate Filtering`
3. `Primary Routing`
4. `Research Collection`
5. `Research Packet Build`
6. `Secondary Decision`
7. `Draft Writing`
8. `QA Validation`
9. `Layout / Image Decision`
10. `Publishing`

운영 원칙은 아래 3가지다.

- `원문 1개 = 기본 1개 사이트`
- `정책브리핑 단독`, `뉴스와이어 단독`으로는 메인 기사 발행 금지
- `이미지 없음 = 미발행`이 아니라 `이미지 없음 = 다른 편성 방식`

## 4. 단계별 구현

### 4.1 Raw Source Ingestion

입력:

- 정책브리핑 RSS
- 뉴스와이어 RSS
- 추후 공식 사이트 RSS 또는 크롤링 소스

저장 필드:

- `source_id`
- `source_type`
- `source_url`
- `source_title`
- `source_body`
- `source_published_at`
- `raw_html`
- `image_candidates`
- `ingested_at`

구현 포인트:

- 현재 `collect_articles()` 단계에서 바로 기사 후보를 만들지 말고 `raw source` 저장 단계로 분리한다.
- RSS에서 수집한 이미지 후보는 발행용이 아니라 참고 메타데이터로만 저장한다.

### 4.2 Candidate Filtering

역할:

- 기사감 없는 원문을 초기에 제거한다.

우선 제거 대상:

- 행사 개최
- 참가자 모집
- 수상
- 단순 협약 / MOU
- 포럼 안내
- 선언성 발언
- 정보축이 지나치게 적은 공지

출력:

- `candidate = true/false`
- `discard_reason`

구현 방식:

- 1차는 룰 기반으로 시작한다.
- 제목 패턴, 본문 길이, 조치/대상/시점 유무를 기준으로 판정한다.

### 4.3 Primary Routing

역할:

- 각 후보를 `IJ`, `NN`, `CB`, `DROP` 중 하나로 1차 배정한다.

라우팅 기준:

- `IJ`: 정책 구조, 사회문제, 해결 방식, 공공성
- `NN`: 생활 영향, 신청 방법, 이용 조건, 체감 변화
- `CB`: 규제, 비용, 일정, 공시, 공급망, 계약 영향

출력:

- `assigned_site`
- `routing_reason`

구현 방식:

- 시작은 룰 기반 분류로 한다.
- 이후 필요 시 lightweight classifier를 보조로 붙일 수 있다.

### 4.4 Research Collection

역할:

- 원문 외 추가 근거를 수집한다.

정책브리핑 계열 필수 추가 소스:

- 관련 부처 보도자료
- FAQ / 설명자료
- 법령 / 시행령 / 행정예고
- 브리핑문

뉴스와이어 계열 필수 추가 소스:

- 기업 공식 홈페이지
- 공시 / 보고서
- 정부 / 기관 확인 자료
- 제3자 보도 1건 이상

출력:

- `source_evidence[]`

항목 예시:

- `evidence_type`
- `url`
- `title`
- `body_excerpt`
- `published_at`
- `reliability_rank`

구현 방식:

- 1차 버전은 deterministic fetch 중심으로 간다.
- 검색 API 의존을 최소화하려면, 원문 안의 링크와 공식 사이트 패턴을 먼저 우선 활용한다.
- 복잡한 케이스만 선택적으로 상위 모델을 써서 evidence priority를 정리한다.

### 4.5 Research Packet Build

역할:

- raw source와 evidence를 기사 작성용 구조화 데이터로 압축한다.

필수 필드:

- `site`
- `main_claim`
- `who_is_affected`
- `effective_date`
- `conditions`
- `exceptions`
- `cost_or_obligation`
- `action_items`
- `key_facts[]`
- `source_refs[]`
- `risk_flags[]`

중요 원칙:

- 모델에 원문 여러 개를 그대로 넘기지 않는다.
- 사람이 읽어도 이해되는 packet을 먼저 만든 뒤 기사 작성 모델에 준다.

### 4.6 Secondary Decision

역할:

- research packet 기준으로 실제 발행 여부를 확정한다.

등급:

- `A`: 메인 기사 가능
- `B`: 짧은 브리프 가능
- `C`: 폐기

판정 기준:

- 핵심 주장에 출처가 붙어 있는가
- 추가 근거가 최소 1~2개 있는가
- 매체 독자에게 실질 가치가 있는가
- 홍보성만 남지 않았는가

### 4.7 Draft Writing

역할:

- 최종 기사 초안을 작성한다.

모델 정책:

- 현재 `solar-pro3`는 이 단계에 계속 사용 가능하다.
- 다만 입력은 `raw body`가 아니라 `research packet`이어야 한다.

사이트별 쓰기 원칙:

- `IJ`: 문제, 해결책, 구조, 남은 조건
- `NN`: 누가 해당되는지, 무엇이 달라지는지, 어떻게 해야 하는지
- `CB`: 의무, 비용, 일정, 예외, 업종 영향

### 4.8 QA Validation

역할:

- 사실 정합성과 매체 적합성을 점검한다.

기존 QA에서 추가할 항목:

- research packet source refs와 핵심 주장 일치 여부
- 추가 근거 없는 해석 문장 존재 여부
- 도메인 간 중복 기사 위험

### 4.9 Layout / Image Decision

역할:

- 발행과 이미지 처리를 분리한다.

새 원칙:

- `safe image`가 있으면 사용
- 없으면 기사 발행은 유지
- 대신 `hero / card / list / brief` 중 어떤 편성 슬롯으로 갈지 따로 결정

즉, 이미지 실패 코드는 발행 실패가 아니라 편성 타입 결정으로 내려보낸다.

### 4.10 Publishing

최종 저장 필드:

- `site`
- `publish_grade`
- `layout_type`
- `image_status`
- `research_packet_id`
- `source_refs`
- `published_at`

## 5. 데이터 모델 변경

권장안은 새 테이블을 추가하는 방식이다.

### 5.1 `raw_sources`

- RSS 및 외부 소스 원문 저장

### 5.2 `source_evidence`

- 원문과 연결된 추가 근거 저장

### 5.3 `research_packets`

- 구조화된 기사 작성 입력 저장

### 5.4 `article_runs`

- 후보 -> packet -> draft -> publish 단계 추적

최소 버전으로 빨리 가려면 기존 테이블에 JSON 컬럼을 붙이는 방법도 가능하다.
다만 운영 추적성과 재처리 편의성을 생각하면 테이블 분리가 더 낫다.

## 6. 코드 변경 범위

핵심 변경 대상은 아래 파일이다.

- `engine.py`
- `prompts/news_editor_ij.md`
- `prompts/news_editor_nn.md`
- `prompts/news_editor_cb.md`
- `prompts/qa_checker.md`

권장 리팩터링 단위:

- `collect_raw_sources()`
- `filter_candidates()`
- `route_candidate()`
- `collect_evidence()`
- `build_research_packet()`
- `write_from_packet()`
- `qa_packet_article()`
- `decide_layout_type()`
- `publish_article()`

## 7. 모델 운영 정책

### 기본안

- `solar-pro3`: packet 기반 기사 작성
- 기존 QA 모델: packet 기반 QA

### 선택적 강화안

- 복잡한 멀티소스 기사만 상위 모델로 `evidence 정리` 수행
- 최종 기사 작성은 계속 `solar-pro3`

핵심은 모델 교체보다 역할 분리다.

## 8. 이미지 운영 정책

- 정책브리핑: 안전한 공식 첨부 이미지면 사용
- 뉴스와이어: 기본은 이미지 비신뢰, 원칙적으로 fallback 편성
- `hero/card`는 강한 비주얼이 있는 기사만
- 이미지 없는 기사는 `list/brief`로 발행

## 9. 구현 순서

### Phase 1. 파이프라인 분리

- raw source 저장
- candidate filtering
- primary routing

### Phase 2. research packet 도입

- evidence collection
- research packet build
- packet 기반 작성

### Phase 3. QA와 발행 분리

- packet 기반 QA
- image/layout decision 분리

### Phase 4. 운영 튜닝

- A/B/C 등급 운영
- 상위 모델 조건부 사용
- 검색 성과 기반 튜닝

## 10. 완료 기준

- 정책브리핑 / 뉴스와이어 단독 재작성 기사가 메인 발행 경로에서 제거된다.
- 기사 작성 입력이 raw body에서 research packet으로 바뀐다.
- 이미지 실패가 발행 실패로 이어지지 않는다.
- 원문 1개가 3도메인에 병렬 발행되지 않는다.
- `IJ`, `NN`, `CB`별 기사 톤과 구조 차이가 packet 단계부터 반영된다.
