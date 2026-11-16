"""Offline regression tests for local LM Studio + Qwen3 8B provider."""
from __future__ import annotations
import json
import socket
import sys
from types import ModuleType
import pytest
import langchain_analysis as ai


def test_server_reachability_offline(monkeypatch):
    seen = {}
    class FakeConnection:
        def __enter__(self): return self
        def __exit__(self, *_): pass
    def fake_connect(address, timeout):
        seen['address'] = address
        seen['timeout'] = timeout
        return FakeConnection()
    monkeypatch.setattr(socket, 'create_connection', fake_connect)
    assert ai.ai_ready()
    assert seen['address'] == ('127.0.0.1', 1235)
    def fail_connect(*args, **kwargs):
        raise OSError('not running')
    monkeypatch.setattr(socket, 'create_connection', fail_connect)
    assert not ai.ai_ready()


def test_local_model_does_not_use_paid_key(monkeypatch):
    options = {}
    class FakeChatOpenAI:
        def __init__(self, **kwargs): options.update(kwargs)
    fake = ModuleType('langchain_openai')
    fake.ChatOpenAI = FakeChatOpenAI
    monkeypatch.setitem(sys.modules, 'langchain_openai', fake)
    result = ai._model()
    assert isinstance(result, FakeChatOpenAI)
    assert options['model'] == 'qwen3-8b'
    assert options['base_url'] == 'http://127.0.0.1:1235/v1'
    assert options['api_key'] == 'lm-studio'
    assert options['max_retries'] == 0


def test_json_response_validation():
    example = {'overview':'기사 요약', 'sentiment':'혼합·불확실',
               'positive_factors':[], 'negative_factors':[],
               'uncertainties':['실적 확인 필요'], 'evidence_numbers':[1]}
    raw = '```json\n' + json.dumps(example, ensure_ascii=False) + '\n```'
    assert ai._json_object_from_response(raw) == example
    assert ai._json_object_from_response('<think>내부 추론</think>' + json.dumps(example, ensure_ascii=False)) == example
    with pytest.raises(ValueError, match='JSON 형식'):
        ai._json_object_from_response('기사에 대해 분석해보면...')


def test_quantitative_probability_is_unchanged():
    from tests.test_langchain_30 import articles
    def executor(schema, prompt, context):
        assert context['numeric_model']['probability_up'] == 0.37
        return {'scenario':'판단 보류','interpretation':'수치 모델 참고',
                'upward_factors':[],'downward_factors':[],
                'limitations':['과거 검증 필요'],'evidence_numbers':[1]}
    result = ai.explain_prediction_ai('삼성전자', {
        '모델':'기술 지표 포함','상승 추정 확률':0.37,'기준 거래일':'2026-11-11'
    }, {}, articles(), executor=executor)
    assert result['numeric_probability_up'] == 0.37
    assert 'LM Studio' in result['method']
