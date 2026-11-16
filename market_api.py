"""On-demand, cache-aware historical daily prices; never label daily data realtime."""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import json
from threading import Lock
import re
import time
from stock_catalog import CATALOG
from config import DATA_CACHE

CODES = {code for _, code, _ in CATALOG}
CATALOG_BY_CODE = {code: (name, sector) for name, code, sector in CATALOG}
_stock_listing_cache: tuple[float, list[dict]] | None = None
KST = timezone(timedelta(hours=9))
_TTL = 15 * 60
_price_cache: dict[tuple, tuple[float, dict]] = {}
_prediction_cache: dict[tuple, tuple[float, dict]] = {}
_lock = Lock()


class MarketAPIError(ValueError):
    pass


def _valid_code(code: str) -> None:
    if not isinstance(code, str) or not re.fullmatch(r'\d{6}', code) or code == '000000':
        raise MarketAPIError('종목코드는 정확한 6자리 국내 주식 코드여야 합니다.')


def _price_payload(code: str, df, meta: dict) -> dict:
    """Serialize actually observed OHLCV. Never synthesize prices."""
    import math
    def optional_number(value):
        try:
            n = float(value)
            return n if math.isfinite(n) else None
        except (TypeError, ValueError, OverflowError):
            return None

    prices = []
    for row in df.itertuples(index=False):
        day = row.Date.date().isoformat() if hasattr(row.Date, 'date') else str(row.Date)[:10]
        close = float(row.Close)
        if not math.isfinite(close) or close <= 0:
            continue
        volume = optional_number(row.Volume)
        if volume is None or volume < 0:
            continue
        prices.append({'date': day, 'close': close, 'volume': int(volume),
                       'open': optional_number(getattr(row, 'Open', None)),
                       'high': optional_number(getattr(row, 'High', None)),
                       'low': optional_number(getattr(row, 'Low', None))})
    if len(prices) < 2:
        raise MarketAPIError('거래일 데이터가 부족합니다.')
    return {'code': code, 'name': CATALOG_BY_CODE.get(code, (f'종목 {code}', '직접 추가'))[0],
            'prices': prices, 'meta': meta}


def cached_prices(code: str, *, days: int = 460) -> dict:
    """Serve previously downloaded real daily prices instantly; never trigger network."""
    _valid_code(code)
    if not isinstance(days, int) or not 120 <= days <= 1300:
        raise MarketAPIError('조회 기간은 120~1300일로 제한됩니다.')
    path = Path(DATA_CACHE) / f'{code}.csv'
    meta_path = Path(DATA_CACHE) / f'{code}.meta.json'
    if not path.is_file() or path.stat().st_size > 8_000_000:
        raise MarketAPIError('저장된 실제 종가 데이터가 없습니다. 온라인으로 자동 조회 중입니다.')
    try:
        from stock_core import read_csv_bytes
        from pandas import to_datetime
        frame = read_csv_bytes(path.read_bytes())
        today = datetime.now(KST).date()
        frame = frame[to_datetime(frame['Date']).dt.date >= today - timedelta(days=days)]
        meta = json.loads(meta_path.read_text('utf-8')) if meta_path.is_file() else {}
        meta = dict(meta, status='cached', data_kind='daily_historical_ohlcv', realtime=False,
                    last_trade_date=frame.iloc[-1]['Date'].date().isoformat(),
                    warning='저장된 실제 과거 일봉입니다. 온라인 최신 조회를 진행 중입니다.')
        return _price_payload(code, frame.tail(850), meta)
    except (ValueError, OSError, KeyError, IndexError, TypeError) as exc:
        raise MarketAPIError('저장된 가격 파일을 읽을 수 없습니다. 온라인으로 다시 조회합니다.') from exc


