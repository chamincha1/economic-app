"""Import manually obtained OHLCV CSV / KIS output2 JSON into MARKET PULSE.

Examples:
  python import_real_data.py --input my_prices.csv --code 005930 --source '자료 제공처' --dry-run
  python import_real_data.py --input my_prices.csv --code 005930 --source '자료 제공처'
  python import_real_data.py --input kis_output2.json --code 005930 --format kis --source KIS

This does NOT certify the user-supplied content as authentic market data.
Use a separate import command per ticker. Never import API source-code archives as prices.
"""
from __future__ import annotations

import argparse
from datetime import datetime, date
import hashlib
import json
from pathlib import Path

import pandas as pd

from config import DATA_CACHE
from market_data import KST, validate_symbol
from stock_core import StockDataError, clean_data, read_csv_bytes
from kis_market import normalize_kis_daily


def _read_user_file(path: Path, kind: str = 'auto') -> pd.DataFrame:
    if path.suffix.lower() not in ('.csv','.json'):
        raise StockDataError('CSV 또는 JSON 파일만 직접 가져올 수 있습니다. GitHub 소스 ZIP은 데이터 파일이 아닙니다.')
    if not path.is_file():
        raise StockDataError('파일이 존재하지 않습니다: ' + str(path))
    if path.stat().st_size > 100 * 1024 * 1024:
        raise StockDataError('입력 파일이 너무 큽니다(100MB 초과).')
    content = path.read_bytes()
    if path.suffix.lower() == '.json':
        try:
            raw = json.loads(content.decode('utf-8-sig'))
        except (UnicodeError, ValueError) as exc:
            raise StockDataError('유효한 JSON 파일이 아닙니다.') from exc
        if not isinstance(raw, (dict,list)):
            raise StockDataError('JSON은 OHLCV 행 목록 또는 KIS output2 객체여야 합니다.')
        if kind == 'kis' or (isinstance(raw,dict) and 'output2' in raw):
            return normalize_kis_daily(raw)
        if isinstance(raw,dict):
            raw = raw.get('rows',raw.get('data',[]))
        return clean_data(pd.DataFrame(raw))
    if kind == 'kis':
        for enc in ('utf-8-sig','cp949','utf-8'):
            try:
                return normalize_kis_daily(pd.read_csv(path,encoding=enc,dtype=str))
            except UnicodeDecodeError:
                continue
        raise StockDataError('KIS CSV 인코딩이 올바르지 않습니다.')
    # Auto-detect KIS API tabular format before normal CSV handling.
    for enc in ('utf-8-sig','cp949','utf-8'):
        try:
            probe = pd.read_csv(path,encoding=enc,dtype=str,nrows=2)
            if {'stck_bsop_date','stck_clpr','acml_vol'}.issubset(probe.columns):
                return normalize_kis_daily(pd.read_csv(path,encoding=enc,dtype=str))
            break
        except UnicodeDecodeError:
            continue
    return read_csv_bytes(content)


