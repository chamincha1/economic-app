"""MARKET PULSE · 국내 주식시장 변동성 분석 & 급변 탐지 웹앱.

Run: python -m streamlit run app.py
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from stock_core import (
    KR_STOCKS, StockDataError, calculate_indicators,
    common_date_align, event_table, make_demo_data,
    read_csv_bytes, summarize, trim_period,
)
from market_data import (
    fetch_historical_prices, format_origin,
    read_historical_cache, save_historical_cache,
)

APP_DIR = Path(__file__).resolve().parent
CACHE_DIR = APP_DIR / "data_cache"
C_BACKGROUND = "#0b1020"
C_PANEL = "#111a2c"
C_TEXT = "#e8edf6"
C_MUTED = "#9aacc7"
C_BLUE = "#67a5ff"
C_AQUA = "#52e0c4"
C_RED = "#ff687c"
C_YELLOW = "#ffcf75"

st.set_page_config(
    page_title="MARKET PULSE | 국내 주식 변동성 분석",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap');
:root { color-scheme: dark; }
html, body, .stApp, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }
.stApp { background: #0b1020; color: #e9eff9; }
[data-testid="stSidebar"] { background: #111a2c; border-right: 1px solid #27334a; }
[data-testid="stMetric"] { background: #121e33; border:1px solid #293750; border-radius:15px; padding: 16px 18px; }
[data-testid="stMetricLabel"] { color: #a3b5d0; }
[data-testid="stMetricValue"] { color: #f6f9ff; }
[data-testid="stTabs"] button { font-weight: 600; }
.block-container { padding-top: 2rem; max-width: 1450px; }
.hero { padding:26px 30px; border: 1px solid #344666; border-radius: 21px;
 background: linear-gradient(115deg,#172f58 0%,#132339 50%,#18243b 100%); margin-bottom: 22px; }
.eyebrow { color: #91c8ff; font-size: .78rem; font-weight: 700; letter-spacing: .12rem; }
.hero-title { color: #ffffff; font-weight:800; letter-spacing: -.04rem; font-size: 2.0rem; margin:7px 0 8px; }
.hero-subtitle { color:#bcd0e9; font-size:.95rem; }
.mode-tag {display:inline-block; background:#263c5b; color:#b5d8fb; padding:5px 11px; border-radius:50px; font-size:.8rem; font-weight:650;margin-top:14px;}
.smallhint { color: #91a5be; font-size: .82rem; }
h1,h2,h3,p,li { letter-spacing:-.01rem; }
div[data-testid="stExpander"] { background: #101c30; border: 1px solid #293750; }
</style>
""", unsafe_allow_html=True)


def chart_base(fig: go.Figure, height: int = 390) -> go.Figure:
    fig.update_layout(
        template="plotly_dark", height=height,
        paper_bgcolor=C_PANEL, plot_bgcolor=C_PANEL,
        font=dict(family="Noto Sans KR, Arial, sans-serif", color=C_TEXT),
        margin=dict(l=22, r=22, t=38, b=26),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.10, x=0),
    )
    fig.update_xaxes(gridcolor="#243149", zerolinecolor="#243149")
    fig.update_yaxes(gridcolor="#243149", zerolinecolor="#243149")
    return fig


@st.cache_data(show_spinner=False)
def demo_cached() -> dict[str, pd.DataFrame]:
    return make_demo_data()


@st.cache_data(ttl=3600, show_spinner=False)
def online_cached(code: str, start_iso: str, end_iso: str):
    prices = fetch_historical_prices(code, date.fromisoformat(start_iso), date.fromisoformat(end_iso))
    # Cache write occurs only on an actual fresh download (not each Streamlit rerender).
    try:
        metadata = save_historical_cache(CACHE_DIR, code, prices)
    except OSError:
        metadata = {
            "source": f"FinanceDataReader:{prices.provider}",
            "last_date": prices.frame["Date"].max().date().isoformat(),
            "collected_at_utc": "저장 실패",
        }
    return prices, metadata


