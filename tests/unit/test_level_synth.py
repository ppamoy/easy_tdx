"""tests for chanlun.level_synth（低级别 K 线合成，供区间套跨周期确认）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from easy_tdx.chanlun.level_synth import (
    synthesize_lower_level,
    units_per_bar,
)


def _daily(n: int = 60, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 10.0 + np.cumsum(rng.normal(0, 0.2, n))
    close = np.maximum(close, 1.0)
    high = close + np.abs(rng.normal(0, 0.1, n))
    low = close - np.abs(rng.normal(0, 0.1, n))
    open_ = low + (high - low) * rng.uniform(0.2, 0.8, n)
    return pd.DataFrame(
        {
            "datetime": pd.bdate_range("2023-01-02", periods=n),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "vol": np.full(n, 1e6),
            "amount": np.full(n, 1e7),
        }
    )


def test_units_per_bar_known_and_unknown():
    assert units_per_bar("DAY", "MIN_30") == 8
    assert units_per_bar("DAY", "MIN_60") == 4
    assert units_per_bar("WEEK", "DAY") == 5
    # 未知组合返回 0（调用方据此拒绝合成）
    assert units_per_bar("DAY", "XXX") == 0


def test_expand_count_matches_units():
    df = _daily(30)
    low = synthesize_lower_level(df, "DAY", "MIN_30")
    assert low is not None
    assert len(low) == 30 * 8


def test_synth_never_exceeds_parent_bar_range():
    """核心正确性：子 bar 不能凭空造出高级别 bar 之外的价格。"""
    df = _daily(40, seed=11)
    low = synthesize_lower_level(df, "DAY", "MIN_30")
    assert low is not None
    per = units_per_bar("DAY", "MIN_30")
    for i in range(len(df)):
        g = low.iloc[i * per : (i + 1) * per]
        assert g["high"].max() <= df["high"].iloc[i] + 1e-6
        assert g["low"].min() >= df["low"].iloc[i] - 1e-6


def test_synth_preserves_close_endpoint():
    """每根高级别 bar 的最后一根子 bar 收盘价 == 高级别收盘价。"""
    df = _daily(25, seed=3)
    low = synthesize_lower_level(df, "DAY", "MIN_30")
    assert low is not None
    per = units_per_bar("DAY", "MIN_30")
    for i in range(len(df)):
        last_close = low["close"].iloc[(i + 1) * per - 1]
        assert last_close == pytest.approx(df["close"].iloc[i], rel=1e-6)


def test_synth_ohlc_self_consistent():
    df = _daily(20, seed=5)
    low = synthesize_lower_level(df, "DAY", "MIN_30")
    assert low is not None
    assert (low["high"] >= low["low"] - 1e-9).all()
    assert (low["high"] >= low["close"] - 1e-9).all()
    assert (low["low"] <= low["close"] + 1e-9).all()
    assert (low["high"] >= low["open"] - 1e-9).all()
    assert (low["low"] <= low["open"] + 1e-9).all()


def test_synth_datetime_monotonic():
    df = _daily(20)
    low = synthesize_lower_level(df, "DAY", "MIN_30")
    assert low is not None
    assert pd.to_datetime(low["datetime"]).is_monotonic_increasing


def test_synth_is_reproducible():
    """回测必须可复现：同 seed 两次结果完全一致。"""
    df = _daily(20, seed=9)
    a = synthesize_lower_level(df, "DAY", "MIN_30", seed=42)
    b = synthesize_lower_level(df, "DAY", "MIN_30", seed=42)
    assert a is not None and b is not None
    pd.testing.assert_frame_equal(a, b)


def test_synth_returns_none_on_unknown_pair():
    df = _daily(10)
    assert synthesize_lower_level(df, "DAY", "NOPE") is None


def test_synth_returns_none_when_columns_missing():
    df = _daily(10).drop(columns=["high"])
    assert synthesize_lower_level(df, "DAY", "MIN_30") is None


def test_synth_returns_none_on_empty():
    assert synthesize_lower_level(_daily(0), "DAY", "MIN_30") is None


def test_low_level_yields_richer_structure_than_high():
    """区间套的前提：低级别必须比高级别产生更丰富的笔/中枢。"""
    from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig

    df = _daily(120, seed=21)
    low = synthesize_lower_level(df, "DAY", "MIN_30")
    assert low is not None
    cfg = ChanlunConfig(zs_from_xd=False)
    hi_res = ChanlunAnalyser(code="H", frequency="daily", config=cfg).process_klines(df)
    lo_res = ChanlunAnalyser(code="L", frequency="low", config=cfg).process_klines(low)
    assert len(lo_res.bis) > len(hi_res.bis)
