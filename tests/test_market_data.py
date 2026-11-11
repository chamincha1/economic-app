from datetime import date
from pathlib import Path
import json

import pandas as pd
import pytest

from market_data import (
    HistoricalPrices, fetch_historical_prices, save_historical_cache,
    read_historical_cache, format_origin,
)
from stock_core import StockDataError, calculate_indicators, trim_period


def mock_ohlcv():
    days = pd.bdate_range('2024-12-02', periods=90)
    return pd.DataFrame({
        'Date': days,
        'Open': [100.0] * len(days),
        'High': [105.0] * len(days),
        'Low': [95.0] * len(days),
        'Close': [100.0] * len(days),
        'Volume': [1000] * len(days),
    })


def test_real_provider_name_and_historical_dates():
    calls = []

    def reader(symbol, start, end):
        calls.append((symbol, start, end))
        return mock_ohlcv()

    prices = fetch_historical_prices('005930', '2025-01-01', '2025-03-31', reader=reader)
    assert prices.provider == 'NAVER'
    assert calls[0][0] == 'NAVER:005930'
    assert calls[0][1] < '2025-01-01'  # warm-up period
    assert prices.frame['Date'].max().date() <= date(2025, 3, 31)


def test_fallback_to_secondary_provider_without_fabrication():
    calls = []
    def reader(symbol, start, end):
        calls.append(symbol)
        if symbol.startswith('NAVER:'):
            raise TimeoutError('blocked')
        return mock_ohlcv()

    result = fetch_historical_prices('000660', '2025-01-01', '2025-03-31', reader=reader)
    assert result.provider == 'KRX'
    assert calls == ['NAVER:000660', 'KRX:000660']


def test_fails_without_real_data():
    def reader(symbol, start, end):
        raise ConnectionError('offline')
    with pytest.raises(StockDataError, match='수집 실패'):
        fetch_historical_prices('005930', '2025-01-01', '2025-03-31', reader=reader)


def test_cache_with_metadata_and_origin(tmp_path):
    prices = HistoricalPrices(mock_ohlcv(), 'NAVER')
    meta = save_historical_cache(tmp_path, '005930', prices)
    assert meta['is_realtime'] is False
    assert meta['source'] == 'FinanceDataReader:NAVER'
    assert (tmp_path / '005930.csv').exists()
    assert (tmp_path / '005930.meta.json').exists()
    df, stored = read_historical_cache(tmp_path, '005930')
    assert len(df) == len(prices.frame)
    assert stored['last_date'] == meta['last_date']
    assert 'NAVER' in format_origin(stored, cached=True)
    assert '이전 저장 자료' in format_origin(stored, cached=True)


def test_cache_old_version_uses_explicit_unknown_source(tmp_path):
    mock_ohlcv().to_csv(tmp_path / '005930.csv', index=False)
    _, meta = read_historical_cache(tmp_path, '005930')
    assert meta['source'].startswith('출처 미기록')
    assert meta['is_realtime'] is False


def test_invalid_or_wrong_period_is_rejected():
    with pytest.raises(StockDataError):
        fetch_historical_prices('GOOG', '2025-01-01', '2025-02-01', reader=lambda *a: mock_ohlcv())
    with pytest.raises(StockDataError):
        fetch_historical_prices('005930', '2025-03-01', '2025-02-01', reader=lambda *a: mock_ohlcv())
    with pytest.raises(StockDataError, match='수집 실패'):
        fetch_historical_prices('005930', '2026-01-01', '2026-03-01', reader=lambda *a: mock_ohlcv())


def test_discard_invalid_ohlc_rows():
    frame = mock_ohlcv()
    frame.loc[21, 'Open'] = 0
    frame.loc[22, 'High'] = float('nan')
    prices = fetch_historical_prices('005930', '2025-01-01', '2025-03-31', reader=lambda *a: frame)
    assert len(prices.frame) == (frame['Date'].dt.date <= date(2025, 3, 31)).sum() - 2
    assert (prices.frame['Open'] > 0).all()


def test_real_collection_output_compatible_with_stock_analysis():
    prices = fetch_historical_prices('005930', '2025-01-01', '2025-03-31', reader=lambda *a: mock_ohlcv())
    analyzed = calculate_indicators(prices.frame)
    output = trim_period(analyzed, '2025-01-01', '2025-03-31')
    assert len(output) > 10
    assert output['Scorable'].any()
