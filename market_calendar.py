"""Reference KRX closed dates extracted verbatim from the uploaded FDR archive.

This is not a live official exchange calendar. Weekend closures and temporary
exchange decisions are not inferred from this data. Do not filter price series
based on the calendar: actual vendor observations are authoritative.
"""
from __future__ import annotations
from datetime import date
from functools import lru_cache
from pathlib import Path
import csv

_CALENDAR = Path(__file__).resolve().parent / 'reference_data' / 'holidays-krx.csv'

@lru_cache(maxsize=1)
def load_krx_holidays() -> frozenset[date]:
    if not _CALENDAR.is_file():
        return frozenset()
    with _CALENDAR.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if 'date' not in (reader.fieldnames or []):
            raise ValueError('KRX 휴장일 파일의 date 헤더가 없습니다.')
        return frozenset(date.fromisoformat(row['date']) for row in reader if row.get('date'))

def is_krx_holiday(day: date) -> bool:
    """True only for explicitly listed dates, never an inferred schedule."""
    return day in load_krx_holidays()
