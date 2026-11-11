"""Preload daily domestic stock history; real remote connectivity required."""
from __future__ import annotations
import argparse
from datetime import date, timedelta
from market_data import fetch_historical
from kis_market import fetch_kis_historical
from config import STOCKS


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='MARKET PULSE 국내 일별 주가 저장')
    parser.add_argument('--start', default=(date.today() - timedelta(days=365 * 3)).isoformat())
    parser.add_argument('--end', default=date.today().isoformat())
    parser.add_argument('--only', nargs='*', help='수집할 6자리 종목코드; 기본 6개')
    parser.add_argument('--provider',choices=['fdr','kis'],default='fdr',
                        help='fdr: NAVER→KRX, kis: 인증이 필요한 한국투자증권 조회 전용 API')
    parser.add_argument('--market',choices=['J','NX','UN'],default='J',
                        help='KIS 조회 시장: J=KRX, NX=NXT, UN=통합')
    parser.add_argument('--raw',action='store_true',
                        help='KIS 원주가 사용. 지정하지 않으면 KIS 기간별시세의 수정주가 옵션 사용')
    args = parser.parse_args(argv)
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    codes = args.only if args.only else list(STOCKS.values())
    failures = []
    for code in codes:
        try:
            if args.provider == 'kis':
                result = fetch_kis_historical(code, start, end,
                    adjusted=not args.raw, market=args.market)
            else:
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
