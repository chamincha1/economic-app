"""MARKET PULSE · Educational domestic stock analytics, news and ML lab.

Run with: python -m streamlit run app.py
All displayed charts use verified online or explicitly unverified user-input historical data.
The current predictor is an exploratory probability classifier, not advice.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
import io
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from config import (STOCKS, INDICES, TODAY, DEFAULT_START,
                    DEFAULT_END, get_secret, secret_status)
from stock_core import (StockDataError, read_csv_bytes,
                        calculate_indicators, trim_period, common_date_align,
                        event_table, summarize)
from market_data import (fetch_historical, list_domestic_stocks, price_snapshot,
                         MarketResult)
from kis_market import KISReadOnlyClient, fetch_kis_historical, kis_credentials_ready, fetch_kis_trade_volume
from technical_indicators import add_indicators
from news_collector import (fetch_naver_news, read_news_csv, normalize_articles)
from news_analyzer import analyze_articles
from disclosure_collector import fetch_disclosures
from prediction_model import run_experiments
from backtesting import walkforward_scores
from model_explainer import describe_logistic_model
from market_calendar import is_krx_holiday

APP_TITLE = 'MARKET PULSE | 국내 주식 · 뉴스 · AI 데이터 분석'
DARK = '#091120'
PANEL = '#111d31'
BLUE = '#75adff'
CYAN = '#49d8c5'
RED = '#ff7287'
GOLD = '#ffd47b'
TEXT = '#edf3ff'

st.set_page_config(page_title=APP_TITLE, page_icon='📊', layout='wide',
                   initial_sidebar_state='expanded')
st.markdown('''
<style>
.stApp {background:#091120; color:#edf3ff;}
[data-testid="stSidebar"] {background:#111d31; border-right:1px solid #283950;}
[data-testid="stMetric"] {background:#142239;border:1px solid #28405e;border-radius:15px;padding:16px;}
[data-testid="stTabs"] button {font-weight:650;}
.block-container {max-width:1650px; padding-top:1.3rem;}
.mp-hero {border-radius:19px;padding:25px 30px;margin-bottom:18px;
  background:linear-gradient(115deg,#16375f,#142339 53%,#102b38);
  border:1px solid #315277;}
.mp-title {font-weight:850;font-size:2rem;letter-spacing:-.04em;color:#f7fbff;}
.mp-sub {color:#b9cbe1;font-size:.95rem;margin-top:5px;}
.mp-chip {display:inline-block;border-radius:25px;padding:4px 11px;background:#274567;
  color:#c4e2ff;font-size:.76rem;margin-top:14px;}
.stButton > button {border-radius:11px;}
</style>
''', unsafe_allow_html=True)
st.markdown('''<div class="mp-hero"><div style="color:#8fd2ff;font-size:.78rem;letter-spacing:.1em;font-weight:750">KOREA STOCK MARKET · DATA INTELLIGENCE</div>
<div class="mp-title">MARKET PULSE <span style="color:#7cb3ff">/</span> 금융 데이터 연구소</div>
<div class="mp-sub">일별 시세 · 캔들/거래량 · 기술적 지표 · 이상 변동 · 금융 뉴스/공시 · 다음 거래일 확률 모델</div>
<div class="mp-chip">교육용 분석 플랫폼 · 실시간 시세 / 매매 추천 / 예측 보장 없음</div></div>''',
            unsafe_allow_html=True)


def csv_bytes(df: pd.DataFrame) -> bytes:
    result = df.copy()
    for column in result.columns:
        if pd.api.types.is_datetime64_any_dtype(result[column]):
            result[column] = result[column].astype(str)
    return result.to_csv(index=False).encode('utf-8-sig')


def theme_plot(fig: go.Figure, height: int = 400) -> go.Figure:
    fig.update_layout(template='plotly_dark', height=height, paper_bgcolor=PANEL,
                      plot_bgcolor=PANEL, font=dict(color=TEXT, family='Arial'),
                      margin=dict(l=24, r=24, b=28, t=50),
                      hovermode='x unified',
                      legend=dict(orientation='h', x=0, y=1.11))
    fig.update_xaxes(gridcolor='#263850', showline=False)
    fig.update_yaxes(gridcolor='#263850', zerolinecolor='#263850')
    return fig


def candlestick_chart(raw: pd.DataFrame, analyzed: pd.DataFrame, name: str) -> go.Figure:
    df = add_indicators(raw)
    cutoff = pd.to_datetime(analyzed['Date']).min()
    df = df[df['Date'] >= cutoff].copy()
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=.07,
                        row_heights=[.59, .23, .18],
                        subplot_titles=('가격 및 이동평균(원)', '거래량(주)', 'RSI(14)'))
    if {'Open', 'High', 'Low'}.issubset(df.columns) and df[['Open','High','Low','Close']].notna().all().all():
        fig.add_trace(go.Candlestick(x=df['Date'], open=df['Open'], high=df['High'],
                      low=df['Low'], close=df['Close'], name='일별 캔들',
                      increasing_line_color=RED, decreasing_line_color=BLUE), row=1, col=1)
    else:
        fig.add_trace(go.Scatter(x=df['Date'], y=df['Close'], mode='lines',
                      line=dict(color=BLUE, width=2), name='종가'), row=1, col=1)
    for key, color in [('SMA_5', GOLD), ('SMA_20', CYAN), ('SMA_60', '#a99aff')]:
        if df[key].notna().any():
            fig.add_trace(go.Scatter(x=df['Date'], y=df[key], name=key.replace('_', ' '),
                                     line=dict(width=1.6, color=color)), row=1, col=1)
    jumps = analyzed.loc[analyzed['PriceJump']]
    if not jumps.empty:
        fig.add_trace(go.Scatter(x=jumps['Date'], y=jumps['Close'], mode='markers',
                                 name='기존 가격 급변', marker=dict(color='#ffdf92',
                                 size=9, symbol='diamond')), row=1, col=1)
    bar_colors = np.where(df['Close'] >= df['Close'].shift(1), '#f17587', '#77adf7')
    fig.add_trace(go.Bar(x=df['Date'], y=df['Volume'], marker_color=bar_colors,
                         name='거래량', showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=df['Date'], y=df['Volume_SMA20'], name='평균 거래량(20)',
                             line=dict(color=GOLD, width=1.5)), row=2, col=1)
    fig.add_trace(go.Scatter(x=df['Date'], y=df['RSI_14'], name='RSI 14',
                             line=dict(color=CYAN, width=1.7)), row=3, col=1)
    fig.add_hline(y=70, row=3, col=1, line_dash='dot', line_color='#9daec7', opacity=.5)
    fig.add_hline(y=30, row=3, col=1, line_dash='dot', line_color='#9daec7', opacity=.5)
    fig.update_yaxes(title_text='원', row=1, col=1)
    fig.update_yaxes(title_text='주', row=2, col=1)
    fig.update_yaxes(title_text='RSI', range=[0,100], row=3, col=1)
    fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
    fig.update_layout(title=f'{name} · 과거 OHLCV / 변동 분석')
    return theme_plot(fig, 740)


def normalized_price_chart(results: dict[str, pd.DataFrame]) -> go.Figure:
    fig = go.Figure()
    colors = [BLUE, CYAN, GOLD, '#aa94ff', RED, '#9be1a4']
    for i, (name, df) in enumerate(results.items()):
        series = df['Close'] / df['Close'].iloc[0] * 100
        fig.add_trace(go.Scatter(x=df['Date'], y=series, mode='lines', name=name,
                                 line=dict(color=colors[i % len(colors)], width=2)))
    fig.update_layout(title='시작일=100 · 종목별 가격 변화 비교', yaxis_title='지수화된 종가')
    return theme_plot(fig, 405)


def bar_comparison(summary: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Bar(x=summary['종목'], y=summary['평균 일일변동성(%)'],
                           marker_color=([BLUE, CYAN, GOLD, '#9e9aff', RED, '#82ddad'] * (1 + len(summary)//6))[:len(summary)],
                           text=summary['평균 일일변동성(%)'].round(2), textposition='outside'))
    fig.update_layout(title='종목별 평균 20일 변동성', yaxis_title='수익률 표준편차 (%포인트)')
    return theme_plot(fig, 405)


def volatility_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Scatter(x=df['Date'], y=df['Volatility'], mode='lines',
                              fill='tozeroy', line=dict(color=CYAN, width=2),
                              name='설정 기간 변동성'))
    fig.update_layout(title='변동성 추이 · 연율화하지 않은 일일 수익률 표준편차',
                      yaxis_title='%포인트')
    return theme_plot(fig, 280)


def prediction_reliability_chart(predictions: pd.DataFrame) -> go.Figure:
    x = predictions.copy()
    x['bin'] = pd.cut(x['ProbabilityUp'], bins=np.linspace(0, 1, 6),
                      include_lowest=True)
    grouped = x.groupby('bin', observed=False).agg(
        predicted=('ProbabilityUp','mean'), actual=('ActualUp', 'mean'),
        count=('ActualUp','size')).dropna().reset_index()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[0,1], y=[0,1], line=dict(dash='dash', color='#8599b4'),
                             name='완전 보정 기준'))
    fig.add_trace(go.Scatter(x=grouped['predicted'], y=grouped['actual'], mode='markers+lines',
                             marker=dict(color=CYAN, size=np.maximum(9, grouped['count']*0.6)),
                             name='실제 비율'))
    fig.update_layout(title='확률 보정 참고 그래프 (표본이 적으면 불안정)',
                      xaxis_title='평균 추정 확률', yaxis_title='실제 상승 비율',
                      xaxis=dict(range=[0,1]), yaxis=dict(range=[0,1]))
    return theme_plot(fig, 340)


@st.cache_data(ttl=3600, show_spinner=False)
def get_online(code: str, start: date, end: date, backend: str = 'fdr') -> MarketResult:
    if code in INDICES.values() or backend == 'fdr':
        return fetch_historical(code, start, end, index=code in INDICES.values())
    if backend == 'kis':
        return fetch_kis_historical(code, start, end)
    raise StockDataError('인식할 수 없는 시세 데이터 제공처입니다.')


@st.cache_data(ttl=1800, show_spinner=False)
def get_krx_listing() -> pd.DataFrame:
    return list_domestic_stocks()


def with_provenance(frame: pd.DataFrame, metas: dict[str, dict],
                    selected: str | None = None) -> pd.DataFrame:
    """Include dataset provenance in every exported analysis/ML CSV."""
    output = frame.copy()
    if '종목' in output.columns:
        names = output['종목'].astype(str)
        output['데이터상태'] = names.map(lambda n: metas.get(n, {}).get('status', 'unknown'))
        output['원출처'] = names.map(lambda n: metas.get(n, {}).get('source', 'unknown'))
        output['마지막거래일'] = names.map(lambda n: metas.get(n, {}).get('last_trade_date', ''))
    elif selected is not None:
        meta = metas.get(selected, {})
        output['데이터상태'] = meta.get('status', 'unknown')
        output['원출처'] = meta.get('source', 'unknown')
        output['마지막거래일'] = meta.get('last_trade_date', '')
    return output


def source_caption(name: str, meta: dict) -> str:
    state = meta.get('status', '알 수 없음')
    state_text = {'fresh': '온라인 조회 성공', 'cached': '이전 캐시(최신 아님)',
                  'uploaded': '사용자 업로드', 'imported': '직접 등록(진위 미확인)'}.get(state, state)
    return (f"{name} · {state_text} · 제공처: {meta.get('source', '미상')} · "
            f"마지막 거래일: {meta.get('last_trade_date', '미상')} · "
            f"수집 시각: {meta.get('retrieved_at', '확인 불가')}")


# ---------------------------- Controls -----------------------------------
with st.sidebar:
    st.header('⚙️ 데이터 및 분석 설정')
    mode = st.radio('데이터 출처', ['국내 주식 실데이터', 'CSV 직접 업로드'],
                    help='실데이터는 인터넷이 필요하며 모두 과거 일별 데이터입니다.')
    start = st.date_input('분석 시작일', value=DEFAULT_START, format='YYYY-MM-DD')
    end = st.date_input('분석 종료일', value=DEFAULT_END, format='YYYY-MM-DD')
    win = st.slider('과거 비교 기간(거래일)', 10, 60, 20, 5)
    z_limit = st.slider('가격 급변 Z 기준', 1.5, 4.0, 2.5, .5)
    vol_limit = st.slider('거래량 급증 배율', 1.2, 3.0, 1.5, .1)
    st.divider()
    selection: dict[str, str] = {}
    uploads = []
    backend = 'fdr'
    if mode == '국내 주식 실데이터':
        backend = st.radio('과거 일별 시세 제공처', ['fdr', 'kis'],
            format_func=lambda s: 'FinanceDataReader (NAVER → KRX)' if s == 'fdr' else 'KIS Open API (조회 전용)',
            help='KIS는 본인 명의의 적법한 앱키가 설정되어 있어야 하며 데이터를 다른 캐시 폴더에 저장합니다.')
        if backend == 'kis' and not kis_credentials_ready():
            st.warning('KIS 인증키가 설정되어 있지 않습니다. KIS를 이용할 수 없다면 FinanceDataReader를 선택하세요.')
        chosen = st.multiselect('기본 분석 기업', list(STOCKS), default=['삼성전자'], max_selections=6)
        selection.update({name: STOCKS[name] for name in chosen})
        typed_code = st.text_input('추가 종목코드(6자리)', placeholder='예: 005930')
        if typed_code:
            if len(typed_code) == 6 and typed_code.isdigit():
                if typed_code not in selection.values():
                    selection[f'종목 {typed_code}'] = typed_code
            else:
                st.warning('6자리 숫자 종목코드를 입력하세요.')
        if st.button('🔎 KRX 전체 종목 목록 검색', use_container_width=True):
            try:
                with st.spinner('KRX 종목 목록을 조회합니다...'):
                    st.session_state['krx_listing'] = get_krx_listing()
            except Exception as exc:
                st.warning(f'상장 목록 조회 실패: {type(exc).__name__}')
        if 'krx_listing' in st.session_state:
            catalog = st.session_state['krx_listing']
            q = st.text_input('기업명으로 검색', placeholder='회사명 또는 종목코드 일부')
            if q:
                matching = catalog[catalog['Name'].str.contains(q, regex=False, case=False, na=False) |
                                   catalog['Code'].str.contains(q, regex=False, na=False)].head(60)
                if not matching.empty:
                    options = {f"{r.Name} ({r.Code})": (r.Name, r.Code) for r in matching.itertuples()}
                    option = st.selectbox('검색 결과', list(options))
                    if st.button('검색 종목 분석에 추가'):
                        st.session_state['extra_stock'] = options[option]
            if 'extra_stock' in st.session_state:
                nm, co = st.session_state['extra_stock']
                selection[nm] = co
        if st.button('↻ 가격 캐시 조회 재시도', use_container_width=True):
            get_online.clear()
            st.rerun()
    else:
        uploads = st.file_uploader('주식 CSV 파일(다중 선택)', type='csv', accept_multiple_files=True)
        st.caption('Date, Close, Volume 필수. Open/High/Low 선택. UTF-8/CP949 가능.')
    st.divider()
    st.caption('실제 시세 수집과 뉴스 API 연결에는 인터넷이 필요합니다.')
    st.caption('인터넷이 없으면 실제 출처를 확인한 CSV를 직접 업로드하세요.')

if start > end:
    st.error('분석 시작일이 종료일보다 늦습니다.')
    st.stop()
if is_krx_holiday(end):
    st.caption('참고: 종료일은 제공된 FinanceDataReader KRX 휴장일 참고 목록에 있습니다. 휴장일 목록은 갱신이 필요할 수 있으며 실제 거래일 확인은 시세 데이터 기준입니다.')

raw_data: dict[str, pd.DataFrame] = {}
source_meta: dict[str, dict] = {}
load_errors: list[str] = []
if mode == '국내 주식 실데이터':
    st.info('🌐 인터넷으로 **과거 일별 시세**를 수집합니다. 실시간 체결가가 아닙니다.')
    for name, code in selection.items():
        try:
            with st.spinner(f'{name} 일별 가격을 확인합니다...'):
                result = get_online(code, start, end, backend)
            raw_data[name] = result.frame
            source_meta[name] = result.meta
            if result.is_cached:
                st.warning(f"{name}: 온라인 수집 실패, 이전 저장 데이터를 사용합니다. "
                           f"마지막 거래일 {result.meta.get('last_trade_date', '미상')}")
        except Exception as exc:
            load_errors.append(f'{name}: {exc}')
if mode == 'CSV 직접 업로드':
    for upload in uploads or []:
        name = Path(upload.name).stem
        suffix = 2
        original = name
        while name in raw_data:
            name = f'{original} ({suffix})'
            suffix += 1
        try:
            df = read_csv_bytes(upload.getvalue())
            raw_data[name] = df
            source_meta[name] = {'status': 'uploaded', 'source': upload.name,
                                 'last_trade_date': df['Date'].max().date().isoformat(),
                                 'retrieved_at': '업로드 시각 확인 불가'}
        except Exception as exc:
            load_errors.append(f'{upload.name}: {exc}')

for msg in load_errors:
    st.error(msg)
if not raw_data:
    st.info('← 왼쪽에서 기업을 선택하거나 출처가 확인된 CSV를 업로드하세요. API가 실패하면 실제 데이터를 만들어 대체하지 않습니다.')
    st.stop()

results: dict[str, pd.DataFrame] = {}
for name, raw in raw_data.items():
    try:
        analyzed = calculate_indicators(raw, window=win, z_limit=z_limit, q_limit=vol_limit)
        results[name] = trim_period(analyzed, start, end)
    except (StockDataError, ValueError, TypeError) as exc:
        st.warning(f'{name}: 분석 불가 - {exc}')
if not results:
    st.error('계산 가능한 데이터가 없습니다. 기간을 넓히거나 더 긴 CSV를 사용하세요.')
    st.stop()
results, aligned = common_date_align(results)
if not aligned:
    st.warning('종목의 공통 거래일이 10일 미만이라 각기 다른 기간의 데이터를 비교합니다.')
summary = summarize(results)
events = event_table(results)
if summary.empty:
    st.warning('선택 기간에 점수를 평가할 수 있는 날짜가 없습니다.')
    st.stop()

selected_name = st.selectbox('📌 상세 분석 종목', list(results))
selected_raw = raw_data[selected_name]
selected_frame = results[selected_name]
meta = source_meta[selected_name]
selected_code = selection.get(selected_name, '') if mode == '국내 주식 실데이터' else ''
st.caption(source_caption(selected_name, meta))
price_fingerprint = int(pd.util.hash_pandas_object(selected_raw[['Date', 'Close', 'Volume']], index=False).sum())

stat_a, stat_b, stat_c, stat_d = st.columns(4)
stat_a.metric('분석 종목', f'{len(results)}개')
stat_b.metric('가격 급변 탐지', f"{summary['가격급변(회)'].sum():.0f}회")
stat_c.metric('거래량 급증 탐지', f"{summary['거래량급증(회)'].sum():.0f}회")
stat_d.metric('평균 변동성', f"{summary['평균 일일변동성(%)'].mean():.2f}%p")

p_over, p_detail, p_anomaly, p_news, p_ai, p_test, p_data = st.tabs([
    '📊 대시보드', '📈 종목 상세', '🚨 급변 탐지', '📰 뉴스·공시',
    '🤖 AI 예측', '🧪 백테스트', '⚙️ 데이터·설명'])

with p_over:
    st.subheader('국내 종합 주식시장 분석')
    if mode == '국내 주식 실데이터':
        if st.button('KOSPI·KOSDAQ 과거 지수 가져오기'):
            info = {}
            for market, symbol in INDICES.items():
                try:
                    info[market] = get_online(symbol, start, end)
                except Exception as exc:
                    st.warning(f'{market}: 지수 조회 실패 ({type(exc).__name__})')
            st.session_state['index_results'] = info
            st.session_state['index_selection'] = (start, end)
        if 'index_results' in st.session_state and st.session_state.get('index_selection') == (start, end):
            info = st.session_state['index_results']
            cols = st.columns(2)
            for col, market in zip(cols, INDICES):
                if market in info:
                    index_raw = info[market].frame
                    info_last = price_snapshot(index_raw)
                    col.metric(f'{market} (일별 종가)', f"{info_last['close']:,.2f}",
                               f"{info_last['change_pct']:+.2f}%")
                    col.caption(f"{info[market].meta.get('last_trade_date','')} · {info[market].meta.get('status','')}")
    else:
        st.caption('실제 KOSPI/KOSDAQ은 실데이터 모드에서만 조회합니다. 현재는 사용자 입력 또는 가상기업의 값입니다.')
    left, right = st.columns([1.05, 1])
    with left:
        st.plotly_chart(bar_comparison(summary), use_container_width=True)
    with right:
        st.plotly_chart(normalized_price_chart(results), use_container_width=True)
    st.dataframe(summary, use_container_width=True, hide_index=True)
    st.download_button('기업 비교표 CSV 저장', csv_bytes(with_provenance(summary, source_meta)),
                       file_name='market_pulse_summary.csv', mime='text/csv')
    st.caption('기업별 평균 변동성은 일일 수익률 표본표준편차이며, 수익률 또는 위험의 미래 예측값이 아닙니다.')

with p_detail:
    st.subheader(f'{selected_name} · 가격 및 보조지표')
    snapshot = price_snapshot(selected_raw)
    a,b,c,d = st.columns(4)
    a.metric('마지막 일별 종가', f"{snapshot['close']:,.0f}원", f"{snapshot['change_pct']:+.2f}%")
    b.metric('마지막 거래량', f"{snapshot['volume']:,}주")
    c.metric('약 52주 최고', f"{snapshot['high_52w']:,.0f}원")
    d.metric('약 52주 최저', f"{snapshot['low_52w']:,.0f}원")
    st.caption(f"기준 거래일 {snapshot['last_trade_date']} · 실제 거래대금 미수집 · "
               f"종가×거래량 **추정치** {snapshot['approx_turnover']:,.0f}원 (실제 거래대금 아님)")
    if mode == '국내 주식 실데이터' and selected_code:
        st.markdown('#### KIS REST 현재가 조회 (선택 기능)')
        st.caption('KIS REST 응답은 버튼을 누른 순간 수신한 조회 결과입니다. 실시간 WebSocket 시세가 아닙니다.')
        if kis_credentials_ready():
            if st.button('KIS 조회 시점 가격 확인', key=f'kis_quote_button_{selected_code}'):
                try:
                    with st.spinner('KIS 현재가(REST) 확인...'):
                        quote = KISReadOnlyClient(environment=get_secret('KIS_ENV') or 'prod').quote(selected_code)
                    st.session_state['kis_quote'] = quote
                except Exception as exc:
                    st.warning(f'KIS 현재가 조회 실패: {type(exc).__name__}: {str(exc)[:130]}')
            quote = st.session_state.get('kis_quote')
            if isinstance(quote, dict) and quote.get('symbol') == selected_code:
                st.write(f"조회 가격: {quote.get('price')}원 · 거래량: {quote.get('volume')}주 · "
                         f"조회 시각: {quote.get('retrieved_at')} · "
                         f"거래대금(API 제공): {quote.get('turnover')}")
                st.caption(quote.get('warning',''))
        else:
            st.caption('KIS 키가 없어 REST 현재가 조회를 사용할 수 없습니다. 과거 일별 차트는 계속 사용할 수 있습니다.')
    if selected_code and kis_credentials_ready():
        with st.expander('KIS 실제 일별 매수·매도 체결량(별도 조회)', expanded=False):
            st.caption('공식 KIS 종목별일별매수매도체결량 API를 호출합니다. OHLCV Volume과 별개 지표입니다. 주문 기능은 없습니다.')
            if st.button('일별 매수·매도 체결량 조회', key=f'kis_buy_sell_{selected_code}'):
                try:
                    with st.spinner('KIS 매수·매도 체결량 조회 중...'):
                        trade_result = fetch_kis_trade_volume(selected_code, start, end)
                    st.session_state['kis_trade_volume_result'] = trade_result
                    st.success(f'실제 제공처 기록 {len(trade_result.frame)}거래일 확인')
                except Exception as exc:
                    st.error(f'KIS 매수·매도 체결량 조회 실패: {type(exc).__name__}: {str(exc)[:110]}')
            trade_result = st.session_state.get('kis_trade_volume_result')
            if trade_result is not None and trade_result.meta.get('symbol') == selected_code:
                st.caption(f"데이터 제공처: {trade_result.meta.get('source')} · 상태: {trade_result.meta.get('status')} · 마지막 거래일: {trade_result.meta.get('last_trade_date')}")
                st.dataframe(trade_result.frame.tail(30), hide_index=True, use_container_width=True)
                st.download_button('매수·매도 체결량 CSV 저장', csv_bytes(trade_result.frame), file_name=f'{selected_code}_buy_sell_executed_volume.csv', mime='text/csv')
    st.plotly_chart(candlestick_chart(selected_raw, selected_frame, selected_name), use_container_width=True)
    st.plotly_chart(volatility_chart(selected_frame), use_container_width=True)
    extra = add_indicators(selected_raw)
    current = extra.iloc[-1]
    st.markdown('#### 주요 기술적 지표')
    extras = {key: (round(float(current[key]),3) if pd.notna(current[key]) else None)
              for key in ('RSI_14','MACD','MACD_signal','ATR_14','Volatility_20d',
                          'Return_5d','Return_20d','Volume_Ratio')}
    st.dataframe(pd.DataFrame([extras]), use_container_width=True, hide_index=True)
    st.caption('기술적 지표는 기업행동·가격 조정 여부·개별 거래정지 영향을 별도로 확인해야 합니다.')
    st.download_button('기술적 지표 CSV 저장', csv_bytes(with_provenance(extra, source_meta, selected_name)),
                       file_name='market_pulse_indicators.csv', mime='text/csv')
    st.download_button('기존 급변 분석 CSV 저장', csv_bytes(with_provenance(selected_frame, source_meta, selected_name)),
                       file_name='market_pulse_indicators_anomaly.csv', mime='text/csv')

with p_anomaly:
    st.subheader('직전 거래일 기준의 과거 급변 탐지')
    kind = st.selectbox('탐지 유형', ['전체','가격·거래량 동반 급변','가격 급변','거래량 급증'])
    visible = events if kind == '전체' else events[events['탐지분류'] == kind]
    st.write(f'탐지 결과: **{len(visible)}건**')
    st.dataframe(visible.round(3), use_container_width=True, hide_index=True)
    st.download_button('급변 탐지 CSV 저장', csv_bytes(with_provenance(visible, source_meta)),
                       file_name='market_pulse_anomalies.csv', mime='text/csv')
    st.caption('가격 급변 Z점수는 직전 N일 수익률과 당일 수익률을 비교합니다. ' 
               '이상 사건의 원인이나 미래 가격을 자동 판정하지 않습니다.')

# News metadata uses actual API responses or user-submitted files; no synthetic stories.
news_key = f'{mode}|{selected_code or selected_name}'
if 'news_by_symbol' not in st.session_state:
    st.session_state['news_by_symbol'] = {}
with p_news:
    st.subheader(f'{selected_name} · 금융 뉴스/기업 공시')
    st.info('NEWS: 네이버 API는 **검색 결과 제목·요약·링크**만 수집합니다. 기사 본문 크롤링이나 자동 거래는 하지 않습니다.')
    status = secret_status()
    st.caption('API 준비 상태: NAVER 뉴스 ' + ('연결 설정 있음' if status['NAVER_CLIENT_ID'] and status['NAVER_CLIENT_SECRET'] else '키 미설정') +
               ' · OpenDART ' + ('연결 설정 있음' if status['DART_API_KEY'] else '키 미설정'))
    if st.button('네이버 금융 뉴스 가져오기', disabled=not (status['NAVER_CLIENT_ID'] and status['NAVER_CLIENT_SECRET'])):
        try:
            with st.spinner('뉴스 검색 메타데이터를 확인합니다...'):
                news_result = fetch_naver_news(selected_name, selected_code)
            st.session_state['news_by_symbol'][news_key] = news_result
            st.success(f'뉴스 검색 결과 {len(news_result)}건 수집')
        except Exception as exc:
            st.error(f'뉴스 검색 실패: {type(exc).__name__}: {str(exc)[:140]}')
    if selected_code and st.button('OpenDART 공시 가져오기', disabled=not status['DART_API_KEY']):
        try:
            with st.spinner('DART 종목코드 매핑 및 공시 검색...'):
                filings = fetch_disclosures(selected_code, (end-timedelta(days=100)).isoformat(), end.isoformat())
            old = st.session_state['news_by_symbol'].get(news_key, pd.DataFrame())
            st.session_state['news_by_symbol'][news_key] = normalize_articles(pd.concat([old, filings], ignore_index=True))
            st.success(f'공시 {len(filings)}건 확인')
        except Exception as exc:
            st.error(f'공시 조회 실패: {type(exc).__name__}: {str(exc)[:140]}')
    upload_news = st.file_uploader('별도 뉴스 메타데이터 CSV 불러오기', type='csv', key='news_upload')
    if upload_news and st.button('업로드 뉴스 적용'):
        try:
            st.session_state['news_by_symbol'][news_key] = read_news_csv(upload_news.getvalue())
            st.success('뉴스 CSV 저장 완료')
        except Exception as exc:
            st.error(f'뉴스 CSV 형식 오류: {exc}')
    current_news = st.session_state['news_by_symbol'].get(news_key, pd.DataFrame())
    if current_news is not None and not current_news.empty:
        current_news = analyze_articles(current_news)
        st.caption('감성 분석은 금융 특화 학습 AI가 아닌 설명 가능한 **키워드 휴리스틱**입니다. ' 
                   '개별 기사 감성이 주가의 상승 확률을 뜻하지 않습니다.')
        selected_topic = st.selectbox('기사 분류 필터', ['전체'] + sorted(current_news['topic'].unique().tolist()))
        shown = current_news if selected_topic == '전체' else current_news[current_news['topic'] == selected_topic]
        columns = ['published_at','title','publisher','topic','sentiment_label',
                   'sentiment_score','evidence','first_seen_at','source_url']
        st.dataframe(shown[columns].astype({'title': str}), use_container_width=True, hide_index=True)
        st.download_button('뉴스 분석 CSV 저장', csv_bytes(current_news),
                           file_name='market_pulse_news.csv', mime='text/csv')
        st.caption('과거 기사라도 최초 확인 시간이 오늘이라면 과거 예측에 소급해서 사용할 수 없습니다.')
    else:
        st.info('사용할 뉴스가 없습니다. API 키를 설정하거나 CSV를 업로드해 주세요.')

# Recompute the identity whenever inputs change, never reuse a previous model silently.
active_news = st.session_state['news_by_symbol'].get(news_key, pd.DataFrame())
news_fingerprint = (int(pd.util.hash_pandas_object(
    active_news[['title', 'published_at', 'first_seen_at']].fillna('').astype(str), index=False).sum())
    if active_news is not None and not active_news.empty else 0)
prediction_identity = (news_key, meta.get('last_trade_date'), len(selected_raw), win,
                       price_fingerprint, news_fingerprint)

with p_ai:
    st.subheader('다음 거래일 종가 상승 확률 · 탐색적 모델')
    st.info('로지스틱 회귀 모델을 시계열 방식으로 검증합니다. 확률은 **미보정 추정치**이며 미래 결과를 보장하지 않습니다.')
    if meta.get('status') == 'cached':
        st.warning('오래된 캐시의 마지막 거래일을 기준으로 한 예측입니다. 오늘의 예측으로 해석하지 마세요.')
    current_news = st.session_state['news_by_symbol'].get(news_key, pd.DataFrame())
    st.caption('모델 A: 가격·거래량 | 모델 B: +기술적 지표 | 모델 C: +뉴스(충분한 시점 기록이 있을 때만)')
    if st.button('🤖 데이터 기준 AI 예측·평가 실행', type='primary'):
        try:
            with st.spinner('시간순 훈련·검증·시험 구간 계산...'):
                evaluation = run_experiments(selected_raw, news=current_news)
            st.session_state['prediction_result'] = evaluation
            st.session_state['prediction_identity'] = prediction_identity
        except Exception as exc:
            st.session_state.pop('prediction_result', None)
            st.error(f'AI 예측 계산 불가: {exc}')
    identity = prediction_identity
    if st.session_state.get('prediction_identity') == identity and 'prediction_result' in st.session_state:
        p = st.session_state['prediction_result']
        st.warning(p.news_note)
        st.markdown('#### 다음 거래일 상승 추정 확률')
        st.dataframe(p.forecasts.style.format({'상승 추정 확률':'{:.1%}', '평가 Brier':'{:.4f}'}),
                     use_container_width=True, hide_index=True)
        st.markdown('#### 시험 구간 성능(한 번만 사용한 마지막 구간)')
        st.dataframe(p.summary.style.format({'정확도':'{:.1%}','정밀도':'{:.1%}',
                   '재현율':'{:.1%}','F1':'{:.3f}','Brier':'{:.4f}',
                   '기준 Brier':'{:.4f}'}), use_container_width=True, hide_index=True)
        st.caption('Brier는 작을수록 좋습니다. 기준보다 Brier가 크면 검증 기간에서 기준 모델보다 못합니다.')
        # Choose a fixed explanatory model; selecting by TEST Brier would leak test info.
        best = '기술 지표 포함' if '기술 지표 포함' in p.evaluations else list(p.evaluations)[0]
        try:
            ev = p.evaluations[best]
            from feature_engineering import usable_history
            from backtesting import _predictor
            tbl = usable_history(p.history, ev.feature_names)
            fitted = _predictor().fit(tbl[ev.feature_names].replace([np.inf,-np.inf], np.nan), tbl['TargetUp'].astype(int))
            factors = describe_logistic_model(fitted, ev.feature_names,
                    p.history.tail(1).replace([np.inf,-np.inf], np.nan))
            st.markdown('#### 모델 변수 기여도(로그오즈 방향, 인과관계 아님)')
            st.dataframe(factors.head(8), use_container_width=True, hide_index=True)
        except Exception:
            st.caption('모델 변수 설명을 생성할 수 없습니다.')
        st.download_button('AI 예측 CSV 저장', csv_bytes(with_provenance(p.forecasts, source_meta, selected_name)),
                           file_name='market_pulse_predictions.csv', mime='text/csv')
        st.download_button('모델 검증 CSV 저장', csv_bytes(with_provenance(p.summary, source_meta, selected_name)),
                           file_name='market_pulse_model_scores.csv', mime='text/csv')
    else:
        st.caption('버튼을 눌러 계산합니다. 자료 부족·단일 클래스·뉴스 시점 정보 미확인 시 해당 모델은 생성되지 않습니다.')

with p_test:
    st.subheader('시계열 백테스트와 기준값 민감도')
    st.caption('최종 20% 시계열 시험 구간, 학습·검증 경계 1행 간격, 예측 목표는 t+1 종가 상승 여부입니다.')
    if st.session_state.get('prediction_identity') == prediction_identity and 'prediction_result' in st.session_state:
        p = st.session_state['prediction_result']
        label = st.selectbox('백테스트할 모델', list(p.evaluations))
        ev = p.evaluations[label]
        st.dataframe(ev.prediction_rows, use_container_width=True, hide_index=True)
        st.plotly_chart(prediction_reliability_chart(ev.prediction_rows), use_container_width=True)
        if st.button('Walk-forward(3회) 추가 검증'):
            try:
                from feature_engineering import usable_history
                table = usable_history(p.history, ev.feature_names)
                folds = walkforward_scores(table, ev.feature_names, splits=3)
                st.session_state['walkforward'] = folds
                st.session_state['walkforward_id'] = (news_key, label)
            except Exception as exc:
                st.error(f'Walk-forward 실행 오류: {exc}')
        if st.session_state.get('walkforward_id') == (news_key, label):
            st.dataframe(st.session_state['walkforward'], use_container_width=True)
        st.download_button('시험 구간 예측 내역 CSV 저장', csv_bytes(with_provenance(ev.prediction_rows, source_meta, selected_name)),
                           file_name='market_pulse_backtest.csv', mime='text/csv')
    else:
        st.info('먼저 AI 예측 탭에서 모델을 계산하면 시험 구간 검증이 표시됩니다.')
    z_points = [1.5,2.,2.5,3.,3.5,4.]
    z_counts = []
    for threshold in z_points:
        computed = calculate_indicators(selected_raw, win, threshold, vol_limit)
        clipped = trim_period(computed, start, end)
        z_counts.append(int(clipped['PriceJump'].sum()))
    fig = go.Figure(go.Bar(x=[str(q) for q in z_points], y=z_counts,
                           marker_color=BLUE, text=z_counts, textposition='outside'))
    fig.update_layout(title='Z점수 문턱값 변경에 따른 과거 가격 급변 건수',
                      xaxis_title='Z 기준', yaxis_title='탐지 건수')
    st.plotly_chart(theme_plot(fig, 325), use_container_width=True)
    st.caption('탐지 건수 변화는 검출 민감도이지 미래 예측 정확도가 아닙니다.')

with p_data:
    st.subheader('수집 상태·입력 형식·계산 원리')
    provenance = pd.DataFrame([{'종목': name, **source_meta[name]} for name in raw_data])
    st.dataframe(provenance, use_container_width=True, hide_index=True)
    st.download_button('수집 출처 메타데이터 CSV', csv_bytes(provenance),
                       file_name='market_pulse_provenance.csv', mime='text/csv')
    with st.expander('계산 원리 / 미래 정보 누출 방지', expanded=True):
        st.markdown('''
- **일일 수익률**: `(Close[t]/Close[t-1] - 1) × 100`
- **N일 변동성**: 당일 포함 최근 N개 일일 수익률의 표본표준편차(연율화하지 않음)
- **과거 급변 Z점수**: `abs(Return[t]-평균[직전 N개 수익률]) / 표준편차[직전 N개 수익률]`
- **거래량 배율**: `Volume[t] / 평균[직전 N거래일 거래량]`
- **RSI**: 최근 상승·하락 크기의 상대적 강도. **MACD**: 12/26 EMA 차이와 9 EMA 신호선.
- **다음 거래일 타깃**: `Close[t+1] > Close[t]`. t 날짜의 피처에는 `t+1`이 포함되지 않습니다.
- **뉴스 시점**: 최초 확인 시각 및 공개 시각이 모두 t일 16:00 KST 이전에 확인된 기사만 t일 예측의 피처로 사용할 수 있습니다.
- **MDD**: 선택 기간에서 이전 누적 최고 종가에 비해 가장 크게 하락한 비율.

표준편차나 이전 거래량이 0인 경우 기존 급변 탐지 엔진은 별도 예외 처리 규칙을 사용합니다.
''')
    with st.expander('실제 데이터·시세의 한계', expanded=True):
        st.markdown('''
- FinanceDataReader 및 KIS 기간별 OHLCV는 **실시간 체결가·호가·현재 매수·매도 잔량**이 아닙니다. KIS REST 현재가도 스트리밍 시세가 아닙니다.
- 저장 캐시를 사용했다면 마지막 거래일과 수집 시각을 확인하세요.
- 거래량은 체결된 주식 수이지 기업 매출액이나 매도 주문량이 아닙니다.
- 액면분할, 배당, 권리락 등 기업행동은 원시 가격 변화의 해석을 왜곡할 수 있습니다.
- 뉴스 감성은 문장 규칙의 결과이며 뉴스 인과관계나 실제 가격 예측 확률이 아닙니다.
- AI 모델은 탐색적 확률 분류기이며 미래 주가·수익을 보장하지 않습니다.
- 테스트에 사용된 모의 응답은 실제 시세가 아니며 사용자 화면의 시세로 제공하지 않습니다.
''')
    with st.expander('API 키 설정 및 실행 오류'):
        st.markdown('''
- API 키는 `.env`/환경변수 또는 `.streamlit/secrets.toml`에 저장하고 GitHub에 공개하지 마세요.
- `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`: 네이버 뉴스 검색용.
- `DART_API_KEY`: 금융감독원 전자공시 조회용.
- API 요청이 실패하더라도 프로그램이 기사나 주가를 만들어 실제 데이터라고 표시하지 않습니다.
- Python 설치: `python -m pip install -r requirements.txt`
- 실행: `python -m streamlit run app.py`
- 테스트: `python -m pytest -q`
''')

st.divider()
st.caption('MARKET PULSE · 교육/연구 전용 · 데이터 출처와 기준시각 확인 필수 · 특정 종목 매매 지시/투자 자문이 아닙니다.')
