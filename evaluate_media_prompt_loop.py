#!/usr/bin/env python3
"""NN / CB 프롬프트 수정 전후 배치 비교 + 색인/SEO 효용 평가."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

REPO_DIR = Path(__file__).resolve().parent
os.environ.setdefault("REVIEW_ONLY", "1")
sys.path.insert(0, str(REPO_DIR))

import engine as eng  # noqa: E402


TARGET_IDS = [
    "148962762",
    "148962757",
    "148962748",
    "148962753",
    "148962743",
    "148962420",
    "148962744",
    "148962741",
    "148962740",
    "148962737",
    "148962738",
    "148962731",
    "148962726",
    "148962697",
    "148962687",
    "148962678",
    "148962690",
    "148962419",
    "148962676",
    "148962669",
]

MEDIA_PREFIXES = ["NN_", "CB_"]
MEDIA_LABELS = {
    "NN_": "Neighbor News",
    "CB_": "CSR Briefing",
}
FETCH_WORKERS = 6
FETCH_TIMEOUT = 8
LOCAL_SOURCES = [
    {
        "url_id": "local-posco-carbon",
        "url": "local://posco-carbon",
        "title": "포스코홀딩스, 제품별 탄소 배출량 공개…완성차 공급망 대응",
        "body": """
포스코홀딩스가 2025년부터 자사 철강 제품의 탄소 발자국을 제품 단위별로 공개하기로 했다. 포스코는 연간 철강 생산량의 50% 이상을 차지하는 주요 제품군 8종에 대해 생산 1톤당 탄소 배출량을 반기별로 고객사에 제공한다. 2024년 기준 포스코의 제품별 탄소 집약도는 철강 업종 글로벌 평균의 1.4배 수준이다.

이번 결정의 배경에는 현대차·기아 등 주요 완성차 고객사의 공급망 탄소 데이터 요구가 있다. 현대차는 2023년부터 1차 협력사에 탄소 발자국 데이터를 납품 평가 항목에 포함했으며 2026년부터는 소재 공급사로 범위를 확대할 방침이다. 포스코가 탄소 데이터 공개를 거부하거나 기준을 충족하지 못하면 완성차 공급망에서 이탈할 가능성이 생긴다. 자동차용 강판은 포스코 매출의 약 27%를 차지하는 핵심 사업이다.

포스코는 탄소 집약도 개선을 위해 수소 환원 제철 기술 개발에 2030년까지 3조 4000억 원을 투자한다. 현재는 시범 설비 수준이며 상용화까지 최소 8년이 걸릴 것으로 전망된다. 단기 탄소 감축은 전기로 전환과 재생에너지 사용 비중 확대로 대응한다.

다만 탄소 데이터 공개가 경쟁사 대비 불리한 수치를 노출시킬 수 있다는 점은 리스크 요인이다. 한국철강협회는 국내 철강사의 탄소 집약도가 유럽 경쟁사보다 높은 현실에서 데이터 투명성이 오히려 시장 지위를 약화시킬 수 있다고 지적했다. 포스코는 2027년까지 탄소 집약도를 10% 낮추는 단기 목표를 제시했다.
""".strip(),
    },
    {
        "url_id": "local-lgchem-supplier",
        "url": "local://lgchem-supplier",
        "title": "LG화학, 협력사 ESG 공시 의무화…미달 시 신규 계약 제한",
        "body": """
LG화학이 2025년부터 1차 협력사 전체를 대상으로 온실가스 배출량과 산업재해 현황을 반기별로 공개하는 의무 보고 체계를 도입한다. 공개 대상은 약 320개 협력사이며 이 중 중소기업 비중이 78%에 달한다. 공개 기준을 충족하지 못한 협력사는 2026년부터 신규 계약 체결이 제한된다.

이번 조치는 EU 공급망실사지침 대응이 배경이다. 이 지침은 2026년부터 일정 규모 이상 기업에 공급망 내 인권·환경 실사 의무를 부과하며 위반 시 매출의 최대 5%를 과징금으로 부과한다. LG화학의 2024년 유럽 매출은 약 4조 7000억 원으로, 이론상 상당한 과징금 리스크를 안고 있다.

