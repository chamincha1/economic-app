from __future__ import annotations
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import date, datetime
from threading import Thread
from unittest.mock import patch, MagicMock
from urllib.request import urlopen, Request
from urllib.error import HTTPError
import pandas as pd

# The bundled tests run without contacting real price or AI vendors.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import groq_client
import market_api
from article_link import ArticleFetchError, parse_article_html, FetchedArticle, _validate_public_link
from app_server import AppHandler
from http.server import ThreadingHTTPServer


def _json_call(host, path, body=None):
    blob = json.dumps(body).encode() if body is not None else None
    request = Request(host + path, blob, {'Content-Type':'application/json'} if body is not None else {}, method='POST' if body is not None else 'GET')
    try:
        with urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), AppHandler)
        cls.thread = Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.host = f'http://127.0.0.1:{cls.httpd.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close();cls.thread.join(timeout=2)

    def test_health(self):
        code, body = _json_call(self.host, '/api/health')
        self.assertEqual(code,200);self.assertEqual(body['market'],'historical_daily');self.assertFalse(body['realtime'])

    def test_catalog(self):
        code, body = _json_call(self.host, '/api/catalog')
        self.assertEqual(code,200);self.assertEqual(len(body),30)

    def test_main(self):
        with urlopen(self.host+'/', timeout=2) as r:
            blob=r.read().decode('utf-8');self.assertIn('MARKET PULSE',blob);self.assertEqual(r.status,200)

    def test_assets(self):
        for name in ['/src/app.js','/src/analytics.js','/styles.css','/assets/favicon.svg','/assets/logo.png','/assets/catalog.json']:
            with self.subTest(name=name):
                with urlopen(self.host+name, timeout=2) as r:
                    self.assertEqual(r.status,200);self.assertTrue(r.read())

    def test_hidden_data_denied(self):
        for path in ['/.env','/.env.example','/package.json','/server.mjs','/app_server.py','/data_cache/005930.csv','/.gitignore','/README.md','/src/../../app_server.py']:
            with self.subTest(path=path):
                try: urlopen(self.host+path, timeout=2)
                except HTTPError as e:self.assertIn(e.code,(400,403,404))
                else:self.fail('private file exposed: '+path)

    def test_unknown_api(self):
        code,body=_json_call(self.host,'/api/does-not-exist')
        self.assertEqual(code,404)

    def test_no_key_blocks_paid_ai(self):
        with patch.object(groq_client, 'configured', return_value=False), patch('app_server.configured',return_value=False):
            code,body=_json_call(self.host,'/api/news/analyze',{'urls':['https://example.com/news']})
            self.assertEqual(code,503);self.assertIn('GROQ_API_KEY',body['error'])

    def test_empty_json(self):
        code,body=_json_call(self.host,'/api/predict',{})
        self.assertEqual(code,400)

    def test_prediction_endpoint_with_mock(self):
        payload={'code':'005930','name':'삼성전자','forecasts':[],'summary':[]}
        with patch('app_server.predictor',return_value=payload):
            code,body=_json_call(self.host,'/api/predict',{'code':'005930'})
        self.assertEqual(code,200)
        self.assertEqual(body['name'],'삼성전자')

    def test_article_endpoint_with_mock(self):
        a=FetchedArticle(url='https://example.com/news',title='기사 테스트',text='공개 텍스트 '*50,
                         description='',publisher='기자',published_at='',basis='본문',fetched_at='')
        brief={'summary':'공개 기사 1건의 주요 내용','sources':[{'id':1,'url':a.url}], 'request_count':2}
        with patch('app_server.configured',return_value=True),patch('app_server.fetch_public_article',return_value=a),patch('app_server.analyze',return_value=brief) as analyze_mock:
            code,body=_json_call(self.host,'/api/news/analyze',{'urls':[a.url],'quality':'deep'})
        self.assertEqual(code,200)
        self.assertEqual(body['analysis']['summary'],brief['summary'])
        analyze_mock.assert_called_once()

    def test_reject_duplicate_urls_without_external_call(self):
        with patch('app_server.configured',return_value=True),patch('app_server.fetch_public_article') as fetch_mock:
            code,body=_json_call(self.host,'/api/news/analyze',{'urls':['https://example.com/a','https://example.com/a']})
        self.assertEqual(code,400)
        fetch_mock.assert_not_called()


class ArticleTests(unittest.TestCase):
    def test_simple_article(self):
        h='<html><head><meta property="og:title" content="금융 기사 테스트" /></head><body><article>'+''.join('<p>기사의 공개 본문을 확인합니다. 시장 요인을 기록합니다. </p>' for _ in range(8))+'</article></body></html>'
        a=parse_article_html('https://example.com/abc',h)
        self.assertEqual(a.basis,'본문');self.assertGreater(len(a.text),100)

    def test_metadata_only_not_faked(self):
        h='<html><head><meta property="og:title" content="실제 기사"/><meta property="og:description" content="기업의 실적에 관한 보도가 공개되었으며 수치 확인이 필요합니다. 기업의 매출과 이익에 대한 서술은 추가 검증이 필요합니다."/></head><body></body></html>'
        a=parse_article_html('https://example.com/article',h)
        self.assertEqual(a.basis,'제목·요약')

    def test_no_content_rejected(self):
        with self.assertRaises(ArticleFetchError):
            parse_article_html('https://example.com', '<html><title>로그인</title></html>')

    def test_local_article_url_rejected(self):
        for url in ('http://127.0.0.1/private','http://localhost/a','file:///etc/passwd','http://192.168.1.1/admin'):
            with self.subTest(url=url):
                with self.assertRaises(ArticleFetchError):_validate_public_link(url)

    def test_non_http_rejected(self):
        for url in ('javascript:alert(1)','ftp://example.com/file','http://user:pass@example.com/a'):
            with self.subTest(url=url):
                with self.assertRaises(ArticleFetchError):_validate_public_link(url)


