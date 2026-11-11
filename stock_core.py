"""MARKET PULSE — Korean stock OHLCV anomaly/volatility analysis.

Detectors describe historical statistical deviations, not future returns or advice.
All price returns are simple close-to-close returns in percentage points.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Mapping
import re

import numpy as np
import pandas as pd

WINDOW_DEFAULT = 20

KR_STOCKS = {
    "삼성전자": "005930",
    "SK하이닉스": "000660",
    "현대자동차": "005380",
    "기아": "000270",
    "NAVER": "035420",
    "카카오": "035720",
}

COLUMN_ALIASES = {
    "date": "Date", "날짜": "Date", "일자": "Date", "거래일": "Date",
    "datetime": "Date", "time": "Date",
    "close": "Close", "종가": "Close", "종료가": "Close",
    "adj close": "Close", "adj_close": "Close", "adjusted close": "Close",
    "volume": "Volume", "거래량": "Volume", "vol": "Volume",
    "open": "Open", "시가": "Open",
    "high": "High", "고가": "High",
    "low": "Low", "저가": "Low",
}


class StockDataError(ValueError):
    """Invalid input or insufficient stock data."""


def _name_columns(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    # FinanceDataReader yields Date as DatetimeIndex, CSVs usually have a Date column.
    if isinstance(df.index, pd.DatetimeIndex) and not any(
        str(c).strip().lower() in {"date", "날짜", "일자", "거래일", "datetime"}
        for c in df.columns
    ):
        df = df.reset_index()
        if str(df.columns[0]).strip().lower() not in COLUMN_ALIASES:
            df = df.rename(columns={df.columns[0]: "Date"})

    rename = {}
    for col in df.columns:
        key = str(col).strip().lower()
        if key in COLUMN_ALIASES:
            rename[col] = COLUMN_ALIASES[key]
    df = df.rename(columns=rename)
    if df.columns.duplicated().any():
        # Prefer first original/renamed occurrence consistently.
        df = df.loc[:, ~df.columns.duplicated()].copy()
    return df


def clean_data(raw: pd.DataFrame) -> pd.DataFrame:
    """Return Date-sorted daily OHLCV with positive closes and nonnegative volumes."""
    if raw is None or raw.empty:
        raise StockDataError("데이터가 비어 있습니다. 종목·기간·CSV 내용을 확인하세요.")
    df = _name_columns(raw)
    required = {"Date", "Close", "Volume"}
    if not required.issubset(df.columns):
        raise StockDataError(
            "필수 열이 없습니다. Date(날짜), Close(종가), Volume(거래량)이 필요합니다. "
            f"현재 열: {', '.join(map(str, df.columns))}"
        )
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    for col in ("Close", "Volume", "Open", "High", "Low"):
        if col in df.columns:
            as_string = df[col].astype(str).str.replace(",", "", regex=False).str.strip()
            df[col] = pd.to_numeric(as_string, errors="coerce")
    df = df.dropna(subset=["Date", "Close", "Volume"])
    df = df[(df["Close"] > 0) & (df["Volume"] >= 0)].copy()
    df = df.sort_values("Date").drop_duplicates("Date", keep="last").reset_index(drop=True)
    if len(df) < 3:
        raise StockDataError("유효한 거래일이 3일 미만입니다. CSV 또는 수집 기간을 확인하세요.")
    return df


def read_csv_bytes(file_bytes: bytes) -> pd.DataFrame:
    """Read standard Korean/English CSV (including UTF-8-SIG and CP949)."""
    for enc in ("utf-8-sig", "cp949", "utf-8"):
        try:
            df = pd.read_csv(BytesIO(file_bytes), encoding=enc)
            return clean_data(df)
        except UnicodeDecodeError:
            continue
        except pd.errors.EmptyDataError as exc:
            raise StockDataError("CSV 파일이 비어 있습니다.") from exc
    raise StockDataError("CSV 인코딩을 읽을 수 없습니다. UTF-8 또는 CP949로 저장하세요.")


def calculate_indicators(
    raw: pd.DataFrame,
    window: int = WINDOW_DEFAULT,
    z_limit: float = 2.5,
    q_limit: float = 1.5,
) -> pd.DataFrame:
    """Compute lagged benchmarks, anomalies, and explanatory diagnostics.

    Previous rolling benchmarks use returns and volume through t-1 only.
    WINDOW returns require WINDOW+1 preceding closes before a day is scorable.
    """
    if window < 5:
        raise StockDataError("비교 기간은 최소 5거래일이어야 합니다.")
    if z_limit <= 0 or q_limit <= 0:
        raise StockDataError("탐지 기준값은 양수여야 합니다.")

    df = clean_data(raw)
    if len(df) < window + 2:
        raise StockDataError(
            f"20일 전후의 비교 자료가 부족합니다. 최소 {window + 2}거래일이 필요합니다. "
            "더 긴 기간의 데이터를 준비하세요."
        )

    df["ReturnPct"] = df["Close"].pct_change(fill_method=None) * 100
    df["MA"] = df["Close"].rolling(window, min_periods=window).mean()
    df["Volatility"] = df["ReturnPct"].rolling(window, min_periods=window).std(ddof=1)

    prev_returns = df["ReturnPct"].shift(1)
    prev_volume = df["Volume"].shift(1)
    df["PriorMean"] = prev_returns.rolling(window, min_periods=window).mean()
    df["PriorStd"] = prev_returns.rolling(window, min_periods=window).std(ddof=1)
    df["PriorVolume"] = prev_volume.rolling(window, min_periods=window).mean()

    df["Scorable"] = df[["ReturnPct", "PriorMean", "PriorStd", "PriorVolume"]].notna().all(axis=1)
    deviation = (df["ReturnPct"] - df["PriorMean"]).abs()
    sigma_positive = df["PriorStd"] > 1e-12
    df["Zscore"] = deviation.div(df["PriorStd"].where(sigma_positive)).replace([np.inf, -np.inf], np.nan)
    # Identically flat prior return sample: the standard Z-score is undefined.
    df["ZeroStdChange"] = df["Scorable"] & ~sigma_positive & (deviation > 1e-10)
    df["PriceJump"] = df["Scorable"] & ((df["Zscore"] >= z_limit) | df["ZeroStdChange"])

    vol_positive = df["PriorVolume"] > 0
    df["VolumeRatio"] = df["Volume"].div(df["PriorVolume"].where(vol_positive)).replace([np.inf, -np.inf], np.nan)
    df["ZeroVolumeChange"] = df["Scorable"] & ~vol_positive & (df["Volume"] > 0)
    df["VolumeJump"] = df["Scorable"] & ((df["VolumeRatio"] >= q_limit) | df["ZeroVolumeChange"])

    conditions = [
        df["PriceJump"] & df["VolumeJump"],
        df["PriceJump"],
        df["VolumeJump"],
    ]
    df["Status"] = np.select(
        conditions,
        ["가격·거래량 동반 급변", "가격 급변", "거래량 급증"],
        default="일반 범위",
    )
    df.loc[~df["Scorable"], "Status"] = "기준 데이터 부족"
    df["Direction"] = np.select(
        [df["ReturnPct"] > 0, df["ReturnPct"] < 0],
        ["상승", "하락"], default="보합",
    )
    return df


def trim_period(df: pd.DataFrame, start: date | str, end: date | str) -> pd.DataFrame:
    a, b = pd.Timestamp(start), pd.Timestamp(end)
    if a > b:
        raise StockDataError("시작일은 종료일보다 이전이어야 합니다.")
    out = df.loc[df["Date"].between(a, b)].copy()
    if out.empty:
        raise StockDataError("선택한 날짜 범위에 거래 데이터가 없습니다.")
    if not out["Scorable"].any():
        raise StockDataError("선택한 기간에 직전 거래일 기준을 계산할 자료가 부족합니다. 시작일 이전 데이터도 포함하세요.")
    return _recompute_drawdown(out)


def _recompute_drawdown(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["DrawdownPct"] = (df["Close"] / df["Close"].cummax() - 1) * 100
    return df


def common_date_align(results: Mapping[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], bool]:
    """Align comparison periods using common daily observations (>=10 common days)."""
    if len(results) < 2:
        return dict(results), True
    intersections = None
    for df in results.values():
        idx = set(pd.to_datetime(df["Date"]).dt.normalize().tolist())
        intersections = idx if intersections is None else intersections & idx
    if not intersections or len(intersections) < 10:
        return dict(results), False
    out = {}
    for name, df in results.items():
        selected = df[df["Date"].dt.normalize().isin(intersections)].copy()
        out[name] = _recompute_drawdown(selected)
    return out, True


def summarize(results: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, df in results.items():
        valid = df[df["Scorable"]]
        if valid.empty:
            continue
        events = valid["PriceJump"].sum()
        rows.append({
            "종목": name,
            "거래일": len(df),
            "분석가능일": len(valid),
            "평균 일일변동성(%)": round(float(valid["Volatility"].mean()), 3),
            "최대 일일변동성(%)": round(float(valid["Volatility"].max()), 3),
            "가격급변(회)": int(events),
            "급변탐지율(%)": round(100 * float(events) / len(valid), 2),
            "거래량급증(회)": int(valid["VolumeJump"].sum()),
            "동반급변(회)": int((valid["PriceJump"] & valid["VolumeJump"]).sum()),
            "최대낙폭 MDD(%)": round(float(df["DrawdownPct"].min()), 2),
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("평균 일일변동성(%)", ascending=False).reset_index(drop=True)


def event_table(results: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    frames = []
    for name, df in results.items():
        events = df[df["Scorable"] & (df["PriceJump"] | df["VolumeJump"])].copy()
        if events.empty:
            continue
        events.insert(0, "종목", name)
        events = events.rename(columns={
            "Date": "날짜", "Close": "종가", "ReturnPct": "일일수익률(%)",
            "Zscore": "Z점수", "VolumeRatio": "거래량배율",
            "Status": "탐지분류", "Direction": "방향",
            "ZeroStdChange": "과거표준편차0", "ZeroVolumeChange": "과거거래량0",
        })
        frames.append(events[["종목", "날짜", "종가", "일일수익률(%)", "Z점수", "거래량배율", "방향", "탐지분류", "과거표준편차0", "과거거래량0"]])
    if not frames:
        return pd.DataFrame(columns=["종목", "날짜", "종가", "일일수익률(%)", "Z점수", "거래량배율", "방향", "탐지분류", "과거표준편차0", "과거거래량0"])
    return pd.concat(frames, ignore_index=True).sort_values("날짜", ascending=False).reset_index(drop=True)


def fetch_live_data(code: str, start: date, end: date) -> pd.DataFrame:
    """Download OHLCV using FinanceDataReader; online connectivity required."""
    import FinanceDataReader as fdr

    # Fetch warm-up trading days so the requested start date can be scored.
    fetch_start = pd.Timestamp(start) - pd.Timedelta(days=160)
    fetch_end = pd.Timestamp(end) + pd.Timedelta(days=1)
    data = fdr.DataReader(code, fetch_start.strftime("%Y-%m-%d"), fetch_end.strftime("%Y-%m-%d"))
    return clean_data(data)


def make_demo_data(seed: int = 24) -> dict[str, pd.DataFrame]:
    """Synthetic reproducible OHLCV. Not real prices or real events."""
    dates = pd.bdate_range("2024-06-03", "2026-11-06")
    names = ["가상기업 A", "가상기업 B", "가상기업 C", "가상기업 D"]
    volatilities = [0.010, 0.019, 0.013, 0.024]
    rng = np.random.default_rng(seed)
    output = {}
    for i, (name, vol) in enumerate(zip(names, volatilities)):
        returns = rng.normal(0.0003, vol, len(dates))
        volumes = rng.lognormal(np.log(150000 + i * 24000), 0.32, len(dates)).astype(int)
        for k, shock in [(120 + i * 13, 0.09 + i * 0.02), (320 + i * 7, -0.12 - i * 0.015), (515 + i * 4, 0.10)]:
            if k < len(returns):
                returns[k] = shock if i % 2 == 0 else -shock
                volumes[k] *= 3
        close = (50000 + 10000 * i) * np.cumprod(1 + returns)
        open_ = close / (1 + rng.normal(0, 0.003, len(dates)))
        high = np.maximum(open_, close) * (1 + rng.uniform(0.001, 0.014, len(dates)))
        low = np.minimum(open_, close) * (1 - rng.uniform(0.001, 0.014, len(dates)))
        output[name] = pd.DataFrame({
            "Date": dates, "Open": open_.round(2), "High": high.round(2),
            "Low": low.round(2), "Close": close.round(2), "Volume": volumes,
        })
    return output
