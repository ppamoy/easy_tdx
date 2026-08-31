"""缠论信号类型专属准确度验证的单元测试（使用 signal_accuracy 模块）。"""

from __future__ import annotations

import pytest

from easy_tdx.backtest.signal_accuracy import compute_signal_accuracy_by_type


class TestComputeSignalAccuracyByType:
    """compute_signal_accuracy_by_type 单元测试。"""

    def test_empty_inputs(self) -> None:
        result = compute_signal_accuracy_by_type([], [])
        assert result["by_type"] == {}
        assert result["ranking"] == []
        assert "无信号" in result["summary"]

    def test_insufficient_closes(self) -> None:
        result = compute_signal_accuracy_by_type([10.0, 11.0], [{"type": "1buy", "bar_index": 0}])
        assert "无法验证" in result["summary"]

    def test_uptrend_all_hits(self) -> None:
        """单调上涨：所有买入信号都应命中。"""
        closes = [100 + i * 1.0 for i in range(60)]
        signals = [
            {"type": "1buy", "bar_index": 5},
            {"type": "1buy", "bar_index": 15},
            {"type": "1buy", "bar_index": 25},
        ]
        result = compute_signal_accuracy_by_type(closes, signals, horizons=(5,))
        assert "1buy" in result["by_type"]
        h5 = result["by_type"]["1buy"]["horizons"]["5"]
        assert h5["count"] == 3
        assert h5["hit_rate"] == pytest.approx(1.0)
        assert h5["avg_return"] > 0

    def test_downtrend_sell_hits(self) -> None:
        """单调下跌：所有卖出信号都应命中（避跌）。"""
        closes = [100 - i * 1.0 for i in range(60)]
        signals = [
            {"type": "1sell", "bar_index": 10},
            {"type": "1sell", "bar_index": 20},
        ]
        result = compute_signal_accuracy_by_type(closes, signals, horizons=(5,))
        assert "1sell" in result["by_type"]
        h5 = result["by_type"]["1sell"]["horizons"]["5"]
        assert h5["count"] == 2
        assert h5["hit_rate"] == pytest.approx(1.0)

    def test_multiple_types(self) -> None:
        """多种信号类型应分别统计。"""
        closes = [100 + i * 0.5 for i in range(80)]
        signals = [
            {"type": "1buy", "bar_index": 5},
            {"type": "2buy", "bar_index": 15},
            {"type": "3buy", "bar_index": 25},
            {"type": "1sell", "bar_index": 40},
        ]
        result = compute_signal_accuracy_by_type(closes, signals, horizons=(5, 10))
        assert set(result["by_type"].keys()) == {"1buy", "2buy", "3buy", "1sell"}
        assert len(result["ranking"]) == 4

    def test_bar_index_out_of_range(self) -> None:
        """越界的 bar_index 应被跳过。"""
        closes = [100.0] * 30
        signals = [
            {"type": "1buy", "bar_index": 28},  # 超出 horizons=5 的范围
            {"type": "1buy", "bar_index": 10},  # 有效
        ]
        result = compute_signal_accuracy_by_type(closes, signals, horizons=(5,))
        assert result["by_type"]["1buy"]["horizons"]["5"]["count"] == 1

    def test_ranking_sorted_by_excess(self) -> None:
        """排名应按超额命中率降序排列。"""
        closes = [100 + i for i in range(60)]
        buys = [{"type": "1buy", "bar_index": i * 10} for i in range(1, 5)]
        sells = [{"type": "1sell", "bar_index": i * 10} for i in range(1, 5)]
        mixed = [
            {"type": "2buy", "bar_index": 5},
            {"type": "2buy", "bar_index": 15},
        ]
        result = compute_signal_accuracy_by_type(closes, buys + sells + mixed, horizons=(5,))
        assert len(result["ranking"]) >= 1
        for r in result["ranking"]:
            assert "verdict" in r

    def test_summary_present(self) -> None:
        """结果应包含总体结论。"""
        closes = [100 + i for i in range(60)]
        signals = [{"type": "1buy", "bar_index": 5}, {"type": "1buy", "bar_index": 15}]
        result = compute_signal_accuracy_by_type(closes, signals, horizons=(5,))
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 0