LG화학은 협력사 지원을 위해 협력사 ESG 진단 플랫폼을 2025년 3월 출시한다. 플랫폼 이용료는 무상이지만, 배출량 산정에 필요한 제3자 검증 비용은 협력사가 부담해야 한다. 검증 비용은 기업 규모에 따라 연 500만~3000만 원 수준이다. 국내 중소 협력사 가운데 탄소 배출량을 자체 측정할 역량을 갖춘 곳은 전체의 11%에 불과하다는 조사도 있다.

계약 제한 조항을 놓고 협력업체들의 반발도 나온다. 중소기업 단체는 준비 기간 없이 일방적인 계약 조건 변경은 협력사 경영에 부담을 준다며 적응 기간 연장을 요구했다. LG화학은 기준 미달 협력사에 2년간 개선 계획서 제출로 계약 유지를 허용하는 유예 조항을 마련했다고 밝혔다.
""".strip(),
    },
    {
        "url_id": "local-grid-renewable",
        "url": "local://grid-renewable",
        "title": "재생에너지 70GW 목표에도 전력망 병목…배전망 지능화 3000억 투입",
        "body": """
산업통상자원부가 2025년 재생에너지 보급 확대 계획을 발표하면서 태양광과 풍력 설비 용량을 2030년까지 합산 70GW로 늘리겠다고 밝혔다. 현재 국내 태양광 설비 용량은 약 28GW, 풍력은 2.1GW 수준이다. 목표 달성을 위해서는 앞으로 5년 안에 약 40GW를 추가로 설치해야 한다.

문제는 설비가 늘어도 전력망에 연결되지 못하는 물량이 급증하고 있다는 점이다. 한국전력 자료에 따르면 2024년 말 기준 전력망 접속을 신청하고 대기 중인 태양광 설비만 7.3GW에 달한다. 신규 송전선 하나를 설치하기까지 평균 8~10년이 걸린다.

산업부는 이를 해소하기 위해 2025년 안에 배전망 지능화 투자로 3000억 원을 집행하기로 했다. 계통 포화 지역에는 에너지저장장치 연계를 의무화하는 방안도 추진 중이다. 산업부는 2025년 하반기 중 배전망 지능화 시범사업 지역 10곳을 선정해 우선 투자할 계획이다.

그러나 소규모 농촌 태양광 사업자들은 ESS 의무화 비용을 감당하지 못해 신규 사업을 포기하는 사례가 속출하고 있다. 50kW급 소규모 태양광 설비에 ESS를 연계하는 비용은 설비 투자비의 30~40%에 달한다는 업계 추산이 있다. 전문가들은 전력망 투자 속도를 지금보다 크게 높이지 않으면 2030년 목표 달성이 사실상 어렵다고 본다.
""".strip(),
    },
    {
        "url_id": "local-public-asset",
        "url": "local://public-asset",
        "title": "청년·소상공인·다자녀 양육자 국공유재산 사용 문턱 완화",
        "body": """
행정안전부가 2026년부터 청년과 소상공인, 다자녀 양육자가 국공유재산을 빌리거나 사용할 때 대부료 감면율을 높이고 수의계약 대상을 확대하는 시행령 개정안을 입법예고했다. 청년 창업자와 지방 소상공인은 지역 여건에 따라 기존보다 낮은 사용료를 적용받을 수 있다.

개정안에는 다자녀 양육자에 대한 우선 사용 허가 근거도 담겼다. 현재는 공공시설 일부에서만 우대가 가능하지만, 앞으로는 지방자치단체가 조례로 정한 범위 안에서 공용 창고나 판매시설 등에도 우선 사용 기준을 둘 수 있다.

다만 감면 대상과 폭은 지자체 조례와 재산 종류에 따라 달라진다. 행안부는 재정 여건과 지역 수요를 고려해 세부 기준은 지방정부가 정하도록 했다. 이에 따라 모든 청년이나 소상공인이 동일한 혜택을 받는 것은 아니다.

