"""MARKET PULSE 일별 국내 주식 시세 수집과 출처가 기록되는 로컬 캐시.

실시간 체결가 API가 아닙니다. 실제 데이터 제공처에 접속이 성공할 때만
시세가 생성되며 가상 데이터로 자동 대체하지 않습니다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Callable
import json
import re

import pandas as pd

from stock_core import StockDataError, clean_data, read_csv_bytes

PROVIDERS = ("NAVER", "KRX")
REQUIRED_COLUMNS = ("Date", "Open", "High", "Low", "Close", "Volume")

# This list is deliberately a *fallback*, not a market-cap ranking.  The app
# refreshes the actual order from KRX through FinanceDataReader when available.
# Keeping a broad local list means a temporary KRX listing outage never removes
# the user's ability to analyse well-known large Korean companies.
FALLBACK_LARGE_CAP_STOCKS = (
    ("삼성전자", "005930", "KOSPI"), ("SK하이닉스", "000660", "KOSPI"),
    ("LG에너지솔루션", "373220", "KOSPI"), ("삼성바이오로직스", "207940", "KOSPI"),
    ("현대자동차", "005380", "KOSPI"), ("기아", "000270", "KOSPI"),
    ("KB금융", "105560", "KOSPI"), ("셀트리온", "068270", "KOSPI"),
    ("NAVER", "035420", "KOSPI"), ("신한지주", "055550", "KOSPI"),
    ("삼성물산", "028260", "KOSPI"), ("삼성생명", "032830", "KOSPI"),
    ("삼성SDI", "006400", "KOSPI"), ("POSCO홀딩스", "005490", "KOSPI"),
    ("LG화학", "051910", "KOSPI"), ("현대모비스", "012330", "KOSPI"),
    ("한화에어로스페이스", "012450", "KOSPI"), ("HD현대중공업", "329180", "KOSPI"),
    ("HD한국조선해양", "009540", "KOSPI"), ("두산에너빌리티", "034020", "KOSPI"),
    ("한화오션", "042660", "KOSPI"), ("현대로템", "064350", "KOSPI"),
    ("카카오", "035720", "KOSPI"), ("삼성전기", "009150", "KOSPI"),
    ("LG전자", "066570", "KOSPI"), ("SK이노베이션", "096770", "KOSPI"),
    ("KT", "030200", "KOSPI"), ("KT&G", "033780", "KOSPI"),
    ("고려아연", "010130", "KOSPI"), ("한국전력", "015760", "KOSPI"),
    ("SK텔레콤", "017670", "KOSPI"), ("삼성화재", "000810", "KOSPI"),
    ("우리금융지주", "316140", "KOSPI"), ("하나금융지주", "086790", "KOSPI"),
    ("기업은행", "024110", "KOSPI"), ("삼성중공업", "010140", "KOSPI"),
    ("HD현대일렉트릭", "267260", "KOSPI"), ("크래프톤", "259960", "KOSPI"),
    ("하이브", "352820", "KOSPI"), ("대한항공", "003490", "KOSPI"),
    ("에코프로비엠", "247540", "KOSDAQ"), ("에코프로", "086520", "KOSDAQ"),
    ("알테오젠", "196170", "KOSDAQ"), ("HLB", "028300", "KOSDAQ"),
    ("레인보우로보틱스", "277810", "KOSDAQ"), ("삼천당제약", "000250", "KOSDAQ"),
    ("펄어비스", "263750", "KOSDAQ"), ("휴젤", "145020", "KOSDAQ"),
    ("파마리서치", "214450", "KOSDAQ"), ("클래시스", "214150", "KOSDAQ"),
)


@dataclass
class HistoricalPrices:
    frame: pd.DataFrame
    provider: str


def fallback_large_cap_universe(limit: int = 50) -> pd.DataFrame:
    """Return a usable 50-stock selection when KRX's listing service is down."""
    rows = [
        {"순위": i, "종목": name, "종목코드": code, "시장": market, "시가총액": None}
        for i, (name, code, market) in enumerate(FALLBACK_LARGE_CAP_STOCKS[:limit], start=1)
    ]
    return pd.DataFrame(rows)


