"""KIS domestic stock daily buy/sell executed-volume API adapter.

Directly follows `examples_llm/domestic_stock/inquire_daily_trade_volume/`
from the user's supplied open-trading-api archive:
  - path: /uapi/domestic-stock/v1/quotations/inquire-daily-trade-volume
  - TR ID: FHKST03010800
  - Market: J (KRX) or NX (NXT)
  - Output: shnu_cnqn_smtn, seln_cnqn_smtn and stck_bsop_date

These are *executed* buy/sell volumes, NOT order-book depth or OHLCV volume.
Does not submit buy/sell orders. Credentials are required for real values.
"""
from __future__ import annotations
from datetime import date
import pandas as pd
from stock_core import StockDataError

API_PATH = '/uapi/domestic-stock/v1/quotations/inquire-daily-trade-volume'
TR_ID = 'FHKST03010800'


def normalize_trade_volume(output: list[dict] | dict | pd.DataFrame) -> pd.DataFrame:
    if isinstance(output, dict):
        output = output.get('output2', [])
    table = output.copy() if isinstance(output, pd.DataFrame) else pd.DataFrame(output)
    if table.empty:
        return pd.DataFrame(columns=['Date', 'BuyExecutedVolume','SellExecutedVolume'])
    required = {'stck_bsop_date', 'shnu_cnqn_smtn', 'seln_cnqn_smtn'}
    if not required.issubset(table.columns):
        raise StockDataError('KIS 매수·매도 체결량 응답에 필요한 필드가 없습니다: ' + ', '.join(sorted(required - set(table.columns))))
    renamed = table.rename(columns={'stck_bsop_date':'Date',
                                    'shnu_cnqn_smtn':'BuyExecutedVolume',
                                    'seln_cnqn_smtn':'SellExecutedVolume'})
    renamed['Date'] = pd.to_datetime(renamed['Date'].astype(str),format='%Y%m%d',errors='coerce')
    for field in ('BuyExecutedVolume','SellExecutedVolume'):
        renamed[field] = pd.to_numeric(renamed[field].astype(str).str.replace(',','',regex=False),errors='coerce')
    result=renamed.dropna(subset=['Date','BuyExecutedVolume','SellExecutedVolume'])
    result=result[(result['BuyExecutedVolume']>=0)&(result['SellExecutedVolume']>=0)]
    return result[['Date','BuyExecutedVolume','SellExecutedVolume']].sort_values('Date').drop_duplicates('Date',keep='last').reset_index(drop=True)


def daily_trade_volume(client, symbol: str, begin: date, end: date, *, market: str = 'J') -> pd.DataFrame:
    """API call delegated to read-only KIS client, using server dates unchanged."""
    from market_data import validate_symbol
    symbol = validate_symbol(symbol)
    if market not in ('J','NX'):
        raise StockDataError('매수·매도 체결량 조회 시장은 J 또는 NX만 지원합니다.')
    if begin > end:
        raise StockDataError('시작일이 종료일보다 늦습니다.')
    data=client._get(API_PATH,TR_ID,{
        'FID_COND_MRKT_DIV_CODE': market,
        'FID_INPUT_ISCD':symbol,
        'FID_PERIOD_DIV_CODE':'D',
        'FID_INPUT_DATE_1':begin.strftime('%Y%m%d'),
        'FID_INPUT_DATE_2':end.strftime('%Y%m%d')})
    if not isinstance(data.get('output2'), list):
        raise StockDataError('KIS 매수·매도 체결량 output2 형식이 올바르지 않습니다.')
    normalized=normalize_trade_volume(data['output2'])
    return normalized[(normalized['Date'].dt.date >= begin)&
                      (normalized['Date'].dt.date <= end)].reset_index(drop=True)
