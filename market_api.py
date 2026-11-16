"""On-demand, cache-aware historical daily prices; never label daily data realtime."""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from threading import Lock
import time
from stock_catalog import CATALOG

CODES = {code for _, code, _ in CATALOG}
KST = timezone(timedelta(hours=9))
_TTL = 15 * 60
_price_cache: dict[tuple, tuple[float, dict]] = {}
_prediction_cache: dict[tuple, tuple[float, dict]] = {}
_lock = Lock()


class MarketAPIError(ValueError):
    pass


def recent_prices(code: str, *, days: int = 450, force: bool = False) -> dict:
    if code not in CODES:
        raise MarketAPIError('현재 등록된 30개 국내 종목코드만 지원합니다.')
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
        df = result.frame.tail(850)
        prices = []
        for row in df.itertuples(index=False):
            day = row.Date.date().isoformat() if hasattr(row.Date, 'date') else str(row.Date)[:10]
            prices.append({'date': day, 'close': float(row.Close), 'volume': int(row.Volume),
                           'open': float(row.Open) if hasattr(row, 'Open') else None,
                           'high': float(row.High) if hasattr(row, 'High') else None,
                           'low': float(row.Low) if hasattr(row, 'Low') else None})
        if len(prices) < 2:
            raise MarketAPIError('거래일 데이터가 부족합니다.')
        payload = {'code': code, 'name': next(name for name, sym, _ in CATALOG if sym == code),
                   'prices': prices, 'meta': result.meta}
        with _lock:
            _price_cache[key] = (time.monotonic() + _TTL, payload)
        return payload
    except ImportError as exc:
        raise MarketAPIError('실제 주가 조회용 FinanceDataReader가 없습니다. requirements.txt를 설치하세요.') from exc
    except Exception as exc:
        with _lock:
            stale = _price_cache.get(key)
            if stale:
                fallback = dict(stale[1]); fallback['meta'] = dict(fallback.get('meta') or {}, status='cached', warning='최근 조회 실패. 메모리 캐시 사용')
                return fallback
        raise MarketAPIError(f'주가 조회 실패: {str(exc)[:220]}') from exc


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
