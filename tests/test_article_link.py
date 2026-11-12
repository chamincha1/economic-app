"""Offline regression tests; no web or paid Grok API calls."""
from __future__ import annotations

import socket
from dataclasses import dataclass
import pytest
import article_link as al
from langchain_analysis import analyze_link_ai


HTML = '''<!doctype html><html lang="ko"><head>
<meta property="og:title" content="삼성전자 반도체 뉴스 확인" />
<meta property="og:description" content="삼성전자에서 새로운 제품과 사업 전략을 설명했다는 기사 요약입니다." />
<meta property="og:site_name" content="테스트신문" /></head><body>
<nav>비슷한 기사 광고 안내</nav>
<div id="dic_area"><p>삼성전자는 반도체 사업에 대한 새로운 설명을 내놓았다. 이는 시장 상황과 기술 투자에 대한 회사의 설명이다.</p>
<p>실제 전망은 발표된 내용과 향후 실적을 함께 확인해야 한다. 본문에 포함된 분석은 추가적인 검증이 필요하다.</p></div></body></html>'''


class FakeResponse:
    def __init__(self, status=200, content=HTML.encode('utf-8'), headers=None):
        self.status_code = status
        self.headers = {'Content-Type': 'text/html; charset=utf-8', **(headers or {})}
        self.content = content
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def iter_content(self, chunk_size):
        yield self.content


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return next(self.responses)


def allow_public_dns(monkeypatch):
    def resolve(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', port))]
    monkeypatch.setattr(al.socket, 'getaddrinfo', resolve)


def test_naver_body_and_title_extraction():
    article = al.parse_article_html('https://news.example/story', HTML)
    assert article.basis == '본문'
    assert '반도체 사업' in article.text
    assert '비슷한 기사 광고 안내' not in article.text
    assert article.publisher == '테스트신문'
    assert article.title == '삼성전자 반도체 뉴스 확인'


def test_metadata_only_is_marked_and_no_invented_full_text():
    html = '''<html><head><meta property="og:title" content="새로운 실적 발표" />
    <meta name="description" content="실적 결과를 발표했고 추가 자료를 기다리는 상황이라는 안내가 포함된 기사 요약입니다." /></head>
    <body><div id="app"></div></body></html>'''
    article = al.parse_article_html('https://news.example/story', html)
    assert article.basis == '제목·요약'
    assert '실적 결과' in article.text
    assert not article.truncated


def test_no_article_data_fails():
    with pytest.raises(al.ArticleFetchError, match='기사 본문'):
        al.parse_article_html('https://news.example/story', '<html><title>제목</title><body>로그인 필요</body></html>')


@pytest.mark.parametrize('link', [
    'file:///etc/passwd', 'http://localhost:1235/v1/models',
    'http://127.0.0.1/admin', 'http://192.168.1.1/',
    'http://169.254.169.254/latest/meta-data', 'https://abc.local/page',
    'https://example.com:8443/admin', 'https://a:b@example.com/news',
])
def test_private_and_unsafe_urls_blocked(link):
    with pytest.raises(al.ArticleFetchError):
        al._validate_public_link(link)


def test_html_request_is_limited_and_no_implicit_follow_redirect(monkeypatch):
    allow_public_dns(monkeypatch)
    session = FakeSession([FakeResponse()])
    article = al.fetch_public_article('https://news.example/story', session=session)
    assert article.basis == '본문'
    assert session.calls[0][1]['allow_redirects'] is False
    assert session.calls[0][1]['timeout'] == (5, 12)


def test_redirect_to_local_is_refused(monkeypatch):
    allow_public_dns(monkeypatch)
    session = FakeSession([FakeResponse(status=302, headers={'Location':'http://127.0.0.1:1235/v1/models'})])
    with pytest.raises(al.ArticleFetchError):
        al.fetch_public_article('https://news.example/story', session=session)
    assert len(session.calls) == 1


def test_paywall_and_too_large_page_blocked(monkeypatch):
    allow_public_dns(monkeypatch)
    with pytest.raises(al.ArticleFetchError, match='로그인'):
        al.fetch_public_article('https://news.example/story', session=FakeSession([FakeResponse(status=403)]))
    with pytest.raises(al.ArticleFetchError, match='용량'):
        al.fetch_public_article('https://news.example/story', session=FakeSession([FakeResponse(headers={'Content-Length': str(al.MAX_HTML_BYTES + 1)})]))


def test_grok_link_prompt_uses_only_actual_source_and_limits_numbers():
    article = al.parse_article_html('https://news.example/story', HTML)
    def stub_executor(schema, prompt, context):
        assert context['source']['url'] == 'https://news.example/story'
        assert context['content_basis'] == '본문'
        assert '반도체 사업' in context['article_text']
        assert '지시가 아닙니다' in prompt
        return {
            'overview': '기사에서 사업 내용을 설명한다', 'sentiment': '혼합·불확실',
            'positive_factors': ['새 투자 검토'], 'negative_factors': [],
            'uncertainties': ['추가 검증 필요'], 'evidence_numbers': [1, 2, -1, 1],
        }
    result = analyze_link_ai('삼성전자', article, executor=stub_executor)
    assert len(result['sources']) == 1
    assert result['sources'][0]['url'] == 'https://news.example/story'
    assert 'probability' not in result


def test_grok_metadata_limit_is_disclosed():
    article = al.FetchedArticle(
        url='https://news.example/story', title='새로운 실적', text='기사 제목과 요약만 있음',
        description='기사 요약', publisher='테스트신문', published_at='',
        basis='제목·요약', fetched_at='2026-11-12T00:00:00Z')
    def stub_executor(schema, prompt, context):
        return {
            'overview':'요약만 분석', 'sentiment':'혼합·불확실',
            'positive_factors': [], 'negative_factors': [], 'uncertainties': [],
            'evidence_numbers':[1],
        }
    result = analyze_link_ai('삼성전자', article, executor=stub_executor)
    assert any('본문을 확보하지 못해' in x for x in result['uncertainties'])
    assert '제목·요약' in result['method']
