"""MARKET PULSE's presentation-only UI components.

All numeric displays derive from actual user/API frames. Company badges are
locally drawn *identification icons*, NOT official corporate trademarks.
HTML content is escaped before rendering. No remote image dependency.
"""
from __future__ import annotations
import base64
from functools import lru_cache
from html import escape
from pathlib import Path
import math
from typing import Mapping

import pandas as pd

from market_data import price_snapshot

ASSETS = Path(__file__).resolve().parent / 'assets' / 'company_icons'
COMPANY_CODES = {
    '삼성전자': '005930', 'SK하이닉스': '000660', '현대자동차': '005380',
    '기아': '000270', 'NAVER': '035420', '카카오': '035720',
}
MAIN_COLUMNS = ('종목', '최근 종가', '전일 대비', '등락률', '거래량', '52주 최고', '52주 최저', '기준일')


def _numeric(number: object, decimals: int = 0) -> str:
    try:
        value = float(number)
        if not math.isfinite(value):
            return '—'
        return f'{value:,.{decimals}f}'
    except (ValueError, TypeError):
        return '—'


def _sign(number: object, decimals: int = 2) -> str:
    try:
        value = float(number)
        return f'{value:+,.{decimals}f}' if math.isfinite(value) else '—'
    except (ValueError, TypeError):
        return '—'


def _direction(value: float) -> str:
    if value > 0:
        return 'up'
    if value < 0:
        return 'down'
    return 'flat'


def sparkline_svg(close: pd.Series, gain: float, width: int = 124, height: int = 39) -> str:
    """A tiny actual-data graph. No seeded, fabricated, or interpolated quotes."""
    values = pd.to_numeric(close, errors='coerce').dropna().tail(44)
    if len(values) < 2:
        return '<span class="mp-muted">기록 없음</span>'
    bottom = float(values.min())
    top = float(values.max())
    span = max(top - bottom, abs(top) * 1e-7, 1e-7)
    points = [
        (3 + j * (width - 6) / (len(values) - 1), 4 + (top - float(v)) / span * (height - 8))
        for j, v in enumerate(values)
    ]
    coords = ' '.join(f'{x:.1f},{y:.1f}' for x, y in points)
    color = '#e34e56' if gain > 0 else ('#3375ce' if gain < 0 else '#9aa4b2')
    return (f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            f'aria-label="최근 {len(values)}거래일 실제 종가 추이" role="img">'
            f'<polyline fill="none" stroke="{color}" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round" points="{coords}" /></svg>')


@lru_cache(maxsize=30)
def icon_html(name: str, code: str = '') -> str:
    # Only local badges from this repository; none are represented as official logos.
    symbol = code if code in COMPANY_CODES.values() else COMPANY_CODES.get(name, '')
    f = ASSETS / f'{symbol}.png' if symbol else None
    safe_name = escape(name, quote=True)
    if f is not None and f.is_file():
        payload = base64.b64encode(f.read_bytes()).decode('ascii')
        return f'<img class="mp-company-icon" src="data:image/png;base64,{payload}" alt="{safe_name} 구분 아이콘" />'
    abbrev = ''.join(ch for ch in name if ch.isalnum())[:2] or '?'
    return f'<span class="mp-company-icon mp-icon-fallback" aria-label="{safe_name} 구분 아이콘">{escape(abbrev)}</span>'


def make_rows(frames: Mapping[str, pd.DataFrame], metas: Mapping[str, dict],
              codes: Mapping[str, str] | None = None) -> list[dict]:
    """Only calculate rows for real supplied frames; never generate values."""
    codes = codes or {}
    rows: list[dict] = []
    for name, frame in frames.items():
        if frame is None or frame.empty:
            continue
        s = price_snapshot(frame)
        rows.append({
            'name': name, 'code': codes.get(name, COMPANY_CODES.get(name, '')),
            'close': s['close'], 'change': s['change'], 'pct': s['change_pct'],
            'volume': s['volume'], 'high52': s['high_52w'], 'low52': s['low_52w'],
            'trading_day': s['last_trade_date'],
            'source': metas.get(name, {}).get('source', '출처 확인 필요'),
            'status': metas.get(name, {}).get('status', 'unknown'),
            'spark': sparkline_svg(frame['Close'], s['change_pct']),
        })
    return rows


