"""Mock fetcher for REVIEW_ONLY Target engine tests (official URLs with unique excerpts)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


# Sentence intentionally absent from standard korea.kr electric-rate press text.
_KEPCO_UNIQUE = (
    "한전ON 모바일 앱에서는 요금제 비교 시뮬레이션과 전기사용 패턴 분석 리포트를 "
    "무료로 제공한다. 사업장 담당자는 앱에서 고지서 예상 요금을 미리 확인할 수 있다."
)

_PRICE_UNIQUE = (
    "참가격 에너지마켓플레이스에서는 LED 등 고효율 설비 지원 신청 절차와 "
    "소상공인 대상 에너지 효율 컨설팅 예약 방법을 안내한다."
)

_PRICE_HYGIENE_UNIQUE = (
    "참가격 누리집에서는 위생용품·생활용품별 용량·개수 변경 이력과 단위가격 비교표를 "
    "제공한다. 소비자단체·NGO 담당자는 품목별 고시 일정과 변경 전후 사양을 열람할 수 있다."
)

_MOTIE_RETURN_UNIQUE = (
    "산업통상자원부 유턴지원단 누리집에서는 해외법인 청산 절차 안내와 지방 투자 연계 상담 예약, "
    "복귀 기업 맞춤형 세제·보조금 신청 경로를 한눈에 확인할 수 있다."
)


def target_fixture_fetcher(url: str) -> Any:
    host = (urlparse(url).netloc or "").lower()
    body = ""
    if "kepco" in host:
        body = f"<html><head><title>한전ON</title></head><body><article><p>{_KEPCO_UNIQUE}</p></article></body></html>"
    elif "price.go" in host:
        body = f"<html><body><article><p>{_PRICE_HYGIENE_UNIQUE}</p></article></body></html>"
    elif "en-ter" in host:
        body = f"<html><body><p>{_PRICE_UNIQUE}</p></body></html>"
    elif "motie.go.kr" in host:
        body = f"<html><body><article><p>{_MOTIE_RETURN_UNIQUE}</p></article></body></html>"
    elif "korea.kr" in host:
        body = "<html><body><p>정책브리핑 본문</p></body></html>"
    else:
        body = f"<html><body><p>{'공식 안내 ' * 30}</p></body></html>"

    return type(
        "FixtureResponse",
        (),
        {"status_code": 200, "text": body, "content": body.encode("utf-8")},
    )()
