"""Verify uploaded archive *reference records* and KIS adapter mapping.

The HTTP responses below are test doubles, not real market quotes.
"""
from __future__ import annotations
import csv
import hashlib
import json
from datetime import date
from pathlib import Path
import pandas as pd
import pytest
from market_calendar import load_krx_holidays, is_krx_holiday
from kis_trade_volume import normalize_trade_volume, daily_trade_volume, API_PATH, TR_ID
from kis_market import KISReadOnlyClient, fetch_kis_trade_volume
from stock_core import StockDataError

ROOT=Path(__file__).resolve().parents[1]


def test_holidays_are_original_archive_bytes():
    original=(ROOT/'reference_data'/'holidays-krx.csv').read_bytes()
    provenance=json.loads((ROOT/'reference_data'/'SOURCE_PROVENANCE.json').read_text())
    assert hashlib.sha256(original).hexdigest() == provenance['files']['holidays-krx.csv']['original_sha256']
    assert len(load_krx_holidays()) == 620
    assert is_krx_holiday(date(2026,1,1))
    assert not is_krx_holiday(date(2026,11,11))


def test_catalog_is_subset_of_original_archive():
    with (ROOT/'reference_data'/'kis_stock_api_reference.csv').open(encoding='utf-8-sig', newline='') as f:
        rows=list(csv.DictReader(f))
    assert len(rows) == 8
    names={r['function_name'] for r in rows}
    assert {'inquire_daily_itemchartprice','inquire_price','inquire_daily_trade_volume'}.issubset(names)


def test_trade_volume_exact_kis_fields_and_no_fabrication():
    rows=[{'stck_bsop_date':'20251103','shnu_cnqn_smtn':'1,205','seln_cnqn_smtn':'1,403'},
          {'stck_bsop_date':'20251104','shnu_cnqn_smtn':'1,400','seln_cnqn_smtn':'1,400'}]
    frame=normalize_trade_volume(rows)
    assert list(frame.columns)==['Date','BuyExecutedVolume','SellExecutedVolume']
    assert frame.iloc[0].BuyExecutedVolume == 1205
    assert frame.iloc[1].SellExecutedVolume == 1400
    assert len(frame)==len(rows)
    assert normalize_trade_volume([]).empty
    with pytest.raises(StockDataError,match='필요한 필드'):
        normalize_trade_volume([{'stck_bsop_date':'20251103'}])


class Stub:
    def _get(self, path, tr_id, params):
        assert path == API_PATH
        assert tr_id == TR_ID
        assert params['FID_COND_MRKT_DIV_CODE'] == 'J'
        return {'output2':[{'stck_bsop_date':'20251104','shnu_cnqn_smtn':'30','seln_cnqn_smtn':'50'}]}


def test_api_arguments_and_history_persistence(tmp_path):
    result=fetch_kis_trade_volume('005930',date(2025,11,1),date(2025,11,5),
                                  cache_dir=tmp_path,client=Stub())
    assert result.meta['status']=='fresh'
    assert len(result.frame)==1
    assert (tmp_path/'kis_trade_volume'/'005930_J.csv').exists()
    class Fails:
        def _get(self,*args,**kwargs): raise ConnectionError('offline')
    cached=fetch_kis_trade_volume('005930',date(2025,11,1),date(2025,11,5),
                                   cache_dir=tmp_path,client=Fails())
    assert cached.meta['status']=='cached'
    assert cached.meta['realtime'] is False


def test_readonly_api_blocklist():
    client=KISReadOnlyClient(app_key='test-only',app_secret='test-only')
    with pytest.raises(StockDataError,match='허용되지 않은'):
        client._get('/uapi/domestic-stock/v1/trading/order-cash','ORDER_TR',{})