행안부는 헐값 매각 우려를 막기 위해 매각 규정은 유지하고, 임대와 사용 허가 중심으로 완화 조치를 적용한다고 밝혔다. 개정안 의견 수렴은 다음 달까지 진행되며, 최종 시행 시점은 법제 심사 이후 확정된다.
""".strip(),
    },
    {
        "url_id": "local-ktx-srt",
        "url": "local://ktx-srt",
        "title": "호남선 KTX-SRT 중련운행 도입…좌석 820석으로 확대",
        "body": """
국토교통부와 코레일, SR이 5월 15일부터 호남선 일부 시간대에 KTX와 SRT를 연결해 한 편성처럼 운행하는 중련운행을 시작한다. 대상은 주말과 금요일 저녁 수요가 집중되는 구간이며, 한 번에 공급되는 좌석 수는 기존 410석 수준에서 최대 820석으로 늘어난다.

중련운행은 같은 시간대에 같은 방향으로 운행하던 KTX와 SRT를 묶어 운영하는 방식이다. 승객은 기존처럼 예매 단계에서 KTX 또는 SRT를 선택해야 하며, 승차권 가격 체계도 그대로 유지된다. 좌석이 늘어나는 대신 운임 할인이나 노선 신설이 이뤄지는 것은 아니다.

정부는 명절과 주말마다 반복되던 호남선 매진 문제를 줄이기 위한 조치라고 설명했다. 다만 선로 운영과 차량 배차가 가능한 시간대에만 적용돼 모든 열차로 즉시 확대되지는 않는다.

코레일과 SR은 한 달간 시범 운영 뒤 정시성, 승객 분산 효과, 차량 운용 안정성을 점검해 확대 여부를 결정할 계획이다. 정시성 문제가 발생하면 일부 시간대는 다시 단독 운행으로 전환될 수 있다.
""".strip(),
    },
    {
        "url_id": "local-kculture-event",
        "url": "local://kculture-event",
        "title": "외국인 인플루언서 120명 초청…비빔밥·DMZ 체험으로 K-컬처 홍보",
        "body": """
문화체육관광부가 올해 하반기 외국인 인플루언서 120명을 초청해 비빔밥 만들기, DMZ 방문, 전통시장 체험 등 한국 문화 홍보 프로그램을 운영한다. 참가자는 6회에 걸쳐 방한하며, 체험 영상은 각자의 사회관계망서비스 계정에 게시될 예정이다.

문체부는 한국 관광과 지역 문화에 대한 해외 관심을 높이기 위한 사업이라고 설명했다. 참가자 항공과 숙박, 이동 비용 일부는 정부 예산으로 지원된다. 다만 일반 시민이 신청해 참여하는 공개 프로그램은 아니다.

행사에는 지방자치단체와 한식, 전통문화 관련 기관이 협력기관으로 참여한다. 정부는 지역 관광지와 전통시장 방문을 통해 지방 관광 수요 분산 효과를 기대한다고 밝혔다.

다만 행사 효과를 측정하는 정량 목표는 아직 공개되지 않았다. 참가자가 제작한 콘텐츠 노출 수나 실제 관광객 유입 증가가 어느 정도인지에 따라 사업 지속 여부가 달라질 수 있다는 지적도 나온다.
""".strip(),
    },
]

SEO_SYSTEM_PROMPT = """
너는 검색 색인성과 SEO 관점에서 기사의 독자 효용을 판정하는 뉴스 품질 심사자다.
원문 대비 재작성 기사가 검색 결과에 노출될 만큼 새로운 효용을 주는지 평가한다.
반드시 JSON만 출력한다.

평가 기준
- unique_utility: 원문을 단순히 바꿔 적지 않고 독자가 새로 이해할 수 있는 구조, 맥락, 적용 포인트를 주는가
- search_intent: 제목과 리드가 독자가 실제로 찾을 질문(누가, 무엇이, 언제, 어떤 조건)과 잘 맞는가
- specificity: 대상, 변화, 조건, 시점, 예외 중 핵심 축이 구체적으로 드러나는가
- distinctiveness: 원문 대비 구조적 재구성과 해설 가치가 분명한가
- risk_control: 근거 없는 과장, 홍보 문체, 과도한 SEO식 표현 없이 원문 정합성을 지키는가