def load_online(name: str, code: str, start: date, end: date) -> tuple[pd.DataFrame, str]:
    try:
        prices, metadata = online_cached(code, start.isoformat(), end.isoformat())
        return prices.frame, format_origin(metadata, cached=False)
    except Exception as exc:
        try:
            frame, metadata = read_historical_cache(CACHE_DIR, code)
            return frame, format_origin(metadata, cached=True)
        except (OSError, StockDataError, ValueError):
            pass
        raise StockDataError(
            f"{name}: 온라인 수집 실패 ({type(exc).__name__}: {str(exc)[:220]}). "
            "인터넷 연결 또는 제공처 상태를 확인하거나 CSV/가상 데이터 모드를 사용하세요."
        ) from exc


def png_chart_note():
    st.caption("변동성 = 20거래일 일일 수익률 표준편차(%포인트). 급변은 과거 대비 통계적 이례성이며 투자 판단·미래 수익률 예측이 아닙니다.")


def plot_comparison(summary: pd.DataFrame):
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=summary["종목"], y=summary["평균 일일변동성(%)"],
        marker_color=(["#6c9efd", "#69d8d0", "#9a90ff", "#ffcc76", "#e984aa", "#8edb87"] * (1 + len(summary) // 6))[:len(summary)],
        name="평균 20일 변동성",
        text=summary["평균 일일변동성(%)"].map(lambda x: f"{x:.2f}%"),
        textposition="outside",
        hovertemplate="%{x}<br>평균 20일 변동성: %{y:.3f}%<extra></extra>",
    ))
    fig.update_layout(yaxis_title="일일 수익률 표준편차 (%포인트)", xaxis_title="종목")
    return chart_base(fig, height=410)


def plot_price_and_vol(df: pd.DataFrame, name: str):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.13, row_heights=[.66, .34])
    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["Close"], mode="lines", name="종가",
        line=dict(color=C_BLUE, width=2.2),
        hovertemplate="%{x|%Y-%m-%d}<br>종가: %{y:,.0f}<extra></extra>"
    ), row=1, col=1)
    if "MA" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["Date"], y=df["MA"], mode="lines", name="20일 이동평균",
            line=dict(color=C_YELLOW, width=1.5, dash="dot")
        ), row=1, col=1)
    price_jumps = df[df["PriceJump"]]
    if not price_jumps.empty:
        fig.add_trace(go.Scatter(
            x=price_jumps["Date"], y=price_jumps["Close"], mode="markers", name="가격 급변",
            marker=dict(color=C_RED, size=10, symbol="diamond", line=dict(color="#ffffff", width=.7)),
            customdata=price_jumps[["ReturnPct"]].to_numpy(),
            hovertemplate="%{x|%Y-%m-%d}<br>종가: %{y:,.0f}<br>수익률: %{customdata[0]:.2f}%<extra>급변 탐지</extra>",
        ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df["Date"], y=df["Volatility"], mode="lines", name="20일 변동성",
        fill="tozeroy", line=dict(color=C_AQUA, width=2),
        fillcolor="rgba(82,224,196,.12)",
        hovertemplate="%{x|%Y-%m-%d}<br>변동성: %{y:.3f}%<extra></extra>"
    ), row=2, col=1)
    fig.update_yaxes(title_text="종가", row=1, col=1)
    fig.update_yaxes(title_text="변동성(%)", row=2, col=1)
    fig.update_layout(title=f"{name} · 주가 & 급변 탐지")
    return chart_base(fig, height=580)


