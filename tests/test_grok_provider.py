"""Offline safety checks for the optional Grok API provider. No network traffic."""
from __future__ import annotations
import sys
from types import ModuleType
import pytest

import langchain_analysis as ai


def test_grok_ready_requires_xai_key(monkeypatch):
    monkeypatch.setattr(ai, 'get_secret', lambda key: '' if key == 'XAI_API_KEY' else 'grok-4')
    assert not ai.ai_ready()
    with pytest.raises(ValueError, match='XAI_API_KEY'):
        ai._model()


def test_grok_uses_chatxai_and_custom_model(monkeypatch):
    details = {}

    class FakeChatXAI:
        def __init__(self, **kwargs):
            details.update(kwargs)

    module = ModuleType('langchain_xai')
    module.ChatXAI = FakeChatXAI
    monkeypatch.setitem(sys.modules, 'langchain_xai', module)
    monkeypatch.setattr(ai, 'get_secret', lambda key: {'XAI_API_KEY': 'test-only-not-real', 'XAI_MODEL': 'grok-4'}.get(key, ''))
    assert ai.ai_ready()
    result = ai._model()
    assert isinstance(result, FakeChatXAI)
    assert details['model'] == 'grok-4'
    assert details['api_key'] == 'test-only-not-real'
    assert details['max_retries'] == 1


def test_numerical_probability_not_generated_by_grok():
    from tests.test_langchain_30 import articles

    def executor(schema, prompt, context):
        assert context['numeric_model']['probability_up'] == 0.37
        return {
            'scenario':'판단 보류',
            'interpretation':'수치 모델은 참고용입니다.',
            'upward_factors':[], 'downward_factors':[],
            'limitations':['검증 성능 확인 필요'], 'evidence_numbers':[1],
        }
    report = ai.explain_prediction_ai('삼성전자', {
        '모델':'기술 지표 포함', '상승 추정 확률': 0.37, '기준 거래일':'2026-11-11'
    }, {}, articles(), executor=executor)
    assert report['numeric_probability_up'] == 0.37
    assert 'Grok' in report['method']
