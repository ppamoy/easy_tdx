"""样本外验证（V105）的单元测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from easy_tdx.backtest.out_of_sample import compute_out_of_sample
from easy_tdx.backtest.strategies import get_registry


def _make_df(closes: list[float]) -> pd.DataFrame:
    c = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {
            "datetime": pd.date_range("2022-01-01", periods=len(closes), freq="D"),
            "open": [x - 0.2 for x in c],
            "high": [x + 0.3 for x in c],
            "low": [x - 0.3 for x in c],
            "close": c,
            "vol": [1_000_000] * len(closes),
            "amount": [1_000_000.0] * len(closes),
        }
    )


def _ma_factory():
    entry = get_registry().get("ma_cross")
    return lambda: entry.build({"fast": 5, "slow": 20})


class TestComputeOutOfSample:
    def test_empty(self) -> None:
        rep = compute_out_of_sample(pd.DataFrame(), _ma_factory())
        assert "无数据" in rep["verdict"]

    def test_too_small(self) -> None:
        df = _make_df([100 + i for i in range(80)])
        rep = compute_out_of_sample(df, _ma_factory())
        assert "数据不足 120" in rep["verdict"]

    def test_returns_train_test_sections(self) -> None:
        rng = np.random.default_rng(5)
        closes = [100 + x for x in np.cumsum(rng.normal(0.02, 0.8, 600))]
        df = _make_df(closes)
        rep = compute_out_of_sample(df, _ma_factory(), train_ratio=0.7)
        assert rep["train_bars"] == pytest.approx(420, abs=2)
        assert rep["test_bars"] >= 30
        for key in ("total_return", "win_rate", "sharpe", "trades", "buy_hold_return", "alpha"):
            assert key in rep["train"]
            assert key in rep["test"]
        assert isinstance(rep["degraded"], bool)
        assert isinstance(rep["verdict"], str) and len(rep["verdict"]) > 0

    def test_degraded_flag_when_oos_loses(self) -> None:
        # 训练段涨、样本外跌 → 标记退化
        train = [100 + i * 0.5 for i in range(300)]
        test = [250 - i * 0.5 for i in range(300)]
        df = _make_df(train + test)
        rep = compute_out_of_sample(df, _ma_factory(), train_ratio=0.5)
        assert rep["degraded"] is True
        assert "过拟合" in rep["verdict"]
        # 样本外总收益 <= 0 是主要退化信号之一
        assert rep["test"]["total_return"] <= 0

    def test_oos_positive_report_shape(self) -> None:
        # 全段上涨 → 样本外仍正收益；验证报告字段与判定齐全
        closes = [100 + i * 0.4 for i in range(600)]
        df = _make_df(closes)
        rep = compute_out_of_sample(df, _ma_factory(), train_ratio=0.7)
        assert rep["test"]["total_return"] > 0
        assert "训练段收益" in rep["verdict"]
        assert "样本外" in rep["verdict"]
        assert isinstance(rep["degraded"], bool)
