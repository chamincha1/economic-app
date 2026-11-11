import numpy as np
import pandas as pd
import pytest
from stock_core import make_demo_data
from news_analyzer import classify_text, analyze_articles
from news_collector import normalize_articles, fetch_naver_news, read_news_csv
from feature_engineering import (make_news_features, prepare_feature_table,
                                 PRICE_FEATURES, historical_news_coverage)
from technical_indicators import add_indicators
from tests._news_fixture import news_fixture


def sample_articles():
    return pd.DataFrame([{'stock_code':'005930', 'title':'기업 실적 개선',
       'description':'적자 축소', 'published_at':'2025-01-02T14:00:00+09:00',
       'first_seen_at':'2025-01-02T14:05:00+09:00','source_url':'https://example.org/a',
       'synthetic':True}])


def test_keyword_sentiment_not_probability():
    data = classify_text('적자 축소 · 실적 개선')
    assert data['sentiment_label'] == '긍정'
    assert data['sentiment_score'] <= 1
    assert data['method'].startswith('설명 가능한')


def test_news_html_strip_and_duplicates():
    n = sample_articles()
    n.loc[0,'title'] = '<b>실적</b> &amp; 전망'
    result = normalize_articles(pd.concat([n,n]))
    assert len(result) == 1
    assert result.loc[0,'title'] == '실적 & 전망'


def test_article_historic_access_requires_first_seen():
    n = sample_articles()
    n['first_seen_at'] = '2025-01-06T10:00:00+09:00'
    dates = pd.to_datetime(['2025-01-02', '2025-01-03', '2025-01-06'])
    out = make_news_features(pd.Series(dates), n)
    assert out['news_count_7d'].tolist() == [0,0,1]


def test_articles_after_close_excluded_until_next_session():
    n = sample_articles()
    n['published_at'] = '2025-01-02T17:00:00+09:00'
    n['first_seen_at'] = '2025-01-02T17:05:00+09:00'
    dates = pd.to_datetime(['2025-01-02','2025-01-03'])
    out = make_news_features(pd.Series(dates), n)
    assert out['news_count_7d'].tolist() == [0,1]


def test_missing_first_seen_remains_unknown():
    n = sample_articles().drop(columns=['first_seen_at'])
    result = normalize_articles(n)
    assert result['first_seen_at'].isna().all()
    f = make_news_features(pd.Series(pd.to_datetime(['2025-01-03'])), n)
    assert f['news_count_7d'].sum() == 0


def test_news_api_headers_and_received_at():
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'items':[{'title':'<b>기업</b> 실적 개선',
          'description':'뉴스 검색 요약', 'originallink':'https://example.com/story',
          'pubDate':'Fri, 07 Nov 2025 14:00:00 +0900'}]}
    used = []
    def getter(url, **kw):
        used.append((url,kw))
        return Response()
    out = fetch_naver_news('삼성전자', '005930', client_id='local_id',
        client_secret='local_secret', request_get=getter)
    assert len(out) == 1
    assert out.loc[0,'title'] == '기업 실적 개선'
    assert pd.notna(out.loc[0,'first_seen_at'])
    assert used[0][1]['headers']['X-Naver-Client-Id'] == 'local_id'


def test_technical_indicators_are_past_only():
    df = make_demo_data()['가상기업 A']
    earlier = add_indicators(df.iloc[:150]).iloc[-1]
    full = add_indicators(df).iloc[149]
    for key in ('SMA_20','RSI_14','MACD_hist','Return_5d'):
        assert earlier[key] == pytest.approx(full[key])


def test_target_is_strictly_next_day():
    df = make_demo_data()['가상기업 A']
    table = prepare_feature_table(df)
    assert pd.isna(table['TargetUp'].iloc[-1])
    assert table['TargetUp'].iloc[0] == float(df['Close'].iloc[1] > df['Close'].iloc[0])
    changed = df.copy()
    changed.loc[100:, 'Close'] *= 20
    second = prepare_feature_table(changed)
    assert table['Return_1d'].iloc[99] == second['Return_1d'].iloc[99]
    assert table['TargetUp'].iloc[98] == second['TargetUp'].iloc[98]


def test_demo_news_historical_coverage():
    a = news_fixture('가상기업 A')
    status = historical_news_coverage(a, pd.Timestamp('2026-11-06'))
    assert status['ok'] and status['synthetic']


def test_no_news_historical_false():
    assert historical_news_coverage(pd.DataFrame(), pd.Timestamp('2026-11-06'))['ok'] is False
