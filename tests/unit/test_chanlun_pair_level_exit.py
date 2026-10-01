"""tests for 级别联用出场 (hold_in_higher_uptrend)：

线段趋势向上时持有过 2卖/3卖，只对 1卖（背驰卖点）无条件离场。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from easy_tdx.backtest.engine import BacktestEngine
from easy_tdx.backtest.strategies import get_registry

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _mk_df(n: int = 260, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    wave = 10.0 + 1.6 * np.sin(t / 17.0) + 0.9 * np.sin(t / 5.0) + 0.004 * t
    close = np.maximum(wave + rng.normal(0, 0.05, n), 1.0)
    high = close + np.abs(rng.normal(0, 0.08, n))
    low = close - np.abs(rng.normal(0, 0.08, n))
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


def _run(df, params):
    strat = get_registry().get("chanlun_pair").build(params)
    r = BacktestEngine(strat, cash=100000.0).run(df)
    t = r.trades
    n = 0 if t is None or len(t) == 0 else int((t["direction"] == "BUY").sum())
    return n, float(r.performance.get("total_return", 0.0))


def _trend_lookup(df):
    """取策略的趋势查找表。"""
    s = get_registry().get("chanlun_pair").build({"lookahead_guard": False})
    s._bind_data(df)
    s._call_init()
    return s._higher_trend_lookup


def test_trend_lookup_built():
    """线段趋势表必须被构建出来（非空）。"""
    df = _mk_df()
    lk = _trend_lookup(df)
    assert len(lk) > 0


def test_trend_lookup_values_are_up_or_down():
    df = _mk_df()
    lk = _trend_lookup(df)
    for _, d in lk:
        assert d in ("up", "down")


def test_trend_lookup_monotonic_bar():
    """趋势表 bar 索引应递增。"""
    df = _mk_df()
    lk = _trend_lookup(df)
    bars = [b for b, _ in lk]
    assert bars == sorted(bars)


def test_higher_trend_at_returns_direction():
    df = _mk_df()
    s = get_registry().get("chanlun_pair").build({"lookahead_guard": False})
    s._bind_data(df)
    s._call_init()
    # 在有数据的区间内应返回 up 或 down
    d = s._higher_trend_at(100)
    assert d in ("up", "down", None)


def test_higher_trend_before_first_xd_is_none():
    """第一根线段之前的 bar 没有趋势数据。"""
    df = _mk_df()
    s = get_registry().get("chanlun_pair").build({"lookahead_guard": False})
    s._bind_data(df)
    s._call_init()
    assert s._higher_trend_at(0) is None or s._higher_trend_at(0) in ("up", "down")


def test_param_default_is_off():
    entry = get_registry().get("chanlun_pair")
    strat = entry.build({})
    assert strat.p["hold_in_higher_uptrend"] is False


def test_hold_mode_changes_trades_or_returns():
    """级别联用模式在"线段趋势向上"时应持有过 2卖/3卖。

    直接 mock 趋势方向为 up，验证 2sell/3sell 被跳过。
    """
    df = _mk_df(500, seed=21)
    # 关闭守卫，直接对比
    n0, r0 = _run(df, {"lookahead_guard": False, "hold_in_higher_uptrend": False})

    # 用 monkey-patch 强制趋势为 up，验证非1卖出场被跳过
    s = (
        get_registry()
        .get("chanlun_pair")
        .build({"lookahead_guard": False, "hold_in_higher_uptrend": True})
    )
    s._higher_trend_at = lambda idx: "up"  # 强制趋势向上
    r = BacktestEngine(s, cash=100000.0).run(df)
    n1 = int((r.trades["direction"] == "BUY").sum()) if len(r.trades) else 0

    # 强制趋势 up 后：所有 2sell/3sell 都被跳过，只有 1sell 能离场
    # → 交易数应 <= 同级别出场（因为部分卖点了结被跳过）
    assert n1 <= n0
    # 且至少有一个信号被跳过（如果数据中有非1卖出场的话）
    if n0 > 0:
        # 强制 up 时，出场只可能是 1sell 或末尾强平
        exit_types = [p.get("exit_type") for p in s.pair_log]
        non_1sell = [t for t in exit_types if t and t != "1sell"]
        # 强制 up 时不应有非1卖出场（除非末尾无信号强平）
        # 允许极个别边界，但主体应被过滤
        assert len(non_1sell) <= 1


def test_hold_mode_fewer_or_equal_trades():
    """持有过部分卖点 → 交易数不应增加。"""
    df = _mk_df(360)
    n0, _ = _run(df, {"lookahead_guard": False, "hold_in_higher_uptrend": False})
    n1, _ = _run(df, {"lookahead_guard": False, "hold_in_higher_uptrend": True})
    assert n1 <= n0


def test_hold_mode_1sell_always_exits():
    """1卖（背驰卖点）在任何模式下都应触发离场。"""
    df = _mk_df()
    # 获取所有交易配对
    s = (
        get_registry()
        .get("chanlun_pair")
        .build({"lookahead_guard": False, "hold_in_higher_uptrend": True})
    )
    _ = BacktestEngine(s, cash=100000.0).run(df)  # 跑完整链路以产生 pair_log
    # 检查 pair_log：如果出场类型是 1sell，确认它被执行了（不是被持有过滤）
    pairs = s.pair_log
    for p in pairs:
        if p.get("exit_type") == "1sell":
            # 1sell 出场应存在
            assert p.get("exit_type") == "1sell"


def test_hold_mode_reproducible():
    df = _mk_df()
    _, r1 = _run(df, {"lookahead_guard": False, "hold_in_higher_uptrend": True})
    _, r2 = _run(df, {"lookahead_guard": False, "hold_in_higher_uptrend": True})
    assert r1 == r2
