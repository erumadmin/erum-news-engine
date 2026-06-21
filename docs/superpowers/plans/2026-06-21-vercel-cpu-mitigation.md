# Vercel CPU Mitigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `NN`, `CB`, 그리고 origin article API`에 남아 있는 고비용 경로를 줄여 `fluidCpuDuration` 재발 가능성을 낮춘다.

**Architecture:** 작업을 두 단계로 나눈다. 1차는 `neighbornews-frontend`, `csrbriefing-frontend`의 SEO/prerender 경로를 `impactjournal-kr`의 저비용 패턴으로 맞춘다. 2차는 `erum-company-website`의 공개 `/api/articles` 경로를 공개 소비 기준으로 경량화한다.

**Tech Stack:** Next.js App Router, route handlers, fetch cache/revalidate, Prisma, Vercel deployment model, local builds/tests

---

## Execution Status (2026-06-21)

- Phase 1 local implementation complete
  - `NN`, `CB` split sitemap routes added
  - `feed/news sitemap` XML helpers added
  - article `generateStaticParams()` removed from `NN`, `CB` detail pages
- Phase 2 local implementation complete
  - public `/api/articles` cost policy helpers added
  - session-cookie short-circuit added
  - public summary/count work reduced
  - public cache headers lengthened
- Live verification pending because `erum-one.com` still returns `DEPLOYMENT_DISABLED`
- Reusable live audit script added: `scripts/run_vercel_cpu_mitigation_audit.py`

## File Map

| File | Responsibility |
|------|----------------|
| `impactjournal-kr/src/app/sitemap.xml/route.ts` | 기준이 되는 분할 sitemap index 구조 |
| `impactjournal-kr/src/app/sitemaps/articles/[slug]/route.ts` | 기준이 되는 article sitemap 분할 route |
| `impactjournal-kr/src/app/feed.xml/route.ts` | 기준이 되는 feed 캐시 정책 |
| `neighbornews-frontend/src/app/sitemap.ts` | 현재 NN의 고비용 전체 sitemap |
| `neighbornews-frontend/src/app/sitemap-news.xml/route.ts` | NN news sitemap |
| `neighbornews-frontend/src/app/feed.xml/route.ts` | NN feed route |
| `neighbornews-frontend/src/app/article/[id]/page.tsx` | NN detail prerender 경로 |
| `csrbriefing-frontend/src/app/sitemap.ts` | 현재 CB의 고비용 전체 sitemap |
| `csrbriefing-frontend/src/app/sitemap-news.xml/route.ts` | CB news sitemap |
| `csrbriefing-frontend/src/app/feed.xml/route.ts` | CB feed route |
| `csrbriefing-frontend/src/app/article/[id]/page.tsx` | CB detail prerender 경로 |
| `erum-company-website/app/api/articles/route.ts` | 공개/관리자 article 목록 API |

## Task 1: Freeze CPU mitigation scope

**Files:**
- Reference: `docs/superpowers/specs/2026-06-21-vercel-cpu-mitigation-design.md`
- Reference: `impactjournal-kr`
- Reference: `neighbornews-frontend`
- Reference: `csrbriefing-frontend`
- Reference: `erum-company-website`

- [ ] **Step 1: Reconfirm current Vercel block reason**

Run:

```bash
vercel api '/v2/teams?limit=20' | jq '.teams[] | select(.slug=="erums-projects-cfc8699e") | {slug, softBlock, billing: .billing.status}'
```

Expected: `softBlock.blockedDueToOverageType` is `fluidCpuDuration`

- [ ] **Step 2: Record current CPU-related frontend commits**

Run:

```bash
git -C /Users/leegyeongsub/Documents/Playground/impactjournal-kr log --oneline -5
git -C /Users/leegyeongsub/Documents/Playground/neighbornews-frontend log --oneline -5
git -C /Users/leegyeongsub/Documents/Playground/csrbriefing-frontend log --oneline -5
```

Expected: IJ CPU reduction commits and NN/CB cache-only commits visible

- [ ] **Step 3: Capture current high-cost route files**

Run:

```bash
rg -n "getArticles\\({ limit: 1000 }\\)|generateStaticParams|feed.xml|sitemap-news|sitemap" \
  /Users/leegyeongsub/Documents/Playground/neighbornews-frontend/src \
  /Users/leegyeongsub/Documents/Playground/csrbriefing-frontend/src
```

Expected: NN/CB sitemap and article prerender hotspots listed

## Task 2: Design NN sitemap split based on IJ pattern

