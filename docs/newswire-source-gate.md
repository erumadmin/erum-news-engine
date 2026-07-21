# 뉴스와이어 Source Gate

주간에도 뉴스와이어 RSS를 **후보 풀**로 쓰되, 발행 전 원문 단위로 `IJ`/`NN`/`CB`/`DROP`을 선별한다.

## 모드

| `NEWSWIRE_DAYTIME_MODE` | 동작 |
|---|---|
| `screened` (기본) | 정책 수집과 별도로 뉴스와이어 후보 수집 → 원문 보강 → local/LLM gate → ROUTE만 병합 |
| `legacy` | 기존: 야간(18시+)·목표 미달 시에만 뉴스와이어로 잔여 채움 |
| `off` | 뉴스와이어 비활성 |

## 환경변수

```env
NEWSWIRE_DAYTIME_MODE=screened
NEWSWIRE_MAX_SELECTED_PER_RUN=5
NEWSWIRE_MAX_DAILY_SHARE=30
NEWSWIRE_MAX_PER_SITE_PER_RUN=3
NEWSWIRE_CANDIDATE_SCAN_LIMIT=80

SOURCE_GATE_PROVIDER=openrouter
SOURCE_GATE_MODEL=deepseek/deepseek-v4-flash
SOURCE_GATE_INPUT_MAX_CHARS=3000
SOURCE_GATE_MAX_OUTPUT_TOKENS=500
SOURCE_GATE_TEMPERATURE=0
SOURCE_GATE_AUTO_DROP_BELOW=35
SOURCE_GATE_AUTO_ROUTE_ABOVE=82
SOURCE_GATE_LLM_MIN_SCORE=35
SOURCE_GATE_LLM_MAX_SCORE=81
SOURCE_GATE_LLM=1
OPENROUTER_API_KEY=...
```

## Dry-run (발행 없음)

```bash
# 로컬만
SOURCE_GATE_LLM=0 .venv/bin/python scripts/run_newswire_source_gate_dry_run.py --limit 55 --no-llm

# DeepSeek 게이트 포함
.venv/bin/python scripts/run_newswire_source_gate_dry_run.py --limit 55 --with-llm
```

리포트: `review_outputs/source_gate/`

## 파이프라인 연결

- ROUTE 결과는 `article["_source_gate_site"]`로 전달되고, 편집 파이프라인에서 **1원문=1매체**로만 재작성한다.
- DROP은 `process_article()`에 들어가지 않는다.

## 강화 규칙 (2026-07-12)

- 제목 `수상|표창|선정|어워드` → 기본 DROP, **IJ 금지**. CB는 강한 실무 신호(키워드 ≥3)만 예외.
- `site_cap` / `org_cap` / run 상한은 **점수 순위 채우기**: 1단계에서 전원 자격심사(캡 무시) → 2단계에서 `ranking_score` 높은 순으로 슬롯 채움. 밀린 ROUTE는 `site_cap:{site}:rank` 등으로 DROP.
- decide 단건에서 preferred site가 이미 찬 경우 `site_cap:{site}` (allowed 약점수로 `below_threshold` 위장 금지). `NEWSWIRE_MAX_IJ_PER_RUN` 기본 2.
- 약한 NN 생활 프로그램 홍보(에어로빅·요가·신규 프로그램·인기 등, 공공·정책 신호 없음)는 `local_auto_route` 금지 + `weak_nn_promo` DROP. 순위 페널티(-45)와 공공·정책 보너스로 생활 PR이 공익 NN/IJ 슬롯을 뺏지 못하게 함. (IJ 슬롯 floor는 이번 라운드 미도입 — rank/보너스만으로 충분하고 floor는 캡 복잡도↑)
- 코호트/커리어 모집 PR(`교육생|수강생|N기 모집`, 미디어 커리어·빌드업 등)은 `recruit_promo` hard DROP + 순위 −50. 제목-강한 코호트(교육생 모집·제목 커리어 프레임)는 본문 우연 공공 키워드(고립/은둔/복지)로 면제되지 않음; 제목 자체에 고립은둔·학교밖·복지 정책·지원센터가 있을 때만 좁은 면제. 약한 경로(제목 모집만 + 본문 커리어)는 기존 `is_public_policy_signal` 면제 가능.
- Soft CB 파트너/제품 PR(`디자인 파트너|파트너 프로그램`, `기능 출시|월렛|양자 위험 관리` 등, EPC·공급망·공시·탄소·IRA·건설·M&A substance <2)는 `soft_cb_promo` hard DROP + CB `local_auto_route` 금지 + 재검증 DROP + 순위 −40. AI·보안·금융·투자 fluff만으로는 면제되지 않음 (비트고·엘립틱류가 한화큐셀 EPC 슬롯을 뺏지 못하게).
- Soft CB ETF/펀드 상품 출시(`UCITS ETF|ETF|ETN|상장지수펀드|펀드 출시|신규 ETF` + 출시·론칭 프레임, Defiance류)도 `soft_cb_promo` hard DROP; 재검증은 모든 site ROUTE를 DROP해 LLM이 기술/공급망 서사로 CB 우회하지 못하게 함. substance keep ≥2(한화 EPC·러셀 M&A·장기 주주 등)는 계속 ROUTE CB.
- CB 실무 substance(EPC·공급망·재생에너지·복합단지·건설·IRA·공장·계약·M&A 등 ≥2, ESG/CSR/탄소 fluff 제외)는 로컬 CB +8/hit(최대 6) 및 순위 +7/+14로 mid soft-ESG보다 우선 채움.
- LLM이 빈/무효 JSON을 내면 로컬이 약할 때만 `parse_fail` DROP; 로컬이 `auto_drop_below`(공공 NN/IJ·ops CB) 또는 ≥40(일반)이면 `llm_fallback_local:{site}` / stage `llm_fallback`로 ROUTE.
- 로컬 IJ−CB ≥ 15이면 CB ROUTE를 IJ로 재검증(`ij_fidelity_from_cb`); IJ 캡이면 DROP. (밀리언드림즈류 사이트 오분류 방지)
- LLM이 IJ로 내어도 로컬 재검증으로 DROP/CB·NN 재분류 가능.
- 이미지 없음: CB 신호 충분하면 soft(`NO_IMAGE`) 후 진행, 그 외 hard DROP.
- Dry-run 기본 상한은 운영과 동일(`MAX_SELECTED=5`). 완화는 `--max-selected` 또는 `SOURCE_GATE_DRY_RUN_RELAX_CAP=1`.