def plot_normalized(results: dict[str, pd.DataFrame]):
    fig = go.Figure()
    colors = [C_BLUE, C_AQUA, C_YELLOW, "#bd95ff", C_RED, "#96e48b"]
    for i, (name, df) in enumerate(results.items()):
        if df.empty or df["Close"].iloc[0] <= 0:
            continue
        indexed = df["Close"] / df["Close"].iloc[0] * 100
        fig.add_trace(go.Scatter(x=df["Date"], y=indexed, name=name, mode="lines", line=dict(color=colors[i % len(colors)], width=2)))
    fig.update_layout(yaxis_title="시작일 = 100", title="주가 변화 비교 (시작일 100 기준)")
    return chart_base(fig, 385)


def plot_drawdown(df: pd.DataFrame):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["Date"], y=df["DrawdownPct"], name="고점 대비 낙폭", fill="tozeroy",
                             line=dict(color=C_RED, width=2), fillcolor="rgba(255,104,124,.17)"))
    fig.update_layout(title="분석 기간의 최대 낙폭(MDD)", yaxis_title="고점 대비 변화율 (%)")
    return chart_base(fig, 270)


def plot_sensitivity(raw: pd.DataFrame, start: date, end: date, window: int, q: float) -> go.Figure:
    limits = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
    counts = []
    for limit in limits:
        df = trim_period(calculate_indicators(raw, window, limit, q), start, end)
        counts.append(int(df["PriceJump"].sum()))
    fig = go.Figure(go.Bar(x=[str(z) for z in limits], y=counts, marker_color=C_BLUE,
                           text=counts, textposition="outside"))
    fig.update_layout(title="Z 기준값에 따른 가격 급변 탐지 횟수", xaxis_title="급변 기준값 (Z ≥)", yaxis_title="탐지 횟수 (회)")
    return chart_base(fig, 310)


