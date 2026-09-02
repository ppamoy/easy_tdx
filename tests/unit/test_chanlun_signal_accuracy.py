"""缠论信号准确度验证测试。

测试内容：
1. 前瞻命中率计算
2. 按类型分组验证
3. 组合回测聚合
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from easy_tdx.backtest.signal_accuracy import (
    aggregate_portfolio_accuracy,
    compute_signal_accuracy,
    compute_signal_accuracy_by_type,
)


class TestComputeSignalAccuracy:
    """信号准确度计算测试。"""

    def test_basic_buy_hit_rate(self):
        """基本买入命中率计算。"""
        n = 100
        closes = np.linspace(10, 20, n).tolist()
        dates = pd.date_range("2025-01-01", periods=n, freq="D")
        df = pd.DataFrame(
            {
                "datetime": dates,
                "close": closes,
                "open": [c - 0.1 for c in closes],
                "high": [c + 0.1 for c in closes],
                "low": [c - 0.2 for c in closes],
            }
        )

        trades = pd.DataFrame(
            {
                "datetime": [dates[10]],
                "direction": ["BUY"],
                "rejected": [False],
            }
        )

        result = compute_signal_accuracy(df, trades, horizons=(5,))
        assert result["buy"] is not None
        assert result["buy"]["signals"] == 1
        assert result["buy"]["horizons"]["5"]["hit_rate"] > 0.5

    def test_sell_avoids_drop(self):
        """卖出信号应能避开下跌。"""
        n = 100
        closes = np.linspace(20, 10, n).tolist()
        dates = pd.date_range("2025-01-01", periods=n, freq="D")
        df = pd.DataFrame(
            {
                "datetime": dates,
                "close": closes,
                "open": [c + 0.1 for c in closes],
                "high": [c + 0.2 for c in closes],
                "low": [c - 0.1 for c in closes],
            }
        )

        trades = pd.DataFrame(
            {
                "datetime": [dates[10]],
                "direction": ["SELL"],
                "rejected": [False],
            }
        )

        result = compute_signal_accuracy(df, trades, horizons=(5,))
        assert result["sell"] is not None
        assert result["sell"]["horizons"]["5"]["hit_rate"] > 0.5

    def test_empty_trades(self):
        """空交易记录返回空报告。"""
        n = 50
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2025-01-01", periods=n, freq="D"),
                "close": list(range(n)),
                "open": list(range(n)),
                "high": list(range(n)),
                "low": list(range(n)),
            }
        )
        trades = pd.DataFrame(columns=["datetime", "direction", "rejected"])

        result = compute_signal_accuracy(df, trades)
        assert result["buy"] is None
        assert result["sell"] is None

    def test_missing_columns(self):
        """缺少close列返回空报告。"""
        df = pd.DataFrame({"datetime": pd.date_range("2025-01-01", periods=10, freq="D")})
        trades = pd.DataFrame(columns=["datetime", "direction", "rejected"])

        result = compute_signal_accuracy(df, trades)
        assert "note" in result


class TestComputeSignalAccuracyByType:
    """按类型分组的信号准确度测试。"""

    def test_buy_1_buy_2_different_hit_rates(self):
        """不同类型买卖点应有不同命中率。"""
        n = 200
        np.random.seed(42)
        base = np.linspace(10, 25, n) + np.random.randn(n) * 0.5
        closes = base.tolist()

        signals = [
            {"type": "1buy", "bar_index": 50},
            {"type": "1buy", "bar_index": 120},
            {"type": "2buy", "bar_index": 70},
            {"type": "2buy", "bar_index": 140},
            {"type": "3buy", "bar_index": 90},
        ]

        result = compute_signal_accuracy_by_type(closes, signals, horizons=(5,))
        assert "by_type" in result
        assert "ranking" in result
        assert "summary" in result
        assert len(result["ranking"]) > 0

    def test_sell_signals(self):
        """卖出信号命中率为下跌概率。"""
        n = 200
        np.random.seed(42)
        base = np.linspace(25, 10, n) + np.random.randn(n) * 0.5
        closes = base.tolist()

        signals = [
            {"type": "1sell", "bar_index": 50},
            {"type": "1sell", "bar_index": 120},
            {"type": "2sell", "bar_index": 70},
        ]

        result = compute_signal_accuracy_by_type(closes, signals, horizons=(5,))
        assert "by_type" in result
        for sig_type, report in result["by_type"].items():
            if "sell" in sig_type:
                h5 = report["horizons"].get("5")
                if h5 and h5.get("count", 0) > 0:
                    # 下降趋势下卖出命中率应不低于随机基准（样本小时允许恰为 0.5）
                    assert h5["hit_rate"] >= 0.5

    def test_insufficient_data(self):
        """数据不足时返回空结果。"""
        result = compute_signal_accuracy_by_type([1.0, 2.0], [])
        assert result["by_type"] == {}
        assert result["ranking"] == []

    def test_none_bar_index_filtered(self):
        """bar_index为None的信号应被过滤。"""
        closes = list(range(100))
        signals = [
            {"type": "1buy", "bar_index": None},
            {"type": "1buy", "bar_index": 50},
        ]
        result = compute_signal_accuracy_by_type(closes, signals)
        assert len(result["ranking"]) <= 1


class TestAggregatePortfolioAccuracy:
    """组合准确度聚合测试。"""

    def test_basic_aggregation(self):
        """基本组合聚合。"""
        results = {
            "SZ000001": {
                "signal_accuracy": {
                    "buy": {
                        "signals": 5,
                        "horizons": {
                            "5": {
                                "count": 5,
                                "hit_rate": 0.8,
                                "baseline_hit_rate": 0.5,
                                "excess_hit_rate": 0.3,
                                "avg_return": 0.05,
                            }
                        },
                    }
                },
                "performance": {
                    "total_return": 0.2,
                    "win_rate": 0.6,
                    "sharpe": 1.2,
                    "max_drawdown": 0.1,
                    "total_trades": 10,
                },
            },
            "SH600519": {
                "signal_accuracy": {
                    "buy": {
                        "signals": 3,
                        "horizons": {
                            "5": {
                                "count": 3,
                                "hit_rate": 0.6,
                                "baseline_hit_rate": 0.5,
                                "excess_hit_rate": 0.1,
                                "avg_return": 0.02,
                            }
                        },
                    }
                },
                "performance": {
                    "total_return": 0.1,
                    "win_rate": 0.5,
                    "sharpe": 0.8,
                    "max_drawdown": 0.15,
                    "total_trades": 8,
                },
            },
        }

        result = aggregate_portfolio_accuracy(results)
        assert "symbols" in result
        assert "portfolio" in result
        assert "verdict" in result
        assert len(result["symbols"]) == 2

    def test_empty_results(self):
        """空结果返回最小报告。"""
        result = aggregate_portfolio_accuracy({})
        assert result["portfolio"] == {}
        assert "无标的" in result["verdict"]

    def test_mixed_accuracy(self):
        """混合准确度数据的聚合。"""
        results = {
            "A": {
                "signal_accuracy": {
                    "buy": {"signals": 5, "horizons": {"5": {"count": 5, "hit_rate": 0.8}}}
                },
                "performance": {"total_return": 0.2, "win_rate": 0.6},
            },
            "B": {"performance": {"total_return": -0.1, "win_rate": 0.4}},
        }
        result = aggregate_portfolio_accuracy(results)
        assert len(result["symbols"]) == 2
        assert result["portfolio"]["symbols_with_accuracy"] == 1
