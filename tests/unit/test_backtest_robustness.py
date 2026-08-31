"""分段稳健性 / 过拟合检查的单元测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from easy_tdx.backtest.robustness import (
    _segment_split,
    compute_segment_robustness,
)
from easy_tdx.backtest.strategies import get_registry


def _make_df(closes: list[float]) -> pd.DataFrame:
    c = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {
            "datetime": pd.date_range("2022-01-01", periods=len(closes), freq="D"),
            "open": c - 0.2,
            "high": c + 0.3,
            "low": c - 0.3,
            "close": c,
            "vol": 1_000_000,
            "amount": 1_000_000.0,
        }
    )


def _ma_factory(params: dict | None = None):
    entry = get_registry().get("ma_cross")
    return lambda: entry.build(params or {"fast": 5, "slow": 20})


class TestSegmentSplit:
    def test_even_split(self) -> None:
        df = _make_df([100 + i for i in range(90)])
        parts = _segment_split(df, 3)
        assert len(parts) == 3
        assert [len(p) for p in parts] == [30, 30, 30]
        # 顺序保持
        assert parts[0]["close"].iloc[0] == 100
        assert parts[2]["close"].iloc[-1] == 189

    def test_last_segment_takes_remainder(self) -> None:
        df = _make_df([100 + i for i in range(100)])
        parts = _segment_split(df, 3)
        assert len(parts) == 3
        assert [len(p) for p in parts] == [33, 33, 34]

    def test_too_small_returns_whole(self) -> None:
        df = _make_df([100.0] * 5)
        parts = _segment_split(df, 3)
        assert len(parts) == 1
        assert len(parts[0]) == 5


class TestComputeSegmentRobustness:
    def test_empty_df(self) -> None:
        rep = compute_segment_robustness(pd.DataFrame(), _ma_factory(), segments=3)
        assert rep["segments"] == []
        assert "无数据" in rep["verdict"]

    def test_small_df(self) -> None:
        df = _make_df([100.0 + i for i in range(40)])
        rep = compute_segment_robustness(df, _ma_factory(), segments=3)
        assert "数据不足 60" in rep["verdict"]

    def test_runs_segments_and_consistency(self) -> None:
        rng = np.random.default_rng(7)
        closes = [100 + x for x in np.cumsum(rng.normal(0.02, 1.0, 600))]
        df = _make_df(closes)
        rep = compute_segment_robustness(df, _ma_factory(), segments=3)
        assert len(rep["segments"]) == 3
        assert all(not s["skipped"] for s in rep["segments"])
        cons = rep["consistency"]
        assert cons["segments_analyzed"] == 3
        assert 0.0 <= cons["positive_segment_ratio"] <= 1.0
        assert 0.0 <= cons["beats_buy_hold_ratio"] <= 1.0
        assert "best_segment" in cons and "worst_segment" in cons
        assert isinstance(rep["verdict"], str) and len(rep["verdict"]) > 0
        assert isinstance(rep["overfit_likely"], bool)

    def test_segment_reports_have_metrics(self) -> None:
        rng = np.random.default_rng(11)
        closes = [100 + x for x in np.cumsum(rng.normal(0.01, 0.8, 500))]
        df = _make_df(closes)
        rep = compute_segment_robustness(df, _ma_factory(), segments=2)
        valid = [s for s in rep["segments"] if not s["skipped"]]
        assert len(valid) >= 1
        seg = valid[0]
        for key in (
            "label",
            "bars",
            "total_return",
            "win_rate",
            "sharpe",
            "max_drawdown",
            "trades",
            "buy_hold_return",
            "alpha",
        ):
            assert key in seg, f"缺字段 {key}"

    def test_deterministic_segments_count(self) -> None:
        df = _make_df([100 + i for i in range(600)])
        rep = compute_segment_robustness(df, _ma_factory(), segments=4)
        analyzed = rep["consistency"].get("segments_analyzed", 0)
        assert analyzed >= 2

    def test_strategy_factory_called_fresh_per_segment(self) -> None:
        df = _make_df([100 + i for i in range(300)])
        calls: list[int] = []

        def factory():
            calls.append(1)
            return _ma_factory()()

        rep = compute_segment_robustness(df, factory, segments=3)
        assert len(calls) == len(rep["segments"])
