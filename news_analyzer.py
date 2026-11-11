"""Transparent Korean headline keyword classifier (NOT a trained financial NLP model).

Only article titles/short API descriptions are considered. The interpretation
is educational and context-sensitive finance claims are deliberately limited.
"""
from __future__ import annotations
import re
import pandas as pd

POSITIVE = ('흑자전환', '흑자 전환', '실적 개선', '실적개선', '사상 최대', '최대 실적',
            '수주 확대', '신규 수주', '매출 증가', '이익 증가', '성장', '공급 계약',
            '회복', '상향', '증가', '돌파', '개선', '투자 확대', '적자 축소')
NEGATIVE = ('적자 확대', '적자전환', '적자 전환', '실적 악화', '실적악화',
            '공급 차질', '비용 증가', '소송', '하향', '감소', '악화', '하락', '부진',
            '손실', '적자', '감산', '중단', '위기', '경고')
TOPIC_TERMS = {
    '실적': ('매출', '이익', '실적', '흑자', '적자', '분기'),
    '투자·계약': ('투자', '수주', '계약', '인수', '합병'),
    '산업·제품': ('반도체', '신제품', '서비스', '배터리', '자동차', '플랫폼'),
    '정책·거시': ('금리', '환율', '정책', '규제', '정부', '관세'),
    '위험 요인': ('소송', '공급 차질', '중단', '경고'),
}


def classify_text(text: str) -> dict:
    """Return explainable heuristic sentiment, score not a return or probability."""
    value = re.sub(r'\s+', ' ', str(text or '')).strip()
    positive = [word for word in POSITIVE if word in value]
    negative = [word for word in NEGATIVE if word in value]
    # Multiword phrases take precedence over broad tokens inside them.
    if '적자 축소' in positive and '적자' in negative:
        negative.remove('적자')
    if '적자 확대' in negative and '적자' in negative:
        negative.remove('적자')
    if '비용 증가' in negative and '증가' in positive:
        positive.remove('증가')
    raw = len(positive) - len(negative)
    score = max(-1.0, min(1.0, raw / 3))
    label = '긍정' if raw > 0 else ('부정' if raw < 0 else '중립/미분류')
    topic = next((name for name, terms in TOPIC_TERMS.items()
                  if any(term in value for term in terms)), '기타')
    return {'sentiment_label': label, 'sentiment_score': score,
            'topic': topic, 'evidence': ', '.join((positive + negative)[:5]) or '키워드 없음',
            'method': '설명 가능한 키워드 규칙(학습 모델 아님)'}


def analyze_articles(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return frame.copy() if frame is not None else pd.DataFrame()
    result = frame.copy()
    computed = [classify_text(f"{r.get('title', '')} {r.get('description', '')}")
                for _, r in result.iterrows()]
    for field in ('sentiment_label', 'sentiment_score', 'topic', 'evidence', 'method'):
        result[field] = [d[field] for d in computed]
    return result