class GroqTests(unittest.TestCase):
    def setUp(self):
        self.article = FetchedArticle(url='https://example.com', title='공개 기사 제목', text='기사 내용 '*40,
            description='',publisher='신문사',published_at='2026-11-16',basis='본문',fetched_at='2026-11-16T00:00:00Z')
        self.out = {'summary':'기사에 기반한 핵심 요약','stance':'중립','positive_factors':[{'point':'기사 사실','sources':[1],'type':'기사 사실'}],
                    'negative_factors':[],'key_numbers':[],'uncertainties':['정보 부족'],'possible_impact':'인과관계 불확실','limitations':'기사 범위 제한'}

    def test_quality_standard_one_request(self):
        with patch.object(groq_client,'_completion',return_value=self.out) as f:
            result=groq_client.analyze([self.article],'standard')
        self.assertEqual(f.call_count,1);self.assertEqual(result['request_count'],1)

    def test_quality_deep_two_requests(self):
        with patch.object(groq_client,'_completion',return_value=self.out) as f:
            result=groq_client.analyze([self.article],'deep')
        self.assertEqual(f.call_count,2);self.assertEqual(result['request_count'],2)

    def test_unsupported_quality(self):
        with self.assertRaises(groq_client.GroqError):
            groq_client.analyze([self.article],'unsafe')

    def test_invalid_sources_removed(self):
        d=dict(self.out);d['positive_factors']=[{'point':'P','sources':[0,1,7,'2',-1]}]
        out=groq_client._normalize(d,1)
        self.assertEqual(out['positive_factors'][0]['sources'],[1])

    def test_empty_summary_blocked(self):
        d=dict(self.out);d['summary']=''
        with self.assertRaises(groq_client.GroqError): groq_client._normalize(d,1)

    def test_no_env_file_without_key(self):
        with patch.dict(os.environ,{'GROQ_API_KEY':''},clear=False):
            with self.assertRaises(groq_client.GroqError):groq_client._completion([],max_tokens=5)

    def test_local_request_cap_blocks_excess(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(groq_client,'USAGE_PATH',Path(temp)/'usage.json'):
                with patch.dict(os.environ,{'GROQ_DAILY_REQUEST_CAP':'2'},clear=False):
                    self.assertEqual(groq_client.remaining_today(),2)
                    groq_client.reserve_daily_request()
                    groq_client.reserve_daily_request()
                    self.assertEqual(groq_client.remaining_today(),0)
                    with self.assertRaises(groq_client.GroqError):groq_client.reserve_daily_request()


class StockTests(unittest.TestCase):
    def test_fetch_history_source_and_fallback(self):
        from market_data import fetch_historical
        days=pd.bdate_range('2026-10-01','2026-11-13')
        frame=pd.DataFrame({'Open':range(100,100+len(days)), 'High':range(102,102+len(days)),
            'Low':range(98,98+len(days)), 'Close':range(101,101+len(days)), 'Volume':[150]*len(days)},index=days)
        with tempfile.TemporaryDirectory() as temp:
            fresh=fetch_historical('005930',date(2026,10,1),date(2026,11,13),cache_dir=temp,
                 reader=lambda sym,start,end:frame)
            self.assertEqual(fresh.meta['source'],'NAVER:005930')
            self.assertFalse(fresh.meta['realtime'])
            cached=fetch_historical('005930',date(2026,10,1),date(2026,11,13),cache_dir=temp,
                 reader=lambda *a: (_ for _ in ()).throw(ConnectionError('TEST_OFFLINE')))
            self.assertEqual(cached.meta['status'],'cached')
            self.assertTrue(cached.meta['warning'])

    def test_unknown_code(self):
        with self.assertRaises(market_api.MarketAPIError):market_api.recent_prices('000000')

    def test_invalid_days(self):
        with self.assertRaises(market_api.MarketAPIError):market_api.recent_prices('005930',days=3)

    def test_price_normalization_and_cache(self):
        dates=pd.to_datetime(['2026-10-05','2026-10-06','2026-10-07'])
        frame=pd.DataFrame({'Date':dates,'Open':[100,110,112],'High':[120,125,130],
            'Low':[90,95,98],'Close':[110,112,115],'Volume':[100,150,190]})
        result=type('Result',(),{'frame':frame,'meta':{'source':'TEST_ONLY','status':'fresh','last_trade_date':'2026-10-07'}})()
        with patch('market_data.fetch_historical',return_value=result) as fetch:
            x=market_api.recent_prices('005930',days=371,force=True)
            y=market_api.recent_prices('005930',days=371)
        self.assertEqual(fetch.call_count,1);self.assertEqual(len(x['prices']),3);self.assertEqual(x,y)

if __name__=='__main__':unittest.main()