def csv_data(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


# ---- Header and sidebar -------------------------------------------------

st.markdown("""
<div class="hero">
  <div class="eyebrow">KOREA STOCK MARKET · DATA ANALYTICS</div>
  <div class="hero-title">MARKET PULSE <span style="color:#6eafff">/</span> 주식시장 이상 변동 분석</div>
  <div class="hero-subtitle">주가 수익률 · 통계적 변동성 · 거래량 변화 · 급변 탐지 · 기업 비교를 한 화면에서</div>
  <div class="mode-tag">● 교육용 데이터 분석 시스템 · 투자 추천 기능 없음</div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### ⚙️ 분석 설정")
    mode = st.radio("데이터 출처", ["국내 주식 실데이터", "예시 데이터 (인터넷 불필요)", "CSV 직접 업로드"],
                    help="예시 데이터는 프로그램 시연용 가상 자료입니다. 실제 주식 가격이 아닙니다.")
    st.divider()
    start_date = st.date_input("분석 시작일", value=date.today() - timedelta(days=365 * 3), format="YYYY-MM-DD")
    end_date = st.date_input("분석 종료일", value=date.today(), format="YYYY-MM-DD")
    window = st.slider("비교 기간 (거래일)", min_value=10, max_value=60, value=20, step=5)
    z_limit = st.slider("가격 급변 Z 기준", min_value=1.5, max_value=4.0, value=2.5, step=.5)
    q_limit = st.slider("거래량 급증 배율", min_value=1.2, max_value=3.0, value=1.5, step=.1)
    st.divider()
    uploads = None
    if mode == "국내 주식 실데이터":
        names = st.multiselect("분석 기업 (최대 6개)", list(KR_STOCKS), default=list(KR_STOCKS), max_selections=6)
        st.caption("FinanceDataReader의 NAVER → KRX 경로로 과거 일별 시세를 가져옵니다. 장중 실시간 시세가 아닙니다. 제공처 장애 시 기존 저장 자료를 명시적으로 표시합니다.")
        if st.button("🔄 온라인 데이터 캐시 새로고침", use_container_width=True):
            online_cached.clear()
            st.rerun()
    elif mode == "예시 데이터 (인터넷 불필요)":
        demo = demo_cached()
        names = st.multiselect("분석 기업", list(demo), default=list(demo))
    else:
        uploads = st.file_uploader("CSV 파일을 선택하세요", type="csv", accept_multiple_files=True,
                                   help="각 CSV에 Date, Close, Volume 열이 있어야 합니다. 한국어 날짜, 종가, 거래량도 지원합니다.")
        names = []
        st.caption("각 파일을 하나의 종목으로 인식합니다. 파일명이 화면의 종목 이름이 됩니다.")
    st.divider()
    st.caption("📐 급변 점수는 **당일 제외 직전 거래일** 자료로 계산합니다.")
    st.caption("📉 최대 낙폭은 선택한 분석 기간의 종가 최고점 대비 하락폭입니다.")

if start_date > end_date:
    st.error("시작일이 종료일보다 늦습니다. 분석 기간을 다시 선택해 주세요.")
    st.stop()

# ---- Data collection and calculation ------------------------------------

raw_data: dict[str, pd.DataFrame] = {}
sources: dict[str, str] = {}
errors: list[str] = []

if mode == "예시 데이터 (인터넷 불필요)":
    st.warning("🧪 **가상 데이터 시연 모드** — 표시되는 가격·변동성·탐지 날짜는 실제 기업의 측정값이 아닙니다.")
    for name in names:
        raw_data[name] = demo_cached()[name]
        sources[name] = "교육용 가상 데이터"
elif mode == "국내 주식 실데이터":
    st.info("🌐 실제 국내 주식의 과거 일별 OHLCV를 수집합니다. 실시간 호가가 아니며 공급원·마지막 거래일·수집 시각을 구분해 표시합니다. 이전 캐시 자료는 최신 시세가 아닙니다.")
    with st.spinner("국내 주식 시세를 확인하고 있습니다..."):
        for name in names:
            try:
                raw_data[name], sources[name] = load_online(name, KR_STOCKS[name], start_date, end_date)
            except StockDataError as exc:
                errors.append(str(exc))
else:
    st.info("📂 CSV 모드 — 첫 분석일 이전의 과거 자료도 30거래일 이상 포함하면 더 정확한 초기 비교가 가능합니다.")
    for file in uploads or []:
        stem = Path(file.name).stem
        unique_name = stem
        suffix = 2
        while unique_name in raw_data:
            unique_name = f"{stem} ({suffix})"
            suffix += 1
        try:
            raw_data[unique_name] = read_csv_bytes(file.getvalue())
            sources[unique_name] = "사용자 업로드 CSV"
        except (StockDataError, ValueError, OSError) as exc:
            errors.append(f"{file.name}: {exc}")

for msg in errors:
    st.error(msg)
if not raw_data:
    st.info("👈 왼쪽에서 기업을 선택하거나 CSV 파일을 추가하면 분석이 시작됩니다.")
    st.stop()

if mode == "국내 주식 실데이터":
    with st.expander("🗂️ 실제 데이터 수집 현황 · 마지막 관측일 확인", expanded=True):
        st.dataframe(pd.DataFrame([{
            "기업": name,
            "종목코드": KR_STOCKS[name],
            "첫 거래일": frame["Date"].min().date().isoformat(),
            "마지막 거래일": frame["Date"].max().date().isoformat(),
            "거래일 수": len(frame),
            "출처 및 수집 시각": sources[name],
        } for name, frame in raw_data.items()]), use_container_width=True, hide_index=True)

results = {}
for name, raw in raw_data.items():
    try:
        analyzed = calculate_indicators(raw, window=window, z_limit=z_limit, q_limit=q_limit)
        results[name] = trim_period(analyzed, start_date, end_date)
    except (StockDataError, ValueError, TypeError) as exc:
        st.warning(f"{name}: {exc}")

if not results:
    st.error("분석할 수 있는 종목이 없습니다. 날짜 범위를 넓히거나 자료를 변경해 주세요.")
    st.stop()

results, aligned = common_date_align(results)
if not aligned:
    st.warning("기업들의 공통 거래일이 10일 미만입니다. 종목별 개별 기간으로 계산되므로 비교 기간이 동일하지 않을 수 있습니다.")

summary = summarize(results)
events = event_table(results)
if summary.empty:
    st.error("유효한 분석 결과가 없습니다.")
    st.stop()

# ---- Overview metrics ---------------------------------------------------

cols = st.columns(4)
cols[0].metric("분석 종목", f"{len(results)}개")
cols[1].metric("가격 급변 탐지", f"{int(summary['가격급변(회)'].sum())}회")
cols[2].metric("동반 급변 탐지", f"{int(summary['동반급변(회)'].sum())}회")
cols[3].metric("평균 일일변동성", f"{summary['평균 일일변동성(%)'].mean():.2f}%")
if aligned and len(results) >= 2:
    st.caption("기업별 비교는 공통으로 관측된 거래일을 기준으로 정렬했습니다. 변동성의 20일 이동 계산에는 이전 거래일까지의 자료가 사용됩니다.")

panel_overview, panel_detail, panel_events, panel_check = st.tabs([
    "📊 대시보드", "📈 종목 상세", "🚨 급변 탐지 내역", "🧪 검증 · 사용법"
])

with panel_overview:
    a, b = st.columns([1.15, 1])
    with a:
        st.plotly_chart(plot_comparison(summary), use_container_width=True)
    with b:
        if len(results) >= 2:
            st.plotly_chart(plot_normalized(results), use_container_width=True)
        else:
            st.plotly_chart(plot_drawdown(next(iter(results.values()))), use_container_width=True)
    st.subheader("기업별 변동성 비교표")
    st.dataframe(summary, use_container_width=True, hide_index=True)
    st.download_button("⬇️ 기업별 비교표 CSV 저장", csv_data(summary), file_name="market_pulse_summary.csv", mime="text/csv")
    png_chart_note()

with panel_detail:
    chosen = st.selectbox("자세히 살펴볼 종목", list(results), key="selected_stock")
    selected = results[chosen]
    sel_row = summary[summary["종목"] == chosen].iloc[0]
    st.caption(f"출처: {sources.get(chosen, '알 수 없음')} · 데이터 기간: {selected['Date'].min():%Y-%m-%d} ~ {selected['Date'].max():%Y-%m-%d}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("평균 변동성", f"{sel_row['평균 일일변동성(%)']:.2f}%")
    m2.metric("가격 급변", f"{int(sel_row['가격급변(회)'])}회")
    m3.metric("거래량 급증", f"{int(sel_row['거래량급증(회)'])}회")
    m4.metric("최대 낙폭", f"{sel_row['최대낙폭 MDD(%)']:.2f}%")
    st.plotly_chart(plot_price_and_vol(selected, chosen), use_container_width=True)
    st.plotly_chart(plot_drawdown(selected), use_container_width=True)
    st.download_button("⬇️ 이 종목 분석 데이터 CSV 저장", csv_data(selected),
                       file_name=f"market_pulse_{KR_STOCKS.get(chosen, 'custom')}.csv", mime="text/csv")
    png_chart_note()

with panel_events:
    st.subheader("자동 탐지된 이례적 거래일")
    st.caption("주가 급변과 거래량 급증을 별도로 탐지하며, 특정 경제 사건의 원인을 자동으로 판정하지 않습니다.")
    types = ["전체", "가격·거래량 동반 급변", "가격 급변", "거래량 급증"]
    selected_type = st.selectbox("분류 필터", types)
    visible = events if selected_type == "전체" else events[events["탐지분류"] == selected_type]
    st.write(f"**탐지 결과: {len(visible)}건**")
    display = visible.copy()
    for col in ["일일수익률(%)", "Z점수", "거래량배율"]:
        display[col] = display[col].round(2)
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.download_button("⬇️ 탐지 결과 CSV 저장", csv_data(visible), file_name="market_pulse_events.csv", mime="text/csv")
    if visible.empty:
        st.info("선택한 탐지 기준과 기간에서 해당하는 이벤트가 없습니다.")
    st.info("참고: '과거표준편차0'인 행은 통상적인 Z점수를 계산할 수 없어 과거의 정체된 수익률에서 변화가 발생했다는 별도 규칙으로 탐지합니다.")

with panel_check:
    st.subheader("탐지 기준을 바꾸면 결과가 얼마나 달라질까?")
    check_name = st.selectbox("민감도 실험 대상", list(results), key="verify_stock")
    st.plotly_chart(plot_sensitivity(raw_data[check_name], start_date, end_date, window, q_limit), use_container_width=True)
    st.caption("이는 민감도 분석이지 정확도 평가가 아닙니다. 실제 사건 정답표가 없는 경우 탐지 횟수만으로 정확도를 판단할 수 없습니다.")
    with st.expander("알고리즘 계산 원리", expanded=True):
        st.markdown("""
1. **일일 수익률:** `(오늘 종가 / 전일 종가 - 1) × 100`
2. **20일 변동성:** 당일까지의 최근 20개 일일 수익률의 *표본 표준편차* (연율화하지 않음)
3. **급변 점수(Z):** `|오늘 수익률 - 직전 20개 수익률 평균| / 직전 20개 수익률 표준편차`
4. **거래량 배율:** `오늘 거래량 / 직전 20거래일의 평균 거래량`
5. **최대 낙폭(MDD):** 선택한 기간의 각 날짜까지의 최고 종가 대비 현재 종가의 하락률 중 최솟값

직전 20거래일의 계산에는 **오늘의 정보가 들어가지 않습니다**. 표준편차나 평균 거래량이 0이면 해당 비율은 계산할 수 없으며, 변화 유무를 별도로 표시합니다.
""")
    with st.expander("데이터 품질과 한계", expanded=True):
        st.markdown("""
- **가상 데이터**는 교육용 시연 자료이며 실제 가격·이벤트가 아닙니다. 실데이터 모드를 선택해야 실제 기업을 분석할 수 있습니다.
- **실데이터**의 제공처 변경, 인터넷 문제 또는 이용 제한으로 수집이 실패할 수 있습니다. 이때 자동으로 가상 데이터를 실데이터로 둔갑시키지 않습니다.
- **이전 저장 데이터** 사용 시 갱신 시점이 오래될 수 있으므로 분석 시점을 확인하세요.
- **액면분할, 배당, 권리락, 거래정지** 등 기업행동 및 시장 구조 변화가 원시 종가에 영향을 줄 수 있습니다. 가격 급변이 곧 투자 위험·원인·예측을 의미하지 않습니다.
- **CSV 파일**은 `Date,Close,Volume` 열을 포함해야 합니다. `날짜,종가,거래량`도 가능합니다. 시작일보다 최소 비교 기간 이상 앞선 데이터가 있으면 좋습니다.
- 서로 다른 종목은 공통 거래일로 정렬해 비교하지만, 수정주가 적용 방식과 거래일 누락 등의 차이를 추가로 점검해야 합니다.
""")
    with st.expander("수행평가 테스트 체크리스트"):
        for item in [
            "정상적인 변화에서 과도한 급변이 감지되지 않는지 검토",
            "급등·급락 가상 데이터에서 가격 급변 탐지 확인",
            "가격은 유지되지만 거래량만 급증한 가상 데이터 확인",
            "중복 날짜, 결측값, 음수 종가 데이터 정리 확인",
            "분석 기간 부족 및 인터넷 오류 시 안내 메시지 확인",
            "기업별 결과와 CSV 출력 데이터 일치 확인",
        ]:
            st.checkbox(item, key=f"test_{item}")

st.divider()
st.caption("MARKET PULSE · 수행평가용 교육 프로젝트 | 시세 분석 도구이며 금융상품 매수·매도 조언 또는 미래 주가 예측 도구가 아닙니다.")
