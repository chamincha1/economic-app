"""MARKET PULSE configuration and UI-safe key discovery.

Never commit secrets or put raw credentials in cache/exports. Streamlit secrets
and process environment are both supported, with environment taking precedence.
"""
from __future__ import annotations
import os
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_CACHE = ROOT / 'data_cache'
NEWS_CACHE = ROOT / 'news_cache'
MODEL_DIR = ROOT / 'models'
TODAY = date.today()
DEFAULT_START = TODAY - timedelta(days=365 * 3)
DEFAULT_END = TODAY
NEWS_LIMIT = 40
from stock_catalog import STOCKS, STOCK_SECTORS, DEFAULT_SELECTED
INDICES = {'KOSPI': 'KS11', 'KOSDAQ': 'KQ11'}


def get_secret(key: str) -> str:
    """Return secret without reading/loading Streamlit in offline unit tests."""
    if os.environ.get(key):
        return os.environ[key]
    try:
        import streamlit as st
        return str(st.secrets.get(key, ''))
    except Exception:
        return ''


def secret_status() -> dict[str, bool]:
    return {k: bool(get_secret(k)) for k in
            ('NAVER_CLIENT_ID', 'NAVER_CLIENT_SECRET', 'DART_API_KEY', 'KIS_APP_KEY', 'KIS_APP_SECRET', 'XAI_API_KEY')}
