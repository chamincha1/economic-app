"""MARKET PULSE UI Revamp

Streamlit UI refactor with sidebar navigation and cleaner stock-site style layout.
This file is designed to replace the existing app.py in the user's project.
"""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from config import (
    STOCKS, INDICES, DEFAULT_START, DEFAULT_END, get_secret, secret_status
)
from stock_core import (
    StockDataError, read_csv_bytes, calculate_indicators, trim_period,
    common_date_align, event_table, summarize,
)
from market_data import fetch_historical, list_domestic_stocks, price_snapshot, MarketResult
from technical_indicators import add_indicators
from news_collector import fetch_naver_news, normalize_articles
from news_analyzer import analyze_articles
from disclosure_collector import fetch_disclosures
from prediction_model import run_experiments
from backtesting import walkforward_scores
from model_explainer import describe_logistic_model
from market_calendar import is_krx_holiday
from market_ui import make_rows, order_rows, market_table_html, watch_card_html, css as market_css
from stock_catalog import CATALOG, DEFAULT_SELECTED, STOCK_SECTORS, filter_catalog
from langchain_analysis import ai_ready, analyze_news_ai, analyze_link_ai, explain_prediction_ai
from article_link import fetch_public_article, ArticleFetchError
from news_store import load_news, merge_news
from kis_market import (
    KISReadOnlyClient, fetch_kis_historical, kis_credentials_ready, fetch_kis_trade_volume,
)

APP_TITLE = 'MARKET PULSE | 국내 주식 분석 대시보드'
BG = '#f5f7fb'
CARD = '#ffffff'
BORDER = '#e5e9f2'
TEXT = '#111827'
SUBTLE = '#6b7280'
ACCENT_DARK = '#0fa958'
RED = '#ef4444'
BLUE = '#2563eb'
PURPLE = '#8b5cf6'
ORANGE = '#f59e0b'

st.set_page_config(page_title=APP_TITLE, page_icon='📈', layout='wide', initial_sidebar_state='expanded')

st.markdown(f"""
<style>
.stApp {{background:{BG}; color:{TEXT};}}
.block-container {{max-width: 1500px; padding-top: 1.0rem;}}
[data-testid="stSidebar"] {{background:#f1f4f9; border-right:1px solid {BORDER};}}
[data-testid="stSidebar"] * {{color:#1f2937;}}
[data-testid="stSidebar"] .stRadio label p, [data-testid="stSidebar"] .stCheckbox label p,
[data-testid="stSidebar"] .stSelectbox label p, [data-testid="stSidebar"] .stMultiSelect label p,
[data-testid="stSidebar"] .stTextInput label p, [data-testid="stSidebar"] .stDateInput label p,
[data-testid="stSidebar"] .stSlider label p, [data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] .stCaption, [data-testid="stSidebar"] summary {{color:#1f2937 !important;}}
[data-testid="stSidebar"] div[data-baseweb="select"] > div,
[data-testid="stSidebar"] .stDateInput > div > div,
[data-testid="stSidebar"] .stTextInput > div > div,
[data-testid="stSidebar"] .stMultiSelect > div > div {{background:#ffffff; color:#111827; border:1px solid {BORDER};}}
[data-testid="stSidebar"] .stRadio [role="radiogroup"] label {{background:#ffffff; border:1px solid {BORDER}; border-radius:12px; padding:6px 10px; margin-bottom:6px;}}
[data-testid="stSidebar"] .stRadio [role="radiogroup"] label:hover {{background:#f8fafc;}}
[data-testid="stMetric"] {{background:{CARD}; border:1px solid {BORDER}; border-radius:16px; padding:14px 16px; box-shadow:0 2px 10px rgba(15,23,42,.04);}}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p {{color:#57647a !important;}}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] div {{color:#142334 !important;}}
.stButton > button {{border-radius:12px; border:1px solid {BORDER};}}
.stDownloadButton > button {{border-radius:12px;}}
div[data-baseweb="select"] > div, .stDateInput > div > div, .stTextInput > div > div {{border-radius:12px;}}
.mp-hero {{background:linear-gradient(135deg,#ffffff,#f8fbff 55%,#effcf6); border:1px solid {BORDER}; border-radius:24px; padding:24px 28px; margin-bottom:14px; box-shadow:0 10px 28px rgba(15,23,42,.05);}}
.mp-title {{font-size:2rem; font-weight:850; color:{TEXT}; letter-spacing:-0.02em;}}
.mp-sub {{font-size:.95rem; color:{SUBTLE}; margin-top:5px;}}
.mp-chip {{display:inline-block; padding:6px 12px; border-radius:999px; background:#ecfdf3; color:{ACCENT_DARK}; border:1px solid #ccf2db; font-size:.78rem; font-weight:650; margin-top:12px; margin-right:8px;}}
.mp-card {{background:{CARD}; color:{TEXT}; border:1px solid {BORDER}; border-radius:18px; padding:16px 18px; box-shadow:0 4px 12px rgba(15,23,42,.04); height:100%;}}
.mp-section-title {{font-size:1.05rem; font-weight:800; color:{TEXT}; margin-bottom:12px;}}
.mp-note {{color:{SUBTLE}; font-size:.84rem;}}
.mp-sidebar-label {{font-size:.8rem; color:{SUBTLE}; font-weight:700; text-transform:uppercase; letter-spacing:.06em; margin:10px 0 6px;}}
.mp-nav-hint {{font-size:.82rem; color:{SUBTLE}; line-height:1.5;}}
table {{font-size:.95rem;}}
</style>
""", unsafe_allow_html=True)
st.markdown(market_css(), unsafe_allow_html=True)


def csv_bytes(df: pd.DataFrame) -> bytes:
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].astype(str)
    return out.to_csv(index=False).encode('utf-8-sig')


def inject_hero(selected_name: str | None = None):
    title_tail = f' · {selected_name}' if selected_name else ''
    st.markdown(
        f'''<div class="mp-hero">
        <div style="font-size:.78rem;font-weight:800;letter-spacing:.08em;color:{ACCENT_DARK};">KOREA MARKET · DATA INTELLIGENCE</div>
        <div class="mp-title">MARKET PULSE{title_tail}</div>
        <div class="mp-sub">국내 주식 실데이터 · 캔들/거래량 · 기술적 지표 · 급변 탐지 · 뉴스/공시 · AI 예측</div>
        <div><span class="mp-chip">편리한 메뉴 구성</span><span class="mp-chip">실제 데이터 우선</span><span class="mp-chip">교육용 분석 플랫폼</span></div>
        </div>''',
        unsafe_allow_html=True,
    )