def fetch_krx_large_cap_universe(
    limit: int = 50,
    *,
    listing_reader: Callable | None = None,
) -> pd.DataFrame:
    """Fetch the current KRX market-cap ranking for KOSPI and KOSDAQ.

    The function is intentionally separate from historical price collection so
    callers can fall back to a clearly labelled local list if the KRX listing
    endpoint is unavailable.  The returned ranking reflects the provider's
    latest available trading-day snapshot, not intraday prices.
    """
    if limit < 1:
        raise StockDataError("가져올 종목 수는 1개 이상이어야 합니다.")
    if listing_reader is None:
        try:
            import FinanceDataReader as fdr
        except ImportError as exc:
            raise StockDataError("FinanceDataReader가 설치되지 않았습니다. requirements.txt를 설치하세요.") from exc
        listing_reader = fdr.StockListing
    try:
        listing = listing_reader("KRX")
    except Exception as exc:
        raise StockDataError(f"KRX 상장목록을 가져오지 못했습니다: {type(exc).__name__}: {str(exc)[:180]}") from exc
    if not isinstance(listing, pd.DataFrame) or listing.empty:
        raise StockDataError("KRX 상장목록이 비어 있습니다.")

    columns = {str(col).strip().lower(): col for col in listing.columns}
    code_col = columns.get("code") or columns.get("symbol")
    name_col = columns.get("name") or columns.get("종목명")
    market_col = columns.get("market") or columns.get("marketname") or columns.get("시장구분")
    cap_col = columns.get("marcap") or columns.get("marketcap") or columns.get("시가총액")
    if not all((code_col, name_col, market_col, cap_col)):
        raise StockDataError("KRX 상장목록에 종목코드·종목명·시장·시가총액 열이 없습니다.")

    universe = listing[[code_col, name_col, market_col, cap_col]].copy()
    universe.columns = ["종목코드", "종목", "시장", "시가총액"]
    universe["종목코드"] = universe["종목코드"].astype(str).str.extract(r"(\d{6})", expand=False)
    universe["시가총액"] = pd.to_numeric(universe["시가총액"], errors="coerce")
    universe["시장"] = universe["시장"].astype(str).str.upper()
    universe = universe[
        universe["종목코드"].notna()
        & universe["종목"].notna()
        & universe["시장"].isin(["KOSPI", "KOSDAQ"])
        & universe["시가총액"].gt(0)
    ]
    universe = universe.sort_values("시가총액", ascending=False).drop_duplicates("종목코드")
    universe = universe.head(limit).reset_index(drop=True)
    if universe.empty:
        raise StockDataError("시가총액이 있는 KOSPI/KOSDAQ 종목을 찾지 못했습니다.")
    universe.insert(0, "순위", range(1, len(universe) + 1))
    return universe


