from datetime import date
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest
from market_data import fetch_historical, validate_symbol, price_snapshot, list_domestic_stocks
from stock_core import StockDataError


def fixture_ohlcv(n=80):
    return pd.DataFrame({'Date': pd.bdate_range('2025-01-01', periods=n),
                         'Open': np.arange(n)+99, 'High': np.arange(n)+102,
                         'Low': np.arange(n)+97, 'Close': np.arange(n)+100,
                         'Volume': [1000]*n})


def test_naver_failure_then_krx_success(tmp_path):
    calls = []
    def reader(symbol, start, end):
        calls.append(symbol)
        if symbol.startswith('NAVER:'):
            raise ConnectionError('simulated provider failure')
        return fixture_ohlcv()
    result = fetch_historical('005930', date(2025,1,2),date(2025,6,1),
                              cache_dir=tmp_path, reader=reader)
    assert calls == ['NAVER:005930','KRX:005930']
    assert result.meta['status'] == 'fresh'
    assert result.meta['source'] == 'KRX:005930'
    assert (tmp_path/'005930.csv').exists()
    assert json.loads((tmp_path/'005930.meta.json').read_text(encoding='utf-8'))['realtime'] is False


def test_cached_provenance_never_renamed_fresh(tmp_path):
    fetch_historical('005930', date(2025,1,2),date(2025,6,1),
        cache_dir=tmp_path, reader=lambda *_: fixture_ohlcv())
    original = json.loads((tmp_path/'005930.meta.json').read_text(encoding='utf-8'))
    def failed(*args):
        raise ConnectionError('offline')
    saved = fetch_historical('005930', date(2025,1,2),date(2025,6,1),
        cache_dir=tmp_path, reader=failed)
    assert saved.is_cached
    assert saved.meta['retrieved_at'] == original['retrieved_at']
    assert len(saved.meta['attempt_errors']) == 2
    assert json.loads((tmp_path/'005930.meta.json').read_text(encoding='utf-8'))['status'] == 'fresh'


def test_no_fabricated_real_data(tmp_path):
    with pytest.raises(StockDataError, match='온라인 및 이전 캐시'):
        fetch_historical('005930', date(2025,1,2),date(2025,6,1),
            cache_dir=tmp_path, reader=lambda *_: (_ for _ in ()).throw(ConnectionError('offline')))


def test_symbol_validation():
    assert validate_symbol('005930') == '005930'
    with pytest.raises(StockDataError):
        validate_symbol('../bad')
    assert validate_symbol('KS11', index=True) == 'KS11'


def test_snapshot_and_listing():
    out = price_snapshot(fixture_ohlcv())
    assert out['volume'] == 1000
    assert out['close'] == 179
    assert out['approx_turnover'] == 179000
    stocks = list_domestic_stocks(lambda _: pd.DataFrame({'Code':['5930'], 'Name':['삼성전자']}))
    assert stocks['Code'].iloc[0] == '005930'


def test_index_can_have_no_volume(tmp_path):
    df = fixture_ohlcv().drop(columns=['Volume'])
    value = fetch_historical('KS11', date(2025,1,2),date(2025,6,1),
        cache_dir=tmp_path, reader=lambda *_: df, index=True)
    assert value.frame['Volume'].eq(0).all()