def order_rows(rows: list[dict], sort_by: str) -> list[dict]:
    rules = {
        '거래량순': lambda r: (-r['volume'], r['name']),
        '상승률순': lambda r: (-r['pct'], r['name']),
        '하락률순': lambda r: (r['pct'], r['name']),
        '종목명순': lambda r: r['name'],
    }
    return sorted(rows, key=rules.get(sort_by, rules['거래량순']))


def market_table_html(rows: list[dict], show_spark: bool = True) -> str:
    """Readable securities-style table; no click handlers or fabricated data."""
    head = ('<div class="mp-table-wrap"><table class="mp-market-table"><thead><tr>'
            '<th class="mp-center">순위</th><th>종목명</th><th>최근 종가</th>'
            '<th>전일 대비</th><th>등락률</th><th>거래량</th>')
    if show_spark:
        head += '<th class="mp-center">최근 주가 흐름</th>'
    head += '<th>52주 최고</th><th>52주 최저</th><th>거래 기준일</th></tr></thead><tbody>'
    table_rows: list[str] = []
    for i, row in enumerate(rows, 1):
        move = _direction(row['pct'])
        icon = icon_html(row['name'], row['code'])
        name = escape(str(row['name']))
        code = escape(str(row['code']))
        status = row['status']
        tag = '<span class="mp-old-data">저장 데이터</span>' if status == 'cached' else ''
        part = (
            f'<tr><td class="mp-center mp-rank">{i}</td>'
            f'<td><div class="mp-company">{icon}<div><div class="mp-name">{name} {tag}</div>'
            f'<div class="mp-code">{code or "CSV 입력"}</div></div></div></td>'
            f'<td class="mp-strong">{_numeric(row["close"])}<span class="mp-unit">원</span></td>'
            f'<td class="mp-{move}">{_sign(row["change"], 0)}<span class="mp-unit">원</span></td>'
            f'<td class="mp-{move} mp-strong">{_sign(row["pct"])}%</td>'
            f'<td>{_numeric(row["volume"])}<span class="mp-unit">주</span></td>'
        )
        if show_spark:
            part += f'<td class="mp-center">{row["spark"]}</td>'
        part += (
            f'<td>{_numeric(row["high52"])}<span class="mp-unit">원</span></td>'
            f'<td>{_numeric(row["low52"])}<span class="mp-unit">원</span></td>'
            f'<td class="mp-day">{escape(str(row["trading_day"]))}</td></tr>'
        )
        table_rows.append(part)
    if not table_rows:
        table_rows.append('<tr><td colspan="10" class="mp-empty">조회한 데이터가 없습니다.</td></tr>')
    return head + ''.join(table_rows) + '</tbody></table></div>'


def watch_card_html(row: dict) -> str:
    direction = _direction(row['pct'])
    last_day = escape(str(row['trading_day']))
    return (
        f'<div class="mp-watch">'
        f'<div class="mp-watch-top">{icon_html(row["name"], row["code"])}'
        f'<div><div class="mp-watch-name">{escape(str(row["name"]))}</div>'
        f'<div class="mp-code">{escape(str(row["code"]))} · {last_day} 종가</div></div></div>'
        f'<div class="mp-watch-prices"><div class="mp-watch-price">{_numeric(row["close"])}<small>원</small></div>'
        f'<div class="mp-watch-change mp-{direction}">{_sign(row["pct"])}%</div></div>'
        f'<div class="mp-watch-spark">{row["spark"]}</div>'
        f'<div class="mp-watch-foot">거래량 <strong>{_numeric(row["volume"])}주</strong></div></div>'
    )


