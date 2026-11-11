"""UI-specific tests. All price values below are synthetic test fixtures only.
They are not displayed as real market data and are not packaged as demo CSVs.
"""
from pathlib import Path
import pandas as pd
import pytest
from market_ui import make_rows, order_rows, market_table_html, watch_card_html, sparkline_svg, icon_html, ASSETS


def fake_prices(last_price=104., volume=1200):
    n=35
    return pd.DataFrame({
        'Date': pd.bdate_range('2026-01-01', periods=n),
        'Open': [100.]*(n-1)+[last_price-1],
        'High': [101.]*(n-1)+[last_price+1],
        'Low': [99.]*(n-1)+[last_price-2],
        'Close': [100.]*(n-1)+[last_price],
        'Volume': [800]*(n-1)+[volume],
    })


def test_ui_only_uses_input_frames():
    rows=make_rows({'삼성전자':fake_prices(104,2200)},
                   {'삼성전자': {'source':'test-not-live','status':'cached'}},
                   {'삼성전자':'005930'})
    assert len(rows)==1
    assert rows[0]['close']==104
    assert rows[0]['volume']==2200
    assert rows[0]['pct']==pytest.approx(4.0)
    assert rows[0]['status']=='cached'
    assert rows[0]['trading_day']=='2026-02-18'


def test_sorting_and_empty_rows():
    frames={'A':fake_prices(110,400),'B':fake_prices(90,1200)}
    rows=make_rows(frames,{})
    assert [r['name'] for r in order_rows(rows,'거래량순')]==['B','A']
    assert [r['name'] for r in order_rows(rows,'상승률순')]==['A','B']
    assert [r['name'] for r in order_rows(rows,'하락률순')]==['B','A']
    assert make_rows({}, {}) == []


def test_html_escaping_and_source_badges():
    frames={'<b>위험</b>':fake_prices()}
    rows=make_rows(frames,{})
    markup=market_table_html(rows)
    assert '<b>위험</b>' not in markup
    assert '&lt;b&gt;위험&lt;/b&gt;' in markup
    assert 'data:image/png;base64' not in markup  # unknown stock = fallback
    assert '<table' in markup and '52주 최고' in markup
    assert '최근 종가' in markup
    assert 'data:image/png;base64' in icon_html('삼성전자','005930')


def test_data_based_sparkline_and_card():
    row=make_rows({'삼성전자':fake_prices()}, {})[0]
    assert '<svg' in sparkline_svg(fake_prices()['Close'], 4.0)
    assert '104' in watch_card_html(row)
    assert '<svg' in row['spark']
    assert '기록 없음' in sparkline_svg(pd.Series([1]), 0.)


def test_six_local_company_icons_exist():
    codes=['005930','000660','005380','000270','035420','035720']
    assert all((ASSETS/(code+'.png')).is_file() for code in codes)
