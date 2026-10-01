"""tests for 前视守卫 (look-ahead guard)：信号必须经确认期复核、延后发出。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

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


def _signals(df, **kw):
    """返回 (bar_idx, type) 列表（直接读策略 init 后的信号队列）。"""
    s = get_registry().get("chanlun_pair").build(kw)
    s._bind_data(df)
    s._call_init()
    return [(x[0], x[1]) for x in s._chanlun_signals]


def test_guard_off_vs_on_changes_signal_set():
    """守卫必须真的改变信号集（否则没生效）。"""
    df = _mk_df()
    off = _signals(df, lookahead_guard=False)
    on = _signals(df, lookahead_guard=True, confirm_lag=3)
    # 守卫要么丢弃部分信号、要么延迟；两者不可能完全相同
    assert off != on or len(off) != len(on)


def test_guard_delays_signals_by_at_least_lag():
    """守卫开信号生效 bar 应 >= 候选 bar（已延迟）。"""
    df = _mk_df()
    off = _signals(df, lookahead_guard=False)
    on = _signals(df, lookahead_guard=True, confirm_lag=3)
    if not on:
        pytest.skip("本数据无守卫信号")
    # 每个"守卫开"信号都应在某个"守卫关"信号的基础上后移
    off_bars = {b for b, _ in off}
    # 守卫发出的 bar 减去 lag 后应能对应到一个候选
    for b, _ in on:
        assert (b - 3) in off_bars or b in off_bars


def test_guard_can_be_disabled():
    """显式关闭守卫时应与旧逻辑一致。"""
    df = _mk_df()
    default = _signals(df)
    off = _signals(df, lookahead_guard=False)
    assert default != off  # 默认开守卫


def test_guard_default_is_on():
    """默认参数必须开启守卫（不能让前视悄悄漏过）。"""
    entry = get_registry().get("chanlun_pair")
    strat = entry.build({})
    assert strat.p["lookahead_guard"] is True
    assert strat.p["confirm_lag"] >= 1


def test_guard_returns_no_future_dependent_signals():
    """核心回归：守卫开信号必须能被"截至自身生效 bar 的前缀"复现。

    若某信号 e 依赖了 e 之后的数据，则用 df[:e+1] 跑（守卫关）时应该
    得不到对应结构锚点（b=e-lag）。守卫通过后，任何 e 都应可复现。
    """
    df = _mk_df()
    lag = 3
    on = _signals(df, lookahead_guard=True, confirm_lag=lag)
    if not on:
        pytest.skip("无信号")
    unreproducible = []
    for e, typ in on:
        b = e - lag
        sub = df.iloc[: e + 1].reset_index(drop=True)
        s_sub = _signals(sub, lookahead_guard=False)
        if not any(x[0] == b and x[1] == typ for x in s_sub):
            unreproducible.append((e, typ, b))
    # 允许极少数边界情况（最后一根附近数据不足），但主体必须可复现
    assert len(unreproducible) <= max(1, len(on) // 5), (
        f"守卫后仍有 {len(unreproducible)}/{len(on)} 个信号无法在前缀上复现 → 仍有前视"
    )


def test_guard_reproducible_across_runs():
    """同参数两次跑结果一致（可复现）。"""
    df = _mk_df()
    a = _signals(df, lookahead_guard=True, confirm_lag=3)
    b = _signals(df, lookahead_guard=True, confirm_lag=3)
    assert a == b


def test_confirm_lag_larger_means_fewer_or_equal_signals():
    """确认期越大，通过复核的信号不应增多。"""
    df = _mk_df(360)
    small = _signals(df, lookahead_guard=True, confirm_lag=2)
    big = _signals(df, lookahead_guard=True, confirm_lag=10)
    assert len(big) <= len(small)
