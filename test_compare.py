#!/usr/bin/env python3
"""NN / CB 프롬프트 테스트 — Solar Pro 3"""
import os, sys, re
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

import engine as eng

print(f"Rewrite model: {eng.UPSTAGE_MODEL_REWRITE}")
print(f"QA model:      {eng.UPSTAGE_MODEL_QA}")

# ─── 원문 3종 ───────────────────────────────────────────────

SOURCES = {
    "1200자": """
포스코홀딩스가 2025년부터 자사 철강 제품의 탄소 발자국을 제품 단위별로 공개하기로 했다. 포스코는 연간 철강 생산량의 50% 이상을 차지하는 주요 제품군 8종에 대해 생산 1톤당 탄소 배출량을 반기별로 고객사에 제공한다. 2024년 기준 포스코의 제품별 탄소 집약도는 철강 업종 글로벌 평균(1.85tCO2e/t)의 1.4배 수준이다.

이번 결정의 배경에는 현대차·기아 등 주요 완성차 고객사의 공급망 탄소 데이터 요구가 있다. 현대차는 2023년부터 1차 협력사에 탄소 발자국 데이터를 납품 평가 항목에 포함했으며 2026년부터는 소재 공급사로 범위를 확대할 방침이다. 포스코가 탄소 데이터 공개를 거부하거나 기준을 충족하지 못하면 완성차 공급망에서 이탈할 가능성이 생긴다. 자동차용 강판은 포스코 매출의 약 27%를 차지하는 핵심 사업이다.

포스코는 탄소 집약도 개선을 위해 수소 환원 제철 기술 개발에 2030년까지 3조 4,000억 원을 투자한다. 수소 환원 제철은 석탄 대신 수소를 환원제로 사용해 철강 생산 시 이산화탄소 대신 물만 발생하는 기술이다. 현재는 시범 설비 수준이며 상용화까지 최소 8년이 걸릴 것으로 전망된다. 단기 탄소 감축은 전기로 전환과 재생에너지 사용 비중 확대로 대응한다.

다만 탄소 데이터 공개가 경쟁사 대비 불리한 수치를 노출시킬 수 있다는 점은 리스크 요인이다. 한국철강협회는 "국내 철강사의 탄소 집약도가 유럽 경쟁사보다 높은 현실에서 데이터 투명성이 오히려 시장 지위를 약화시킬 수 있다"고 지적했다. 포스코는 2027년까지 탄소 집약도를 10% 낮추는 단기 목표를 제시했으나 유럽 경쟁사들과의 격차를 좁히는 데는 2030년 이후가 될 것으로 보인다.
""".strip(),

    "1500자": """
LG화학이 2025년부터 1차 협력사 전체를 대상으로 온실가스 배출량과 산업재해 현황을 반기별로 공개하는 의무 보고 체계를 도입한다. 공개 대상은 약 320개 협력사이며 이 중 중소기업 비중이 78%에 달한다. 공개 기준을 충족하지 못한 협력사는 2026년부터 신규 계약 체결이 제한된다. LG화학은 이 정보를 자사 지속가능경영보고서에 통합해 매년 공개하기로 했다.

이번 조치는 EU 공급망실사지침(CSDDD) 대응이 배경이다. CSDDD는 2026년부터 연매출 1억 5,000만 유로(약 2,200억 원) 이상 기업에 공급망 내 인권·환경 실사 의무를 부과하며 위반 시 매출의 최대 5%를 과징금으로 부과한다. LG화학의 2024년 유럽 매출은 약 4조 7,000억 원으로, 이론상 최대 2,350억 원의 과징금 리스크를 안고 있다. 재계에서는 이번 LG화학의 조치가 CSDDD 선제 대응 차원이라고 분석한다.

LG화학은 협력사 지원을 위해 '협력사 ESG 진단 플랫폼'을 2025년 3월 출시한다. 플랫폼 이용료는 무상이지만, 배출량 산정에 필요한 제3자 검증 비용은 협력사가 부담해야 한다. 검증 비용은 기업 규모에 따라 연 500만~3,000만 원 수준이다. 한국공급망ESG협의회에 따르면 국내 중소 협력사 가운데 탄소 배출량을 자체 측정할 역량을 갖춘 곳은 전체의 11%에 불과하다.

계약 제한 조항을 놓고 협력업체들의 반발이 나오고 있다. 중소기업중앙회는 "준비 기간 없이 일방적인 계약 조건 변경은 협력사 경영에 직접적인 부담을 준다"며 적응 기간 2년 연장을 요청했다. LG화학은 기준 미달 협력사에 2026~2027년 2년간 개선 계획서 제출로 계약 유지를 허용하는 유예 조항을 마련했다고 밝혔다. 그러나 유예 기간 종료 이후에도 기준을 충족하지 못하면 계약 해지가 가능해, 중소 협력사들의 불안은 가시지 않고 있다.

LG화학은 이번 조치와 별도로 2030년까지 배터리 소재 부문의 탄소 집약도를 2022년 대비 35% 낮추겠다는 목표도 내세웠다. 글로벌 전기차 제조사들이 배터리 소재 공급업체에 탄소 발자국 데이터를 납품 조건으로 요구하기 시작했기 때문이다. LG화학은 탄소 집약도 개선이 유럽 및 미국 완성차 공급망 유지와 직결된다고 설명했다. 회사 측은 탄소 목표를 달성하지 못하면 주요 전기차 공급망에서 이탈할 가능성을 공식적으로 인정한 셈이다.
""".strip(),

    "2000자": """
산업통상자원부가 2025년 재생에너지 보급 확대 계획을 발표하면서 태양광과 풍력 설비 용량을 2030년까지 합산 70GW로 늘리겠다고 밝혔다. 현재 국내 태양광 설비 용량은 약 28GW, 풍력은 2.1GW 수준으로 합산 30.1GW에 그친다. 목표 달성을 위해서는 앞으로 5년 안에 약 40GW를 추가로 설치해야 한다. 정부는 2030년 전력 공급에서 재생에너지 비중을 21.6%까지 끌어올리는 것을 목표로 잡고 있다.

문제는 설비가 늘어도 전력망에 연결되지 못하는 물량이 급증하고 있다는 점이다. 한국전력 자료에 따르면 2024년 말 기준 전력망 접속을 신청하고 대기 중인 태양광 설비만 7.3GW에 달한다. 이는 전국 배전망의 포화 상태와 신규 송전선 건설 지연이 복합적으로 작용한 결과다. 새 송전선 하나를 설치하기까지 인허가·주민 협의·시공을 포함해 평균 8~10년이 소요된다. 설비 확대 속도를 전력망이 따라가지 못하는 구조적 문제가 드러나고 있다.

산업부는 이를 해소하기 위해 2025년 안에 배전망 지능화 투자로 3,000억 원을 집행하기로 했다. 분산에너지 활성화 특별법을 통해 지역 내에서 생산한 전력을 해당 지역에서 소비하는 분산형 자급 체계를 구축하는 작업도 병행한다. 계통 포화 지역에는 에너지저장장치(ESS) 연계를 의무화하는 방안을 추진 중이다. 잉여 전력을 ESS에 저장해 전력망 부하를 분산시키겠다는 구상이다. 산업부는 2025년 하반기 중 배전망 지능화 시범사업 지역 10곳을 선정해 우선 투자할 계획이다.

그러나 이 계획에서 소외되는 주체도 있다. 소규모 농촌 태양광 사업자들은 ESS 의무화 비용을 감당하지 못해 신규 사업을 포기하는 사례가 속출하고 있다. 현재 50kW급 소규모 태양광 설비에 ESS를 연계하는 비용은 설비 투자비의 30~40%에 달하는 것으로 알려졌다. 전국태양광협회는 "소규모 사업자에 대한 별도 지원 없이 의무화를 강제하면 대형 자본만 살아남는 시장 쏠림이 발생한다"고 우려했다. 협회에 따르면 지난해 ESS 의무화 규정이 적용된 지역에서 소규모 사업자 73곳이 인허가 신청을 취하했다.

재생에너지 전문가들은 전력망 투자 속도를 현재보다 3배 이상 끌어올리지 않으면 2030년 목표 달성이 사실상 불가능하다고 분석한다. 한국에너지경제연구원은 연간 송전·배전 투자가 현재 수준의 2.8배 이상이어야 70GW 목표와 전력망 확충이 동시에 달성 가능하다고 추산했다. 현재 한전의 연간 배전망 투자 규모는 약 2조 원으로 목표 달성에 필요한 수준의 절반에 못 미친다. 산업부는 이에 대해 중장기 계통 보강 로드맵을 2025년 3분기 중 별도로 발표하겠다고 밝혔다. 전문가들은 로드맵에 소규모 사업자 보호 방안과 지역 주민 수용성 확보 대책이 함께 담겨야 한다고 지적한다.

전력망 문제는 재생에너지 확대에서 비단 한국만의 문제가 아니다. 미국과 유럽에서도 재생에너지 확대 과정에서 전력망 접속 대기 물량이 급증하며 수년째 해결 과제로 남아 있다. 미국 에너지부에 따르면 2023년 기준 미국 전역의 전력망 접속 대기 용량은 2,000GW를 넘어섰다. 한국은 국토 면적 대비 재생에너지 밀도가 높아질수록 이 문제가 더욱 심화될 수 있다.

산업부는 전력망 투자 확대와 함께 재생에너지 발전 예측 정확도를 높이는 기술 개발도 추진한다. 태양광·풍력의 발전량 변동성을 줄이기 위해 기상청과 협력해 2시간 단위 발전 예측 시스템을 2026년까지 구축하기로 했다. 예측 정확도가 높아지면 ESS 용량을 줄이면서도 전력망 안정성을 유지할 수 있어 소규모 사업자의 비용 부담을 낮출 수 있다는 게 정부의 설명이다. 그러나 예측 시스템 도입 효과가 현장에서 나타나기까지는 최소 3~5년이 걸릴 것으로 보여 단기적 해결책이 되기 어렵다는 반론도 있다.
""".strip(),
}

