import pandas as pd
import pytest
from stock_core import make_demo_data
from tests._news_fixture import news_fixture
from prediction_model import run_experiments
from feature_engineering import prepare_feature_table, usable_history, PRICE_FEATURES
from backtesting import chronological_test, walkforward_scores


def test_three_model_group_synthetic():
    prices = make_demo_data()['가상기업 B']
    news = news_fixture('가상기업 B')
    r = run_experiments(prices, news=news)
    assert list(r.summary['모델']) == ['가격·거래량','기술 지표 포함','기술 지표 + 뉴스']
    assert r.summary['표본수'].min() >= 20
    assert r.forecasts['상승 추정 확률'].between(0,1).all()
    assert r.evaluations['가격·거래량'].test_start > r.evaluations['가격·거래량'].fitted_until


def test_missing_news_disables_news_comparison():
    r = run_experiments(make_demo_data()['가상기업 A'])
    assert '기술 지표 + 뉴스' not in list(r.summary['모델'])


def test_short_data_not_reported_as_valid_prediction():
    with pytest.raises(ValueError, match='자료가 부족'):
        run_experiments(make_demo_data()['가상기업 A'].iloc[:75])


def test_walkforward_chronological_boundaries():
    table = prepare_feature_table(make_demo_data()['가상기업 C'])
    history = usable_history(table, PRICE_FEATURES)
    result = chronological_test(history, PRICE_FEATURES)
    assert result.prediction_rows['Date'].is_monotonic_increasing
    assert result.prediction_rows['ProbabilityUp'].between(0,1).all()
    scores = walkforward_scores(history, PRICE_FEATURES)
    assert len(scores) == 3
    assert scores['TestEnd'].is_monotonic_increasing