def _as_date(value: date | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def fetch_historical_prices(
    code: str,
    start: date | str,
    end: date | str,
    *,
    reader: Callable | None = None,
    providers: tuple[str, ...] = PROVIDERS,
) -> HistoricalPrices:
    """Download real daily OHLCV; try NAVER then KRX and report provenance.

    180 calendar days before the analysis period are collected as a warm-up
    for rolling statistics. No synthetic data is used on failure.
    """
    if not re.fullmatch(r"\d{6}", code):
        raise StockDataError("종목 코드는 숫자 6자리여야 합니다.")
    start_date, end_date = _as_date(start), _as_date(end)
    if start_date > end_date:
        raise StockDataError("실데이터 수집 시작일은 종료일보다 이전이어야 합니다.")
    if reader is None:
        try:
            import FinanceDataReader as fdr
        except ImportError as exc:
            raise StockDataError("FinanceDataReader가 설치되지 않았습니다. requirements.txt를 설치하세요.") from exc
        reader = fdr.DataReader

    request_start = (start_date - timedelta(days=180)).isoformat()
    # FinanceDataReader의 종료일 취급 방식에 따른 당일 누락 방지
    request_end = (end_date + timedelta(days=1)).isoformat()
    failures: list[str] = []
    for provider in providers:
        symbol = f"{provider}:{code}"
        try:
            data = reader(symbol, request_start, request_end)
            frame = clean_data(data)
            missing = set(REQUIRED_COLUMNS) - set(frame.columns)
            if missing:
                raise StockDataError(f"필수 시세 열 누락: {', '.join(sorted(missing))}")
            frame = frame.loc[frame["Date"].dt.date <= end_date].copy()
            # OHLC 값이 0/누락인 비정상 행은 검증 없이 시세로 보이지 않는다.
            frame = frame.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
            frame = frame.loc[
                (frame[["Open", "High", "Low", "Close"]] > 0).all(axis=1)
                & (frame["Volume"] >= 0)
            ].reset_index(drop=True)
            # A positive price alone is not enough: malformed provider rows can
            # otherwise make impossible candles appear in the analysis.
            valid_ohlc = (
                (frame["Low"] <= frame[["Open", "Close"]].min(axis=1))
                & (frame["High"] >= frame[["Open", "Close"]].max(axis=1))
                & (frame["High"] >= frame["Low"])
            )
            frame = frame.loc[valid_ohlc].reset_index(drop=True)
            if len(frame) < 3 or not (frame["Date"].dt.date >= start_date).any():
                raise StockDataError("요청한 분석 기간에 유효한 시세가 없습니다.")
            if not frame["Date"].is_monotonic_increasing:
                raise StockDataError("시세 날짜가 올바른 순서가 아닙니다.")
            return HistoricalPrices(frame=frame, provider=provider)
        except Exception as exc:
            failures.append(f"{provider}: {type(exc).__name__}: {str(exc)[:130]}")
    raise StockDataError(
        f"{code} 실데이터 수집 실패 — " + " / ".join(failures)
        + ". 네트워크 또는 제공처 상태를 확인하고 다시 시도하세요."
    )


def save_historical_cache(
    cache_dir: Path | str,
    code: str,
    prices: HistoricalPrices,
) -> dict:
    """Save real OHLCV plus provenance metadata. Never write synthetic fallback."""
    folder = Path(cache_dir)
    folder.mkdir(parents=True, exist_ok=True)
    frame = prices.frame.copy()
    if frame.empty:
        raise StockDataError("빈 시세 데이터는 저장하지 않습니다.")
    metadata = {
        "code": code,
        "provider": prices.provider,
        "source": f"FinanceDataReader:{prices.provider}",
        "collected_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "first_date": frame["Date"].min().date().isoformat(),
        "last_date": frame["Date"].max().date().isoformat(),
        "rows": len(frame),
        "interval": "1d",
        "is_realtime": False,
    }
    # Atomic replace means a failed CSV write does not corrupt an old usable file.
    csv_path = folder / f"{code}.csv"
    json_path = folder / f"{code}.meta.json"
    temp_csv = folder / f".{code}.csv.tmp"
    temp_meta = folder / f".{code}.meta.json.tmp"
    try:
        frame.to_csv(temp_csv, index=False, encoding="utf-8-sig")
        temp_meta.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_csv.replace(csv_path)
        temp_meta.replace(json_path)
    finally:
        temp_csv.unlink(missing_ok=True)
        temp_meta.unlink(missing_ok=True)
    return metadata


def read_historical_cache(cache_dir: Path | str, code: str) -> tuple[pd.DataFrame, dict]:
    folder = Path(cache_dir)
    frame = read_csv_bytes((folder / f"{code}.csv").read_bytes())
    meta_path = folder / f"{code}.meta.json"
    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    except (ValueError, OSError):
        metadata = {}
    # A cache created by the former app has no provenance metadata.
    metadata.setdefault("source", "출처 미기록(구버전 캐시)")
    metadata.setdefault("collected_at_utc", "기록 없음")
    metadata.setdefault("last_date", frame["Date"].max().date().isoformat())
    metadata.setdefault("is_realtime", False)
    return frame, metadata


def format_origin(metadata: dict, *, cached: bool) -> str:
    label = metadata.get("source", "출처 미확인")
    last_date = metadata.get("last_date", "알 수 없음")
    collected = metadata.get("collected_at_utc", "기록 없음")
    try:
        collected = datetime.fromisoformat(collected).astimezone(
            timezone(timedelta(hours=9))
        ).strftime("%Y-%m-%d %H:%M KST")
    except (ValueError, TypeError):
        pass
    prefix = "이전 저장 자료 · 현재 시세 아님" if cached else "온라인 수집(일별 시세)"
    return f"{prefix} | {label} | 마지막 거래일: {last_date} | 수집: {collected}"