**Files:**
- Review: `impactjournal-kr/src/app/sitemap.xml/route.ts`
- Review: `impactjournal-kr/src/app/sitemaps/articles/[slug]/route.ts`
- Modify: `neighbornews-frontend/src/app/sitemap.ts`
- Create or Modify: NN sitemap route files matching chosen split structure

- [ ] **Step 1: Compare IJ sitemap split routes to NN current sitemap**

Run:

```bash
sed -n '1,220p' /Users/leegyeongsub/Documents/Playground/impactjournal-kr/src/app/sitemap.xml/route.ts
sed -n '1,220p' '/Users/leegyeongsub/Documents/Playground/impactjournal-kr/src/app/sitemaps/articles/[slug]/route.ts'
sed -n '1,220p' /Users/leegyeongsub/Documents/Playground/neighbornews-frontend/src/app/sitemap.ts
```

Expected: exact structural difference between split sitemap and 1000-article sitemap understood

- [ ] **Step 2: Define NN target route set**

```text
NN target:
- sitemap index route
- static pages sitemap route
- article pages chunked sitemap route
- reuse existing API list fetch with bounded page size
```

Expected: no remaining plan ambiguity about NN sitemap structure

- [ ] **Step 3: List NN files to add/modify before coding**

```text
Modify:
- /Users/leegyeongsub/Documents/Playground/neighbornews-frontend/src/app/sitemap.ts or replace with route-based structure

Create or modify:
- /Users/leegyeongsub/Documents/Playground/neighbornews-frontend/src/app/sitemap.xml/route.ts
- /Users/leegyeongsub/Documents/Playground/neighbornews-frontend/src/app/sitemaps/pages.xml/route.ts
- /Users/leegyeongsub/Documents/Playground/neighbornews-frontend/src/app/sitemaps/articles/[slug]/route.ts
- /Users/leegyeongsub/Documents/Playground/neighbornews-frontend/src/lib/sitemaps.ts
- tests matching the chosen NN sitemap implementation
```

Expected: implementation surface frozen

## Task 3: Design CB sitemap split based on IJ pattern

**Files:**
- Review: `impactjournal-kr/src/app/sitemap.xml/route.ts`
- Review: `impactjournal-kr/src/app/sitemaps/articles/[slug]/route.ts`
- Modify: `csrbriefing-frontend/src/app/sitemap.ts`
- Create or Modify: CB sitemap route files matching chosen split structure

- [ ] **Step 1: Compare IJ sitemap split routes to CB current sitemap**

Run:

```bash
sed -n '1,220p' /Users/leegyeongsub/Documents/Playground/csrbriefing-frontend/src/app/sitemap.ts
```

Expected: same high-cost 1000-article pattern confirmed for CB

- [ ] **Step 2: Define CB target route set**

```text
CB target:
- sitemap index route
- static pages sitemap route
- article pages chunked sitemap route
- bounded page fetch for article URL sets
```

Expected: no remaining plan ambiguity about CB sitemap structure

- [ ] **Step 3: List CB files to add/modify before coding**

```text
Modify:
- /Users/leegyeongsub/Documents/Playground/csrbriefing-frontend/src/app/sitemap.ts or replace with route-based structure

Create or modify:
- /Users/leegyeongsub/Documents/Playground/csrbriefing-frontend/src/app/sitemap.xml/route.ts
- /Users/leegyeongsub/Documents/Playground/csrbriefing-frontend/src/app/sitemaps/pages.xml/route.ts
- /Users/leegyeongsub/Documents/Playground/csrbriefing-frontend/src/app/sitemaps/articles/[slug]/route.ts
- /Users/leegyeongsub/Documents/Playground/csrbriefing-frontend/src/lib/sitemaps.ts
- tests matching the chosen CB sitemap implementation
```

Expected: implementation surface frozen

## Task 4: Tighten NN and CB feed/news sitemap/detail prerender rules

**Files:**
- Modify: `neighbornews-frontend/src/app/feed.xml/route.ts`
- Modify: `neighbornews-frontend/src/app/sitemap-news.xml/route.ts`
- Modify: `neighbornews-frontend/src/app/article/[id]/page.tsx`
- Modify: `csrbriefing-frontend/src/app/feed.xml/route.ts`
- Modify: `csrbriefing-frontend/src/app/sitemap-news.xml/route.ts`
- Modify: `csrbriefing-frontend/src/app/article/[id]/page.tsx`

- [ ] **Step 1: Inspect current bounded fetch and cache settings**

