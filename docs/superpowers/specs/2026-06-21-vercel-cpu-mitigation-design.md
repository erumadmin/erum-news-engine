# Vercel CPU Mitigation Design

**Date:** 2026-06-21
**Primary workspace:** `erum-news-engine`
**Related frontends:** `impactjournal-kr`, `neighbornews-frontend`, `csrbriefing-frontend`, `erum-company-website`
**Status:** Implemented locally, live verification pending unblock

## Goal

Vercel 제한 해제 전까지 `fluidCpuDuration` 재발 가능성이 높은 경로를 줄여, 서비스가 다시 열렸을 때 동일한 soft block이 반복되지 않도록 한다.

이번 작업은 기존 풀스택 리뷰 목표를 대체하지 않는다. 기존 목표는 그대로 유지하고, 이번 문서는 그 목표를 수행하기 위한 선행 안정화 트랙을 정의한다.

## Current Evidence

현재 확보된 운영 증거는 아래와 같다.

1. Vercel 팀 `erums-projects-cfc8699e`는 `Paused` 상태다.
2. API 응답은 `402`와 `DEPLOYMENT_DISABLED`를 반환한다.
3. 팀 메타데이터에는 아래 soft block 정보가 있다.
   - `reason: FAIR_USE_LIMITS_EXCEEDED`
   - `blockedDueToOverageType: fluidCpuDuration`
4. `impactjournal-kr`에는 이미 CPU 완화 목적 커밋이 별도로 들어갔다.
5. `neighbornews-frontend`, `csrbriefing-frontend`에는 기사 fetch 캐시만 일부 반영됐고, IJ 수준의 SEO 라우트 분할/경량화는 아직 남아 있다.

즉, 이번 문제는 단순 결제 이슈가 아니라 뉴스 프론트와 원본 API가 결합된 CPU 사용 패턴 문제로 보는 것이 타당하다.

## Problem Statement

현재 구조에서 CPU 재발 위험은 크게 두 층으로 나뉜다.

### Layer 1: Frontend SEO/Prerender routes

특히 `NN`, `CB`에 아래 패턴이 남아 있다.

- `sitemap.ts`가 기사 목록을 대량 fetch한다.
- `sitemap-news.xml`과 `feed.xml`이 기사 목록 조회를 전제로 동작한다.
- 기사 상세 `generateStaticParams()`가 고정 개수의 기사 선조회를 수행한다.

이 경로들은 검색엔진, 피드 리더, 빌드/ISR 재생성 시 반복 호출될 수 있어 `fluidCpuDuration` 누적에 직접 연결될 가능성이 높다.

### Layer 2: Origin article API cost

`erum-company-website`의 공개 `/api/articles`는 다음과 같은 비용 요인을 가진다.

- 공개 요청에서도 비교적 짧은 캐시만 사용한다.
- 목록 조회에 `count()`가 여러 번 붙는다.
- 검색 조건에서 `content contains`까지 포함한다.
- 기사 목록 조회가 본문 포함 레코드를 그대로 읽는다.

따라서 프론트가 캐시 miss를 내거나 SEO 라우트가 집중 호출되면, origin CPU가 다시 빠르게 누적될 수 있다.

## Scope

## In Scope

- `neighbornews-frontend`의 sitemap/news-sitemap/feed/detail prerender 경량화
- `csrbriefing-frontend`의 sitemap/news-sitemap/feed/detail prerender 경량화
- `impactjournal-kr`의 현재 완화 구조를 기준 패턴으로 재검토
- `erum-company-website` 공개 `/api/articles` 비용 절감 설계

## Out of Scope

- 기사 엔진 rewrite/publish 로직 자체 변경
- 관리자 포털 전반 리팩터링
- 라이브 운영 검증 결과가 필요한 기능 추가
- unrelated UI redesign

## Approaches

### Option 1: Frontend-only mitigation

장점:
- 가장 빨리 적용 가능하다.
- `NN`, `CB`의 반복적인 고비용 SEO 경로를 바로 줄일 수 있다.

