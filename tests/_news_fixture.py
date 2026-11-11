"""Synthetic-only unit-test fixtures. Never copied into production data/cache."""
from datetime import timedelta
import pandas as pd


def news_fixture(code: str, days: int = 130, first: str = '2025-06-02') -> pd.DataFrame:
    dates = pd.date_range(first, periods=days, freq='7D', tz='Asia/Seoul')
    return pd.DataFrame([{'stock_code':code, 'title':f'단위 테스트 자료 {i}',
            'description':'테스트 시점의 데이터',
            'published_at':(d+pd.Timedelta(hours=11)).isoformat(),
            'first_seen_at':(d+pd.Timedelta(hours=12)).isoformat(),
            'source_url':f'https://example.invalid/{i}', 'synthetic':True}
            for i,d in enumerate(dates)])