def theme_plot(fig: go.Figure, height: int = 380) -> go.Figure:
    fig.update_layout(
        template='plotly_white', height=height, paper_bgcolor=CARD, plot_bgcolor=CARD,
        font=dict(color=TEXT, family='Arial'), margin=dict(l=24, r=24, t=50, b=24),
        hovermode='x unified', legend=dict(orientation='h', y=1.08, x=0),
    )
    fig.update_xaxes(gridcolor='#eef2f7', linecolor='#eef2f7')
    fig.update_yaxes(gridcolor='#eef2f7', zerolinecolor='#eef2f7')
    return fig


def render_card(title: str, body: str, caption: str = ''):
    st.markdown(
        f'''<div class="mp-card"><div class="mp-section-title">{title}</div>
        <div style="font-size:1.25rem;font-weight:800;margin-bottom:6px;">{body}</div>
        <div class="mp-note">{caption}</div></div>''',
        unsafe_allow_html=True,
    )


def render_market_cards(index_info: dict[str, MarketResult]):
    cols = st.columns(max(1, len(index_info)))
    for col, (market, result) in zip(cols, index_info.items()):
        snap = price_snapshot(result.frame)
        delta = f"{snap['change_pct']:+.2f}%"
        color = RED if snap['change_pct'] >= 0 else BLUE
        col.markdown(
            f'''<div class="mp-card">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <div style="font-weight:800">{market}</div>
              <div style="font-size:.78rem;color:{SUBTLE}">{result.meta.get('last_trade_date','')}</div>
            </div>
            <div style="font-size:1.65rem;font-weight:850;margin-top:8px;">{snap['close']:,.2f}</div>
            <div style="font-size:.95rem;color:{color};font-weight:750;">{delta}</div>
            <div class="mp-note" style="margin-top:8px;">출처: {result.meta.get('source','미상')}</div>
            </div>''',
            unsafe_allow_html=True,
        )


def candlestick_chart(raw: pd.DataFrame, analyzed: pd.DataFrame, name: str) -> go.Figure:
    df = add_indicators(raw)
    cutoff = pd.to_datetime(analyzed['Date']).min()
    df = df[df['Date'] >= cutoff].copy()
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=.08,
                        row_heights=[.72, .28], subplot_titles=('가격 / 이동평균', '거래량'))
    if {'Open', 'High', 'Low'}.issubset(df.columns) and df[['Open', 'High', 'Low', 'Close']].notna().all().all():
        fig.add_trace(go.Candlestick(
            x=df['Date'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
            name='캔들', increasing_line_color=RED, decreasing_line_color=BLUE,
            increasing_fillcolor='rgba(239,68,68,.55)', decreasing_fillcolor='rgba(37,99,235,.55)'
        ), row=1, col=1)
    else:
        fig.add_trace(go.Scatter(x=df['Date'], y=df['Close'], mode='lines', line=dict(color=BLUE, width=2.2), name='종가'), row=1, col=1)
    for key, color in [('SMA_5', ORANGE), ('SMA_20', ACCENT_DARK), ('SMA_60', PURPLE)]:
        if key in df and df[key].notna().any():
            fig.add_trace(go.Scatter(x=df['Date'], y=df[key], mode='lines', line=dict(color=color, width=1.7), name=key.replace('_', ' ')), row=1, col=1)
    jumps = analyzed.loc[analyzed['PriceJump']]
    if not jumps.empty:
        fig.add_trace(go.Scatter(x=jumps['Date'], y=jumps['Close'], mode='markers', name='가격 급변', marker=dict(color='#111827', size=8, symbol='diamond')), row=1, col=1)
    bar_colors = np.where(df['Close'] >= df['Close'].shift(1), 'rgba(239,68,68,.85)', 'rgba(37,99,235,.85)')
    fig.add_trace(go.Bar(x=df['Date'], y=df['Volume'], marker_color=bar_colors, name='거래량'), row=2, col=1)
    if 'Volume_SMA20' in df:
        fig.add_trace(go.Scatter(x=df['Date'], y=df['Volume_SMA20'], mode='lines', line=dict(color=ORANGE, width=1.6), name='거래량 평균(20)'), row=2, col=1)
    fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
    fig.update_layout(title=f'{name} · 가격 차트', showlegend=True)
    return theme_plot(fig, 620)


def normalized_price_chart(results: dict[str, pd.DataFrame]) -> go.Figure:
    fig = go.Figure()
    colors = [ACCENT_DARK, BLUE, ORANGE, PURPLE, RED, '#0ea5e9']
    for idx, (name, df) in enumerate(results.items()):
        base = df['Close'].iloc[0]
        series = df['Close'] / base * 100
        fig.add_trace(go.Scatter(x=df['Date'], y=series, mode='lines', line=dict(width=2.2, color=colors[idx % len(colors)]), name=name))
    fig.update_layout(title='종목별 수익률 비교 (시작일 = 100)', yaxis_title='지수화 종가')
    return theme_plot(fig, 360)


def volatility_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Scatter(x=df['Date'], y=df['Volatility'], fill='tozeroy', line=dict(color=ACCENT_DARK, width=2.2), name='변동성'))
    fig.update_layout(title='변동성 추이', yaxis_title='%포인트')
    return theme_plot(fig, 280)


def prediction_reliability_chart(predictions: pd.DataFrame) -> go.Figure:
    x = predictions.copy()
    x['bin'] = pd.cut(x['ProbabilityUp'], bins=np.linspace(0, 1, 6), include_lowest=True)
    grouped = x.groupby('bin', observed=False).agg(predicted=('ProbabilityUp','mean'), actual=('ActualUp','mean'), count=('ActualUp','size')).dropna().reset_index()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[0,1], y=[0,1], line=dict(dash='dash', color='#9ca3af'), name='이상적 보정'))
    if not grouped.empty:
        fig.add_trace(go.Scatter(x=grouped['predicted'], y=grouped['actual'], mode='markers+lines', marker=dict(color=ACCENT_DARK, size=np.maximum(8, grouped['count']*0.7)), name='실제 결과'))
    fig.update_layout(title='확률 보정 참고 그래프', xaxis_title='예측 확률', yaxis_title='실제 상승 비율', xaxis=dict(range=[0,1]), yaxis=dict(range=[0,1]))
    return theme_plot(fig, 330)