단점:
- origin API의 비싼 응답 구조는 남는다.
- soft block 해제 후 트래픽이 몰리면 다시 누적될 수 있다.

### Option 2: Origin API-only mitigation

장점:
- 근본 비용을 줄이는 방향이다.
- 모든 브랜드에 공통 이득이 있다.

단점:
- 영향 범위가 넓다.
- 관리자/비공개 조회와 공개 조회를 함께 건드릴 가능성이 높아 회귀 위험이 크다.

### Option 3: Two-phase mitigation

1차로 `NN`, `CB` 프론트의 SEO/prerender 경로를 `IJ` 수준으로 경량화하고,
2차로 origin `/api/articles`를 공개 소비 기준으로 분리 최적화한다.

장점:
- 가장 위험한 재발 패턴부터 빠르게 제거할 수 있다.
- API 최적화를 별도 단계로 분리해 회귀 범위를 통제할 수 있다.
- 제한이 아직 풀리지 않은 상황에서도 로컬 코드 검토와 빌드 기준으로 진행할 수 있다.

단점:
- 작업이 두 단계로 나뉘어 문서와 검증이 더 필요하다.

## Recommendation

이번 건은 `Option 3`이 맞다.

이유는 다음과 같다.

1. 현재 가장 직접적인 재발 패턴은 `NN`, `CB` 프론트의 SEO 경로에 남아 있다.
2. `IJ`에는 이미 같은 문제를 줄이기 위한 선행 커밋이 들어가 있어, 재사용 가능한 기준 구현이 있다.
3. origin API는 반드시 손봐야 하지만, 영향 범위가 넓어 1차 수정과 한 번에 묶으면 검증 단위가 커진다.

## Execution Goals

### Top Goal