MEDIAS = ["IJ_", "NN_", "CB_"]

def run_one(label, source, model_name, media_prefix, use_gemini=False):
    """단일 모델·매체로 리라이트+QA 실행. 결과 dict 반환."""
    persona = eng.PERSONA_DEFINITIONS[media_prefix]
    src_len = len(source)
    min_body = int(src_len * 0.8)

    print(f"    [{media_prefix}] 리라이트...", end="", flush=True)
    try:
        if use_gemini:
            raw = eng._ask_gemini_rest(persona, source, model=model_name, stage="rewrite")
        else:
            raw = eng.ask_llm(persona, source, model=model_name, stage="rewrite")
    except Exception as ex:
        print(f" 오류: {str(ex)[:60]}")
        return {
            "title": "", "excerpt": "", "body": f"[오류: {str(ex)[:80]}]",
            "full_body_len": 0, "rw_len": 0, "score": 0,
            "passed": False, "fixed": False,
            "issues": [f"API 오류: {str(ex)[:60]}"],
        }

    p = eng.parse_llm_response(raw)
    rw_len = len(p.get('body', ''))
    print(f" {rw_len}자", end="", flush=True)

    print(f" | QA...", end="", flush=True)
    passed, fails, score, fixed = eng.ai_quality_check(p['title'], p['body'], media_prefix, source_len=src_len)
    final = fixed if fixed else p
    final_body_raw = final.get('body', '')
    final_plain = re.sub(r'<[^>]+>', ' ', final_body_raw).strip()
    final_plain_len = len(final_plain)

    ok = "fixed" if fixed else ("통과" if passed else "탈락")
    print(f" {score}점({ok}) {final_plain_len}자")

    issues = []
    if final_plain_len < min_body:
        issues.append(f"분량 미달 {final_plain_len}자 < 기준 {min_body}자")
    if not p.get('title'):
        issues.append("제목 없음")

    return {
        "title": final.get('title', ''),
        "excerpt": final.get('excerpt', ''),
        "body": final_plain[:400] + ("..." if len(final_plain) > 400 else ""),
        "full_body_len": final_plain_len,
        "rw_len": rw_len,
        "score": score,
        "passed": passed,
        "fixed": bool(fixed),
        "issues": issues,
    }

