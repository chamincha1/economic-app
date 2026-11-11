"""OpenDART public filing search; requires an official API key.

A DART corporation code (8 digits) is not a stock ticker (6 digits).
Filing date without known publication time is conservatively treated as
23:59 KST for feature availability, not assumed known at market close.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from io import BytesIO
from zipfile import ZipFile
import xml.etree.ElementTree as ET
import pandas as pd
import requests
from config import get_secret

KST = timezone(timedelta(hours=9))
DART_BASE = 'https://opendart.fss.or.kr/api'


def fetch_corp_mapping(key: str | None = None, requester=None) -> pd.DataFrame:
    token = key or get_secret('DART_API_KEY')
    if not token:
        raise ValueError('DART_API_KEY가 설정되지 않았습니다.')
    getter = requester or requests.get
    res = getter(f'{DART_BASE}/corpCode.xml', params={'crtfc_key': token}, timeout=25)
    res.raise_for_status()
    with ZipFile(BytesIO(res.content)) as z:
        xml_name = next((n for n in z.namelist() if n.lower().endswith('.xml')), None)
        if not xml_name:
            raise ValueError('DART 기업코드 ZIP에 XML이 없습니다.')
        root = ET.fromstring(z.read(xml_name))
    rows = []
    for item in root.findall('list'):
        stock = (item.findtext('stock_code') or '').strip()
        if len(stock) == 6 and stock.isdigit():
            rows.append({'stock_code': stock, 'corp_code': (item.findtext('corp_code') or '').strip(),
                         'corp_name': (item.findtext('corp_name') or '').strip()})
    return pd.DataFrame(rows).drop_duplicates('stock_code')


def fetch_disclosures(stock_code: str, start: str, end: str, *,
                      key: str | None = None, requester=None,
                      mapping: pd.DataFrame | None = None) -> pd.DataFrame:
    token = key or get_secret('DART_API_KEY')
    if not token:
        raise ValueError('DART_API_KEY가 설정되지 않았습니다.')
    getter = requester or requests.get
    mapping = mapping if mapping is not None else fetch_corp_mapping(token, requester=getter)
    match = mapping[mapping['stock_code'] == stock_code]
    if match.empty:
        raise ValueError('종목코드에 대응되는 DART corp_code를 찾을 수 없습니다.')
    corp_code = str(match.iloc[0]['corp_code'])
    res = getter(f'{DART_BASE}/list.json', params={
        'crtfc_key': token, 'corp_code': corp_code,
        'bgn_de': pd.Timestamp(start).strftime('%Y%m%d'),
        'end_de': pd.Timestamp(end).strftime('%Y%m%d'), 'page_count': 100}, timeout=15)
    res.raise_for_status()
    payload = res.json()
    if payload.get('status') == '013':  # no data
        return pd.DataFrame()
    if payload.get('status') != '000':
        raise ValueError(f"DART 응답 오류: {payload.get('status')}: {payload.get('message')}")
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for r in payload.get('list', []):
        receipt = ''.join(c for c in str(r.get('rcept_no', '')) if c.isdigit())
        day = pd.to_datetime(r.get('rcept_dt'), format='%Y%m%d', errors='coerce')
        if pd.isna(day):
            continue
        # No clock time in list.json; *not* asserted to be public at 15:30.
        publication = day.strftime('%Y-%m-%d') + 'T23:59:00+09:00'
        rows.append({'stock_code': stock_code, 'title': r.get('report_nm', ''),
                     'description': '', 'publisher': '금융감독원 OpenDART',
                     'published_at': publication, 'first_seen_at': now, 'collected_at': now,
                     'source_url': f'https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}',
                     'source_type': '공시', 'synthetic': False})
    from news_collector import normalize_articles
    return normalize_articles(pd.DataFrame(rows))