Vercel 제한 해제 전까지 `NN`, `CB`, origin API`에 남아 있는 고비용 경로를 정리해 `fluidCpuDuration` 재발 가능성을 낮춘다.

### Phase 1 Goal

`NN`, `CB` 프론트의 sitemap, news sitemap, feed, article prerender 경로를 `IJ`와 같은 저비용 구조로 정리한다.

### Phase 2 Goal

`erum-company-website`의 공개 `/api/articles` 경로를 공개 소비 전용 저비용 구조로 분리해 origin CPU 사용량을 줄인다.

## Success Criteria

### Phase 1

1. `NN`, `CB`에서 기사 전체 일괄 fetch 기반 sitemap 경로가 제거된다.
2. `NN`, `CB`의 feed/news sitemap/article prerender 경로가 제한된 fetch 또는 분할 구조를 사용한다.
3. 두 프론트 모두 로컬 build가 통과한다.
4. SEO 라우트 관련 테스트가 있으면 통과하고, 없으면 최소한 추가된 구조를 검증하는 테스트가 생긴다.

### Phase 2

1. 공개 `/api/articles`에서 불필요한 count, 검색, 본문 포함 비용이 줄어든다.
2. 관리자/비공개 조회 동작은 유지된다.
3. 세 프론트의 `src/lib/api.ts` 소비 계약이 유지된다.
4. 관련 테스트와 build가 통과한다.

## Design Outline

### Phase 1 design

- `impactjournal-kr`의 분할 sitemap 구조를 `NN`, `CB`에 맞게 이식한다.
- `sitemap.ts` 또는 단일 sitemap route가 대량 article fetch를 하지 않도록 바꾼다.
- `news sitemap`과 `feed`는 최근 기사만 읽고, 명시적 revalidate/cache header를 강화한다.
- `generateStaticParams()`는 꼭 필요한 범위만 유지하거나 제거 가능한지 검토한다.

### Phase 2 design

- 공개 article 목록 응답과 관리자용 응답을 논리적으로 분리한다.
- 공개 목록에서는 summary 목적의 필드만 읽는 방향을 우선 검토한다.
- 공개 요청에서만 더 긴 캐시 정책을 적용한다.
- 검색 쿼리와 일반 목록 쿼리를 분리해 비싼 `content contains` 조건이 기본 경로에 섞이지 않게 한다.

## Risks

1. 프론트 SEO 라우트 변경 후 sitemap URL 구조가 바뀌면 검색엔진 소비 경로가 흔들릴 수 있다.
2. origin API 최적화 과정에서 관리자 화면이 기대하던 summary/count 동작이 깨질 수 있다.
3. 라이브 API가 막혀 있어 실제 트래픽 환경 검증은 제한 해제 후 재확인이 필요하다.

## Validation Strategy

제한 해제 전 검증은 아래까지를 목표로 한다.

- 코드 경로 검토
- 관련 테스트 추가/수정
- `NN`, `CB`, `IJ`, `erum-company-website` 로컬 build 통과
- 가능하면 route 단위 응답 shape 테스트

제한 해제 후 재검증은 별도로 아래를 확인한다.

- `DEPLOYMENT_DISABLED` 해제
- live sitemap/feed/article 응답 정상화
- search engine facing routes의 응답 시간과 payload 확인

## Execution Snapshot (2026-06-21)

현재까지 로컬 기준으로 확인된 실행 결과는 아래와 같다.

### Phase 1 implemented

- `neighbornews-frontend`
  - 단일 `sitemap.ts` 제거
  - `sitemap.xml` index route 추가
  - `sitemaps/pages.xml` route 추가
  - `sitemaps/articles/[slug]` route 추가
  - `feed.xml`, `rss.xml`, `news-sitemap.xml`, `sitemap-news.xml` 공통 XML helper로 정리
  - article detail `generateStaticParams()` 제거
- `csrbriefing-frontend`
  - 단일 `sitemap.ts` 제거
  - `sitemap.xml` index route 추가
  - `sitemaps/pages.xml` route 추가
  - `sitemaps/articles/[slug]` route 추가
  - `feed.xml`, `sitemap-news.xml` 공통 XML helper로 정리
  - article detail `generateStaticParams()` 제거

### Phase 2 implemented

- `erum-company-website`
  - 공개 `/api/articles`용 cache policy helper 추가
  - 공개 요청에서 session cookie가 없으면 세션 조회 생략
  - 공개 요청은 summary count 3종 추가 계산을 생략
  - 공개 요청은 더 긴 cache header 사용
  - 공개 목록은 필요한 article/category 필드만 select

## Verification Snapshot (2026-06-21)

현재까지 확보된 검증 증거는 아래와 같다.

- `neighbornews-frontend`
  - helper tests pass
  - production build pass
- `csrbriefing-frontend`
  - helper tests pass
  - production build pass
- `erum-company-website`
  - article access/cache policy tests pass
  - `seo-routes.test.ts` pass
  - webpack build pass
- `impactjournal-kr`
  - webpack build pass after origin API changes
- `NN`, `CB` source scan
  - `getArticles({ limit: 1000 })` no longer present
- `erum-news-engine`
  - post-unblock audit helper tests pass
  - reusable verification script added: `scripts/run_vercel_cpu_mitigation_audit.py`

## Audit Status

| Requirement | Evidence | Result |
|---|---|---|
| Remove bulk sitemap fetch in `NN`, `CB` | `sitemap.ts` removed, split sitemap routes added, `limit: 1000` scan clean | Proven locally |
| Strengthen cache policy on SEO routes | route handlers now emit explicit `Cache-Control` headers | Proven locally |
| `NN`, `CB` build/test pass | helper tests + local builds | Proven locally |
| Reduce public `/api/articles` cost | cookie short-circuit, public summary reduction, public select/cache policy | Proven locally |
| Preserve frontend consumer contract | `impactjournal-kr`, `neighbornews-frontend`, `csrbriefing-frontend` builds pass | Proven locally |
| Verify live runtime behavior after unblock | blocked by `DEPLOYMENT_DISABLED` | Not yet proven |
