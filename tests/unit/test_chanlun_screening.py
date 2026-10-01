"""tests for 缠论原著选股 (chanlun-scan) helper functions.

Tests behavior of _chanlun_screen and its sub-helpers using real chanlun
analysis on synthetic + real-structured data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig
from easy_tdx.web.routers.screening import (
    _chanlun_has_beichi,
    _chanlun_latest_signal,
    _chanlun_screen,
    _chanlun_trend_direction,
    _chanlun_zs_position,
)

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _mk_df(n: int = 260, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    wave = 10.0 + 2.0 * np.sin(t / 17.0) + 1.0 * np.sin(t / 5.0) + 0.005 * t
    close = np.maximum(wave + rng.normal(0, 0.06, n), 1.0)
    high = close + np.abs(rng.normal(0, 0.10, n))
    low = close - np.abs(rng.normal(0, 0.10, n))
    open_ = np.clip(low + (high - low) * rng.uniform(0.2, 0.8, n), low, high)
    return pd.DataFrame(
        {
            "datetime": pd.bdate_range("2022-01-03", periods=n),
            "open": open_,
            "high": np.maximum(high, np.maximum(close, open_)),
            "low": np.minimum(low, np.minimum(close, open_)),
            "close": close,
            "vol": np.full(n, 1e6),
            "amount": np.full(n, 1e7),
        }
    )


def _result(df):
    cfg = ChanlunConfig()
    return ChanlunAnalyser(code="TEST", frequency="daily", config=cfg).process_klines(df)


@pytest.fixture(scope="module")
def df():
    return _mk_df(360, seed=42)


@pytest.fixture(scope="module")
def result(df):
    return _result(df)


# ── trend direction ──────────────────────────────────────────────────────


def test_trend_direction_returns_string_or_none(result):
    d = _chanlun_trend_direction(result)
    assert d in ("up", "down", None)


def test_trend_direction_no_xds():
    """空 result 对象返回 None。"""

    class Empty:
        xds = []
        bis = []
        zss = []
        bcs = []
        mmds = []
        klines = []

    assert _chanlun_trend_direction(Empty()) is None


# ── zs position ───────────────────────────────────────────────────────────


def test_zs_position_returns_string_or_none(result, df):
    close = float(df["close"].iloc[-1])
    pos = _chanlun_zs_position(result, close)
    assert pos in ("above", "below", "inside", None)


def test_zs_position_none_without_close(result):
    assert _chanlun_zs_position(result, None) is None


def test_zs_position_none_without_zs():
    class NoZS:
        zss = []

    assert _chanlun_zs_position(NoZS(), 100.0) is None


# ── has beichi ─────────────────────────────────────────────────────────────


def test_has_beichi_returns_bool(result):
    assert isinstance(_chanlun_has_beichi(result), bool)


def test_has_beichi_empty():
    class Empty:
        bcs = []

    assert _chanlun_has_beichi(Empty()) is False


# ── latest signal ─────────────────────────────────────────────────────────


def test_latest_signal_returns_dict_or_none(result):
    sig = _chanlun_latest_signal(result)
    if sig is not None:
        assert "type" in sig
        assert "is_buy" in sig
        assert "date" in sig
        assert "price" in sig


def test_latest_signal_empty():
    class Empty:
        mmds = []

    assert _chanlun_latest_signal(Empty()) is None


# ── _chanlun_screen full logic ────────────────────────────────────────────


def test_screen_any_passes(result, df):
    """默认条件(any_buy)应过滤出最新信号是买入的股票。"""
    close = float(df["close"].iloc[-1])
    passes, details = _chanlun_screen(result, {"signal_type": "any"}, close)
    assert isinstance(passes, bool)
    assert "latest_signal" in details
    assert "trend" in details
    assert "zs_position" in details
    assert "quality_score" in details


def test_screen_details_complete(result, df):
    close = float(df["close"].iloc[-1])
    _, details = _chanlun_screen(result, {"signal_type": "any"}, close)
    expected_keys = {
        "latest_signal",
        "trend",
        "zs_position",
        "has_beichi",
        "quality_score",
        "bi_count",
        "zs_count",
        "bc_count",
        "classification",
    }
    assert expected_keys.issubset(details.keys())


def test_screen_min_zs_filter(result, df):
    """min_zs_count 过高应过滤掉所有股票。"""
    close = float(df["close"].iloc[-1])
    passes, _ = _chanlun_screen(result, {"min_zs_count": 999}, close)
    assert passes is False


def test_screen_min_quality_filter(result, df):
    """min_quality 过高应过滤掉所有股票。"""
    close = float(df["close"].iloc[-1])
    passes, _ = _chanlun_screen(result, {"min_quality": 999}, close)
    assert passes is False


def test_screen_trend_filter_both_sides(result, df):
    """走势过滤：指定 up 时，若趋势非 up 则 False；any 时不过滤。"""
    close = float(df["close"].iloc[-1])
    _, details = _chanlun_screen(result, {"signal_type": "any"}, close)
    actual_trend = details["trend"]
    if actual_trend is None:
        pytest.skip("此数据无线段，无法测趋势过滤")

    # 指定与实际相反的方向 → 应过滤
    opposite = "down" if actual_trend == "up" else "up"
    passes, _ = _chanlun_screen(result, {"signal_type": "any", "trend": opposite}, close)
    assert passes is False

    # 指定与实际相同 → 应通过（前提是其他条件也满足）
    passes, _ = _chanlun_screen(result, {"signal_type": "any", "trend": actual_trend}, close)
    assert passes is True

    # any → 不过滤
    passes, _ = _chanlun_screen(result, {"signal_type": "any", "trend": "any"}, close)
    assert passes is True


def test_screen_has_beichi_filter(result, df):
    """has_beichi=True 时，若无背驰则 False。用 signal_type=any 隔离信号过滤。"""
    close = float(df["close"].iloc[-1])
    _, details = _chanlun_screen(result, {"signal_type": "any"}, close)
    actual_bc = details["has_beichi"]
    passes, _ = _chanlun_screen(result, {"signal_type": "any", "has_beichi": True}, close)
    assert passes == actual_bc


def test_screen_signal_type_any_buy_requires_buy(result, df):
    """signal_type=any_buy 时，最新信号必须是买入方向。"""
    close = float(df["close"].iloc[-1])
    passes, details = _chanlun_screen(result, {"signal_type": "any_buy"}, close)
    if details["latest_signal"] is None:
        assert passes is False
    else:
        assert passes == details["latest_signal"]["is_buy"]


def test_screen_no_signal_fails():
    """没有买卖点的 result 应被过滤。"""

    class NoMMD:
        mmds = []
        bis = []
        zss = []
        bcs = []
        xds = []
        klines = []

    passes, details = _chanlun_screen(NoMMD(), {"signal_type": "any_buy"}, 100.0)
    assert passes is False
    assert details["latest_signal"] is None


def test_screen_reproducible(result, df):
    """同一数据同一条件，结果一致。"""
    close = float(df["close"].iloc[-1])
    p1, d1 = _chanlun_screen(result, {"signal_type": "any", "trend": "any"}, close)
    p2, d2 = _chanlun_screen(result, {"signal_type": "any", "trend": "any"}, close)
    assert p1 == p2
    assert d1 == d2


def test_screen_zs_position_filter(result, df):
    """中枢位置过滤：指定 above 时，若实际非 above 则 False。"""
    close = float(df["close"].iloc[-1])
    _, details = _chanlun_screen(result, {"signal_type": "any"}, close)
    actual = details["zs_position"]
    if actual is None:
        pytest.skip("此数据无中枢，无法测位置过滤")

    # 指定与实际不同 → 过滤
    others = {"above", "below", "inside"} - {actual}
    for other in others:
        passes, _ = _chanlun_screen(result, {"signal_type": "any", "zs_position": other}, close)
        assert passes is False

    # 指定与实际相同 → 通过
    passes, _ = _chanlun_screen(result, {"signal_type": "any", "zs_position": actual}, close)
    assert passes is True

    # any → 不过滤
    passes, _ = _chanlun_screen(result, {"signal_type": "any", "zs_position": "any"}, close)
    assert passes is True