def source_caption(name: str, meta: dict) -> str:
    state = meta.get('status', '알 수 없음')
    state_text = {'fresh':'온라인 조회 성공','cached':'이전 캐시(최신 아님)','uploaded':'사용자 업로드','imported':'직접 등록(진위 미확인)'}.get(state, state)
    return f"{name} · {state_text} · 제공처: {meta.get('source','미상')} · 마지막 거래일: {meta.get('last_trade_date','미상')} · 수집 시각: {meta.get('retrieved_at','확인 불가')}"


def with_provenance(frame: pd.DataFrame, metas: dict[str, dict], selected: str | None = None) -> pd.DataFrame:
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


@st.cache_data(ttl=3600, show_spinner=False)
def get_online(code: str, start: date, end: date, backend: str = 'fdr') -> MarketResult:
    if code in INDICES.values() or backend == 'fdr':
        return fetch_historical(code, start, end, index=code in INDICES.values())
    if backend == 'kis':
        return fetch_kis_historical(code, start, end)
    raise StockDataError('인식할 수 없는 시세 데이터 제공처입니다.')


@st.cache_data(ttl=900, show_spinner=False)
def get_article_by_link(url: str):
    # Network requests only happen after the user submits a news link.
    return fetch_public_article(url)


@st.cache_data(ttl=1800, show_spinner=False)
def get_krx_listing() -> pd.DataFrame:
    return list_domestic_stocks()


@st.cache_data(ttl=1800, show_spinner=False)
def compute_indicators_cached(raw: pd.DataFrame, window: int, z_limit: float, vol_limit: float) -> pd.DataFrame:
    return calculate_indicators(raw, window=window, z_limit=z_limit, q_limit=vol_limit)