def import_file(input_path: str | Path, symbol: str, *, source: str,
                cache_dir: Path | str = DATA_CACHE, replace: bool = False,
                dry_run: bool = False, kind: str = 'auto',
                adjustment: str = 'unknown') -> tuple[pd.DataFrame,dict]:
    """Convert and validate data; persist with metadata only on explicit request.

    Always label user-uploaded data as UNVERIFIED even if `source` is named.
    """
    symbol = validate_symbol(symbol)
    if kind not in ('auto','kis','ohlcv'):
        raise StockDataError('--format은 auto, kis, ohlcv만 가능합니다.')
    if adjustment not in ('unknown','adjusted','raw'):
        raise StockDataError('--adjustment는 unknown, adjusted, raw 중 하나입니다.')
    if not source.strip():
        raise StockDataError('데이터 출처 설명(--source)을 작성하세요.')
    path = Path(input_path)
    frame = clean_data(_read_user_file(path,kind))
    # A strict validated OHLCV check (when these optional fields are supplied).
    for column in ('Open','High','Low'):
        if column in frame.columns and (frame[column].isna() | (frame[column] <= 0)).any():
            raise StockDataError(f'가격 열 {column}에 유효하지 않은 값이 있습니다.')
    if {'Open','High','Low'}.issubset(frame.columns):
        bad = ((frame['High'] < frame[['Open','Close','Low']].max(axis=1)) |
               (frame['Low'] > frame[['Open','Close']].min(axis=1)))
        if bad.any():
            raise StockDataError('OHLC 값이 일관되지 않습니다(고가/저가 관계 확인).')
    if frame['Date'].dt.date.max() > date.today():
        raise StockDataError('미래 날짜의 거래일 행이 발견되어 가져오기를 중단합니다.')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    meta = {'symbol':symbol,'status':'imported',
            'source':'사용자 지정 출처: '+source.strip(),
            'origin_filename':path.name,'origin_sha256':digest,
            'source_verified':False,
            'warning':'사용자 제공 파일입니다. 실제 시세 여부와 제공처 정확성을 별도로 확인해야 합니다.',
            'retrieved_at':datetime.now(KST).isoformat(timespec='seconds'),
            'first_trade_date':frame['Date'].min().date().isoformat(),
            'last_trade_date':frame['Date'].max().date().isoformat(),
            'adjusted_price':adjustment,'data_kind':'daily_historical_ohlcv',
            'realtime':False,'row_count':len(frame)}
    target_dir = Path(cache_dir)
    target_csv = target_dir / f'{symbol}.csv'
    target_meta = target_dir / f'{symbol}.meta.json'
    if not dry_run:
        target_dir.mkdir(parents=True,exist_ok=True)
        if (target_csv.exists() or target_meta.exists()) and not replace:
            raise StockDataError(f'기존 저장 파일이 있습니다: {symbol}. 덮어쓰려면 --replace를 추가하세요.')
        temp_csv = target_dir / f'{symbol}.csv.tmp'
        temp_meta = target_dir / f'{symbol}.meta.json.tmp'
        frame.to_csv(temp_csv,index=False,encoding='utf-8-sig')
        temp_meta.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
        temp_csv.replace(target_csv)
        temp_meta.replace(target_meta)
    return frame,meta


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='MARKET PULSE 수집 CSV / KIS JSON → 표준 OHLCV')
    parser.add_argument('--input',required=True,help='CSV 또는 KIS output2 JSON 파일 경로')
    parser.add_argument('--code',required=True,help='6자리 종목코드 (예: 005930)')
    parser.add_argument('--source',required=True,help='원본 자료의 제공처 설명 (진위 자동 인증 아님)')
    parser.add_argument('--format',choices=['auto','kis','ohlcv'],default='auto')
    parser.add_argument('--adjustment',choices=['unknown','adjusted','raw'],default='unknown')
    parser.add_argument('--dry-run',action='store_true',help='검증만 수행, 파일 저장 안 함')
    parser.add_argument('--replace',action='store_true',help='같은 종목의 기존 캐시 덮어쓰기')
    args = parser.parse_args(argv)
    try:
        frame,meta = import_file(args.input,args.code,source=args.source,
                   kind=args.format,adjustment=args.adjustment,
                   replace=args.replace,dry_run=args.dry_run)
        state = '검증만 완료' if args.dry_run else '저장 완료'
        print(f'{state}: {args.code} · {len(frame)}거래일 · '
              f"{meta['first_trade_date']} ~ {meta['last_trade_date']}")
        if not args.dry_run:
            print(f'저장 위치: data_cache/{args.code}.csv + {args.code}.meta.json')
        print('출처 확인: 사용자 입력(외부 인증 없음), 실시간 시세 아님')
        return 0
    except (OSError,ValueError,StockDataError,KeyError) as exc:
        print(f'오류: {type(exc).__name__}: {exc}')
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
