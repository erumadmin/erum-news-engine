"""KST day-boundary helpers for draft accounting (DB-timezone independent)."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now_kst(now: Optional[datetime] = None) -> datetime:
    if now is None:
        return datetime.now(KST)
    if now.tzinfo is None:
        return now.replace(tzinfo=KST)
    return now.astimezone(KST)


def kst_day_window(now: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """Aware KST [today 00:00, tomorrow 00:00)."""
    current = now_kst(now)
    start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def kst_naive_day_window(now: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """
    Naive datetimes representing KST wall-clock bounds for DATETIME columns
    that store KST-naive timestamps (engine convention).
    """
    start, end = kst_day_window(now)
    return start.replace(tzinfo=None), end.replace(tzinfo=None)


def now_kst_naive(now: Optional[datetime] = None) -> datetime:
    return now_kst(now).replace(tzinfo=None)
