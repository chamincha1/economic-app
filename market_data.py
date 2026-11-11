"""Historical OHLCV acquisition and explicit cached/online provenance.

NAVER -> KRX is attempted only for KRX six-digit domestic stock codes.
Every request is best-effort: data vendors may be inaccessible or change fields.
Actual intraday quote feeds are NOT supplied by this module.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
import json
import re
import pandas as pd
from stock_core import clean_data, StockDataError, read_csv_bytes
from config import DATA_CACHE, STOCKS

KST = timezone(timedelta(hours=9))

@dataclass
class MarketResult:
    frame: pd.DataFrame
    meta: dict

    @property
    def is_cached(self) -> bool:
        return self.meta.get('status') == 'cached'


def _json_write(path: Path, meta: dict):
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')


def validate_symbol(symbol: str, index: bool = False) -> str:
    symbol = str(symbol).strip().upper()
    if index and symbol in ('KS11', 'KQ11'):
        return symbol
    if not re.fullmatch(r'\d{6}', symbol):
        raise StockDataError('국내 종목은 정확한 6자리 종목코드를 입력하세요.')
    return symbol


def fetch_historical(symbol: str, start: date, end: date, *,
                     cache_dir: Path | str = DATA_CACHE,
                     reader: Callable | None = None,
                     index: bool = False) -> MarketResult:
    """Acquire daily candles with metadata; fallback never labeled fresh.

    `reader(symbol, begin_iso, end_iso)` is dependency-injected for tests.
    API end is exclusive in FinanceDataReader, hence end + 1 day.
    """
    if start > end:
        raise StockDataError('시작일은 종료일보다 이전이어야 합니다.')
    symbol = validate_symbol(symbol, index=index)
    path = Path(cache_dir)
    path.mkdir(parents=True, exist_ok=True)
    csv_path = path / f'{symbol}.csv'
    meta_path = path / f'{symbol}.meta.json'
    requests_made = []
    if reader is None:
        try:
            import FinanceDataReader as fdr
            reader = fdr.DataReader
        except ImportError as exc:
            requests_made.append(f'FinanceDataReader 미설치: {exc}')
    begin = (start - timedelta(days=170)).isoformat()
    until = (end + timedelta(days=1)).isoformat()
    providers = [symbol] if index else [f'NAVER:{symbol}', f'KRX:{symbol}']
    if reader:
        for provider in providers:
            try:
                raw = reader(provider, begin, until)
                if index and 'Volume' not in raw and '거래량' not in raw:
                    raw = raw.copy()
                    raw['Volume'] = 0
                frame = clean_data(raw)
                frame = frame[pd.to_datetime(frame['Date']).dt.date <= end].reset_index(drop=True)
                if frame.empty or frame['Date'].max().date() < start:
                    raise StockDataError('요청 기간의 거래일 데이터가 없습니다.')
                now = datetime.now(KST).isoformat(timespec='seconds')
                meta = {'symbol': symbol, 'source': provider, 'status': 'fresh',
                        'retrieved_at': now, 'requested_from': start.isoformat(),
                        'requested_to': end.isoformat(),
                        'first_trade_date': frame['Date'].min().date().isoformat(),
                        'last_trade_date': frame['Date'].max().date().isoformat(),
                        'adjusted_price': 'unknown', 'data_kind': 'daily_historical_ohlcv',
                        'realtime': False, 'attempt_errors': requests_made}
                # Write CSV first; cannot advertise a file that was never saved.
                frame.to_csv(csv_path, index=False, encoding='utf-8-sig')
                _json_write(meta_path, meta)
                return MarketResult(frame, meta)
            except Exception as exc:
                requests_made.append(f'{provider}: {type(exc).__name__}: {str(exc)[:150]}')
    if csv_path.is_file():
        try:
            frame = read_csv_bytes(csv_path.read_bytes())
            frame = frame[pd.to_datetime(frame['Date']).dt.date <= end].copy()
            if frame.empty or frame['Date'].max().date() < start:
                raise StockDataError('저장된 CSV에 요청 분석 기간의 거래일이 없습니다.')
            prev = json.loads(meta_path.read_text('utf-8')) if meta_path.exists() else {}
            meta = dict(prev)
            meta.update(symbol=symbol, status='cached',
                        first_trade_date=frame['Date'].min().date().isoformat(),
                        last_trade_date=frame['Date'].max().date().isoformat(),
                        data_kind='daily_historical_ohlcv', realtime=False,
                        warning='온라인 조회 실패로 이전 저장 데이터를 사용합니다.',
                        attempt_errors=requests_made,
                        source=prev.get('source', '기존 캐시(원출처 확인 불가)'))
            return MarketResult(frame.reset_index(drop=True), meta)
        except (OSError, ValueError, StockDataError, json.JSONDecodeError) as exc:
            requests_made.append(f'캐시 오류: {exc}')
    raise StockDataError('온라인 및 이전 캐시 조회 실패. ' + ' / '.join(requests_made[-3:]))


def list_domestic_stocks(reader: Callable | None = None) -> pd.DataFrame:
    """Refresh user-triggered KRX stock listing; do not silently invent names."""
    if reader is None:
        import FinanceDataReader as fdr
        reader = fdr.StockListing
    frame = reader('KRX')
    code = next((c for c in ('Code', 'Symbol', '종목코드') if c in frame), None)
    name = next((c for c in ('Name', '종목명') if c in frame), None)
    if not code or not name:
        raise StockDataError('종목 목록에서 이름과 코드를 찾을 수 없습니다.')
    result = frame[[code, name]].rename(columns={code: 'Code', name: 'Name'}).copy()
    result['Code'] = result['Code'].astype(str).str.zfill(6)
    return result[result['Code'].str.fullmatch(r'\d{6}')].drop_duplicates('Code')


def price_snapshot(frame: pd.DataFrame) -> dict:
    """Daily close-based summary, not a live or delayed quote."""
    df = clean_data(frame)
    last = df.iloc[-1]
    previous = df.iloc[-2]
    recent = df.tail(252)
    close = float(last['Close'])
    return {
        'last_trade_date': last['Date'].date().isoformat(),
        'close': close,
        'previous_close': float(previous['Close']),
        'change': close - float(previous['Close']),
        'change_pct': (close / float(previous['Close']) - 1) * 100,
        'volume': int(last['Volume']),
        'open': float(last['Open']) if 'Open' in df and pd.notna(last['Open']) else None,
        'high': float(last['High']) if 'High' in df and pd.notna(last['High']) else None,
        'low': float(last['Low']) if 'Low' in df and pd.notna(last['Low']) else None,
        'high_52w': float(recent['High'].max()) if 'High' in df else float(recent['Close'].max()),
        'low_52w': float(recent['Low'].min()) if 'Low' in df else float(recent['Close'].min()),
        'approx_turnover': float(last['Close'] * last['Volume']),
        'history_days': len(recent),
    }
