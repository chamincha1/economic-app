"""수행평가 앱용 국내 주식 과거 OHLCV 일괄 수집기.

실행: python collect_real_data.py
예:   python collect_real_data.py --start 2024-01-01 --only 005930 000660
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path
import time

from market_data import fetch_historical_prices, save_historical_cache
from stock_core import KR_STOCKS


BASE = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description="국내 주식 실제 과거 시세를 CSV로 저장")
    parser.add_argument("--start", default=(date.today() - timedelta(days=365 * 3)).isoformat())
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--only", nargs="+", metavar="종목코드", help="예: 005930 000660")
    parser.add_argument("--output", type=Path, default=BASE / "data_cache", help="저장 폴더")
    args = parser.parse_args()
    selected = {
        name: code for name, code in KR_STOCKS.items()
        if args.only is None or code in args.only
    }
    if not selected or (args.only and set(args.only) != set(selected.values())):
        parser.error("--only에는 지원되는 종목코드 6개 중에서 지정하세요.")

    print(f"MARKET PULSE 실제 일별 데이터 수집: {args.start} ~ {args.end}")
    print("※ 데이터 제공처에 접속한 결과만 저장하며, 실패 시 가상 데이터로 대체하지 않습니다.")
    success = 0
    for name, code in selected.items():
        try:
            prices = fetch_historical_prices(code, args.start, args.end)
            info = save_historical_cache(args.output, code, prices)
            print(f"[성공] {name} ({code}) | {info['provider']} | "
                  f"{info['rows']}거래일 | 마지막: {info['last_date']}")
            success += 1
        except Exception as exc:
            print(f"[실패] {name} ({code}): {exc}")
        time.sleep(0.6)
    print(f"완료: {success}/{len(selected)}종목 | 저장 폴더: {args.output}")
    return 0 if success == len(selected) else 1


if __name__ == "__main__":
    raise SystemExit(main())
