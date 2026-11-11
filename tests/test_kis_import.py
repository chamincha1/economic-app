"""Offline KIS response fixtures: no credentials or network access required."""
from __future__ import annotations
from datetime import date
import json
import pandas as pd
import pytest
from kis_market import (KISReadOnlyClient, normalize_kis_daily, fetch_kis_historical)
from import_real_data import import_file
from stock_core import StockDataError


def kis_rows(n=90, first='2025-01-02'):
    dates = pd.bdate_range(first,periods=n)
    return [{'stck_bsop_date':d.strftime('%Y%m%d'), 'stck_oprc':str(1000+i),
             'stck_hgpr':str(1010+i),'stck_lwpr':str(990+i),
             'stck_clpr':str(1005+i),'acml_vol':str(10000+i),
             'acml_tr_pbmn':str(50000+i)} for i,d in enumerate(dates)]


def test_output2_to_standard_ohlcv():
    converted = normalize_kis_daily({'output2':kis_rows(5)})
    assert converted.columns.to_list()[:6] == ['Date','Open','High','Low','Close','Volume']
    assert converted.iloc[0]['Date'].date() == date(2025,1,2)
    assert converted.iloc[0]['Close'] == 1005
    assert converted.iloc[0]['Volume'] == 10000
    assert converted['Date'].is_unique


def test_missing_required_kis_columns_errors():
    with pytest.raises(StockDataError,match='필수 열'):
        normalize_kis_daily([{'stck_bsop_date':'20250102'}])


class FakeResponse:
    def __init__(self, body, status=200):
        self.status_code = status
        self.body = body
    def json(self):
        return self.body


class FakeHTTP:
    def __init__(self):
        self.post_calls = 0
        self.get_calls = []
    def post(self,url,**kwargs):
        assert url.endswith('/oauth2/tokenP')
        self.post_calls += 1
        return FakeResponse({'access_token':'dummy-token','expires_in':3600})
    def get(self,url,params=None,headers=None,**kwargs):
        assert 'inquire-' in url
        assert headers['authorization'].startswith('Bearer ')
        self.get_calls.append((url,dict(params)))
        if url.endswith('inquire-price'):
            return FakeResponse({'rt_cd':'0','output':{'stck_prpr':'70000',
                                  'stck_prdy_clpr':'68000','acml_vol':'10000',
                                  'acml_tr_pbmn':'700000000','prdy_ctrt':'2.94'}})
        # Mimic API returning only the requested chunk
        a = pd.Timestamp(params['FID_INPUT_DATE_1'])
        b = pd.Timestamp(params['FID_INPUT_DATE_2'])
        rows = [r for r in kis_rows() if a <= pd.Timestamp(r['stck_bsop_date']) <= b]
        return FakeResponse({'rt_cd':'0','output2':rows,'output1':{}})


def test_readonly_auth_quote_and_daily(monkeypatch):
    http = FakeHTTP()
    client = KISReadOnlyClient(app_key='TEST',app_secret='TEST',session=http)
    df = client.daily('005930',date(2025,1,2),date(2025,2,28))
    assert len(df)>20
    assert http.get_calls[0][1]['FID_ORG_ADJ_PRC'] == '0'
    quote = client.quote('005930')
    assert quote['price']==70000
    assert quote['realtime'] is False
    assert http.post_calls==1
    assert all('/quotations/' in entry[0] for entry in http.get_calls)


def test_kis_save_separate_cache_and_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr('kis_market.time.sleep',lambda *_:None)
    http=FakeHTTP()
    client=KISReadOnlyClient(app_key='TEST',app_secret='TEST',session=http)
    result = fetch_kis_historical('005930', date(2025,2,1),date(2025,4,15),
                                   cache_dir=tmp_path, client=client)
    assert result.meta['status']=='fresh'
    assert result.meta['source']=='KIS:J'
    assert not result.meta['realtime']
    assert (tmp_path/'kis'/'005930_J_adj.csv').is_file()
    assert not (tmp_path/'005930.csv').exists()
    class Offline:
        def daily(self,*_args,**_kwargs):
            raise ConnectionError('offline')
    cached=fetch_kis_historical('005930', date(2025,2,1),date(2025,4,15),
                                cache_dir=tmp_path,client=Offline())
    assert cached.is_cached
    assert cached.meta['source']=='KIS:J'
    assert json.loads((tmp_path/'kis'/'005930_J_adj.meta.json').read_text())['status']=='fresh'


def test_import_kis_json_writes_standard_csv(tmp_path):
    path=tmp_path/'KIS_output2.json'
    path.write_text(json.dumps({'output2':kis_rows(20)}),encoding='utf-8')
    f,meta=import_file(path,'005930',source='KIS JSON 수동 다운로드',cache_dir=tmp_path/'data_cache')
    assert len(f)==20
    assert meta['status']=='imported'
    assert meta['source_verified'] is False
    dest=tmp_path/'data_cache'/'005930.csv'
    assert dest.is_file()
    saved=pd.read_csv(dest)
    assert all(k in saved for k in ('Date','Open','High','Low','Close','Volume'))
    assert (tmp_path/'data_cache'/'005930.meta.json').exists()
    with pytest.raises(StockDataError,match='덮어쓰려면'):
        import_file(path,'005930',source='KIS',cache_dir=tmp_path/'data_cache')


def test_manual_csv_dry_run_does_not_write(tmp_path):
    path=tmp_path/'prices.csv'
    path.write_text('Date,Open,High,Low,Close,Volume\n'
                    '2025-01-02,100,110,95,105,300\n'
                    '2025-01-03,105,113,100,110,200\n'
                    '2025-01-06,110,115,102,111,250\n',encoding='utf-8')
    frame,_ = import_file(path,'005930',source='테스트',cache_dir=tmp_path/'cache',dry_run=True)
    assert len(frame)==3
    assert not (tmp_path/'cache').exists()
    with pytest.raises(StockDataError,match='6자리'):
        import_file(path,'../bad',source='테스트',cache_dir=tmp_path/'cache')


def test_import_rejects_bad_prices(tmp_path):
    path=tmp_path/'bad.csv'
    path.write_text('Date,Open,High,Low,Close,Volume\n'
                    '2025-01-02,100,101,95,105,300\n'
                    '2025-01-03,105,113,100,110,200\n'
                    '2025-01-06,110,115,102,111,250\n',encoding='utf-8')
    with pytest.raises(StockDataError,match='OHLC'):
        import_file(path,'005930',source='테스트',cache_dir=tmp_path/'cache')


def test_kis_missing_token_no_credentials():
    with pytest.raises(StockDataError,match='KIS_APP_KEY'):
        KISReadOnlyClient(app_key='',app_secret='')


def test_import_does_not_accept_vendor_source_zip(tmp_path):
    path=tmp_path/'some.zip';path.write_bytes(b'not a data file')
    with pytest.raises(StockDataError,match='ZIP'):
        import_file(path,'005930',source='압축',cache_dir=tmp_path/'cache')


def test_compact_yyyymmdd_dates_from_vendor_csv(tmp_path):
    path = tmp_path / 'compact.csv'
    path.write_text('Date,Close,Volume\n20250102,100,10\n20250103,101,11\n20250106,102,12\n',encoding='utf-8')
    frame, _ = import_file(path,'005930',source='타사 제공 CSV',cache_dir=tmp_path/'cache',dry_run=True)
    assert frame['Date'].iloc[0].date() == date(2025,1,2)
