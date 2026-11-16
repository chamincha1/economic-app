"""Regression tests for automatic prices, custom watchlist and saved true-source caches."""
from __future__ import annotations
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Thread
from unittest.mock import patch
from urllib.request import urlopen
from urllib.error import HTTPError
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import market_api
from app_server import AppHandler
from http.server import ThreadingHTTPServer


class PriceWorkflowTests(unittest.TestCase):
    def test_unknown_six_digit_code_passes_to_actual_reader(self):
        rows = pd.DataFrame({
            'Date': pd.to_datetime(['2026-11-10', '2026-11-11', '2026-11-12']),
            'Open': [100, 103, 102], 'High': [105, 108, 109],
            'Low': [99, 102, 101], 'Close': [102, 107, 104], 'Volume': [20, 30, 40]
        })
        result = type('Result', (), {'frame': rows, 'meta': {'status': 'fresh', 'source': 'UNIT_TEST', 'last_trade_date': '2026-11-12'}})()
        with patch('market_data.fetch_historical', return_value=result) as fetch:
            data = market_api.recent_prices('123456', days=380, force=True)
        fetch.assert_called_once()
        self.assertEqual(data['code'], '123456')
        self.assertEqual(data['name'], '종목 123456')
        self.assertEqual(data['prices'][-1]['close'], 104)
        self.assertEqual(data['meta']['source'], 'UNIT_TEST')

    def test_invalid_code_rejected_before_network(self):
        for code in ('000000', '12345', '../../secrets', 'abcdef', '1234567'):
            with self.subTest(code=code):
                with patch('market_data.fetch_historical') as mock:
                    with self.assertRaises(market_api.MarketAPIError):
                        market_api.recent_prices(code, force=True)
                    mock.assert_not_called()

    def test_cached_real_daily_prices_are_available_without_online_request(self):
        with tempfile.TemporaryDirectory() as dirname:
            folder = Path(dirname)
            today = datetime.now(market_api.KST).date()
            days = [today-timedelta(days=n) for n in (3, 2, 1)]
            frame = pd.DataFrame({'Date': days, 'Open': [99, 100, 108], 'High': [105, 110, 115],
                                  'Low': [90, 95, 100], 'Close': [100, 108, 110], 'Volume': [22, 33, 44]})
            frame.to_csv(folder/'005930.csv', index=False)
            (folder/'005930.meta.json').write_text(json.dumps({'source': 'UNIT_TEST_NAVER', 'last_trade_date': days[-1].isoformat()}),encoding='utf-8')
            with patch.object(market_api,'DATA_CACHE',folder), patch('market_data.fetch_historical') as online:
                result = market_api.cached_prices('005930')
                online.assert_not_called()
            self.assertEqual(result['meta']['status'], 'cached')
            self.assertFalse(result['meta']['realtime'])
            self.assertEqual(result['prices'][-1]['close'], 110)
            self.assertEqual(result['meta']['source'], 'UNIT_TEST_NAVER')

    def test_no_cached_prices_is_not_fabricated(self):
        with tempfile.TemporaryDirectory() as dirname:
            with patch.object(market_api, 'DATA_CACHE', Path(dirname)):
                with self.assertRaisesRegex(market_api.MarketAPIError, '저장된 실제 종가'):
                    market_api.cached_prices('005930')

    def test_krx_search_only_on_explicit_call(self):
        listing = pd.DataFrame({'Code':['005930','123456'], 'Name':['삼성전자','검증주식']})
        with patch('market_data.list_domestic_stocks', return_value=listing) as getter:
            with patch.object(market_api,'_stock_listing_cache',None):
                matches=market_api.search_stocks('검증')
            self.assertEqual(matches, [{'code':'123456','name':'검증주식','sector':'KRX 검색'}])
            getter.assert_called_once()


class EndpointWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(('127.0.0.1',0),AppHandler)
        cls.thread = Thread(target=cls.httpd.serve_forever,daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.httpd.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown();cls.httpd.server_close();cls.thread.join(timeout=2)

    def test_cached_endpoint_does_not_trigger_network(self):
        fake = {'code':'005930','name':'삼성전자','prices':[], 'meta':{'status':'cached'}}
        with patch('app_server.cached_prices',return_value=fake) as cached, patch('app_server.recent_prices') as online:
            with urlopen(self.url+'/api/stock/cached?code=005930') as response:
                payload=json.load(response)
        self.assertEqual(payload['meta']['status'],'cached')
        cached.assert_called_once();online.assert_not_called()

    def test_krx_search_endpoint(self):
        matches=[{'code':'123456','name':'검증기업','sector':'KRX 검색'}]
        with patch('app_server.search_stocks',return_value=matches):
            with urlopen(self.url+'/api/search?q=%EA%B2%80%EC%A6%9D') as response:
                self.assertEqual(json.load(response)['results'],matches)

    def test_custom_code_live_endpoint(self):
        fake={'code':'123456','name':'종목 123456','prices':[],'meta':{'status':'fresh'}}
        with patch('app_server.recent_prices',return_value=fake) as stock:
            with urlopen(self.url+'/api/stock?code=123456&days=460') as response:
                data=json.load(response)
        self.assertEqual(data['code'],'123456')
        stock.assert_called_once_with('123456',days=460,force=False)

    def test_no_private_files_can_be_served(self):
        for p in ('/.env', '/data_cache/005930.csv', '/market_api.py', '/requirements.txt', '/app_server.py'):
            with self.subTest(p=p):
                with self.assertRaises(HTTPError) as caught:
                    urlopen(self.url+p)
                self.assertEqual(caught.exception.code,404)


if __name__=='__main__':unittest.main()
