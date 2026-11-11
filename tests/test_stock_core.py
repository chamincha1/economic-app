import numpy as np
import pandas as pd
import pytest

from stock_core import (
    StockDataError, clean_data, read_csv_bytes, make_demo_data,
    calculate_indicators, trim_period, summarize, common_date_align, event_table,
)


def fixture_frame(n=70, shock_day=45, shock_value=130, shock_volume=2000):
    dates = pd.bdate_range('2025-01-01', periods=n)
    closes = [100.] * n
    volumes = [1000] * n
    if shock_day is not None and shock_day < n:
        closes[shock_day:] = [shock_value] * (n - shock_day)
        volumes[shock_day] = shock_volume
    return pd.DataFrame({'Date': dates, 'Close': closes, 'Volume': volumes})


def test_clean_bad_rows_duplicate_and_numeric():
    df = fixture_frame(n=50)
    duplicate = df.iloc[2:3].copy()
    duplicate['Close'] = '101'
    df.loc[0, 'Close'] = -2
    df.loc[1, 'Volume'] = -1
    df = pd.concat([df, duplicate], ignore_index=True)
    clean = clean_data(df)
    assert clean['Date'].is_unique
    assert (clean['Close'] > 0).all()
    assert (clean['Volume'] >= 0).all()
    assert len(clean) == 48


def test_return_and_scorable_not_today_leakage():
    df = fixture_frame()
    out = calculate_indicators(df)
    assert out.loc[45, 'ReturnPct'] == pytest.approx(30.)
    assert out.loc[45, 'PriorMean'] == pytest.approx(0.)
    assert out.loc[45, 'PriorStd'] == pytest.approx(0.)
    assert bool(out.loc[45, 'ZeroStdChange'])
    assert bool(out.loc[45, 'PriceJump'])
    assert bool(out.loc[45, 'VolumeJump'])
    assert out.loc[45, 'Status'] == '가격·거래량 동반 급변'
    assert out.loc[45, 'Direction'] == '상승'


def test_price_fall_without_volume_jump():
    df = fixture_frame(shock_value=80, shock_volume=1000)
    out = calculate_indicators(df)
    assert out.loc[45, 'Direction'] == '하락'
    assert bool(out.loc[45, 'PriceJump'])
    assert not bool(out.loc[45, 'VolumeJump'])
    assert out.loc[45, 'Status'] == '가격 급변'


def test_volume_only_jump():
    df = fixture_frame(shock_value=100, shock_volume=3000)
    out = calculate_indicators(df)
    assert not bool(out.loc[45, 'PriceJump'])
    assert bool(out.loc[45, 'VolumeJump'])
    assert out.loc[45, 'Status'] == '거래량 급증'


def test_constant_return_baseline_zero_not_divide():
    df = fixture_frame(shock_day=None)
    out = calculate_indicators(df)
    ready = out[out['Scorable']]
    assert ready['PriceJump'].sum() == 0
    assert ready['Zscore'].isna().all()


def test_short_period_and_bad_columns():
    with pytest.raises(StockDataError):
        calculate_indicators(fixture_frame(n=10))
    with pytest.raises(StockDataError):
        clean_data(pd.DataFrame({'foo': [1], 'bar': [2]}))


def test_dataframe_mdd_and_events():
    a = calculate_indicators(fixture_frame(shock_value=80))
    a = trim_period(a, '2025-01-01', '2026-01-01')
    assert a['DrawdownPct'].min() == pytest.approx(-20)
    summary = summarize({'A': a})
    assert summary.iloc[0]['최대낙폭 MDD(%)'] == -20
    events = event_table({'A': a})
    assert not events.empty
    assert (events['종목'] == 'A').all()


def test_common_dates_alignment():
    a = trim_period(calculate_indicators(fixture_frame()), '2025-01-01', '2026-01-01')
    b = a.iloc[2:].copy()
    aligned, success = common_date_align({'A': a, 'B': b})
    assert success
    assert len(aligned['A']) == len(aligned['B'])
    assert (aligned['A']['Date'].to_numpy() == aligned['B']['Date'].to_numpy()).all()


def test_csv_korean_and_commas():
    raw = '날짜,종가,거래량\n2025-01-02,"1,200","50,000"\n2025-01-03,"1,250","60,000"\n2025-01-06,"1,300","40,000"'
    df = read_csv_bytes(raw.encode('utf-8-sig'))
    assert df['Close'].iloc[0] == 1200
    assert df['Volume'].iloc[1] == 60000


def test_demo_has_four_stocks_and_signals():
    demo = make_demo_data()
    assert len(demo) == 4
    for raw in demo.values():
        out = calculate_indicators(raw)
        assert out['PriceJump'].sum() >= 1
        assert out['VolumeJump'].sum() >= 1


def test_zero_prior_volume_special_case():
    df = fixture_frame(shock_day=None)
    df['Volume'] = 0
    df.loc[45, 'Volume'] = 1000
    out = calculate_indicators(df)
    assert bool(out.loc[45, 'ZeroVolumeChange'])
    assert bool(out.loc[45, 'VolumeJump'])
    assert pd.isna(out.loc[45, 'VolumeRatio'])