채점 규칙
- 각 항목은 0~20점
- total은 항목 합계
- verdict는 strong, borderline, weak 중 하나
- reasons는 핵심 판단 2~4개

출력 JSON 형식
{
  "scores": {
    "unique_utility": 0,
    "search_intent": 0,
    "specificity": 0,
    "distinctiveness": 0,
    "risk_control": 0
  },
  "total": 0,
  "verdict": "strong",
  "reasons": ["..."]
}
""".strip()


@dataclass
class VariantResult:
    title: str
    excerpt: str
    body: str
    body_chars: int
    valid: bool
    valid_msg: str
    qa_score: int
    qa_pass: bool
    qa_fails: List[str]
    fixed_applied: bool
    seo_total: int
    seo_verdict: str
    seo_reasons: List[str]
    attempts: List[dict]


def git_show(path_in_repo: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(REPO_DIR), "show", f"HEAD:{path_in_repo}"],
        text=True,
    )


def load_prompt_versions() -> Dict[str, Dict[str, str]]:
    common_text = (REPO_DIR / "prompts" / "news_editor_common.md").read_text(encoding="utf-8")
    versions = {
        "baseline": {
            "NN_": git_show("prompts/news_editor_nn.md"),
            "CB_": git_show("prompts/news_editor_cb.md"),
        },
        "current": {
            "NN_": (REPO_DIR / "prompts" / "news_editor_nn.md").read_text(encoding="utf-8"),
            "CB_": (REPO_DIR / "prompts" / "news_editor_cb.md").read_text(encoding="utf-8"),
        },
    }
    for version in versions.values():
        for prefix, specific in list(version.items()):
            version[prefix] = f"{common_text}\n\n{specific}"
    return versions


def fetch_review_article(url_id: str) -> dict | None:
    source_url = url_id if url_id.startswith("http") else f"https://www.korea.kr/news/policyNewsView.do?newsId={url_id}&call_from=rsslink"
    resp = eng.fetch_with_retry(source_url, max_retries=0, timeout=FETCH_TIMEOUT)
    if not resp or resp.status_code != 200:
        print(f"   ⚠️ [리뷰 원문] 직접 fetch 실패: {url_id} (HTTP {getattr(resp, 'status_code', 'none')})", flush=True)
        return None

    resp.encoding = "utf-8"
    soup = eng.BeautifulSoup(resp.text, "html.parser")
    title = ""
    h1 = soup.select_one("h1")
    if h1:
        title = h1.get_text(" ", strip=True)
    if not title:
        og_title = soup.find("meta", attrs={"property": "og:title"}) or soup.find("meta", attrs={"name": "og:title"})
        if og_title and og_title.get("content"):
            title = og_title.get("content", "").strip()
    if not title:
        title = url_id

    body_node = (
        soup.select_one(".view_cont")
        or soup.select_one(".article-content")
        or soup.select_one("#articleBody")
        or soup.select_one("article")
        or soup.select_one(".content")
        or soup.select_one(".view_cont")
    )
    body_text = body_node.get_text(separator="\n", strip=True) if body_node else eng.strip_html_tags(resp.text)
    main_node = soup.select_one("main.main") or soup.select_one("section.area_contents") or soup.select_one("main")
    source_published_at = None
    if main_node:
        source_published_at = eng._extract_first_date(main_node.get_text(" ", strip=True)[:1200])
    if not source_published_at:
        source_published_at = eng._extract_first_date(soup.get_text(" ", strip=True)[:1200])

    return {
        "url": source_url,
        "url_id": url_id,
        "title": title[:1000],
        "body": body_text[:40000],
        "image": "",
        "source_published_at": source_published_at,
    }


def load_review_articles(target_ids: List[str]) -> List[dict]:
    results: Dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        future_map = {pool.submit(fetch_review_article, url_id): url_id for url_id in target_ids}
        for future in as_completed(future_map):
            url_id = future_map[future]
            try:
                article = future.result()
            except Exception as exc:
                print(f"   ⚠️ [리뷰 원문] 예외: {url_id} ({str(exc)[:120]})", flush=True)
                article = None
            if article:
                results[url_id] = article
    return [results[url_id] for url_id in target_ids if url_id in results]


def load_local_articles() -> List[dict]:
    return [
        {
            **item,
            "image": "",
            "source_published_at": None,
        }
        for item in LOCAL_SOURCES
    ]


def parse_json_block(raw: str) -> dict:
    clean = re.sub(r"```json\s*", "", raw or "")
    clean = re.sub(r"```\s*", "", clean).strip()
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(clean)
    return obj


def judge_seo_utility(article: dict, variant: dict) -> Tuple[int, str, List[str]]:
    source_plain = re.sub(r"\s+", " ", eng.strip_html_tags(article.get("body", ""))).strip()[:1800]
    body_plain = re.sub(r"\s+", " ", eng.strip_html_tags(variant.get("body", ""))).strip()[:2200]
    user_text = "\n".join(
        [
            "원문 기사",
            f"제목: {(article.get('title') or '').strip()}",
            f"출처 URL: {(article.get('url') or '').strip()}",
            f"본문: {source_plain}",
            "",
            "재작성 기사",
            f"제목: {(variant.get('title') or '').strip()}",
            f"리드문: {(variant.get('excerpt') or '').strip()}",
            f"본문: {body_plain}",
        ]
    )
    try:
        raw = eng.ask_llm(
            SEO_SYSTEM_PROMPT,
            user_text,
            model=eng.UPSTAGE_MODEL_QA,
            max_output_tokens=700,
            stage="qa",
        )
        result = parse_json_block(raw)
        total = int(result.get("total", 0))
        verdict = str(result.get("verdict", "weak")).strip() or "weak"
        reasons = [str(x).strip() for x in result.get("reasons", []) if str(x).strip()]
        return total, verdict, reasons[:4]
    except Exception as exc:
        return 0, "weak", [f"SEO judge parse fail: {str(exc)[:120]}"]


def rewrite_once(article: dict, media_prefix: str, persona: str) -> VariantResult:
    rewrite_input = eng.build_rewrite_user_message(article)
    token_budgets = [eng.UPSTAGE_REWRITE_MAX_OUTPUT_TOKENS]
    if eng.UPSTAGE_REWRITE_RETRY_MAX_OUTPUT_TOKENS not in token_budgets:
        token_budgets.append(eng.UPSTAGE_REWRITE_RETRY_MAX_OUTPUT_TOKENS)

    parsed = None
    valid = False
    valid_msg = ""
    attempts: List[dict] = []

    for idx, max_tokens in enumerate(token_budgets):
        raw = eng.ask_llm(
            persona,
            rewrite_input,
            model=eng.UPSTAGE_MODEL_REWRITE,
            max_output_tokens=max_tokens,
            stage="rewrite",
        )
        parsed = eng.parse_llm_response(raw)
        valid, valid_msg = eng.validate_content_quality(parsed["title"], parsed["body"])
        body_chars = len(re.sub(r"\s+", " ", eng.strip_html_tags(parsed["body"])).strip())
        attempts.append(
            {
                "tokens": max_tokens,
                "valid": valid,
                "msg": valid_msg,
                "title": parsed["title"],
                "body_chars": body_chars,
            }
        )
        if valid:
            break
        if idx + 1 >= len(token_budgets) or not eng.should_retry_rewrite_validation(valid_msg):
            break

    if parsed is None:
        return VariantResult(
            title="",
            excerpt="",
            body="",
            body_chars=0,
            valid=False,
            valid_msg="재작성 결과 없음",
            qa_score=0,
            qa_pass=False,
            qa_fails=["재작성 결과 없음"],
            fixed_applied=False,
            seo_total=0,
            seo_verdict="weak",
            seo_reasons=["재작성 실패"],
            attempts=attempts,
        )

    final_variant = parsed
    qa_pass = False
    qa_fails: List[str] = []
    qa_score = 0
    fixed_applied = False

    if valid:
        qa_pass, qa_fails, qa_score, fixed = eng.ai_quality_check(
            parsed["title"],
            parsed.get("excerpt", ""),
            parsed["body"],
            media_prefix,
            source_article=article,
        )
        if not qa_pass and fixed:
            fixed_valid, fixed_msg = eng.validate_content_quality(fixed["title"], fixed["body"])
            if fixed_valid:
                final_variant = fixed
                valid = True
                valid_msg = fixed_msg
                fixed_applied = True
                qa_pass = True

    body_chars = len(re.sub(r"\s+", " ", eng.strip_html_tags(final_variant["body"])).strip())
    seo_total, seo_verdict, seo_reasons = judge_seo_utility(article, final_variant) if valid else (0, "weak", [valid_msg])

    return VariantResult(
        title=final_variant["title"],
        excerpt=final_variant.get("excerpt", ""),
        body=final_variant["body"],
        body_chars=body_chars,
        valid=valid,
        valid_msg=valid_msg,
        qa_score=qa_score,
        qa_pass=qa_pass,
        qa_fails=qa_fails,
        fixed_applied=fixed_applied,
        seo_total=seo_total,
        seo_verdict=seo_verdict,
        seo_reasons=seo_reasons,
        attempts=attempts,
    )


def rewrite_variant(article: dict, media_prefix: str, persona: str) -> VariantResult:
    result = rewrite_once(article, media_prefix, persona)
    if media_prefix not in ("NN_", "CB_"):
        return result
    return result


def summarize_media(rows: List[dict]) -> dict:
    baseline_qa = sum(r["baseline"]["qa_score"] for r in rows) / len(rows)
    current_qa = sum(r["current"]["qa_score"] for r in rows) / len(rows)
    baseline_seo = sum(r["baseline"]["seo_total"] for r in rows) / len(rows)
    current_seo = sum(r["current"]["seo_total"] for r in rows) / len(rows)
    return {
        "sample_size": len(rows),
        "baseline_avg_qa": round(baseline_qa, 2),
        "current_avg_qa": round(current_qa, 2),
        "baseline_avg_seo": round(baseline_seo, 2),
        "current_avg_seo": round(current_seo, 2),
        "baseline_valid_count": sum(1 for r in rows if r["baseline"]["valid"]),
        "current_valid_count": sum(1 for r in rows if r["current"]["valid"]),
        "baseline_pass_count": sum(1 for r in rows if r["baseline"]["qa_pass"]),
        "current_pass_count": sum(1 for r in rows if r["current"]["qa_pass"]),
        "seo_improved_count": sum(1 for r in rows if r["current"]["seo_total"] > r["baseline"]["seo_total"]),
        "seo_same_count": sum(1 for r in rows if r["current"]["seo_total"] == r["baseline"]["seo_total"]),
        "seo_regressed_count": sum(1 for r in rows if r["current"]["seo_total"] < r["baseline"]["seo_total"]),
        "qa_improved_count": sum(1 for r in rows if r["current"]["qa_score"] > r["baseline"]["qa_score"]),
        "qa_same_count": sum(1 for r in rows if r["current"]["qa_score"] == r["baseline"]["qa_score"]),
        "qa_regressed_count": sum(1 for r in rows if r["current"]["qa_score"] < r["baseline"]["qa_score"]),
        "current_strong_count": sum(1 for r in rows if r["current"]["seo_verdict"] == "strong"),
        "current_borderline_count": sum(1 for r in rows if r["current"]["seo_verdict"] == "borderline"),
        "current_weak_count": sum(1 for r in rows if r["current"]["seo_verdict"] == "weak"),
    }


def to_plain_result(result: VariantResult) -> dict:
    return {
        "title": result.title,
        "excerpt": result.excerpt,
        "body_chars": result.body_chars,
        "valid": result.valid,
        "valid_msg": result.valid_msg,
        "qa_score": result.qa_score,
        "qa_pass": result.qa_pass,
        "qa_fails": result.qa_fails,
        "fixed_applied": result.fixed_applied,
        "seo_total": result.seo_total,
        "seo_verdict": result.seo_verdict,
        "seo_reasons": result.seo_reasons,
        "attempts": result.attempts,
    }


def build_markdown(report: dict) -> str:
    lines = [
        "# NN/CB 프롬프트 루프 평가",
        "",
        f"- 생성 시각(KST): {report['created_at']}",
        f"- 원문 소스: {report.get('source_mode', 'unknown')}",
        f"- 대상 기사 수: {report['sample_size']}",
        "",
    ]
    for media_prefix in MEDIA_PREFIXES:
        media = report["media"][media_prefix]
        summary = media["summary"]
        lines.extend(
            [
                f"## {MEDIA_LABELS[media_prefix]}",
                "",
                f"- QA 평균: {summary['baseline_avg_qa']} -> {summary['current_avg_qa']}",
                f"- SEO 효용 평균: {summary['baseline_avg_seo']} -> {summary['current_avg_seo']}",
                f"- 유효성: {summary['baseline_valid_count']}/{summary['sample_size']} -> {summary['current_valid_count']}/{summary['sample_size']}",
                f"- SEO 판정: strong {summary['current_strong_count']} / borderline {summary['current_borderline_count']} / weak {summary['current_weak_count']}",
                f"- SEO 개선/동일/하락: {summary['seo_improved_count']} / {summary['seo_same_count']} / {summary['seo_regressed_count']}",
                "",
                "| 기사 | baseline SEO | current SEO | verdict | baseline QA | current QA |",
                "|---|---:|---:|---|---:|---:|",
            ]
        )
        for row in media["rows"]:
            lines.append(
                f"| {row['source_title']} | {row['baseline']['seo_total']} | {row['current']['seo_total']} | "
                f"{row['current']['seo_verdict']} | {row['baseline']['qa_score']} | {row['current']['qa_score']} |"
            )
        lines.append("")
        weak_rows = [r for r in media["rows"] if r["current"]["seo_verdict"] == "weak"][:5]
        if weak_rows:
            lines.append("### 현재 weak 사례")
            lines.append("")
            for row in weak_rows:
                reasons = ", ".join(row["current"]["seo_reasons"]) or "-"
                lines.append(f"- {row['source_title']}: {reasons}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    print("Loading prompt versions...", flush=True)
    prompt_versions = load_prompt_versions()
    print("Loading review articles...", flush=True)
    articles = load_review_articles(TARGET_IDS)
    source_mode = "live"
    if len(articles) < 4:
        print("Live source fetch failed. Falling back to local benchmark sources.", flush=True)
        articles = load_local_articles()
        source_mode = "local_benchmark"

    report = {
        "created_at": eng.now_kst().strftime("%Y-%m-%d %H:%M:%S"),
        "sample_size": len(articles),
        "source_mode": source_mode,
        "media": {},
    }

    for media_prefix in MEDIA_PREFIXES:
        rows = []
        for idx, article in enumerate(articles, 1):
            print(f"[{media_prefix}] {idx}/{len(articles)} {article.get('title', '')[:60]}", flush=True)
            baseline = rewrite_variant(article, media_prefix, prompt_versions["baseline"][media_prefix])
            current = rewrite_variant(article, media_prefix, prompt_versions["current"][media_prefix])
            rows.append(
                {
                    "source_title": article.get("title", ""),
                    "source_url": article.get("url", ""),
                    "baseline": to_plain_result(baseline),
                    "current": to_plain_result(current),
                }
            )
        report["media"][media_prefix] = {
            "summary": summarize_media(rows),
            "rows": rows,
        }

    output_dir = REPO_DIR / "review_outputs"
    output_dir.mkdir(exist_ok=True)
    ts = eng.now_kst().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"nn_cb_prompt_loop_{ts}.json"
    md_path = output_dir / f"nn_cb_prompt_loop_{ts}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_markdown(report), encoding="utf-8")
    print(f"JSON: {json_path}")
    print(f"MD:   {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
