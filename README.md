# Erum News Engine

정책·뉴스와이어 원문을 **이룸 3매체**용 기사로 재작성·검증·발행하는 Python 파이프라인입니다.

- **운영 실행:** **Vultr 서버 크론** → `python3 engine.py` (프론트는 Vercel, 엔진은 서버)
- **DB·미디어:** 같은 Vultr 인스턴스의 MariaDB / 업로드·API 경로
- **저장소 성격:** `news-engine-test` / 안정화 브랜치 작업용. **`main` 머지·프로덕션 반영은 별도 배포 승인 후**
- **규칙:** 자동 라우팅은 **1원문 = 1매체**. 기사 본문에 원문 URL·출처 링크를 넣지 않음 (v4는 하단 footer로만 출처 조립)

### 운영 런타임 (Vultr)

| 항목 | 값 |
|------|-----|
| 서버 | Vultr `Erum-News-Master` (예: `64.176.227.225`) |
| 경로 | `/root/erum-news-engine` |
| 크론 | 매시 `0 * * * *` → `git pull` 후 `python3 engine.py` |
| 로그 | `/root/erum-news-engine/cron.log` |
| env | `/root/erum-news-engine/.env` |

> **왜 Vultr인가:** korea.kr RSS가 GitHub Actions IP 대역을 차단해, 2026-04-17부터 서버 크론으로 전환했습니다.  
> `.github/workflows/news-engine.yml`은 코드상 남아 있을 수 있으나 **실발행 경로가 아닙니다** (수동 `workflow_dispatch`·레거시용).

---

## 세 데스크

같은 원문이라도 매체 관점이 다릅니다. 정본은 [`prompts/desks/`](prompts/desks/README.md).

| 코드 | 매체 | North Star | Fit가 아니면 |
|------|------|------------|--------------|
| **IJ** | 임팩트저널 | 제도·구조·범위가 보이는 **권위 있는 정책 기사** | 약하면 연대/NGO 패킷 쪽으로만 (Target 모드) |
| **NN** | 이웃뉴스 | **해당 독자**가 바로 판단하는 생활 안내 (리드는 기관 주어 금지) | 재작성 품질 루프 / 드롭 |
| **CB** | CSR브리핑 | 기업 **의무·비용·일정** 브리핑 | **기사를 쓰지 않음** |

엔진 프롬프트: `prompts/news_editor_{ij,nn,cb}.md` + `news_editor_common.md`.

---

## 파이프라인 한눈에

```text
수집(ingest/RSS) → 이미지 필수 → 리서치 → 패킷(brief)
  → LLM 재작성 → finalize/validate/scorecard → 발행본 v4
  → (REVIEW_ONLY=0일 때만) ERUM API 발행 → DB 기록
```

| 단계 | 역할 | 주요 위치 |
|------|------|-----------|
| 수집·중복 | korea.kr / newswire 등, MariaDB 중복 | `engine.py`, `engine/pipeline/ingest.py` |
| 라우팅 | IJ/NN/CB 배정, desk fit | `engine/profiles/`, `desk_fit.py` |
| 리서치 | 근거·discovered facts | `research_collector.py` |
| 패킷 | IJ journalist / NN community / CB compliance brief | `*_packet_writer.py` |
| 재작성 | OpenRouter / Gemini 등 | `engine.py` `ask_llm` |
| 검증 | 문단·리드·fidelity·desk Hard-Fail | `*_rewrite_validate.py`, `publish_validate.py` |
| 발행본 | 본문 무URL + footer, HTML sanitize (`nh3`) | `publish_body.py`, `html_sanitize.py` |
| 소스 게이트 | 원문 대비 재작성 적합성 (뉴스위어 등) | `source_gate.py`, `docs/newswire-source-gate.md` |

오케스트레이션 골격: `engine/pipeline/orchestrator.py`.

---

## 빠른 시작

```bash
cd erum-news-engine-test   # 또는 erum-news-engine (test 브랜치)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest

# 단위 테스트
.venv/bin/python -m pytest tests/ -q --ignore=tests/fixtures
```

