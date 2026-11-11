"""Illustrative linear-model feature contributions, not causal explanations."""
from __future__ import annotations
import numpy as np
import pandas as pd


def describe_logistic_model(pipeline, columns: list[str], latest: pd.DataFrame) -> pd.DataFrame:
    """Feature values multiplied by standardized coefficients (log-odds scale)."""
    transformed = pipeline.named_steps['imputer'].transform(latest[columns])
    scaled = pipeline.named_steps['scale'].transform(transformed)
    beta = pipeline.named_steps['estimator'].coef_[0]
    contribution = np.asarray(scaled[0]) * np.asarray(beta)
    return pd.DataFrame({'변수': columns, '기여 방향 점수': contribution,
                         '표준화된 값': scaled[0]}).assign(
        절댓값=lambda x: x['기여 방향 점수'].abs()).sort_values('절댓값', ascending=False).drop(columns='절댓값')
