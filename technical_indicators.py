"""Causal price/volume indicators. No centered or future-facing windows."""
from __future__ import annotations
import numpy as np
import pandas as pd
from stock_core import clean_data


def _rsi_wilder(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Wilder's smoothing alpha=1/n; require a full initial window.
    avg_g = gain.ewm(alpha=1/n, min_periods=n, adjust=False).mean()
    avg_l = loss.ewm(alpha=1/n, min_periods=n, adjust=False).mean()
    rs = avg_g / avg_l.replace(0, np.nan)
    value = 100 - 100 / (1 + rs)
    value = value.mask((avg_l == 0) & (avg_g > 0), 100)
    value = value.mask((avg_l == 0) & (avg_g == 0), 50)
    return value


def add_indicators(raw: pd.DataFrame) -> pd.DataFrame:
    df = clean_data(raw)
    c = df['Close'].astype(float)
    for n in (5, 10, 20, 60, 120):
        df[f'SMA_{n}'] = c.rolling(n, min_periods=n).mean()
    ema12 = c.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = c.ewm(span=26, adjust=False, min_periods=26).mean()
    df['EMA_12'] = ema12
    df['EMA_26'] = ema26
    df['MACD'] = ema12 - ema26
    df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False, min_periods=9).mean()
    df['MACD_hist'] = df['MACD'] - df['MACD_signal']
    df['RSI_14'] = _rsi_wilder(c)
    std20 = c.rolling(20, min_periods=20).std(ddof=1)
    df['BB_upper'] = df['SMA_20'] + 2 * std20
    df['BB_lower'] = df['SMA_20'] - 2 * std20
    if {'High', 'Low'}.issubset(df.columns):
        high, low = df['High'].astype(float), df['Low'].astype(float)
        tr = pd.concat([(high - low), (high - c.shift(1)).abs(),
                        (low - c.shift(1)).abs()], axis=1).max(axis=1)
        df['ATR_14'] = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    else:
        df['ATR_14'] = np.nan
    df['Volume_SMA20'] = df['Volume'].rolling(20, min_periods=20).mean()
    df['Volume_Ratio'] = df['Volume'].div(df['Volume_SMA20'].shift(1).replace(0, np.nan))
    df['Return_1d'] = c.pct_change(fill_method=None) * 100
    df['Return_5d'] = c.pct_change(5, fill_method=None) * 100
    df['Return_20d'] = c.pct_change(20, fill_method=None) * 100
    df['Volatility_20d'] = df['Return_1d'].rolling(20, min_periods=20).std(ddof=1)
    df['Distance_SMA20'] = (c / df['SMA_20'] - 1) * 100
    df['Drawdown'] = (c / c.cummax() - 1) * 100
    return df