Run:

```bash
sed -n '1,220p' /Users/leegyeongsub/Documents/Playground/neighbornews-frontend/src/app/feed.xml/route.ts
sed -n '1,220p' /Users/leegyeongsub/Documents/Playground/neighbornews-frontend/src/app/sitemap-news.xml/route.ts
sed -n '1,120p' '/Users/leegyeongsub/Documents/Playground/neighbornews-frontend/src/app/article/[id]/page.tsx'
sed -n '1,220p' /Users/leegyeongsub/Documents/Playground/csrbriefing-frontend/src/app/feed.xml/route.ts
sed -n '1,220p' /Users/leegyeongsub/Documents/Playground/csrbriefing-frontend/src/app/sitemap-news.xml/route.ts
sed -n '1,120p' '/Users/leegyeongsub/Documents/Playground/csrbriefing-frontend/src/app/article/[id]/page.tsx'
```

Expected: existing revalidate windows and `generateStaticParams()` usage visible

- [ ] **Step 2: Decide per-route mitigation**

```text
Decision points:
- keep bounded recent article fetch for feed/news sitemap
- strengthen cache headers to explicit public/s-maxage/stale-while-revalidate
- reduce or remove broad static param generation if runtime ISR is enough
```

Expected: exact intended route behavior defined before implementation

- [ ] **Step 3: Enumerate validation commands**

```bash
npm run build
npm test
```

Expected: concrete frontend verification commands ready for both repos

## Task 5: Design public article API cost reduction

**Files:**
- Modify: `erum-company-website/app/api/articles/route.ts`
- Possibly Create: helper module for public article list query shape
- Test: article API route tests in `erum-company-website`

- [ ] **Step 1: Inspect current public GET query plan surface**

Run:

```bash
sed -n '1,280p' /Users/leegyeongsub/Documents/Playground/erum-company-website/app/api/articles/route.ts
```

Expected: current `findMany`, `count`, search, and cache behavior visible

- [ ] **Step 2: Define public/admin split strategy**

```text
Public path should:
- default to published-only
- avoid unnecessary summary counts
- avoid expensive search behavior unless q is present
- prefer lighter field selection for list responses

Admin path should:
- preserve summary counts and broader access
- keep unpublished access rules intact
```

Expected: target split agreed in code terms before implementation

- [ ] **Step 3: List expected tests**

```text
Need tests for:
- public published list still returns expected article fields
- admin path still returns summary counts
- search path still works when q is provided
- cache headers remain correct for public requests
```

Expected: clear TDD scope before touching API code

## Task 6: Phase 1 verification

**Files:**
- Output: frontend build/test logs

- [ ] **Step 1: Build NN after mitigation**

Run:

```bash
cd /Users/leegyeongsub/Documents/Playground/neighbornews-frontend
API_BASE='https://erum-one.com' npm run build
```

Expected: successful production build

- [ ] **Step 2: Build CB after mitigation**

Run:

```bash
cd /Users/leegyeongsub/Documents/Playground/csrbriefing-frontend
API_BASE='https://erum-one.com' npx next build --webpack
```

Expected: successful production build

- [ ] **Step 3: Re-scan for remaining 1000-article sitemap fetches**

Run:

```bash
rg -n "getArticles\\({ limit: 1000 }\\)" \
  /Users/leegyeongsub/Documents/Playground/neighbornews-frontend/src \
  /Users/leegyeongsub/Documents/Playground/csrbriefing-frontend/src
```

Expected: no remaining matches in SEO route paths

## Task 7: Phase 2 verification

**Files:**
- Output: API route tests and consumer contract checks

- [ ] **Step 1: Run article API tests**

Run:

```bash
cd /Users/leegyeongsub/Documents/Playground/erum-company-website
npm test -- --runInBand
```

Expected: relevant route tests pass, or targeted failures identify missing coverage

- [ ] **Step 2: Rebuild the primary consumer**

Run:

```bash
cd /Users/leegyeongsub/Documents/Playground/impactjournal-kr
API_BASE='https://erum-one.com' npx next build --webpack
```

Expected: primary consumer still builds against unchanged contract

- [ ] **Step 3: Recheck live-unblock follow-up command set**

```bash
vercel api '/v2/teams?limit=20' | jq '.teams[] | select(.slug=="erums-projects-cfc8699e") | {slug, softBlock, blocked}'
curl -I -s https://erum-one.com | sed -n '1,20p'
```

Expected: commands ready for post-unblock validation, even if they still show blocked now
