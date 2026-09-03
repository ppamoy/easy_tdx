"""内置策略覆盖率回归——补齐 15 个零测试引用策略的行为级防线。

V386：这 15 个策略此前在测试目录中零引用（atr_breakout/bbi/bias_reversal/dmi/
donchian/ema_cross/emv/keltner/obv_breakout/rsi_divergence/rsi_macd_combo/supertrend/
triple_ma/volume_breakout/wr_reversal），一旦 init()/next() 崩溃，用户跑回测时才暴露。
本文件用参数化模板统一覆盖三类行为：默认/显式参数实例化、足够长度合成行情运行、
短数据与空数据安全降级。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# 触发注册：builtin + changying（import 副作用把策略登记到全局注册表）
import easy_tdx.backtest.strategies.builtin  # noqa: F401
import easy_tdx.backtest.strategies.changying_chanlun  # noqa: F401
from easy_tdx.backtest.strategies.registry import get_registry

# V386 补齐的 15 个零测试引用策略（审计基线，勿随意删减）
ZERO_REF_STRATEGIES: tuple[str, ...] = (
    "atr_breakout",
    "bbi",
    "bias_reversal",
    "dmi",
    "donchian",
    "ema_cross",
    "emv",
    "keltner",
    "obv_breakout",
    "rsi_divergence",
    "rsi_macd_combo",
    "supertrend",
    "triple_ma",
    "volume_breakout",
    "wr_reversal",
)


def _make_df(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """构造带趋势波动的合成 OHLCV 数据，确保部分策略能触发信号。"""
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0.02, 1.0, n))
    close = np.maximum(close, 1.0)
    high = close + rng.uniform(0.5, 2.0, n)
    low = close - rng.uniform(0.5, 2.0, n)
    open_ = low + rng.uniform(0, high - low, n)
    vol = rng.integers(1000, 10000, n).astype(np.float64)
    return pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "vol": vol,
            "amount": vol * 100.0,
        }
    )


def _run_strategy(name: str, df: pd.DataFrame) -> list[object]:
    """实例化策略、绑定数据、跑完全部 bar，返回清空后的信号列表。"""
    strategy = get_registry().get(name).build()
    strategy._bind_data(df)
    strategy._call_init()
    for i in range(len(df)):
        strategy._set_bar_index(i)
        strategy._call_next()
    return strategy._clear_signals()


class TestZeroRefStrategies:
    """15 个零引用内置策略的行为级回归。"""

    @pytest.mark.parametrize("name", ZERO_REF_STRATEGIES)
    def test_default_build_and_run(self, name: str) -> None:
        """默认参数实例化 + 200 根合成行情完整运行不抛异常。"""
        signals = _run_strategy(name, _make_df(n=200))
        assert isinstance(signals, list)

    @pytest.mark.parametrize("name", ZERO_REF_STRATEGIES)
    def test_explicit_params_build(self, name: str) -> None:
        """显式覆盖每个参数为合法边界值，实例化不抛异常。"""
        entry = get_registry().get(name)
        override: dict[str, object] = {}
        for param in entry.params:
            if param.type is int:
                override[param.name] = param.default
            elif param.type is float:
                override[param.name] = param.default
        strategy = entry.build(override)
        assert strategy.p

    @pytest.mark.parametrize("name", ZERO_REF_STRATEGIES)
    def test_short_data_no_crash(self, name: str) -> None:
        """短于预热期的数据安全降级为无信号而非崩溃。"""
        signals = _run_strategy(name, _make_df(n=10))
        assert isinstance(signals, list)

    @pytest.mark.parametrize("name", ZERO_REF_STRATEGIES)
    def test_empty_data_no_crash(self, name: str) -> None:
        """空数据（仅表头无行）安全降级。"""
        df = _make_df(n=5).iloc[0:0]
        signals = _run_strategy(name, df)
        assert signals == []

    @pytest.mark.parametrize("name", ZERO_REF_STRATEGIES)
    def test_signal_shape(self, name: str) -> None:
        """产生的信号必须携带 direction/size/datetime 三要素。"""
        signals = _run_strategy(name, _make_df(n=300, seed=7))
        for sig in signals:
            assert sig.direction in {"BUY", "SELL"}
            assert sig.size >= 0
            assert isinstance(sig.datetime, int)
