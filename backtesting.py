"""Leakage-conscious chronological classification assessment.

The supervised target y[t] requires Close[t+1]; a 1-row gap is deliberately
inserted before each evaluation block to avoid label overlap at the boundary.
The final held-out test block is not used for model selection.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.dummy import DummyClassifier
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                             f1_score, brier_score_loss, log_loss)
from sklearn.model_selection import TimeSeriesSplit


@dataclass
class Evaluation:
    metrics: dict
    prediction_rows: pd.DataFrame
    model: object
    feature_names: list[str]
    fitted_until: str
    test_start: str
    test_end: str


def _predictor() -> Pipeline:
    return Pipeline([('imputer', SimpleImputer(strategy='median', keep_empty_features=True)),
                     ('scale', StandardScaler()),
                     ('estimator', LogisticRegression(max_iter=1000, random_state=42))])


def _baseline() -> DummyClassifier:
    return DummyClassifier(strategy='prior')


def probability_up(model, features: pd.DataFrame) -> np.ndarray:
    proba = model.predict_proba(features)
    classes = list(model.classes_)
    return proba[:, classes.index(1)] if 1 in classes else np.zeros(len(features))


def score_prediction(actual: np.ndarray, probs: np.ndarray) -> dict:
    y = np.asarray(actual, dtype=int)
    p = np.asarray(probs, dtype=float).clip(1e-7, 1 - 1e-7)
    yp = (p >= 0.5).astype(int)
    return {'표본수': len(y), '정확도': float(accuracy_score(y, yp)),
            '정밀도': float(precision_score(y, yp, zero_division=0)),
            '재현율': float(recall_score(y, yp, zero_division=0)),
            'F1': float(f1_score(y, yp, zero_division=0)),
            'Brier': float(brier_score_loss(y, p)),
            'LogLoss': float(log_loss(y, p, labels=[0, 1]))}


def chronological_test(table: pd.DataFrame, features: list[str], *,
                       min_rows: int = 100) -> Evaluation:
    if len(table) < min_rows:
        raise ValueError(f'AI 검증을 위한 자료가 부족합니다. 최소 {min_rows}개 유효한 학습 행이 필요합니다(현재 {len(table)}개).')
    if len(set(table['TargetUp'])) < 2:
        raise ValueError('상승·비상승 사례가 모두 있어야 확률 모델을 학습할 수 있습니다.')
    n = len(table)
    train_end = int(n * .6)
    val_end = int(n * .8)
    if train_end < 40 or val_end - train_end < 15 or n - val_end < 15:
        raise ValueError('훈련/검증/시험용 관측값 수가 부족합니다.')
    x = table[features].replace([np.inf, -np.inf], np.nan)
    y = table['TargetUp'].astype(int)
    # One row gap at boundary, because label[t] uses close[t+1].
    x_train, y_train = x.iloc[:train_end-1], y.iloc[:train_end-1]
    x_val, y_val = x.iloc[train_end:val_end], y.iloc[train_end:val_end]
    if y_train.nunique() < 2:
        raise ValueError('학습 구간의 클래스가 하나여서 로지스틱 회귀를 학습할 수 없습니다.')
    candidate = _predictor().fit(x_train, y_train)
    benchmark = _baseline().fit(x_train, y_train)
    val_scores = {
        '모델': score_prediction(y_val.to_numpy(), probability_up(candidate, x_val)),
        '기준': score_prediction(y_val.to_numpy(), probability_up(benchmark, x_val))
    }
    # Frozen test model, fitted only on data before the final 20% test segment.
    x_trainval, y_trainval = x.iloc[:val_end-1], y.iloc[:val_end-1]
    model = _predictor().fit(x_trainval, y_trainval)
    base = _baseline().fit(x_trainval, y_trainval)
    x_test, y_test = x.iloc[val_end:], y.iloc[val_end:]
    pred = probability_up(model, x_test)
    base_pred = probability_up(base, x_test)
    test_scores = score_prediction(y_test.to_numpy(), pred)
    base_scores = score_prediction(y_test.to_numpy(), base_pred)
    pred_rows = pd.DataFrame({'Date': table['Date'].iloc[val_end:].to_numpy(),
                              'ActualUp': y_test.to_numpy(), 'ProbabilityUp': pred,
                              'BaselineProbabilityUp': base_pred})
    metrics = {'test': test_scores, 'baseline_test': base_scores,
               'validation': val_scores, 'model_version': 'logistic-v2',
               'train_rows': len(x_trainval), 'test_rows': len(x_test)}
    return Evaluation(metrics, pred_rows, model, features,
                      str(table['Date'].iloc[val_end-2].date()),
                      str(table['Date'].iloc[val_end].date()),
                      str(table['Date'].iloc[-1].date()))


def walkforward_scores(table: pd.DataFrame, features: list[str], *, splits=3) -> pd.DataFrame:
    if len(table) < 120:
        raise ValueError('Walk-forward 검증에는 최소 120개 이상의 학습 행이 필요합니다.')
    x = table[features].replace([np.inf, -np.inf], np.nan)
    y = table['TargetUp'].astype(int)
    kfold = TimeSeriesSplit(n_splits=splits, gap=1)
    records = []
    for fold, (train_idx, test_idx) in enumerate(kfold.split(x), 1):
        if y.iloc[train_idx].nunique() != 2:
            continue
        model = _predictor().fit(x.iloc[train_idx], y.iloc[train_idx])
        metrics = score_prediction(y.iloc[test_idx], probability_up(model, x.iloc[test_idx]))
        records.append({'Fold': fold, 'TestStart': table['Date'].iloc[test_idx[0]],
                        'TestEnd': table['Date'].iloc[test_idx[-1]], **metrics})
    return pd.DataFrame(records)