# results[media_prefix] = [(label, src_len, result), ...]
results = {m: [] for m in MEDIAS}

for label, source in SOURCES.items():
    src_len = len(source)
    print(f"\n{'━'*70}")
    print(f"▶ [{label}] 원문 {src_len}자  (기준 {int(src_len*0.8)}자)")
    print(f"{'━'*70}")

    for media in MEDIAS:
        r = run_one(label, source, eng.UPSTAGE_MODEL_REWRITE, media_prefix=media)
        icon = '✅' if not r['issues'] else '⚠️'
        print(f"  ┌─ [{media}] {r['full_body_len']}자 / QA {r['score']}점 {icon}")
        print(f"  │  제목: {r['title']}")
        print(f"  │  리드: {r['excerpt'][:80]}")
        print(f"  │  본문: {r['body']}")
        for iss in r['issues']:
            print(f"  │  ⚠ {iss}")
        print(f"  └{'─'*60}")
        results[media].append((label, src_len, r))

# ─── 종합표 ────────────────────────────────────────────────
print()
print("=" * 72)
print("종합")
print("=" * 72)
print(f"{'원문':>6} | {'매체':<6} | {'리라이트':>6} | {'최종(평문)':>10} | {'기준(80%)':>9} | {'QA':>4} | 판정")
print("-" * 72)
for label, source in SOURCES.items():
    src_len = len(source)
    base = int(src_len * 0.8)
    for media in MEDIAS:
        row = next(r for l, s, r in results[media] if l == label)
        icon = "✅" if not row['issues'] else "❌"
        print(f"{label:>6} | {media:<6} | {row['rw_len']:>6} | {row['full_body_len']:>10} | {base:>9} | {row['score']:>4} | {icon}")
    print(f"{'':>6} | {'':>6} |")