비밀키는 저장소에 넣지 않습니다. 로컬은 `~/.env.erum_infra` 등에서 `OPENROUTER_API_KEY` / DB / API 값을 로드합니다.

### 데스크별 dry-run (발행 없음)

```bash
export REVIEW_ONLY=1 REWRITE_PROVIDER=openrouter

# IJ
FIXTURE_URL='https://www.korea.kr/news/policyNewsView.do?newsId=...' \
  .venv/bin/python scripts/run_ij_full_pipeline.py --mode dry-run

# NN / CB
EDITORIAL_FORCE_SITE=NN FIXTURE_URL='...' \
  .venv/bin/python scripts/run_nn_full_pipeline.py --mode dry-run
EDITORIAL_FORCE_SITE=CB FIXTURE_URL='...' \
  .venv/bin/python scripts/run_cb_full_pipeline.py --mode dry-run
```

| 모드 | 의미 |
|------|------|
| `dry-run` | 재작성·검증만, API 발행 없음 |
| `review` | 품질 루프 + 이미지 프로브(다운로드 포함 가능) |
| `hidden-publish` | DRAFT만, 홈 미노출 — **프로덕션 전 승인 필요** |

비교·리뷰 산출물: `review_outputs/` (커밋하지 않음).

---

## 주요 환경 변수

| 변수 | 기본 | 의미 |
|------|------|------|
| `REVIEW_ONLY` | `0` | `1`이면 발행 API 호출 안 함 |
| `EDITORIAL_PIPELINE` | `1` | ingest → route → research → placement |
| `EDITORIAL_FORCE_SITE` | — | `IJ` / `NN` / `CB` 강제 |
| `IJ_PACKET_PIPELINE` / `NN_PACKET_PIPELINE` / `CB_PACKET_PIPELINE` | 데스크별 | 패킷 하이브리드 재작성 |
| `*_PUBLISH_V4` | `1` 권장 | 본문 무URL + footer + publish gate |
| `REWRITE_PROVIDER` | — | `openrouter` 등 |
| `HIDDEN_PUBLISH_TEST` | `0` | DRAFT 전용 테스트 발행 |

상세: [`docs/editorial-pipeline.md`](docs/editorial-pipeline.md), 데스크 런북 아래 표.

---

## 디렉터리

```text
engine.py                 # 스케줄/CLI 메인 (수집·LLM·발행·DB)
engine/pipeline/          # 편집·검증·발행 모듈
engine/profiles/          # 매체 프로필·라우팅
prompts/                  # LLM 시스템 프롬프트 + desks/
scripts/                  # dry-run / quality loop / source-gate
tests/                    # pytest
docs/                     # 설계·런북
.github/workflows/        # news-engine, editorial review, backfill 등
review_outputs/           # 로컬 리뷰 산출 (gitignore)
```

---

## 운영 문서

| 문서 | 내용 |
|------|------|
| [docs/editorial-pipeline.md](docs/editorial-pipeline.md) | IJ 파이프라인·env·**main 머지 금지** |
| [docs/ij-complete-workflow.md](docs/ij-complete-workflow.md) | IJ 운영 런북 |
| [docs/nn-complete-workflow.md](docs/nn-complete-workflow.md) | NN 운영 런북 |
| [docs/cb-complete-workflow.md](docs/cb-complete-workflow.md) | CB 운영 런북 |
| [docs/newswire-source-gate.md](docs/newswire-source-gate.md) | 뉴스위어 소스 게이트 |
| [prompts/desks/README.md](prompts/desks/README.md) | 데스크 정체성 Hard-Fail |

---

## 품질·안전 메모

- 자동 엔진 점수(예: 10.0)만으로 “데스크 통과”로 보지 않습니다. 원문 대비 **source fidelity / source gate**와 데스크 Hard-Fail을 함께 봅니다.
- Publish HTML은 `nh3` allowlist sanitize를 거칩니다.
- `REVIEW_ONLY=0` 프로덕션 발행·`main` 머지는 **명시적 배포 승인 전 금지**.

---

## 라이선스 / 소유

이룸컴퍼니 내부 뉴스 엔진. 외부 공개용 라이선스 문서는 별도입니다.
