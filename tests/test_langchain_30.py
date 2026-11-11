"""Offline-only contract tests: news/ML inputs are fixtures, not fake market data."""
from datetime import datetime, timezone
import pandas as pd
import pytest
from config import STOCKS, STOCK_SECTORS, DEFAULT_SELECTED, secret_status
from stock_catalog import CATALOG, filter_catalog
from langchain_analysis import prepare_evidence, analyze_news_ai, explain_prediction_ai
from news_store import merge_news, load_news


def articles(code='005930', title='실제 API에서 온 기사 형식', ident='n1'):
    return pd.DataFrame([{
        'article_id': ident, 'stock_code': code, 'title': title,
        'description': '공시 관련 내용', 'publisher': 'news.example',
        'published_at': '2026-10-01T02:00:00+00:00',
        'first_seen_at': '2026-10-01T02:02:00+00:00',
        'collected_at': '2026-10-01T02:03:00+00:00',
        'source_url': 'https://news.example/article/1',
        'source_type': '뉴스', 'synthetic': False,
    }])


def test_30_valid_unique_codes_and_default_limited():
    assert len(STOCKS) == len(CATALOG) == 30
    assert len(set(STOCKS.values())) == 30
    assert all(len(c) == 6 and c.isdigit() for c in STOCKS.values())
    assert all(n in STOCK_SECTORS for n in STOCKS)
    assert set(DEFAULT_SELECTED) <= set(STOCKS)
    assert len(DEFAULT_SELECTED) <= 6
    assert filter_catalog('005930')[0][0] == '삼성전자'
    assert all(x[2] == '금융' for x in filter_catalog(sector='금융'))


def test_news_store_preserves_first_seen_and_sorts(tmp_path):
    one = articles()
    merge_news('005930', one, tmp_path)
    late = articles(title='기사 제목 변경', ident='n1')
    late['first_seen_at'] = '2026-11-02T11:00:00Z'
    merged = merge_news('005930', late, tmp_path)
    assert len(merged) == 1
    assert merged.iloc[0]['first_seen_at'] == pd.Timestamp('2026-10-01T02:02:00Z')
    assert len(load_news('005930', tmp_path)) == 1
    assert not (tmp_path / '005931.json').exists()


def test_news_store_rejects_wrong_stock_and_path_traversal(tmp_path):
    with pytest.raises(ValueError):
        load_news('../secrets', tmp_path)
    assert merge_news('005930', articles('000660'), tmp_path).empty
    assert not (tmp_path/'005930.json').exists()


def test_evidence_filters_synthetic_and_limits_size():
    frame = pd.concat([articles(ident=f'n{i}') for i in range(20)], ignore_index=True)
    frame.loc[0,'synthetic'] = True
    frame.loc[1,'title'] = 'Z'*1000
    items, msg = prepare_evidence(frame)
    assert not msg and len(items) == 12
    assert all(len(x['title']) <= 430 for x in items)
    items2, msg2 = prepare_evidence(frame.assign(synthetic=True))
    assert items2 == [] and msg2


def test_llm_news_source_refs_are_checked_and_no_probability_generated():
    def fake_executor(schema, system, context):
        assert context['stock'] == '삼성전자'
        assert len(context['news_items']) == 1
        assert '기사' in system
        return {
            'overview':'기사 제목에 근거한 요약', 'sentiment':'긍정',
            'positive_factors':['실적'], 'negative_factors':[],
            'uncertainties':['기사 본문 미확인'], 'evidence_numbers':[1,50,-1,1]
        }
    result = analyze_news_ai('삼성전자', articles(), executor=fake_executor)
    assert len(result['sources']) == 1 and result['sources'][0]['number'] == 1
    assert result['sentiment'] == '긍정'
    assert 'probability' not in result


def test_llm_outlook_reuses_exact_numeric_model_probability():
    def fake_executor(schema, system, context):
        assert context['numeric_model']['probability_up'] == 0.43
        return {
            'scenario':'판단 보류', 'interpretation':'뉴스가 충분하지 않습니다',
            'upward_factors':[], 'downward_factors':[],
            'limitations':['검증 필요'], 'evidence_numbers':[1,12]
        }
    output = explain_prediction_ai('삼성전자', {
        '모델':'기술 지표 포함', '상승 추정 확률':0.43,
        '기준 거래일':'2026-11-09'
    }, {'Brier':0.26}, articles(), executor=fake_executor)
    assert output['numeric_probability_up'] == 0.43
    assert len(output['sources']) == 1
    assert output['scenario'] == '판단 보류'


def test_invalid_probability_is_rejected():
    with pytest.raises(ValueError):
        explain_prediction_ai('삼성전자', {'모델':'a','기준 거래일':'a','상승 추정 확률':1.3}, {}, articles(), executor=lambda *_: {})


def test_keys_not_embedded_in_catalog_or_example():
    assert not any('XAI' in x[1] for x in CATALOG)