def css() -> str:
    return '''
<style>
/* Only MARKET PULSE namespaced classes are used for custom content. */
.mp-market-title{font-weight:800;font-size:1.35rem;letter-spacing:-.03em;margin:14px 0 12px;color:#142232}
.mp-section-sub{color:#69778b;font-size:.86rem;margin:-5px 0 14px}
.mp-table-wrap{background:#fff;border:1px solid #e7ebf2;border-radius:16px;overflow-x:auto;box-shadow:0 8px 25px rgba(26,42,60,.04);width:100%;margin:10px 0 18px}
.mp-market-table{border-collapse:separate;border-spacing:0;width:100%;min-width:1050px;font-family:inherit;color:#192536;font-size:.89rem}
.mp-market-table thead th{text-align:right;background:#f8fafc;color:#738194;font-weight:650;padding:13px 13px;border-bottom:1px solid #e9eef4;white-space:nowrap}
.mp-market-table thead th:nth-child(2){text-align:left}
.mp-market-table tbody td{padding:13px;border-bottom:1px solid #eff2f6;text-align:right;vertical-align:middle;white-space:nowrap}
.mp-market-table tbody td:nth-child(2){text-align:left}
.mp-market-table tbody tr:hover{background:#f7fbff}
.mp-market-table tbody tr:last-child td{border-bottom:none}
.mp-center{text-align:center!important}.mp-rank{font-weight:750;color:#65728a}
.mp-company{display:flex;align-items:center;gap:12px;min-width:168px}
.mp-company-icon{width:37px;height:37px;object-fit:contain;flex-shrink:0;border-radius:12px;background:#e9eff8}
.mp-icon-fallback{display:inline-flex;align-items:center;justify-content:center;background:#e6edf8;color:#235f8e;font-weight:800;font-size:.81rem}
.mp-name{font-weight:760;color:#17283b;white-space:normal}.mp-code{font-size:.77rem;color:#8792a0;margin-top:1px}
.mp-strong{font-weight:800}.mp-unit{font-size:.78rem;color:#8a95a4;margin-left:2px;font-weight:400}
.mp-up{color:#e44c55;font-weight:780}.mp-down{color:#2c74d7;font-weight:780}.mp-flat{color:#687b89;font-weight:780}
.mp-day{font-size:.78rem;color:#7c8a9a}.mp-old-data{font-size:.68rem;font-weight:700;color:#9a6e17;background:#fff5d7;border-radius:6px;padding:2px 5px;margin-left:3px}
.mp-empty{text-align:center!important;color:#798697;padding:25px!important}
.mp-watch{background:white;border:1px solid #e7ebf2;border-radius:17px;padding:17px 19px;box-shadow:0 7px 22px rgba(26,42,60,.04);margin:6px 0 12px}
.mp-watch-top{display:flex;align-items:center;gap:9px}.mp-watch-name{font-size:.99rem;font-weight:800;color:#182638}
.mp-watch-prices{display:flex;align-items:baseline;justify-content:space-between;gap:6px;margin-top:14px}
.mp-watch-price{font-size:1.43rem;font-weight:850;letter-spacing:-.03em;color:#162637}
.mp-watch-price small{font-size:.85rem;margin-left:3px;font-weight:500;color:#7b8ba0}
.mp-watch-change{font-size:1rem}.mp-watch-spark{height:47px;display:flex;align-items:center;justify-content:flex-end;margin-top:8px}
.mp-watch-spark svg{width:100%;height:44px;max-height:44px}
.mp-watch-foot{display:flex;justify-content:space-between;border-top:1px solid #f1f3f6;padding-top:10px;margin-top:7px;font-size:.8rem;color:#7e8a9a}
.mp-watch-foot strong{color:#4a5769}.mp-muted{color:#8b96a6;font-size:.77rem}
@media(max-width:1000px){.mp-market-table{font-size:.81rem;min-width:980px}.mp-watch{padding:13px}.mp-company{min-width:140px;gap:8px}.mp-company-icon{width:33px;height:33px}}
</style>
'''