def recent_prices(code: str, *, days: int = 450, force: bool = False) -> dict:
    _valid_code(code)
    if not isinstance(days, int) or days < 120 or days > 1300:
        raise MarketAPIError('조회 기간은 120~1300일로 제한됩니다.')
    today = datetime.now(KST).date()
    key = (code, days, today.isoformat())
    with _lock:
        cached = _price_cache.get(key)
        if cached and not force and cached[0] > time.monotonic():
            return cached[1]
    try:
        from market_data import fetch_historical
        result = fetch_historical(code, today - timedelta(days=days), today)
        payload = _price_payload(code, result.frame.tail(850), result.meta)
        with _lock:
            _price_cache[key] = (time.monotonic() + _TTL, payload)
        return payload
    except ImportError as exc:
        raise MarketAPIError('실제 주가 조회용 FinanceDataReader가 없습니다. requirements.txt를 설치하세요.') from exc
    except Exception as exc:
        with _lock:
            stale = _price_cache.get(key)
            if stale:
                fallback = dict(stale[1]); fallback['meta'] = dict(fallback.get('meta') or {}, status='cached', warning='온라인 조회 실패. 이전 수집 실제 일봉 사용')
                return fallback
        raise MarketAPIError(f'주가 조회 실패: {str(exc)[:220]}') from exc


def search_stocks(query: str, *, limit: int = 15) -> list[dict]:
    """User-triggered full KRX listing lookup. No network request at app startup."""
    global _stock_listing_cache
    if not isinstance(query, str) or len(query.strip()) < 2 or len(query) > 40:
        raise MarketAPIError('검색어를 2~40자로 입력하세요.')
    q = query.casefold().strip()
    with _lock:
        cache = _stock_listing_cache
    if cache is None or cache[0] < time.monotonic():
        from market_data import list_domestic_stocks
        try:
            listing = list_domestic_stocks()
            records = [{'code': str(row.Code), 'name': str(row.Name), 'sector': 'KRX 검색'}
                       for row in listing.itertuples(index=False)]
        except Exception as exc:
            raise MarketAPIError('KRX 전체 종목 검색에 실패했습니다. 6자리 코드를 직접 입력할 수 있습니다. ' + str(exc)[:110]) from exc
        with _lock:
            _stock_listing_cache = (time.monotonic() + 12 * 3600, records)
    else:
        records = cache[1]
    return [r for r in records if q in r['code'] or q in r['name'].casefold()][:limit]


def predictor(code: str) -> dict:
    if code not in CODES:
        raise MarketAPIError('등록된 30개 종목 중에서 예측 대상을 선택하세요.')
    data = recent_prices(code, days=1180)
    cache_key = (code, data['meta'].get('last_trade_date'), data['prices'][-1]['close'], len(data['prices']))
    with _lock:
        cached = _prediction_cache.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return cached[1]
    from prediction_model import run_experiments
    from pandas import DataFrame, to_datetime
    frame = DataFrame(data['prices'])
    frame['Date'] = to_datetime(frame.pop('date'))
    frame = frame.rename(columns={'close':'Close','volume':'Volume','open':'Open','high':'High','low':'Low'})
    result = run_experiments(frame)
    def clean(value):
        if isinstance(value, (int, str, bool)) or value is None:
            return value
        if hasattr(value, 'item'):
            try: return clean(value.item())
            except (TypeError, ValueError): pass
        if isinstance(value, float):
            return round(value, 8) if value == value else None
        return str(value)
    payload = {'code': code, 'name': data['name'], 'last_trade_date': data['meta'].get('last_trade_date'),
            'forecasts': [{k:clean(v) for k,v in row.items()} for row in result.forecasts.to_dict(orient='records')],
            'summary': [{k:clean(v) for k,v in row.items()} for row in result.summary.to_dict(orient='records')],
            'note': result.news_note,
            'method': '과거 가격·거래량 기반 시간순 학습/검증·시험 분리; 탐색적·미보정 확률 추정',
            'realtime': False}
    with _lock:
        _prediction_cache[cache_key] = (time.monotonic() + 30 * 60, payload)
    return payload
