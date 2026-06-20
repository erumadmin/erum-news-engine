# NN (이웃뉴스) 뉴스엔진 목표 설계 v1

**Status:** Draft — IJ v4 패턴을 NN 매체 성격에 맞게 재정의  
**Date:** 2026-06-05  
**Repo:** `erum-news-engine` (`news-engine-test` 브랜치)  
**Related:** [editorial-pipeline.md](./editorial-pipeline.md), [ij-news-engine-target-design-v4.md](./ij-news-engine-target-design-v4.md)

---

## 0. IJ와 NN의 차이 (한 페이지)

| | IJ (Impact Journal) | **NN (이웃뉴스)** |
|---|---------------------|-------------------|
| **North Star** | 권위 있는 **정책·제도 기사** | **생활에 닿는 뉴스**를 이웃이 설명해 주듯 풀어 쓴 기사 |
| **1차 독자** | 정책 관심 일반·업계 | 뉴스가 어렵게 느껴지는 **일반 독자** (지역·생활·이용자) |
| **리드** | 무엇이·언제·누가 바뀌는지 (뉴스) | **영향받는 사람·이용자**가 주어, 실제 변화가 첫 문장 |
| **톤** | 신문체 정책면 | 친절·명료, **대화체 흉내 금지**, 행정어 최소 |
| **4문단 역할** | 변화 → 배경 → 작동 → **다만 한계** | 대상·변화 → 왜 → **조건·절차·이용** → **생활 영향·남은 제한** |
| **독자 가치 축** | discovered·연대 시사점 (내부) | **누구 / 무엇이 바뀌는가 / 조건 / 무엇을 하면 되는가** (최소 3/4) |
| **본문 URL** | v4: 본문 무URL, footer 격리 | **동일** (ERUM CMS 공통) |
| **통과 키** | `article_publish_ready` | **`nn_article_ready`** (community_axes + 구조 + 톤) |

IJ의 NGO·연대 브리핑 장르는 **NN에 적용하지 않는다.**  
조사·`reader_utility`·패킷은 **공유**하되, 재작성·finalize·검증은 NN 전용이다.

---

## 1. North Star

> **어렵게 느껴지는 뉴스를, 내 이웃이 옆집에 설명해 주듯 — 대상·변화·조건·할 일이 분명한 생활 기사로 만든다.**

### 1.1 발행 기준 (`nn_article_ready`)

| # | 기준 | 설명 |
|---|------|------|
| N1 | **대상 선명** | 1문단 주어 = 영향받는 사람·업종·이용자 (기관명 리드 금지) |
| N2 | **생활 4축** | 누구 / 무엇이 바뀌는가 / 조건·시점 / 할 일 — **4개 중 3개 이상** 본문에 반영 |
| N3 | **이용·절차** | 원문에 신청·이용·시행·제외가 있으면 3문단에 반드시 포함 |
| N4 | **친절·품격** | 행정 홍보체·금지 수사(도모·제고·활성화 등) 없음 |
| N5 | **본문 무URL** | v4와 동일 — 확인 경로는 footer |
| N6 | **4문단 완결** | `<p>` 4개, 마지막은 한계·남은 제한 (「다만」 권장) |

---

## 2. 산출물 2층

```
┌─────────────────────────────────────────┐
│  A. PUBLISH ARTICLE (neighbornews.kr)    │
│  title, excerpt, body (4p), sources_footer│
└─────────────────────────────────────────┘
                    ▲
┌─────────────────────────────────────────┐
│  B. INTERNAL — community_brief 패킷       │
│  who_affected, life_change, conditions,   │
│  what_to_do (reader_utility에서 추출)     │
└─────────────────────────────────────────┘
                    ▲
┌─────────────────────────────────────────┐
│  C. RESEARCH CORE (IJ와 공유)             │
│  evidence, reader_utility, key_facts      │
└─────────────────────────────────────────┘
```

---

## 3. Env flags

| Variable | Default | Meaning |
|----------|---------|---------|
| `NN_PACKET_PIPELINE` | `0` | `1` = 원문+패킷+community_brief 하이브리드 재작성 |
| `NN_TARGET_ENGINE` | `0` | `1` = community_brief 생성·검증 활성 |
| `NN_PUBLISH_V4` | `1` | 본문 무URL·footer 격리 (IJ v4와 동일 규칙) |
| `EDITORIAL_PIPELINE` | `1` | ingest → route → research (공유) |

품질 루프: `scripts/run_nn_editorial_quality_loop.py`

---

## 4. 비목표 (v1)

- CB 편집 파이프 (별도 트랙)
- 프로덕션 API 발행 (`REVIEW_ONLY=0`) — Vercel 재개 후
- 원문 밖 사실 수집 (환각 금지 유지)
