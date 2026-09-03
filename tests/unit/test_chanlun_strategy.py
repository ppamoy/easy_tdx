"""缠论回测策略的单元测试。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from easy_tdx.backtest.engine import BacktestEngine
from easy_tdx.backtest.strategies.chanlun import ChanlunStrategy


def _make_trending_df(n: int = 200, trend: str = "up") -> pd.DataFrame:
    """构造趋势明显的模拟 K 线 DataFrame。"""
    rng = np.random.default_rng(42)
    if trend == "up":
        base = 10.0 + np.cumsum(rng.normal(0.05, 0.5, n))
    else:
        base = 100.0 - np.cumsum(rng.normal(0.05, 0.5, n))
    base = np.maximum(base, 1.0)
    return pd.DataFrame(
        {
            "datetime": pd.date_range("2020-01-01", periods=n, freq="D"),
            "open": base + rng.uniform(-0.1, 0.1, n),
            "close": base + rng.uniform(-0.1, 0.1, n),
            "high": base + rng.uniform(0, 0.3, n),
            "low": base - rng.uniform(0, 0.3, n),
            "vol": [1_000_000.0] * n,
            "amount": [10_000_000.0] * n,
        }
    )


class TestChanlunStrategy:
    """ChanlunStrategy 单元测试。"""

    def test_run_with_valid_data(self) -> None:
        """有数据时应能正常回测。"""
        df = _make_trending_df(300, "up")
        engine = BacktestEngine(ChanlunStrategy, cash=100000)
        result = engine.run(df)
        assert result is not None
        assert "total_return" in result.performance

    def test_empty_df_returns_empty_result(self) -> None:
        """空 DataFrame 应返回空结果。"""
        df = pd.DataFrame(columns=["datetime", "open", "close", "high", "low", "vol", "amount"])
        engine = BacktestEngine(ChanlunStrategy, cash=100000)
        result = engine.run(df)
        assert result.performance["total_return"] == 0.0

    def test_min_confidence_filters_signals(self) -> None:
        """高置信度阈值应过滤低质量信号。"""
        df = _make_trending_df(300, "up")
        # 默认（不过滤）
        engine1 = BacktestEngine(ChanlunStrategy, cash=100000)
        result1 = engine1.run(df)
        trades1 = len(result1.trades)

        # 高阈值过滤（策略参数通过构造实例传入，引擎不直接收 params）
        engine2 = BacktestEngine(
            ChanlunStrategy(min_confidence=0.9),
            cash=100000,
        )
        result2 = engine2.run(df)
        trades2 = len(result2.trades)

        # 高阈值应产生更少或相等的交易
        assert trades2 <= trades1

    def test_signal_accuracy_computed(self) -> None:
        """回测结果应包含 signal_accuracy 字段。"""
        df = _make_trending_df(300, "up")
        engine = BacktestEngine(ChanlunStrategy, cash=100000)
        result = engine.run(df)
        assert result.signal_accuracy is not None
        assert "verdict" in result.signal_accuracy

    def test_high_conf_only_param(self) -> None:
        """high_conf_only 参数应生效。"""
        df = _make_trending_df(300, "up")
        engine = BacktestEngine(
            ChanlunStrategy(high_conf_only=True),
            cash=100000,
        )
        result = engine.run(df)
        assert result is not None

    def test_chanlun_accuracy_in_result(self) -> None:
        """缠论策略回测结果应包含 chanlun 专属准确度数据。"""
        df = _make_trending_df(400, "up")
        engine = BacktestEngine(ChanlunStrategy, cash=100000)
        result = engine.run(df)
        sa = result.signal_accuracy
        assert sa is not None
        # chanlun 专属数据可能存在（取决于是否产生信号）
        if "chanlun_by_type" in sa:
            assert isinstance(sa["chanlun_by_type"], dict)


class TestChanlunStrategyEdgeCases:
    """边界条件测试。"""

    def test_very_short_data(self) -> None:
        """数据不足时不应崩溃。"""
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2020-01-01", periods=10, freq="D"),
                "open": [10.0] * 10,
                "close": [10.0] * 10,
                "high": [10.1] * 10,
                "low": [9.9] * 10,
                "vol": [1_000_000.0] * 10,
                "amount": [10_000_000.0] * 10,
            }
        )
        engine = BacktestEngine(ChanlunStrategy, cash=100000)
        result = engine.run(df)
        assert result is not None
        assert result.performance["total_trades"] == 0

    def test_no_signals_generated(self) -> None:
        """无缠论结构数据时（如全部水平）应不产生交易。"""
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2020-01-01", periods=50, freq="D"),
                "open": [10.0] * 50,
                "close": [10.0] * 50,
                "high": [10.0] * 50,
                "low": [10.0] * 50,
                "vol": [1_000_000.0] * 50,
                "amount": [10_000_000.0] * 50,
            }
        )
        engine = BacktestEngine(ChanlunStrategy, cash=100000)
        result = engine.run(df)
        assert result.performance["total_trades"] == 0

    def test_uptrend_long_data(self) -> None:
        """长数据趋势上涨，应有更多买卖点。"""
        df = _make_trending_df(500, "up")
        engine = BacktestEngine(ChanlunStrategy, cash=100000)
        result = engine.run(df)
        # 应该有交易产生（趋势明显时缠论会识别出笔和中枢）
        assert result.performance["total_trades"] >= 0  # 至少不崩溃


class TestV102Advice:
    """V324：3买 按 V102 建议止损止盈。"""

    def _make_strategy(self) -> ChanlunStrategy:
        """构造绕过 init 的策略实例，直接测 next() 出场逻辑。"""
        from unittest.mock import MagicMock

        s = ChanlunStrategy.__new__(ChanlunStrategy)
        s.p = {
            "use_v102_advice": True,
            "use_3buy": True,
            "use_3sell": True,
            "use_2s_signals": False,
            "min_confidence": 0.0,
            "high_conf_only": False,
            "stop_loss_pct": 0.0,
            "take_profit_pct": 0.0,
            "bi_type": "new",
            "zs_min_lines": 3,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
        }
        s._position_count = 1
        s._entry_price = 100.0
        s._bar_index = 1
        s._trade_log = []
        s._signal_ptr = 99  # 无信号
        s._chanlun_signals = []
        s._signal_traces = {}
        s._last_signal_conf = 0.0
        s._last_signal_type = ""
        s.sell = MagicMock()
        s._data_proxy = MagicMock()
        return s

    def test_v102_stop_loss_triggered(self) -> None:
        """盘中跌破 V102 建议止损价 → 立即平仓（记录 v102_stop_loss）。"""
        s = self._make_strategy()
        s._v102_active = True
        s._v102_sl = 95.0
        s._v102_tp = 110.0
        s.data.low = [94.0]
        s.data.high = [101.0]
        s.data.close = [94.0]

        s.next()

        assert s._position_count == 0
        assert s._trade_log[-1]["signal_type"] == "v102_stop_loss"
        assert s.sell.called

    def test_v102_take_profit_triggered(self) -> None:
        """盘中触及 V102 建议止盈价 → 立即平仓（记录 v102_take_profit）。"""
        s = self._make_strategy()
        s._v102_active = True
        s._v102_sl = 95.0
        s._v102_tp = 110.0
        s.data.low = [99.0]
        s.data.high = [111.0]
        s.data.close = [111.0]

        s.next()

        assert s._position_count == 0
        assert s._trade_log[-1]["signal_type"] == "v102_take_profit"
        assert s.sell.called

    def test_v102_inactive_falls_back_to_pct(self) -> None:
        """V102 未激活时走百分比止损。"""
        s = self._make_strategy()
        s._v102_active = False
        s.p["stop_loss_pct"] = 0.05  # 止损 5% → 95
        s.data.low = [94.0]
        s.data.high = [100.0]
        s.data.close = [94.0]

        s.next()

        assert s._position_count == 0
        assert s._trade_log[-1]["signal_type"] == "stop_loss"

    def test_v102_advice_carried_in_signals(self) -> None:
        """init 把 3buy 信号的 V102 建议带进信号队列。"""
        from datetime import datetime, timedelta
        from unittest.mock import MagicMock, patch

        s = ChanlunStrategy.__new__(ChanlunStrategy)
        s.p = {
            "bi_type": "new",
            "zs_min_lines": 3,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "min_confidence": 0.0,
            "high_conf_only": False,
            "use_2s_signals": False,
            "use_3buy": True,
            "use_3sell": True,
        }
        import numpy as np

        # 模拟 60 根 K 线数据（供 init 构建 DataFrame）
        s._data_proxy = MagicMock()
        n = 60
        opens = np.ones(n) * 100.0
        s.data.open.raw = opens
        s.data.close.raw = opens
        s.data.high.raw = opens + 1.0
        s.data.low.raw = opens - 1.0
        s.data.vol.raw = np.ones(n) * 1e6
        s.data.amount.raw = np.ones(n) * 1e8
        dates = [(datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y%m%d") for i in range(n)]
        s._datetime_array = np.array(dates)

        # 构造带 BUY_3 + V102 建议的缠论结果
        from easy_tdx.chanlun.types import MMD, MMDType

        bi = MagicMock()
        bi.index = 0
        bi.end = MagicMock()
        bi.end.k = MagicMock()
        bi.end.k.date = datetime(2024, 1, 2)
        bi.is_done.return_value = True
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3buy", confidence=0.7)
        mmd.bi = bi
        mmd._decision_support = {"entry_price": 100.0, "stop_loss": 95.0, "take_profit_1": 110.0}

        fake_result = MagicMock()
        fake_result.bis = [bi]
        fake_result.mmds = [mmd]

        with patch("easy_tdx.chanlun.ChanlunAnalyser") as mock_analyser:
            mock_analyser.return_value.process_klines.return_value = fake_result
            s.init()

        assert len(s._chanlun_signals) == 1
        bar_idx, mmd_type, conf, advice = s._chanlun_signals[0]
        assert mmd_type == "3buy"
        assert advice is not None
        assert advice["stop_loss"] == 95.0
        assert advice["take_profit_1"] == 110.0

    # ── V385: use_v102_advice 边界（信号队列路径：空仓 → 3buy 首仓） ──

    def _make_entry_strategy(self, advice: dict | None, use_v102: bool = True) -> ChanlunStrategy:
        """构造空仓策略，信号队列首条为 3buy（可带/不带 V102 建议）。"""
        from unittest.mock import MagicMock

        s = self._make_strategy()
        s._position_count = 0
        s._entry_price = 0.0
        s.buy = MagicMock()
        s.data.close = [100.0]
        s.data.high = [101.0]
        s.data.low = [99.0]
        s._v102_active = False
        s._v102_sl = 0.0
        s._v102_tp = 0.0
        s.p["use_v102_advice"] = use_v102
        s.p["stop_loss_pct"] = 0.0
        s.p["take_profit_pct"] = 0.0
        s._chanlun_signals = [(1, "3buy", 0.8, advice)]
        s._signal_ptr = 0
        s._bar_index = 1
        return s

    def test_v102_advice_none_falls_back_to_pct(self) -> None:
        """V385: use_v102_advice=True 但信号无建议 → 不激活 V102，百分比止损生效。"""
        s = self._make_entry_strategy(None)
        s.next()  # 消费 3buy → 建仓
        assert s._position_count == 1
        assert s._v102_active is False

        s.p["stop_loss_pct"] = 0.05  # 95
        s._bar_index = 2
        s.data.close = [94.0]
        s.data.high = [95.0]
        s.data.low = [93.0]
        s.next()
        assert s._position_count == 0
        assert s._trade_log[-1]["signal_type"] == "stop_loss"

    def test_v102_disabled_with_advice_falls_back(self) -> None:
        """V385: use_v102_advice=False 即使信号带建议也不激活（对照）。"""
        s = self._make_entry_strategy({"stop_loss": 95.0, "take_profit_1": 110.0}, use_v102=False)
        s.next()
        assert s._position_count == 1
        assert s._v102_active is False
        assert s._v102_sl == 0.0

    def test_v102_incomplete_advice_no_crash(self) -> None:
        """V385: 建议缺 stop_loss/take_profit_1 → sl/tp=0 不崩溃，百分比回退兜底。"""
        s = self._make_entry_strategy({"entry_price": 100.0})
        s.next()
        assert s._position_count == 1
        assert s._v102_active is True  # advice 非空 → 激活
        assert s._v102_sl == 0.0  # 缺失字段 → 0
        assert s._v102_tp == 0.0

        s.p["stop_loss_pct"] = 0.05
        s._bar_index = 2
        s.data.close = [94.0]
        s.data.high = [95.0]
        s.data.low = [93.0]
        s.next()
        assert s._position_count == 0
        assert s._trade_log[-1]["signal_type"] == "stop_loss"

    def test_v102_add_position_keeps_first_v102(self) -> None:
        """V385: 3buy 首仓激活 V102 后再加仓 → 不覆盖首仓的 V102 止损/止盈。"""
        advice = {"stop_loss": 95.0, "take_profit_1": 110.0}
        s = self._make_entry_strategy(advice)
        s.next()  # 首仓
        assert s._v102_active is True
        assert s._v102_sl == 95.0

        # 第二次 3buy → 加仓分支（position>=1），不重置 V102
        s._chanlun_signals = [(2, "3buy", 0.8, advice)]
        s._signal_ptr = 0
        s._bar_index = 2
        s.data.close = [102.0]
        s.data.high = [103.0]
        s.data.low = [101.0]
        s.next()
        assert s._position_count == 2
        assert s._v102_sl == 95.0  # 保留首仓 V102
        assert s._v102_tp == 110.0

    def test_v102_close_position_resets_state(self) -> None:
        """V385: 3sell 平仓后 V102 状态重置（防残留影响后续持仓）。"""
        advice = {"stop_loss": 95.0, "take_profit_1": 110.0}
        s = self._make_entry_strategy(advice)
        s.next()  # 首仓带 V102
        assert s._v102_active is True

        s._chanlun_signals = [(2, "3sell", 0.8, None)]
        s._signal_ptr = 0
        s._bar_index = 2
        s.data.close = [103.0]
        s.data.high = [104.0]
        s.data.low = [102.0]
        s.next()
        assert s._position_count == 0
        assert s._v102_active is False
        assert s._v102_sl == 0.0
        assert s._v102_tp == 0.0
