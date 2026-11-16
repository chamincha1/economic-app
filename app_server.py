"""Low-overhead localhost-only MARKET PULSE server. Run: python app_server.py.

Serves the existing fintech UI without Node/npm/AI Studio/Streamlit reruns.
Financial fetching & AI only happen after explicit browser actions.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from threading import BoundedSemaphore
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import time
import webbrowser
from threading import Timer

from groq_client import configured, analyze, GroqError, remaining_today
from article_link import fetch_public_article, ArticleFetchError
from market_api import recent_prices, cached_prices, predictor, search_stocks, MarketAPIError
from stock_catalog import CATALOG

ROOT = Path(__file__).resolve().parent
HOST = '127.0.0.1'  # Local computer only; no public binding
DEFAULT_PORT = 8765
MAX_POST_BYTES = 12_000
MAX_API_CONCURRENCY = 3
fetch_slots = BoundedSemaphore(MAX_API_CONCURRENCY)
AI_COOLDOWN_SEC = 3
last_ai_call = 0.0

ALLOWED = {
    '/': 'index.html', '/index.html': 'index.html', '/styles.css': 'styles.css',
    '/src/app.js': 'src/app.js', '/src/analytics.js': 'src/analytics.js',
    '/assets/catalog.json': 'assets/catalog.json', '/assets/favicon.svg': 'assets/favicon.svg',
    '/assets/logo.png': 'assets/logo.png',
}


class UserInputError(ValueError):
    pass


class AppHandler(SimpleHTTPRequestHandler):
    server_version = 'MarketPulseLocal/2.1'
    sys_version = ''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        # Avoid logging full URL query values and submitted article/AI prompts.
        logging.info('%s %s', self.client_address[0], (fmt % args).split('?')[0][:250])

    def _headers(self, code: int, kind: str, length: int) -> None:
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(length))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', 'no-store' if kind.startswith('application/json') else 'public, max-age=120')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()

    def _json(self, data: object, code: int = 200) -> None:
        blob = json.dumps(data, ensure_ascii=False, allow_nan=False, default=str).encode('utf-8')
        self._headers(code, 'application/json; charset=utf-8', len(blob))
        if self.command != 'HEAD': self.wfile.write(blob)

    def _error(self, exc: Exception, code: int = 400) -> None:
        # Only send sanitized messages; never expose API credentials or tracebacks.
        self._json({'ok': False, 'error': str(exc)[:320]}, code=code)

    def _static(self, pathname: str) -> None:
        if pathname not in ALLOWED:
            return self._error(UserInputError('요청한 파일이 없습니다.'), 404)
        filepath = (ROOT / ALLOWED[pathname]).resolve()
        if not filepath.is_file() or ROOT not in filepath.parents or filepath.stat().st_size > 5_000_000:
            return self._error(UserInputError('파일을 찾을 수 없습니다.'), 404)
        kind = {
            '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
            '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml',
            '.json': 'application/json; charset=utf-8', '.png': 'image/png',
        }.get(filepath.suffix, 'application/octet-stream')
        content = filepath.read_bytes()
        self._headers(200, kind, len(content))
        if self.command != 'HEAD': self.wfile.write(content)

    def do_HEAD(self):
        return self.do_GET()

    def do_GET(self):
        try:
            uri = urlsplit(self.path)
            if uri.path in ('/api/health', '/api/catalog', '/api/stock', '/api/stock/cached', '/api/search'):
                if uri.path == '/api/health':
                    return self._json({'ok': True, 'app': 'MARKET PULSE', 'engine': 'python-local',
                                       'market': 'historical_daily', 'realtime': False,
                                       'ai_provider': 'GroqCloud', 'ai_configured': configured(),
                                       'quality_modes': ['standard', 'deep'], 'ai_calls_remaining_local': remaining_today()})
                if uri.path == '/api/catalog':
                    return self._json([{'name': n, 'code': c, 'sector': s} for n, c, s in CATALOG])
                params = parse_qs(uri.query)
                if uri.path == '/api/search':
                    return self._json({'ok': True, 'results': search_stocks(params.get('q', [''])[0])})
                code = params.get('code', [''])[0]
                days = int(params.get('days', ['450'])[0])
                if uri.path == '/api/stock/cached':
                    try: return self._json({'ok': True, **cached_prices(code, days=days)})
                    except MarketAPIError as exc: return self._error(exc, 404)
                force = params.get('refresh', ['0'])[0] == '1'
                if not fetch_slots.acquire(blocking=False):
                    return self._error(UserInputError('다른 자료 조회가 진행 중입니다. 잠시 후 다시 시도하세요.'), 503)
                try: return self._json({'ok': True, **recent_prices(code, days=days, force=force)})
                finally: fetch_slots.release()
            if uri.path.startswith('/api/'):
                return self._error(UserInputError('존재하지 않는 API입니다.'), 404)
            return self._static(uri.path)
        except (UserInputError, MarketAPIError, ValueError, ArticleFetchError, GroqError) as exc:
            return self._error(exc)
        except (ConnectionError, TimeoutError) as exc:
            return self._error(UserInputError('외부 서버 응답이 지연되었습니다.'), 502)
        except Exception:
            logging.exception('GET failed')
            return self._error(UserInputError('서버 처리 중 오류가 발생했습니다.'), 500)

    def do_POST(self):
        try:
            uri = urlsplit(self.path)
            if uri.path not in ('/api/news/analyze', '/api/predict'):
                return self._error(UserInputError('지원하지 않는 API입니다.'), 404)
            try: length = int(self.headers.get('Content-Length', '0'))
            except ValueError: length = -1
            if length <= 0 or length > MAX_POST_BYTES:
                return self._error(UserInputError('요청 데이터 크기가 잘못되었습니다.'), 413)
            if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
                return self._error(UserInputError('JSON 요청만 지원합니다.'), 415)
            try: data = json.loads(self.rfile.read(length))
            except ValueError:
                return self._error(UserInputError('JSON 형식이 올바르지 않습니다.'))
            if not isinstance(data, dict):
                return self._error(UserInputError('요청 형식이 올바르지 않습니다.'))
            if not fetch_slots.acquire(blocking=False):
                return self._error(UserInputError('분석 요청이 실행 중입니다. 중복 호출을 피하기 위해 잠시 제한합니다.'), 503)
            try:
                if uri.path == '/api/predict':
                    code = str(data.get('code', ''))
                    return self._json({'ok': True, **predictor(code)})
                if not configured():
                    return self._error(GroqError('GROQ_API_KEY가 등록되지 않았습니다. 프로젝트 .env 파일에 추가하세요.'), 503)
                urls = data.get('urls', [])
                if not isinstance(urls, list) or not 1 <= len(urls) <= 4:
                    return self._error(UserInputError('공개 기사 URL을 1~4개 입력하세요.'))
                if any(not isinstance(url, str) or len(url) > 2048 for url in urls):
                    return self._error(UserInputError('URL 형식 또는 길이가 올바르지 않습니다.'))
                if len(set(urls)) != len(urls):
                    return self._error(UserInputError('중복된 기사 URL은 제외해 주세요.'))
                quality = str(data.get('quality', 'deep'))
                if quality not in ('standard', 'deep'):
                    return self._error(UserInputError('분석 모드가 올바르지 않습니다.'))
                articles = [fetch_public_article(url) for url in urls]
                # Content is fetched only when a human presses the analyze button.
                result = analyze(articles, quality=quality)
                return self._json({'ok': True, 'analysis': result})
            finally:
                fetch_slots.release()
        except (UserInputError, MarketAPIError, ValueError, ArticleFetchError, GroqError) as exc:
            return self._error(exc)
        except Exception:
            logging.exception('POST failed')
            return self._error(UserInputError('서버 처리 중 오류가 발생했습니다.'), 500)


def main():
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(message)s')
    raw = os.environ.get('MARKET_PULSE_PORT', str(DEFAULT_PORT))
    try:
        port = int(raw)
        if not 1 <= port <= 65535: raise ValueError()
    except ValueError:
        raise SystemExit('MARKET_PULSE_PORT는 1~65535 사이 숫자여야 합니다.')
    httpd = ThreadingHTTPServer((HOST, port), AppHandler)
    httpd.daemon_threads = True
    print(f'MARKET PULSE started: http://{HOST}:{port}', flush=True)
    print('종료하려면 Ctrl+C를 누르세요. 외부 네트워크에 공개하지 않습니다.', flush=True)
    if os.environ.get('MARKET_PULSE_AUTO_OPEN', '1') != '0':
        Timer(1.0, lambda: webbrowser.open(f'http://{HOST}:{port}')).start()
    try: httpd.serve_forever(poll_interval=.25)
    except KeyboardInterrupt: pass
    finally: httpd.server_close()


if __name__ == '__main__':
    main()
