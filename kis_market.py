"""Read-only KIS Developers REST price adapter for MARKET PULSE.

Based on KIS open-trading-api `examples_llm/domestic_stock`:
- inquire-daily-itemchartprice (FHKST03010100), period D
- inquire-price (FHKST01010100) for an on-demand REST quote snapshot

It intentionally has NO order, balance, account, or WebSocket operations.
Do not mistake REST quote snapshots for an exchange-authoritative live stream.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import json
import time
from typing import Any

import pandas as pd
import requests

from config import DATA_CACHE, get_secret
from market_data import MarketResult, KST, validate_symbol
from stock_core import StockDataError, clean_data, read_csv_bytes
from kis_trade_volume import API_PATH as _TRADE_VOLUME_PATH, TR_ID as _TRADE_VOLUME_TR, daily_trade_volume

_PROD = 'https://openapi.koreainvestment.com:9443'
_PAPER = 'https://openapivts.koreainvestment.com:29443'
_DAILY_PATH = '/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice'
_QUOTE_PATH = '/uapi/domestic-stock/v1/quotations/inquire-price'
_TOKEN_PATH = '/oauth2/tokenP'


def kis_credentials_ready() -> bool:
    return bool(get_secret('KIS_APP_KEY') and get_secret('KIS_APP_SECRET'))


def normalize_kis_daily(raw: pd.DataFrame | list[dict] | dict) -> pd.DataFrame:
    """Convert KIS output2 rows to standard Date/Open/High/Low/Close/Volume.

    Pass the API's output2 list, entire API JSON dict, or a KIS export CSV.
    Malformed schemas must fail instead of inventing market data.
    """
    if isinstance(raw, dict):
        raw = raw.get('output2', raw.get('output', []))
    frame = raw.copy() if isinstance(raw, pd.DataFrame) else pd.DataFrame(raw)
    aliases = {'stck_bsop_date':'Date', 'stck_oprc':'Open',
               'stck_hgpr':'High','stck_lwpr':'Low', 'stck_clpr':'Close',
               'acml_vol':'Volume', 'acml_tr_pbmn':'Turnover'}
    if frame.empty:
        raise StockDataError('KIS 데이터가 비어 있습니다.')
    needed = {'stck_bsop_date','stck_oprc','stck_hgpr','stck_lwpr','stck_clpr','acml_vol'}
    if not needed.issubset(frame.columns):
        raise StockDataError('KIS output2 형식이 아닙니다. 필수 열: ' + ', '.join(sorted(needed)))
    result = frame.rename(columns=aliases)
    result['Date'] = pd.to_datetime(result['Date'].astype(str).str.strip(),
                                    format='%Y%m%d', errors='coerce')
    # Detect missing required numeric fields rather than accepting incomplete OHLCV.
    for key in ('Open','High','Low','Close','Volume'):
        result[key] = pd.to_numeric(result[key].astype(str).str.replace(',','',regex=False), errors='coerce')
    result = result.dropna(subset=['Date','Open','High','Low','Close','Volume'])
    result = result[(result['Close']>0) & (result['Open']>0) &
                    (result['High']>=result[['Open','Close','Low']].max(axis=1)) &
                    (result['Low']<=result[['Open','Close']].min(axis=1)) &
                    (result['Low']>0) & (result['Volume']>=0)].copy()
    if 'Turnover' in result:
        result['Turnover'] = pd.to_numeric(result['Turnover'], errors='coerce')
    return result.sort_values("Date").drop_duplicates("Date",keep="last").reset_index(drop=True)


class KISReadOnlyClient:
    """Minimal quote-only KIS REST client. Never calls trade endpoints."""
    def __init__(self, *, app_key: str | None = None,
                 app_secret: str | None = None, environment: str = 'prod',
                 session: Any = None, timeout: int = 12):
        if environment not in ('prod','vps'):
            raise StockDataError('KIS_ENV는 prod 또는 vps만 가능합니다.')
        self._key = app_key if app_key is not None else get_secret('KIS_APP_KEY')
        self._secret = app_secret if app_secret is not None else get_secret('KIS_APP_SECRET')
        if not (self._key and self._secret):
            raise StockDataError('KIS_APP_KEY/KIS_APP_SECRET이 없습니다. 계좌와 API 이용 자격을 먼저 확인하세요.')
        self.environment = environment
        self.base = _PROD if environment == 'prod' else _PAPER
        self.session = session if session is not None else requests.Session()
        self.timeout = timeout
        self._token: str | None = None
        self._expires_at: float = 0

    @staticmethod
    def _response_json(response: Any, operation: str) -> dict:
        if getattr(response, 'status_code', 500) != 200:
            # Do not print HTTP response bodies, bearer tokens, or secret fields.
            raise StockDataError(f'KIS {operation} HTTP {response.status_code} 오류 (자세한 내용은 KIS 포털 확인)')
        try:
            payload = response.json()
        except (ValueError, TypeError) as exc:
            raise StockDataError(f'KIS {operation} 응답이 JSON이 아닙니다.') from exc
        if not isinstance(payload, dict):
            raise StockDataError(f'KIS {operation} 응답 구조가 잘못되었습니다.')
        return payload

    def _authenticate(self) -> str:
        if self._token and time.time() < self._expires_at:
            return self._token
        try:
            res = self.session.post(self.base + _TOKEN_PATH,
                json={'grant_type':'client_credentials',
                      'appkey':self._key, 'appsecret':self._secret},
                headers={'content-type':'application/json'}, timeout=self.timeout)
        except requests.RequestException as exc:
            raise StockDataError(f'KIS 인증 네트워크 오류: {type(exc).__name__}') from exc
        data = self._response_json(res,'인증')
        token = data.get('access_token')
        if not isinstance(token,str) or not token:
            raise StockDataError('KIS 접근 토큰이 없습니다. 앱키 및 API 이용 상태를 확인하세요.')
        self._token = token
        expires_in = int(data.get('expires_in', 86400))
        self._expires_at = time.time() + max(30, expires_in - 120)
        return token

    def _get(self, api_path: str, tr_id: str, params: dict) -> dict:
        # No user-provided URL is accepted: prevents accidentally calling order endpoints.
        if api_path not in (_DAILY_PATH, _QUOTE_PATH, _TRADE_VOLUME_PATH):
            raise StockDataError('허용되지 않은 API 경로입니다.')
        for attempt in range(2):
            token = self._authenticate()
            headers = {'authorization':f'Bearer {token}', 'appkey':self._key,
                       'appsecret':self._secret, 'tr_id':tr_id,
                       'content-type':'application/json; charset=utf-8',
                       'custtype':'P'}
            try:
                res = self.session.get(self.base + api_path, params=params,
                                       headers=headers, timeout=self.timeout)
            except requests.RequestException as exc:
                raise StockDataError(f'KIS 시세 조회 네트워크 오류: {type(exc).__name__}') from exc
            if res.status_code == 401 and attempt == 0:
                self._token = None
                continue
            data = self._response_json(res,'시세 조회')
            if str(data.get('rt_cd')) != '0':
                # API-provided message may disclose account info; show only error code.
                raise StockDataError(f"KIS 시세 API 오류 코드: {data.get('msg_cd', 'UNKNOWN')}")
            return data
        raise StockDataError('KIS 토큰 재인증 후에도 조회할 수 없습니다.')

    def daily(self, symbol: str, begin: date, end: date,
              *, adjusted: bool = True, market: str = 'J') -> pd.DataFrame:
        """One request with <=90 calendar days to respect the 100-row endpoint limit."""
        symbol = validate_symbol(symbol)
        if begin > end:
            raise StockDataError('조회 시작일이 종료일보다 늦습니다.')
        if market not in ('J','NX','UN'):
            raise StockDataError('KIS 시장 구분은 J, NX, UN 중 하나여야 합니다.')
        data = self._get(_DAILY_PATH, 'FHKST03010100', {
            'FID_COND_MRKT_DIV_CODE':market,
            'FID_INPUT_ISCD':symbol,
            'FID_INPUT_DATE_1':begin.strftime('%Y%m%d'),
            'FID_INPUT_DATE_2':end.strftime('%Y%m%d'),
            'FID_PERIOD_DIV_CODE':'D',
            # This value follows inquire-daily-itemchartprice, NOT inquire-daily-price.
            'FID_ORG_ADJ_PRC':'0' if adjusted else '1',
        })
        rows = data.get('output2')
        if not isinstance(rows,list):
            raise StockDataError('KIS output2 필드 형식이 잘못되었습니다.')
        if not rows:
            return pd.DataFrame()
        return normalize_kis_daily(rows)

    def quote(self, symbol: str, *, market: str = 'J') -> dict:
        """On-demand REST quote snapshot; does not subscribe to streaming ticks."""
        symbol = validate_symbol(symbol)
        if market not in ('J','NX','UN'):
            raise StockDataError('지원하지 않는 시장 구분입니다.')
        data = self._get(_QUOTE_PATH, 'FHKST01010100', {
            'FID_COND_MRKT_DIV_CODE':market,'FID_INPUT_ISCD':symbol})
        info = data.get('output')
        if not isinstance(info,dict):
            raise StockDataError('KIS 현재가 output 응답이 없습니다.')
        def number(field: str):
            try:
                value = str(info.get(field,'')).replace(',','').strip()
                return float(value) if value else None
            except (ValueError,TypeError):
                return None
        return {'symbol':symbol, 'provider':f'KIS:{market}',
                'price':number('stck_prpr'), 'previous_close':number('stck_prdy_clpr'),
                'change_pct':number('prdy_ctrt'), 'volume':number('acml_vol'),
                'turnover':number('acml_tr_pbmn'),
                'retrieved_at':datetime.now(KST).isoformat(timespec='seconds'),
                'realtime':False,'kind':'on_demand_rest_snapshot',
                'warning':'REST 호출 시점의 응답입니다. 실시간 스트리밍·시세 보장 아님.'}


def fetch_kis_historical(symbol: str, start: date, end: date, *,
                         cache_dir: Path | str = DATA_CACHE,
                         client: KISReadOnlyClient | None = None,
                         adjusted: bool = True, market: str = 'J') -> MarketResult:
    """Fetch/persist KIS daily OHLCV, with isolated cache and explicit stale fallback.

    Never mix KIS with FDR caches: adjusted/market conventions may differ.
    """
    symbol = validate_symbol(symbol)
    if start > end:
        raise StockDataError('분석 시작일이 종료일보다 늦습니다.')
    folder = Path(cache_dir) / 'kis'
    folder.mkdir(parents=True,exist_ok=True)
    filename = f'{symbol}_{market}_{"adj" if adjusted else "raw"}'
    csv_file = folder / (filename + '.csv')
    meta_file = folder / (filename + '.meta.json')
    failures = []
    try:
        client = client if client is not None else KISReadOnlyClient(
            environment=get_secret('KIS_ENV') or 'prod')
        cursor = start - timedelta(days=170)
        chunks = []
        while cursor <= end:
            right = min(cursor + timedelta(days=89), end)
            part = client.daily(symbol, cursor, right, adjusted=adjusted, market=market)
            if not part.empty:
                chunks.append(part)
            cursor = right + timedelta(days=1)
            if cursor <= end:
                time.sleep(0.08)  # modest request pacing; server limits still apply
        if not chunks:
            raise StockDataError('요청 기간에 KIS 거래일 자료가 없습니다.')
        frame = clean_data(pd.concat(chunks, ignore_index=True))
        frame = frame[(frame['Date'].dt.date <= end)].reset_index(drop=True)
        if frame.empty or frame['Date'].max().date() < start:
            raise StockDataError('요청 분석 기간에 KIS 거래일 자료가 없습니다.')
        meta = {'symbol':symbol,'source':f'KIS:{market}', 'status':'fresh',
                'retrieved_at':datetime.now(KST).isoformat(timespec='seconds'),
                'requested_from':start.isoformat(),'requested_to':end.isoformat(),
                'first_trade_date':frame['Date'].min().date().isoformat(),
                'last_trade_date':frame['Date'].max().date().isoformat(),
                'adjusted_price':'adjusted' if adjusted else 'raw',
                'market':market,'data_kind':'daily_historical_ohlcv',
                'realtime':False,'verified_source':True}
        tmp_csv = csv_file.with_suffix('.csv.tmp')
        tmp_meta = meta_file.with_suffix('.json.tmp')
        frame.to_csv(tmp_csv,index=False,encoding='utf-8-sig')
        tmp_meta.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
        tmp_csv.replace(csv_file)
        tmp_meta.replace(meta_file)
        return MarketResult(frame,meta)
    except Exception as exc:
        # Do not report actual credentials or raw server payloads.
        failures.append(f'{type(exc).__name__}: {str(exc)[:160]}')
    if csv_file.exists():
        try:
            frame = read_csv_bytes(csv_file.read_bytes())
            frame = frame[frame['Date'].dt.date <= end].reset_index(drop=True)
            if frame.empty or frame['Date'].max().date() < start:
                raise StockDataError('이전 KIS 캐시가 요청 기간을 포함하지 않습니다.')
            meta = json.loads(meta_file.read_text(encoding='utf-8')) if meta_file.exists() else {}
            meta.update({'symbol':symbol,'status':'cached',
                         'last_trade_date':frame['Date'].max().date().isoformat(),
                         'source':meta.get('source',f'KIS:{market} (출처 미확인)'),
                         'warning':'KIS 조회 실패. 과거 저장한 CSV를 표시합니다.',
                         'realtime':False,'attempt_errors':failures})
            return MarketResult(frame,meta)
        except (OSError,ValueError,StockDataError) as exc:
            failures.append(f'캐시 오류: {type(exc).__name__}')
    raise StockDataError('KIS 온라인 조회 및 캐시 모두 실패. ' + ' / '.join(failures[-2:]))


def fetch_kis_trade_volume(symbol: str, start: date, end: date, *,
                           cache_dir: Path | str = DATA_CACHE,
                           client: KISReadOnlyClient | None = None,
                           market: str = 'J') -> MarketResult:
    """Collect the *real* daily executed buy/sell volumes with a separate cache.

    Never fabricates rows; cache can be shown when connection fails, flagged as cached.
    """
    symbol = validate_symbol(symbol)
    if start > end:
        raise StockDataError('조회 시작일이 종료일보다 늦습니다.')
    if market not in ('J','NX'):
        raise StockDataError('KIS 체결량 조회는 J/NX만 지원합니다.')
    base = Path(cache_dir) / 'kis_trade_volume'
    base.mkdir(parents=True, exist_ok=True)
    csv_path=base / f'{symbol}_{market}.csv'
    meta_path=base / f'{symbol}_{market}.meta.json'
    errors=[]
    try:
        client=client if client is not None else KISReadOnlyClient(
            environment=get_secret('KIS_ENV') or 'prod')
        parts=[]
        cursor = start
        while cursor <= end:
            last = min(cursor + timedelta(days=89), end)
            part = daily_trade_volume(client,symbol,cursor,last,market=market)
            if not part.empty:
                parts.append(part)
            cursor=last + timedelta(days=1)
            if cursor <= end:
                time.sleep(.08)
        if not parts:
            raise StockDataError('KIS 매수·매도 체결량 API가 해당 기간에 데이터를 반환하지 않았습니다.')
        frame=pd.concat(parts,ignore_index=True).sort_values('Date').drop_duplicates('Date',keep='last')
        frame=frame.reset_index(drop=True)
        if frame['Date'].max().date() < start:
            raise StockDataError('요청 기간의 거래일 자료가 없습니다.')
        meta={'symbol':symbol,'source':f'KIS:{market}/daily-trade-volume',
              'status':'fresh','retrieved_at':datetime.now(KST).isoformat(timespec='seconds'),
              'last_trade_date':frame['Date'].max().date().isoformat(),
              'data_kind':'daily_buy_sell_executed_volume',
              'realtime':False,'requested_from':start.isoformat(),'requested_to':end.isoformat()}
        temp_csv=csv_path.with_suffix('.csv.tmp')
        temp_meta=meta_path.with_suffix('.json.tmp')
        frame.to_csv(temp_csv,index=False,encoding='utf-8-sig')
        temp_meta.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
        temp_csv.replace(csv_path);temp_meta.replace(meta_path)
        return MarketResult(frame,meta)
    except Exception as exc:
        errors.append(f'{type(exc).__name__}: {str(exc)[:120]}')
    if csv_path.exists() and meta_path.exists():
        try:
            from kis_trade_volume import normalize_trade_volume
            raw=pd.read_csv(csv_path,encoding='utf-8-sig')
            # The stored output is already standardized, unlike raw KIS output2.
            required={'Date','BuyExecutedVolume','SellExecutedVolume'}
            if not required.issubset(raw.columns):
                raise StockDataError('체결량 캐시의 열이 잘못되었습니다.')
            raw['Date']=pd.to_datetime(raw['Date'],errors='coerce')
            for col in ('BuyExecutedVolume','SellExecutedVolume'):
                raw[col]=pd.to_numeric(raw[col],errors='coerce')
            raw=raw.dropna(subset=['Date','BuyExecutedVolume','SellExecutedVolume'])
            raw=raw[(raw['BuyExecutedVolume']>=0)&(raw['SellExecutedVolume']>=0)]
            raw=raw[(raw['Date'].dt.date>=start)&(raw['Date'].dt.date<=end)]
            if raw.empty:
                raise StockDataError('캐시에 기간 일치 행이 없습니다.')
            meta=json.loads(meta_path.read_text(encoding='utf-8'))
            meta.update(status='cached', warning='KIS 조회 실패: 이전 체결량 캐시 사용',
                        last_trade_date=raw['Date'].max().date().isoformat(),
                        attempt_errors=errors)
            return MarketResult(raw.reset_index(drop=True),meta)
        except (OSError,ValueError,KeyError,StockDataError) as exc:
            errors.append(f'캐시 오류: {type(exc).__name__}')
    raise StockDataError('KIS 체결량 조회 및 캐시 실패: ' + ' / '.join(errors[-2:]))
