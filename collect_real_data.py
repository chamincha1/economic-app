"""Preload daily domestic stock history; real remote connectivity required."""
from __future__ import annotations
import argparse
from datetime import date, timedelta
from market_data import fetch_historical
from config import STOCKS


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='MARKET PULSE 국내 일별 주가 저장')
    parser.add_argument('--start', default=(date.today() - timedelta(days=365 * 3)).isoformat())
    parser.add_argument('--end', default=date.today().isoformat())
    parser.add_argument('--only', nargs='*', help='수집할 6자리 종목코드; 기본 6개')
    args = parser.parse_args(argv)
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    codes = args.only if args.only else list(STOCKS.values())
    failures = []
    for code in codes:
        try:
            result = fetch_historical(code, start, end)
            print(f"{code}: {result.meta['status']} · {result.meta['source']} · "
                  f"{result.meta['last_trade_date']} · {len(result.frame)}행")
            if result.is_cached:
                failures.append(code)
        except Exception as exc:
            failures.append(code)
            print(f'{code}: 수집 실패 · {exc}')
    return 1 if failures else 0

if __name__ == '__main__':
    raise SystemExit(main())
