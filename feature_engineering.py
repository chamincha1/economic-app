"""Daily post-close t -> next-session t+1 classification features.

A feature may use data available no later than 16:00 KST on date t. News is
included in historical tests only when an actual first-seen timestamp was
recorded in advance (or the whole dataset is marked SYNTHETIC).
"""
from __future__ import annotations
from bisect import bisect_right
from datetime import timedelta
import numpy as np
import pandas as pd
from technical_indicators import add_indicators
from news_analyzer import analyze_articles
from news_collector import normalize_articles

PRICE_FEATURES = ['Return_1d', 'Return_5d', 'Return_20d', 'Volatility_20d', 'Volume_Ratio']
TECH_FEATURES = PRICE_FEATURES + ['Distance_SMA20', 'RSI_14', 'MACD_hist', 'Drawdown']
NEWS_FEATURES = ['news_count_7d', 'news_mean_sentiment_7d', 'news_count_1d']


def make_news_features(dates: pd.Series, articles: pd.DataFrame) -> pd.DataFrame:
    """Return point-in-time 7-day summary, 16:00 KST daily cutoff.

    Publication and first-observed timestamps must BOTH predate cutoff.
    This does NOT turn a newly gathered historical archive into an authentic
    point-in-time backtest: records are only counted after *first_seen_at*.
    """
    result = pd.DataFrame({'news_count_7d': np.zeros(len(dates), dtype=float),
                           'news_mean_sentiment_7d': np.zeros(len(dates), dtype=float),
                           'news_count_1d': np.zeros(len(dates), dtype=float)})
    if articles is None or articles.empty:
        return result
    a = normalize_articles(articles)
    if a.empty:
        return result
    a = analyze_articles(a)
    a = a.dropna(subset=['first_seen_at'])
    if a.empty:
        return result
    # Exact as-of availability: timestamp of publication AND timestamp first seen.
    a['available_at'] = a[['published_at', 'first_seen_at']].max(axis=1)
    a = a.sort_values('available_at')
    timestamps = a['available_at'].astype('int64').to_numpy()
    scores = a['sentiment_score'].astype(float).to_numpy()
    for i, day in enumerate(pd.to_datetime(dates)):
        cutoff = pd.Timestamp(day.date().isoformat() + 'T16:00:00+09:00')
        right = bisect_right(timestamps, cutoff.value)
        left7 = bisect_right(timestamps, (cutoff - pd.Timedelta(days=7)).value)
        left1 = bisect_right(timestamps, (cutoff - pd.Timedelta(days=1)).value)
        result.loc[i, 'news_count_7d'] = right - left7
        result.loc[i, 'news_count_1d'] = right - left1
        if right > left7:
            result.loc[i, 'news_mean_sentiment_7d'] = float(scores[left7:right].mean())
    return result


def prepare_feature_table(price: pd.DataFrame, *, news: pd.DataFrame | None = None) -> pd.DataFrame:
    base = add_indicators(price).reset_index(drop=True)
    target_next = base['Close'].shift(-1)
    # Last row has no known t+1 closing price and stays available for inference.
    base['TargetUp'] = np.where(target_next.notna(), (target_next > base['Close']).astype(float), np.nan)
    base['TargetNextClose'] = target_next
    features = make_news_features(base['Date'], news) if news is not None else make_news_features(base['Date'], pd.DataFrame())
    return pd.concat([base.reset_index(drop=True), features], axis=1)


def usable_history(table: pd.DataFrame, feature_names: list[str]) -> pd.DataFrame:
    """Prepare labels without ever dropping the last inference observation in caller."""
    use = table[['Date', 'TargetUp'] + feature_names].copy()
    use = use.dropna(subset=['TargetUp'])
    # Most rolling indicators require ~20 sessions; don't silently fill beginning.
    use = use.dropna(subset=PRICE_FEATURES)
    return use.reset_index(drop=True)


def historical_news_coverage(news: pd.DataFrame | None, ending_day: pd.Timestamp) -> dict:
    if news is None or news.empty:
        return {'ok': False, 'count': 0, 'reason': '입력한 기사 데이터가 없습니다.'}
    a = normalize_articles(news)
    known = a.dropna(subset=['first_seen_at']).copy()
    known = known[known['first_seen_at'] <= ending_day.tz_localize('Asia/Seoul') + pd.Timedelta(hours=16)]
    if len(known) < 20:
        return {'ok': False, 'count': len(known), 'reason': '과거 시점에 확인된 기사 수가 20건 미만입니다.'}
    span = (known['first_seen_at'].max() - known['first_seen_at'].min()).days
    if span < 45:
        return {'ok': False, 'count': len(known), 'reason': '기사 최초 확인 기록이 45일 미만에 집중되어 있습니다.'}
    return {'ok': True, 'count': len(known),
            'reason': '최초 확인 시각 기록을 이용한 뉴스 변수(수집 완전성은 별도 검증 필요).',
            'synthetic': bool(known['synthetic'].all())}
