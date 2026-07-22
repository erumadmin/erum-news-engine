# 데스크 정체성 가이드 (`prompts/desks`)

기자·LLM이 **매체별 관점으로 기사를 쓰기 위한** 정본 규약입니다.

## 루프 상태

| Cycle | 내용 | 상태 |
|-------|------|------|
| 1 | desks 초안 (Identity→Example) | ✅ |
| 2 | 검토 갭 반영 (실원문 대비, Hard-Fail, 공통 예시) | ✅ |
| 3 | `news_editor_*.md` 이식 + 라우팅 Fit 게이트 | ✅ |
| 4 | Hard-Fail validator / CB fit 엔진 연결 | ✅ |

상세: `docs/superpowers/specs/2026-07-21-desk-identity-loop.md`

## 파일

| 파일 | 매체 | North Star |
|------|------|------------|
| [ij.md](./ij.md) | 임팩트저널 | 제도 구조가 보이는 권위 있는 정책 기사 |
| [nn.md](./nn.md) | 이웃뉴스 | 해당자가 바로 판단하는 생활 안내 기사 |
| [cb.md](./cb.md) | CSR브리핑 | 기업 의무·비용·일정 브리핑 (없으면 미배정) |
| [compare_example_icu.md](./compare_example_icu.md) | 공통 | 같은 원문(중환자실 부하지수) 3사 대비 |

## 기존 `news_editor_*.md`와의 관계

| 층 | 역할 |
|----|------|
| **`desks/*.md`** | 정체성·관점·Hard-Fail 정본 |
| **`news_editor_*.md`** | 엔진 주입용 (Cycle3: North Star+Hard-Fail 이식됨) |
| **`news_editor_common.md`** | 공통 사실·문체 |
| **`engine/pipeline/desk_fit.py`** | CB/NN Fit 라우팅 헬퍼 |
| **IJ validator/scorecard** | Cycle4: 해법 작동 구조(H1) 2·3문단 허용 |

## 사용법

```text
원문 + prompts/desks/{ij|nn|cb}.md  →  해당 매체 기사 초안
의심되면 compare_example_icu.md 로 각도 차이 확인
CB Fit이 아니면 기사를 쓰지 않음
Hard-Fail가 Self-Check보다 우선
```

같은 원문이라도 세 파일을 바꾸면 **제목·주어·문단 역할이 달라져야** 정상입니다.
