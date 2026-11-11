"""Licensed-access metadata-only NAVER search and CSV imports.

News results are current search snapshots. The *first_seen_at* timestamp is
when this system fetched a result; historical backtests must not pretend an
old article was available to our system at its original publication time.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from io import BytesIO
from html import unescape
from pathlib import Path
from urllib.parse import urlparse
import hashlib
import re
import pandas as pd
import requests
from config import get_secret

KST = timezone(timedelta(hours=9))
NAVER_NEWS_ENDPOINT = 'https://openapi.naver.com/v1/search/news.json'
NEWS_COLUMNS = ['article_id', 'stock_code', 'title', 'description', 'publisher',
                'published_at', 'first_seen_at', 'collected_at', 'source_url',
                'source_type', 'synthetic']


def strip_markup(value: str) -> str:
    return re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]+>', '', str(value)))).strip()


def normalize_url(value: str) -> str:
    u = str(value or '')
    parsed = urlparse(u)
    return u if parsed.scheme in ('https', 'http') and parsed.netloc else ''


def normalize_articles(frame: pd.DataFrame, *, synthetic: bool = False) -> pd.DataFrame:
    """Require historical timestamp availability; no inferred first_seen for uploads."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=NEWS_COLUMNS)
    df = frame.copy()
    required = {'title', 'published_at'}
    if not required.issubset(df.columns):
        raise ValueError('뉴스 CSV에는 title, published_at 열이 필요합니다.')
    for name in NEWS_COLUMNS:
        if name not in df.columns:
            df[name] = ''
    df['title'] = df['title'].map(strip_markup)
    df['description'] = df['description'].fillna('').map(strip_markup)
    df['source_url'] = df['source_url'].fillna('').map(normalize_url)
    df['published_at'] = pd.to_datetime(df['published_at'], errors='coerce', utc=True)
    # first_seen_at is mandatory for credible historical availability; blank means unknown.
    df['first_seen_at'] = pd.to_datetime(df['first_seen_at'], errors='coerce', utc=True)
    df['collected_at'] = pd.to_datetime(df['collected_at'], errors='coerce', utc=True)
    df['synthetic'] = df['synthetic'].astype(str).str.lower().isin(('true','1','yes','y')) | synthetic
    df = df.dropna(subset=['published_at'])
    df = df[df['title'].ne('')].copy()
    df['article_id'] = df.apply(lambda row: (row['article_id'] if pd.notna(row['article_id']) and str(row['article_id']).strip() else hashlib.sha256(
        f"{row['stock_code']}|{row['source_url']}|{row['title']}|{row['published_at']}".encode('utf-8')).hexdigest()[:18]), axis=1)
    df = df.drop_duplicates('article_id', keep='first').sort_values('published_at', ascending=False)
    return df[NEWS_COLUMNS].reset_index(drop=True)


def fetch_naver_news(query: str, stock_code: str = '', *, display: int = 40,
                     client_id: str | None = None, client_secret: str | None = None,
                     request_get=None) -> pd.DataFrame:
    client_id = client_id or get_secret('NAVER_CLIENT_ID')
    client_secret = client_secret or get_secret('NAVER_CLIENT_SECRET')
    if not client_id or not client_secret:
        raise ValueError('NAVER_CLIENT_ID 및 NAVER_CLIENT_SECRET 설정이 필요합니다.')
    getter = request_get or requests.get
    now = datetime.now(timezone.utc)
    response = getter(NAVER_NEWS_ENDPOINT,
                      headers={'X-Naver-Client-Id': client_id,
                               'X-Naver-Client-Secret': client_secret},
                      params={'query': str(query)[:100], 'display': min(max(1, display), 100),
                              'start': 1, 'sort': 'date'}, timeout=12)
    response.raise_for_status()
    items = response.json().get('items', [])
    rows = []
    for a in items:
        rows.append({'stock_code': stock_code, 'title': a.get('title', ''),
                     'description': a.get('description', ''),
                     'publisher': urlparse(a.get('originallink') or a.get('link') or '').netloc,
                     'published_at': a.get('pubDate', ''),
                     'first_seen_at': now.isoformat(), 'collected_at': now.isoformat(),
                     'source_url': a.get('originallink') or a.get('link') or '',
                     'source_type': '뉴스', 'synthetic': False})
    return normalize_articles(pd.DataFrame(rows))


def read_news_csv(content: bytes, *, synthetic: bool = False) -> pd.DataFrame:
    for enc in ('utf-8-sig', 'cp949', 'utf-8'):
        try:
            return normalize_articles(pd.read_csv(BytesIO(content), encoding=enc), synthetic=synthetic)
        except UnicodeDecodeError:
            continue
    raise ValueError('UTF-8 또는 CP949 인코딩의 CSV만 지원합니다.')


def availability_ready(df: pd.DataFrame) -> bool:
    """True only when every article has first_seen_at provenance."""
    return bool(df is not None and not df.empty and df['first_seen_at'].notna().all())