def build_market_board(results: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, raw in results.items():
        snap = price_snapshot(raw)
        rows.append({
            '종목': name,
            '현재가': snap['close'],
            '등락률(%)': snap['change_pct'],
            '거래량': snap['volume'],
            '시가': snap.get('open'),
            '고가': snap.get('high'),
            '저가': snap.get('low'),
            '52주최고': snap['high_52w'],
            '52주최저': snap['low_52w'],
            '기준일': snap['last_trade_date'],
        })
    board = pd.DataFrame(rows)
    return board.sort_values(['등락률(%)', '거래량'], ascending=[False, False]).reset_index(drop=True)


def metric_cards(summary: pd.DataFrame):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric('분석 종목 수', f"{len(summary)}개")
    c2.metric('평균 변동성', f"{summary['평균 일일변동성(%)'].mean():.2f}%p")
    c3.metric('가격 급변 건수', f"{int(summary['가격급변(회)'].sum())}회")
    c4.metric('거래량 급증 건수', f"{int(summary['거래량급증(회)'].sum())}회")


with st.sidebar:
    st.markdown('<div class="mp-sidebar-label">기능 메뉴</div>', unsafe_allow_html=True)
    page = st.radio('메뉴', ['🏠 홈 대시보드', '📈 국내 시세 보드', '🔎 종목 상세', '🚨 급변 탐지', '📰 뉴스·공시', '🤖 AI 예측', '🧪 백테스트', '⚙️ 데이터 센터'], label_visibility='collapsed')
    page = page.split(' ', 1)[1]

    st.markdown('<div class="mp-sidebar-label">데이터 설정</div>', unsafe_allow_html=True)
    with st.form('sidebar_controls', clear_on_submit=False):
        mode = st.radio('데이터 출처', ['국내 주식 실데이터', 'CSV 직접 업로드'], help='실데이터는 인터넷이 필요합니다.')
        backend = 'fdr'
        if mode == '국내 주식 실데이터':
            backend = st.radio('시세 제공처', ['fdr', 'kis'], format_func=lambda s: 'FinanceDataReader (NAVER → KRX)' if s == 'fdr' else 'KIS Open API (조회 전용)')
            if backend == 'kis' and not kis_credentials_ready():
                st.warning('KIS 인증키가 없어 FinanceDataReader 사용을 권장합니다.')
        start = st.date_input('분석 시작일', value=DEFAULT_START, format='YYYY-MM-DD')
        end = st.date_input('분석 종료일', value=DEFAULT_END, format='YYYY-MM-DD')
        with st.expander('고급 분석 기준', expanded=False):
            win = st.slider('비교 기간(거래일)', 10, 60, 20, 5)
            z_limit = st.slider('가격 급변 Z기준', 1.5, 4.0, 2.5, .5)
            vol_limit = st.slider('거래량 급증 배율', 1.2, 3.0, 1.5, .1)

        st.markdown('<div class="mp-sidebar-label">종목 선택</div>', unsafe_allow_html=True)
        selection: dict[str, str] = {}
        uploads = []
        if mode == '국내 주식 실데이터':
            chosen = st.multiselect('분석 종목 (30개 중 최대 6개)', list(STOCKS),
                                    default=DEFAULT_SELECTED[:3], max_selections=6,
                                    help='30개를 한꺼번에 조회하면 API 호출 제한과 지연이 발생할 수 있습니다.')
            st.caption(f'관심종목 {len(STOCKS)}개 중 {len(chosen)}개 선택 · 가격은 선택한 종목만 다운로드')
            selection.update({name: STOCKS[name] for name in chosen})
            extra = st.text_input('추가 종목코드(6자리)', placeholder='예: 005930')
            if extra:
                if len(extra) == 6 and extra.isdigit() and extra not in selection.values():
                    selection[f'종목 {extra}'] = extra
                elif not (len(extra) == 6 and extra.isdigit()):
                    st.warning('6자리 숫자 종목코드를 입력하세요.')
        else:
            uploads = st.file_uploader('주식 CSV 업로드', type='csv', accept_multiple_files=True)

        submitted = st.form_submit_button('설정 적용', use_container_width=True, type='primary')

    if mode == '국내 주식 실데이터' and st.button('KRX 종목 검색 열기', use_container_width=True):
        try:
            st.session_state['krx_listing'] = get_krx_listing()
        except Exception as exc:
            st.warning(f'목록 조회 실패: {type(exc).__name__}')
    if 'krx_listing' in st.session_state and mode == '국내 주식 실데이터':
        q = st.text_input('기업명/종목코드 검색')
        if q:
            catalog = st.session_state['krx_listing']
            matching = catalog[catalog['Name'].str.contains(q, regex=False, case=False, na=False) | catalog['Code'].str.contains(q, regex=False, na=False)].head(60)
            if not matching.empty:
                options = {f"{r.Name} ({r.Code})": (r.Name, r.Code) for r in matching.itertuples()}
                opt = st.selectbox('검색 결과', list(options))
                if st.button('검색 종목 추가', use_container_width=True):
                    nm, co = options[opt]
                    st.session_state['extra_stock'] = (nm, co)
                    st.rerun()
        if 'extra_stock' in st.session_state:
            nm, co = st.session_state['extra_stock']
            selection[nm] = co

    if mode == '국내 주식 실데이터' and st.button('가격 캐시 재조회', use_container_width=True):
        get_online.clear()
        compute_indicators_cached.clear()
        st.rerun()

    st.markdown('<div class="mp-sidebar-label">안내</div>', unsafe_allow_html=True)
    st.markdown('<div class="mp-nav-hint">실데이터는 과거 일별 시세입니다. 실시간 체결가가 아닙니다.<br>설정은 <strong>설정 적용</strong> 버튼을 눌렀을 때만 반영되어 불필요한 재실행과 렉을 줄입니다.<br>CSV 모드는 실제 출처를 직접 확인한 데이터만 사용하세요.</div>', unsafe_allow_html=True)

if start > end:
    st.error('분석 시작일이 종료일보다 늦습니다.')
    st.stop()
if is_krx_holiday(end):
    st.caption('참고: 종료일은 제공된 KRX 휴장일 참고 목록에 포함됩니다. 실제 거래일 판단은 수집된 시세 기준입니다.')

raw_data: dict[str, pd.DataFrame] = {}
source_meta: dict[str, dict] = {}
load_errors: list[str] = []

if mode == '국내 주식 실데이터':
    for name, code in selection.items():
        try:
            result = get_online(code, start, end, backend)
            raw_data[name] = result.frame
            source_meta[name] = result.meta
            if result.is_cached:
                st.warning(f"{name}: 온라인 수집 실패로 이전 저장 데이터를 사용합니다.")
        except Exception as exc:
            load_errors.append(f'{name}: {exc}')
else:
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
            source_meta[name] = {'status':'uploaded','source':upload.name,'last_trade_date':df['Date'].max().date().isoformat(),'retrieved_at':'업로드 시각 확인 불가'}
        except Exception as exc:
            load_errors.append(f'{upload.name}: {exc}')

for msg in load_errors:
    st.error(msg)
if not raw_data:
    inject_hero()
    st.info('왼쪽 사이드바에서 종목을 선택하거나 CSV를 업로드하면 화면이 구성됩니다.')
    st.stop()

results: dict[str, pd.DataFrame] = {}
for name, raw in raw_data.items():
    try:
        analyzed = compute_indicators_cached(raw, win, z_limit, vol_limit)
        results[name] = trim_period(analyzed, start, end)
    except (StockDataError, ValueError, TypeError) as exc:
        st.warning(f'{name}: 분석 불가 - {exc}')
if not results:
    st.error('계산 가능한 데이터가 없습니다.')
    st.stop()

results, _aligned = common_date_align(results)
summary = summarize(results)
events = event_table(results)
if summary.empty:
    st.error('선택 기간에 분석 가능한 날짜가 없습니다.')
    st.stop()

with st.sidebar:
    selected_name = st.selectbox('상세 분석할 종목', list(results), index=0)
selected_raw = raw_data[selected_name]
selected_frame = results[selected_name]
selected_code = selection.get(selected_name, '') if mode == '국내 주식 실데이터' else ''
meta = source_meta[selected_name]
inject_hero(selected_name)
st.caption(source_caption(selected_name, meta))
if page == '홈 대시보드':
    metric_cards(summary)

if mode == '국내 주식 실데이터' and page == '홈 대시보드':
    if st.button('KOSPI·KOSDAQ 지수 새로고침', use_container_width=False):
        idx_results = {}
        for market, symbol in INDICES.items():
            try:
                idx_results[market] = get_online(symbol, start, end)
            except Exception:
                pass
        st.session_state['index_results'] = idx_results
        st.session_state['index_key'] = (start, end)
    if st.session_state.get('index_key') != (start, end):
        idx_results = {}
        for market, symbol in INDICES.items():
            try:
                idx_results[market] = get_online(symbol, start, end)
            except Exception:
                pass
        st.session_state['index_results'] = idx_results
        st.session_state['index_key'] = (start, end)
    if st.session_state.get('index_results'):
        render_market_cards(st.session_state['index_results'])
    else:
        st.caption('시장지수 조회에 실패했습니다. 주가 데이터와 기업 분석은 계속 사용할 수 있습니다.')

news_key = f'{mode}|{selected_code or selected_name}'
if 'news_by_symbol' not in st.session_state:
    st.session_state['news_by_symbol'] = {}
if page in {'뉴스·공시', 'AI 예측', '백테스트'} and selected_code and news_key not in st.session_state['news_by_symbol']:
    st.session_state['news_by_symbol'][news_key] = load_news(selected_code)

if page == '홈 대시보드':
    st.markdown('<div class="mp-market-title">관심 종목 한눈에 보기</div>', unsafe_allow_html=True)
    st.caption('각 카드의 가격은 표시된 마지막 거래일의 일별 종가입니다. 실시간 체결가가 아닙니다.')
    rows = make_rows({name: raw_data[name] for name in results}, source_meta, selection)
    for offset in range(0, min(len(rows), 6), 3):
        cards = st.columns(min(3, len(rows) - offset))
        for col, row in zip(cards, rows[offset:offset+3]):
            with col:
                st.markdown(watch_card_html(row), unsafe_allow_html=True)

    st.markdown('<div class="mp-market-title">국내 종목 시세표</div>', unsafe_allow_html=True)
    st.markdown('<div class="mp-section-sub">실제 일별 주가 · 간편 정렬 · 가격 변화 · 거래량 · 52주 범위</div>', unsafe_allow_html=True)
    sort_key = st.radio('정렬 기준', ['거래량순', '상승률순', '하락률순', '종목명순'], horizontal=True, key='home_sort')
    st.markdown(market_table_html(order_rows(rows, sort_key)), unsafe_allow_html=True)
    st.caption('아이콘은 기업을 구분하기 위한 자체 제작 표식이며 공식 기업 로고는 아닙니다. 표의 순위는 선택한 종목 안에서만 계산합니다.')
    with st.expander('기업 비교 통계와 그래프 더 보기', expanded=False):
        left, right = st.columns(2)
        with left:
            st.plotly_chart(normalized_price_chart(results), use_container_width=True)
        with right:
            st.dataframe(summary, use_container_width=True, hide_index=True)
        st.download_button('기업 비교 CSV 저장', csv_bytes(with_provenance(summary, source_meta)),
                           file_name='market_pulse_summary.csv', mime='text/csv')

elif page == '국내 시세 보드':
    st.markdown('<div class="mp-market-title">국내 주식 시세 · 종목 비교</div>', unsafe_allow_html=True)
    with st.expander('추가 가능한 국내 30개 종목 전체 목록', expanded=False):
        query_catalog = st.text_input('목록 검색 (이름 또는 코드)', key='catalog_q')
        sectors = ['전체'] + sorted(set(STOCK_SECTORS.values()))
        sector = st.selectbox('업종 구분', sectors, key='catalog_sector')
        st.dataframe(pd.DataFrame(filter_catalog(query_catalog, sector),
                     columns=['종목명', '종목코드', '분류']), hide_index=True,
                     use_container_width=True)
        st.caption('목록은 가격 데이터가 아니라 종목코드 안내입니다. 상장/변경 여부는 조회 시 확인됩니다.')
    st.markdown('<div class="mp-section-sub">선택한 종목의 실제 마지막 거래일 종가 기준 · 시장 전체 순위가 아닙니다.</div>', unsafe_allow_html=True)
    rows = make_rows({name: raw_data[name] for name in results}, source_meta, selection)
    f1, f2 = st.columns([.72, 1.28])
    with f1:
        sort_key = st.selectbox('정렬', ['거래량순', '상승률순', '하락률순', '종목명순'], key='board_sort')
    with f2:
        keyword = st.text_input('종목명 / 종목코드 검색', placeholder='예: 삼성전자 또는 005930', key='board_search')
    if keyword.strip():
        k = keyword.casefold().strip()
        rows = [r for r in rows if k in r['name'].casefold() or k in r['code'].casefold()]
    rows = order_rows(rows, sort_key)
    st.markdown(market_table_html(rows), unsafe_allow_html=True)
    st.caption('빨강은 상승, 파랑은 하락이며 순위는 이 화면에 불러온 종목만 대상으로 합니다. 공식 로고 이미지가 아니라 식별 아이콘을 사용합니다.')
    if rows:
        st.download_button('정렬된 시세표 CSV', csv_bytes(pd.DataFrame([
            {'종목명': r['name'], '종목코드': r['code'], '최근종가': r['close'],
             '전일대비': r['change'], '등락률(%)': r['pct'], '거래량': r['volume'],
             '52주최고': r['high52'], '52주최저': r['low52'], '기준일': r['trading_day'],
             '데이터상태': r['status'], '출처': r['source']} for r in rows])),
            file_name='market_pulse_stock_board.csv', mime='text/csv')
    with st.expander('주가 비교 그래프', expanded=True):
        if len(results) > 1:
            st.plotly_chart(normalized_price_chart(results), use_container_width=True)
        else:
            st.caption('여러 종목을 선택하면 동일 기준으로 가격 흐름을 비교할 수 있습니다.')

elif page == '종목 상세':
    snap = price_snapshot(selected_raw)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric('최근 종가(일별)', f"{snap['close']:,.0f}원", f"{snap['change_pct']:+.2f}%")
    c2.metric('거래량', f"{snap['volume']:,}주")
    c3.metric('시가 / 고가', f"{snap['open']:,.0f} / {snap['high']:,.0f}" if snap.get('open') is not None and snap.get('high') is not None else '미제공')
    c4.metric('저가', f"{snap['low']:,.0f}원" if snap.get('low') is not None else '미제공')
    c5.metric('52주 최고/최저', f"{snap['high_52w']:,.0f} / {snap['low_52w']:,.0f}")
    st.caption(f"기준 거래일 {snap['last_trade_date']} · 종가×거래량 추정치 {snap['approx_turnover']:,.0f}원 (실거래대금 아님)")
    st.plotly_chart(candlestick_chart(selected_raw, selected_frame, selected_name), use_container_width=True)
    sub1, sub2 = st.columns([1,1])
    with sub1:
        st.plotly_chart(volatility_chart(selected_frame), use_container_width=True)
    with sub2:
        extra = add_indicators(selected_raw)
        cur = extra.iloc[-1]
        indicators = pd.DataFrame([{
            'RSI_14': cur.get('RSI_14'), 'MACD': cur.get('MACD'), 'MACD_signal': cur.get('MACD_signal'),
            'ATR_14': cur.get('ATR_14'), 'Volatility_20d': cur.get('Volatility_20d'),
            'Return_5d': cur.get('Return_5d'), 'Return_20d': cur.get('Return_20d'), 'Volume_Ratio': cur.get('Volume_Ratio'),
        }])
        st.markdown('#### 기술적 지표')
        st.dataframe(indicators, use_container_width=True, hide_index=True)
    if mode == '국내 주식 실데이터' and selected_code and kis_credentials_ready():
        with st.expander('KIS 현재가 / 매수·매도 체결량 조회', expanded=False):
            colq, colt = st.columns(2)
            with colq:
                if st.button('KIS 현재가 조회'):
                    try:
                        quote = KISReadOnlyClient(environment=get_secret('KIS_ENV') or 'prod').quote(selected_code)
                        st.session_state['kis_quote'] = quote
                    except Exception:
                        st.warning('KIS 현재가 조회 실패')
                quote = st.session_state.get('kis_quote')
                if isinstance(quote, dict) and quote.get('symbol') == selected_code:
                    st.write(f"조회 가격: {quote.get('price')}원")
                    st.write(f"거래량: {quote.get('volume')}주")
                    st.write(f"거래대금: {quote.get('turnover')}")
                    st.caption(f"조회 시각: {quote.get('retrieved_at')}")
            with colt:
                if st.button('일별 매수·매도 체결량 조회'):
                    try:
                        tr = fetch_kis_trade_volume(selected_code, start, end)
                        st.session_state['kis_trade_volume_result'] = tr
                    except Exception:
                        st.error('체결량 조회 실패')
                tr = st.session_state.get('kis_trade_volume_result')
                if tr is not None and tr.meta.get('symbol') == selected_code:
                    st.dataframe(tr.frame.tail(20), use_container_width=True, hide_index=True)
                    st.download_button('체결량 CSV 저장', csv_bytes(tr.frame), f'{selected_code}_buy_sell_volume.csv', 'text/csv')

elif page == '급변 탐지':
    st.markdown('#### 급변 탐지 내역')
    if events.empty:
        st.info('선택한 기간에 탐지된 이벤트가 없습니다.')
    else:
        cols = ['종목', '날짜', '종가', '일일수익률(%)', 'Z점수', '거래량배율', '방향', '탐지분류']
        available = [c for c in cols if c in events.columns]
        st.dataframe(events[available], use_container_width=True, hide_index=True)
        st.download_button('급변 탐지 CSV 저장', csv_bytes(with_provenance(events, source_meta)), 'market_pulse_anomalies.csv', 'text/csv')
    z_points = [1.5,2.0,2.5,3.0,3.5,4.0]
    counts = []
    for threshold in z_points:
        computed = compute_indicators_cached(selected_raw, win, threshold, vol_limit)
        clipped = trim_period(computed, start, end)
        counts.append(int(clipped['PriceJump'].sum()))
    fig = go.Figure(go.Bar(x=[str(z) for z in z_points], y=counts, marker_color=ACCENT_DARK, text=counts, textposition='outside'))
    fig.update_layout(title='Z 기준 변경에 따른 탐지 건수', xaxis_title='Z 기준', yaxis_title='탐지 건수')
    st.plotly_chart(theme_plot(fig, 310), use_container_width=True)

elif page == '뉴스·공시':
    st.markdown('#### 실제 금융 뉴스 · 기업 공시')
    st.caption('네이버 뉴스 검색 API가 반환한 기사 **제목·검색 요약·URL·공개 시각**만 사용합니다. 유료 기사 원문을 무단 수집하지 않습니다.')
    status = secret_status()
    st.caption('연결 상태 · NAVER 뉴스: ' + ('설정 완료' if status['NAVER_CLIENT_ID'] and status['NAVER_CLIENT_SECRET'] else '키 없음')
               + ' · OpenDART: ' + ('설정 완료' if status['DART_API_KEY'] else '키 없음')
               + ' · LangChain AI: ' + ('설정 완료' if ai_ready() else '키 없음'))
    st.markdown('##### 🔗 기사 URL 직접 분석 · 네이버 API/CSV 불필요')
    st.caption('뉴스 기사 링크를 붙여 넣으면 공개된 기사 본문을 추출해 Grok에 전달합니다. 본문 접근이 안 되면 공개된 제목·요약만 분석하거나 실패 이유를 표시합니다. URL을 넣었다고 자동으로 호출하지 않으며 버튼을 누를 때만 실행합니다.')
    with st.form('direct_article_analysis_form', clear_on_submit=False):
        input_news_url = st.text_input('뉴스 기사 링크', placeholder='https://n.news.naver.com/mnews/article/…', key='manual_news_url')
        submit_news_link = st.form_submit_button('기사 링크 불러와 Grok으로 분석', type='primary',
                                                  disabled=not ai_ready(), use_container_width=True)
    if not ai_ready():
        st.warning('Grok API 키를 읽지 못했습니다. 실제 프로젝트의 `.streamlit/secrets.toml`에 XAI_API_KEY를 설정하고 앱을 다시 시작하세요.')
    direct_context = (selected_name, input_news_url.strip())
    if submit_news_link:
        st.session_state.pop('direct_article_result', None)
        st.session_state.pop('direct_article_context', None)
        try:
            with st.spinner('공개 기사 내용을 읽어 Grok에 분석을 요청하는 중입니다...'):
                article = get_article_by_link(input_news_url)
                brief = analyze_link_ai(selected_name, article)
            st.session_state['direct_article_result'] = (article, brief)
            st.session_state['direct_article_context'] = direct_context
        except ArticleFetchError as exc:
            st.error(f'기사 불러오기 실패: {exc}')
        except Exception as exc:
            st.error(f'Grok 분석 요청 실패: {type(exc).__name__} (키 권한, 모델 설정, 이용 한도 또는 인터넷 연결을 확인하세요.)')
    if st.session_state.get('direct_article_context') == direct_context and 'direct_article_result' in st.session_state:
        article, direct_brief = st.session_state['direct_article_result']
        st.success('기사 URL 분석이 완료되었습니다.')
        st.markdown(f'**기사 제목:** {article.title}')
        st.caption(f'출처: {article.publisher} · 분석한 자료: {article.basis} · 수집 시각(UTC): {article.fetched_at}')
        st.link_button('원문 링크 확인', article.url)
        st.write(f"**기사 관점:** {direct_brief['sentiment']} · {direct_brief['overview']}")
        u1, u2 = st.columns(2)
        with u1:
            st.markdown('**긍정적인 요인**')
            for line in direct_brief['positive_factors']:
                st.write('• ' + line)
        with u2:
            st.markdown('**부정적인 요인**')
            for line in direct_brief['negative_factors']:
                st.write('• ' + line)
        st.markdown('**불확실성·분석 한계**')
        for line in direct_brief['uncertainties']:
            st.write('• ' + line)
        st.caption(direct_brief['method'])
    st.divider()
    st.markdown('##### 뉴스 검색 API를 이용한 여러 기사 비교 (선택 사항)')
    if not selected_code:
        st.info('뉴스 자동 수집과 캐시는 국내 주식 실데이터 모드에서 종목을 선택해 주세요. 위의 URL 분석은 별도로 사용할 수 있습니다.')
    c1, c2 = st.columns(2)
    with c1:
        if st.button('최신 실제 뉴스 가져오기', disabled=(not selected_code) or not
                     (status['NAVER_CLIENT_ID'] and status['NAVER_CLIENT_SECRET']),
                     use_container_width=True):
            try:
                with st.spinner('네이버 검색 API에서 뉴스 제목·요약을 확인합니다...'):
                    downloaded = fetch_naver_news(selected_name, selected_code, display=40)
                    saved = merge_news(selected_code, downloaded)
                    st.session_state['news_by_symbol'][news_key] = saved
                st.success(f'실제 뉴스 {len(downloaded)}건 조회 · 이전 수집 정보 포함 {len(saved)}건')
            except Exception as exc:
                st.error(f'뉴스 조회에 실패했습니다: {type(exc).__name__}: {str(exc)[:170]}')
    with c2:
        if st.button('기업 공시 조회', disabled=(not selected_code) or not status['DART_API_KEY'],
                     use_container_width=True):
            try:
                with st.spinner('공시자료 조회 중...'):
                    filings = fetch_disclosures(selected_code, (end - timedelta(days=100)).isoformat(), end.isoformat())
                previous = st.session_state['news_by_symbol'].get(news_key, pd.DataFrame())
                combined = normalize_articles(pd.concat([previous, filings], ignore_index=True))
                st.session_state['news_by_symbol'][news_key] = combined
                st.success(f'공시 자료 {len(filings)}건 조회')
            except Exception as exc:
                st.error(f'공시 조회 실패: {type(exc).__name__}: {str(exc)[:170]}')
    current_news = st.session_state['news_by_symbol'].get(news_key, pd.DataFrame())
    if current_news is not None and not current_news.empty:
        analyzed_news = analyze_articles(current_news)
        news_topics = ['전체'] + sorted(analyzed_news['topic'].dropna().unique().tolist())
        topic = st.selectbox('기사 유형', news_topics)
        shown = analyzed_news if topic == '전체' else analyzed_news[analyzed_news['topic'] == topic]
        shown = shown.sort_values('published_at', ascending=False)
        st.markdown('##### 기사 목록 · 실제 API/업로드 출처')
        columns = ['published_at', 'title', 'publisher', 'topic',
                   'sentiment_label', 'sentiment_score', 'first_seen_at', 'source_url']
        st.dataframe(shown[columns], use_container_width=True, hide_index=True,
                     column_config={'source_url': st.column_config.LinkColumn('기사 원문 링크')})
        st.caption('위 감성 점수는 키워드 규칙 분류 결과이며 주가 상승 확률이 아닙니다.')
        st.download_button('기사 메타데이터·감성 분석 CSV', csv_bytes(analyzed_news),
                           file_name='market_pulse_news.csv', mime='text/csv')
        st.markdown('##### Grok 뉴스 분석')
        st.caption('별도 LLM API 연결 시 실제 검색된 최근 기사 최대 12건의 제목·요약을 정성 분석합니다. API 사용 비용이 발생할 수 있습니다.')
        news_fingerprint = int(pd.util.hash_pandas_object(
            analyzed_news[['article_id', 'title', 'description', 'published_at']].astype(str), index=False).sum())
        brief_key = (news_key, news_fingerprint)
        if st.button('Grok으로 기사 근거 분석', disabled=not ai_ready(), type='primary'):
            try:
                with st.spinner('기사 내용을 참고해 AI 분석을 작성합니다...'):
                    st.session_state['news_llm_brief'] = analyze_news_ai(selected_name, analyzed_news)
                    st.session_state['news_llm_brief_key'] = brief_key
            except Exception as exc:
                st.error(f'LangChain 실행 실패: {type(exc).__name__}: {str(exc)[:200]}')
        if st.session_state.get('news_llm_brief_key') == brief_key:
            brief = st.session_state['news_llm_brief']
            st.write(f"**기사 관점:** {brief['sentiment']} · {brief['overview']}")
            n1, n2 = st.columns(2)
            with n1:
                st.markdown('**긍정적인 내용**')
                for line in brief['positive_factors']:
                    st.write('• ' + line)
            with n2:
                st.markdown('**부정적인 내용**')
                for line in brief['negative_factors']:
                    st.write('• ' + line)
            if brief['uncertainties']:
                st.markdown('**판단의 한계**')
                for line in brief['uncertainties']:
                    st.write('• ' + line)
            st.markdown('**분석 근거 기사**')
            for item in brief['sources']:
                st.write(f"[{item['number']}] {item['title']} · {item['published_at']}")
                if item['url']:
                    st.link_button(f"기사 {item['number']} 확인", item['url'])
            st.caption(brief['method'])
        elif not ai_ready():
            st.info('LangChain 기능을 사용하려면 XAI_API_KEY가 필요합니다. 키 없이도 실제 기사 조회와 규칙 기반 분석은 사용할 수 있습니다.')
    else:
        st.info('자동 뉴스 수집 자료는 아직 없습니다. 위의 기사 URL 직접 분석은 네이버 API 키 없이도 사용할 수 있습니다.')

elif page == 'AI 예측':
    st.markdown('#### 통계 모델 + LangChain 뉴스 시나리오')
    current_news = st.session_state['news_by_symbol'].get(news_key, pd.DataFrame())
    price_fingerprint = int(pd.util.hash_pandas_object(selected_raw[['Date', 'Close', 'Volume']], index=False).sum())
    news_fingerprint = (int(pd.util.hash_pandas_object(
        current_news[['article_id', 'title', 'description', 'published_at', 'first_seen_at']].fillna('').astype(str), index=False).sum())
        if current_news is not None and not current_news.empty else 0)
    prediction_identity = (news_key, meta.get('last_trade_date'), len(selected_raw), win,
                           price_fingerprint, news_fingerprint)
    st.info('**숫자 상승 확률은 과거 가격·거래량 기반 시계열 모델이 계산합니다.** LangChain은 최신 기사와 모델 결과를 읽고 정성적 시나리오를 작성합니다. AI 문장이 별도 검증된 예측치는 아닙니다.')
    if meta.get('status') == 'cached':
        st.warning('이전 캐시 기반 예측입니다. 데이터의 마지막 거래일을 확인하세요.')
    st.caption('뉴스 수집을 오늘 처음 시작했다면 과거 뉴스로 모델을 백테스트한 것으로 간주하지 않습니다.')
    if st.button('1. 정량 모델 학습·검증 및 예측', type='primary'):
        try:
            with st.spinner('시간순 학습·검증·시험 데이터를 계산합니다...'):
                evaluation = run_experiments(selected_raw, news=current_news)
            st.session_state['prediction_result'] = evaluation
            st.session_state['prediction_identity'] = prediction_identity
        except Exception as exc:
            st.session_state.pop('prediction_result', None)
            st.error(f'시계열 예측 계산 실패: {exc}')
    if st.session_state.get('prediction_identity') == prediction_identity and 'prediction_result' in st.session_state:
        p = st.session_state['prediction_result']
        st.warning(p.news_note)
        st.markdown('##### 다음 거래일 상승 확률 추정 (미보정)')
        st.dataframe(p.forecasts.style.format({'상승 추정 확률':'{:.1%}', '평가 Brier':'{:.4f}'}),
                     use_container_width=True, hide_index=True)
        st.markdown('##### 시험 구간 모델 검증')
        st.dataframe(p.summary.style.format({'정확도':'{:.1%}', '정밀도':'{:.1%}',
                      '재현율':'{:.1%}', 'F1':'{:.3f}', 'Brier':'{:.4f}',
                      '기준 Brier':'{:.4f}'}), use_container_width=True, hide_index=True)
        st.caption('Brier 오차가 기준 모델보다 클 경우 해당 시험 기간의 예측력 개선을 확인하지 못한 것입니다.')
        st.download_button('확률 예측 CSV', csv_bytes(with_provenance(p.forecasts, source_meta, selected_name)),
                           file_name='market_pulse_predictions.csv', mime='text/csv')
        st.download_button('모델 성능 CSV', csv_bytes(with_provenance(p.summary, source_meta, selected_name)),
                           file_name='market_pulse_model_scores.csv', mime='text/csv')
        st.markdown('##### 2. Grok 정성 예측 시나리오')
        st.caption('현재 뉴스에는 모델 기준 거래일 **이후** 공개된 기사가 포함될 수 있습니다. 이는 정성적 추가 설명일 뿐 과거 수치 예측에 소급 반영한 데이터가 아닙니다. 별도 API 과금이 발생할 수 있습니다.')
        if st.button('Grok 시나리오 생성', disabled=not ai_ready() or p.forecasts.empty):
            try:
                chosen_model = '기술 지표 포함' if '기술 지표 포함' in p.forecasts['모델'].tolist() else p.forecasts.iloc[0]['모델']
                fc = p.forecasts[p.forecasts['모델'] == chosen_model].iloc[0].to_dict()
                matching = p.summary[p.summary['모델'] == chosen_model]
                metrics = matching.iloc[0].to_dict() if not matching.empty else {}
                with st.spinner('뉴스와 검증 결과를 이용해 시나리오를 작성합니다...'):
                    brief = explain_prediction_ai(selected_name, fc, metrics, current_news)
                st.session_state['forecast_llm_brief'] = brief
                st.session_state['forecast_llm_id'] = prediction_identity
            except Exception as exc:
                st.error(f'Grok 시나리오 실패: {type(exc).__name__}: {str(exc)[:200]}')
        if st.session_state.get('forecast_llm_id') == prediction_identity:
            brief = st.session_state['forecast_llm_brief']
            st.write(f"**정성 시나리오:** {brief['scenario']}")
            st.write(brief['interpretation'])
            t1, t2 = st.columns(2)
            with t1:
                st.markdown('**상승 시나리오 요인**')
                for line in brief['upward_factors']:
                    st.write('• ' + line)
            with t2:
                st.markdown('**하락 시나리오 요인**')
                for line in brief['downward_factors']:
                    st.write('• ' + line)
            st.markdown('**해석의 한계**')
            for line in brief['limitations']:
                st.write('• ' + line)
            st.markdown('**참고한 실제 기사**')
            for item in brief['sources']:
                st.write(f"[{item['number']}] {item['title']}")
                if item['url']:
                    st.link_button(f"기사 {item['number']} 보기", item['url'])
            st.caption(brief['method'])
        elif not ai_ready():
            st.caption('XAI_API_KEY를 설정하면 Grok 시나리오 버튼을 사용할 수 있습니다.')
    else:
        st.caption('먼저 정량 모델 실행 버튼을 눌러 실제 수집된 가격 데이터로 모델을 검증하세요.')

elif page == '백테스트':
    st.markdown('#### 시계열 백테스트')
    current_news = st.session_state['news_by_symbol'].get(news_key, pd.DataFrame())
    price_fingerprint = int(pd.util.hash_pandas_object(selected_raw[['Date', 'Close', 'Volume']], index=False).sum())
    news_fingerprint = int(pd.util.hash_pandas_object(current_news[['title', 'published_at', 'first_seen_at']].fillna('').astype(str), index=False).sum()) if current_news is not None and not current_news.empty else 0
    prediction_identity = (news_key, meta.get('last_trade_date'), len(selected_raw), win, price_fingerprint, news_fingerprint)
    if st.session_state.get('prediction_identity') == prediction_identity and 'prediction_result' in st.session_state:
        p = st.session_state['prediction_result']
        label = st.selectbox('검증할 모델', list(p.evaluations))
        ev = p.evaluations[label]
        st.dataframe(ev.prediction_rows, use_container_width=True, hide_index=True)
        st.plotly_chart(prediction_reliability_chart(ev.prediction_rows), use_container_width=True)
        if st.button('Walk-forward 3회 검증'):
            try:
                from feature_engineering import usable_history
                table = usable_history(p.history, ev.feature_names)
                folds = walkforward_scores(table, ev.feature_names, splits=3)
                st.session_state['walkforward'] = folds
                st.session_state['walkforward_id'] = (news_key, label)
            except Exception as exc:
                st.error(f'Walk-forward 오류: {exc}')
        if st.session_state.get('walkforward_id') == (news_key, label):
            st.dataframe(st.session_state['walkforward'], use_container_width=True, hide_index=True)
    else:
        st.info('먼저 AI 예측 탭에서 예측을 계산하세요.')

elif page == '데이터 센터':
    st.markdown('#### 30개 국내 종목 카탈로그')
    st.dataframe(pd.DataFrame(CATALOG, columns=['종목명','종목코드','업종']),
                 hide_index=True, use_container_width=True)
    st.caption('30개 종목 코드는 조회 대상으로 등록된 목록이며 가격 기록 자체가 아닙니다.')
    st.markdown('#### 데이터 출처 및 설명')
    provenance = pd.DataFrame([{'종목': name, **source_meta[name]} for name in raw_data])
    st.dataframe(provenance, use_container_width=True, hide_index=True)
    st.download_button('출처 메타데이터 CSV 저장', csv_bytes(provenance), 'market_pulse_provenance.csv', 'text/csv')
    with st.expander('계산 원리 및 주의사항', expanded=True):
        st.markdown('''
- 일일 수익률 = `(Close[t] / Close[t-1] - 1) × 100`
- 변동성 = 최근 N개 일일 수익률의 표본 표준편차(연율화하지 않음)
- 가격 급변 = 당일 수익률이 직전 N일 평균에서 얼마나 벗어났는지 Z점수로 계산
- 거래량 급증 = 당일 거래량 / 직전 N일 평균 거래량
- AI 예측은 다음 거래일 종가 상승 여부를 탐색적으로 분류한 결과입니다.
- 뉴스는 검색 메타데이터 중심이며, 기사 감성은 설명 가능한 휴리스틱 결과입니다.
- 실제 투자 판단용 서비스가 아니며, 매매 추천을 하지 않습니다.
        ''')
