"""Durable real-news metadata cache, preserving earliest observed timestamp.

No synthetic articles or full-text scraping. A local cache is ephemeral on some
hosted platforms; the UI explicitly labels it as a saved collection snapshot.
"""
from __future__ import annotations
import json
import os
import re
import tempfile
from pathlib import Path
import pandas as pd
from config import NEWS_CACHE
from news_collector import normalize_articles


def _path(code: str, directory: Path | str = NEWS_CACHE) -> Path:
    if not re.fullmatch(r'\d{6}', str(code)):
        raise ValueError('뉴스 캐시에는 유효한 6자리 종목코드가 필요합니다.')
    return Path(directory) / f'{code}.json'


def load_news(code: str, directory: Path | str = NEWS_CACHE) -> pd.DataFrame:
    path = _path(code, directory)
    if not path.is_file():
        return normalize_articles(pd.DataFrame())
    try:
        rows = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(rows, list):
            return normalize_articles(pd.DataFrame())
        return normalize_articles(pd.DataFrame(rows))
    except (OSError, ValueError, TypeError, KeyError):
        return normalize_articles(pd.DataFrame())


def merge_news(code: str, fresh: pd.DataFrame, directory: Path | str = NEWS_CACHE,
               max_articles: int = 400) -> pd.DataFrame:
    """Keep oldest first_seen_at on re-fetch and preserve previous cached articles."""
    old = load_news(code, directory)
    incoming = normalize_articles(fresh)
    if incoming.empty:
        return old
    # Do not persist synthetic news or articles mapped to a different stock.
    incoming = incoming[~incoming['synthetic'] & incoming['stock_code'].astype(str).eq(code)].copy()
    if incoming.empty:
        return old
    combined = pd.concat([old, incoming], ignore_index=True) if not old.empty else incoming.copy()
    # Article id is stable from URL/title; earliest first_seen must survive refresh.
    combined = combined.sort_values('first_seen_at', na_position='last', kind='stable')
    combined = combined.drop_duplicates('article_id', keep='first')
    combined = normalize_articles(combined).head(max_articles)
    path = _path(code, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = combined.copy()
    for col in ('published_at', 'first_seen_at', 'collected_at'):
        payload[col] = payload[col].map(lambda x: x.isoformat() if pd.notna(x) else '')
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                         delete=False, suffix='.tmp') as tmp:
            tmp_path = Path(tmp.name)
            json.dump(payload.to_dict('records'), tmp, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()
    return combined
