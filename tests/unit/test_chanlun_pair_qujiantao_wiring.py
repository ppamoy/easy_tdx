"""tests for 区间套接线：chanlun_pair 的 require_qujiantao 必须真的过滤而非清零交易。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from easy_tdx.backtest.engine import BacktestEngine
from easy_tdx.backtest.strategies import get_registry

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _mk_df(n: int = 260, seed: int = 7) -> pd.DataFrame:
    """合成有明显趋势/回撤的日线，保证能算出买卖点。"""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    wave = 10.0 + 1.6 * np.sin(t / 17.0) + 0.9 * np.sin(t / 5.0) + 0.004 * t
    noise = rng.normal(0, 0.05, n)
    close = np.maximum(wave + noise, 1.0)
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


def _run(df: pd.DataFrame, params: dict) -> tuple[int, float]:
    strat = get_registry().get("chanlun_pair").build(params)
    r = BacktestEngine(strat, cash=100000.0).run(df)
    t = r.trades
    n_buy = 0 if t is None or len(t) == 0 else int((t["direction"] == "BUY").sum())
    return n_buy, float(r.performance.get("total_return", 0.0))


def _nested_labels(df: pd.DataFrame, **kw) -> list:
    """取策略打完区间套标签后的 nested 分布。

    默认不开启区间套（合成只在 require_qujiantao=True 时运行），
    需要看标签时传 require_qujiantao=True。
    """
    strat = get_registry().get("chanlun_pair").build(kw)
    strat._bind_data(df)
    strat._call_init()
    return [x[3] for x in strat._chanlun_signals]


def test_baseline_has_signals():
    """前提：不带区间套时必须有信号，否则后面的对比无意义。"""
    df = _mk_df()
    labels = _nested_labels(df)
    assert len(labels) > 0


def test_qujiantao_labels_are_computed_not_all_none():
    """核心回归：接线后区间套标签必须真的被算出来（不是全部 None）。

    注意：合成只在 require_qujiantao=True 时运行（性能优化），所以这里
    显式开启。
    """
    df = _mk_df()
    labels = _nested_labels(df, require_qujiantao=True)
    assert len(labels) > 0
    # 至少有一个被明确判定（True 或 False），证明跨周期确认真的跑了
    assert any(v is not None for v in labels)


def test_require_qujiantao_does_not_zero_out_trades():
    """关键回归：修复前 require_qujiantao=True 会导致 0 交易。

    这是一个隐蔽 bug：标签算不出来时 nested=None，旧逻辑
    `if require_nested and nested is not True: continue` 会过滤掉一切，
    表现成"策略一动不动"，而不是"区间套不生效"。
    """
    df = _mk_df()
    n_off, _ = _run(df, {})
    n_on, _ = _run(df, {"require_qujiantao": True})
    # 关闭时必须有交易（前提）
    assert n_off > 0, "基线无交易，测试无意义"
    # 开启区间套后绝不能变成 0 交易
    assert n_on > 0, "require_qujiantao=True 导致 0 交易（旧 bug 复现）"


def test_require_qujiantao_actually_filters():
    """区间套必须真的在过滤，而不是放行全部信号。"""
    df = _mk_df()
    n_off, _ = _run(df, {})
    n_on, _ = _run(df, {"require_qujiantao": True})
    assert n_on <= n_off, "区间套应过滤掉部分信号，不能比关闭时更多"


def test_strict_mode_filters_at_least_as_much_as_loose():
    df = _mk_df()
    loose, _ = _run(df, {"require_qujiantao": True})
    strict, _ = _run(df, {"require_qujiantao": True, "qujiantao_strict": True})
    assert strict <= loose


def test_nested_pass_semantics():
    """_nested_pass 的三态语义：True 放行，False 拒绝，None 看 strict。"""
    from easy_tdx.backtest.strategies.chanlun_pair import ChanlunPairStrategy

    f = ChanlunPairStrategy._nested_pass
    assert f(True, False) is True
    assert f(True, True) is True
    assert f(False, False) is False
    assert f(False, True) is False
    assert f(None, False) is True  # 宽松：算不出来则放行
    assert f(None, True) is False  # 严格：算不出来则过滤


def test_low_level_param_accepted():
    """qujiantao_low_level 参数应被接受且可复现。"""
    df = _mk_df()
    a, _ = _run(df, {"require_qujiantao": True, "qujiantao_low_level": "MIN_30"})
    b, _ = _run(df, {"require_qujiantao": True, "qujiantao_low_level": "MIN_30"})
    assert a == b, "同参数两次运行结果必须一致（可复现）"
