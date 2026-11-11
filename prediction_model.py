"""Run price-only vs technical vs historically available news model experiments."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from feature_engineering import (prepare_feature_table, usable_history,
                                 historical_news_coverage, PRICE_FEATURES,
                                 TECH_FEATURES, NEWS_FEATURES)
from backtesting import chronological_test, walkforward_scores, probability_up, _predictor

@dataclass
class PredictionResult:
    summary: pd.DataFrame
    evaluations: dict
    forecasts: pd.DataFrame
    history: pd.DataFrame
    news_note: str


def run_experiments(price: pd.DataFrame, *, news: pd.DataFrame | None = None,
                    min_rows: int = 100) -> PredictionResult:
    table = prepare_feature_table(price, news=news)
    last_date = table['Date'].iloc[-1]
    coverage = historical_news_coverage(news, pd.Timestamp(last_date))
    configurations = {'가격·거래량': PRICE_FEATURES, '기술 지표 포함': TECH_FEATURES}
    if coverage['ok']:
        configurations['기술 지표 + 뉴스'] = TECH_FEATURES + NEWS_FEATURES
    evaluations, rows, predictions = {}, [], []
    for label, feats in configurations.items():
        history = usable_history(table, feats)
        result = chronological_test(history, feats, min_rows=min_rows)
        evaluations[label] = result
        m = result.metrics['test']
        b = result.metrics['baseline_test']
        rows.append({'모델': label, '표본수': m['표본수'], '정확도': m['정확도'],
                     '정밀도': m['정밀도'], '재현율': m['재현율'], 'F1': m['F1'],
                     'Brier': m['Brier'], '기준 Brier': b['Brier'],
                     '평가 시작': result.test_start, '평가 종료': result.test_end})
        # Latest possible t+1 prediction: retrain on ALL known targets only.
        if len(set(history['TargetUp'])) < 2:
            continue
        latest = table[feats].tail(1).replace([np.inf, -np.inf], np.nan)
        model_now = _predictor().fit(
            history[feats].replace([np.inf, -np.inf], np.nan), history['TargetUp'].astype(int))
        p = float(probability_up(model_now, latest)[0])
        predictions.append({'모델': label, '기준 거래일': last_date.date().isoformat(),
                            '예측 대상': '다음 거래일 종가 상승 여부',
                            '상승 추정 확률': p,
                            '평가 Brier': m['Brier'], '검증 표본수': m['표본수'],
                            '모델 버전': 'logistic-v2', '검증 상태': '탐색적·미보정 확률 추정'})
    if not rows:
        raise ValueError('평가 가능한 모델이 없습니다.')
    note = coverage['reason']
    if coverage.get('synthetic'):
        note += ' 모든 뉴스는 가상 생성 기사입니다.'
    return PredictionResult(pd.DataFrame(rows), evaluations, pd.DataFrame(predictions),
                            table, note)
