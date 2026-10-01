"""涨跌停成交约束测试（V-AUDIT 审计修复）。

A 股涨停当日无法买入、跌停当日无法卖出。修复前 OrderSimulator 在涨跌停
日照常按 next_open 撮合，系统性高估追涨/突破类策略的成交率与收益
（默认选股池恰为强势股，偏差叠加放大）。

口径：以成交 bar 前一根收盘为基准，成交价 ≥ 前收×(1+pct) 为涨停（禁买），
≤ 前收×(1-pct) 为跌停（禁卖）。拒绝的成交记 rejected=True。
"""

from __future__ import annotations

import pandas as pd
import pytest

from easy_tdx.backtest.engine import BacktestEngine
from easy_tdx.backtest.orders import OrderSimulator
from easy_tdx.backtest.strategy import Strategy
from easy_tdx.backtest.types import Signal

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _limit_df() -> pd.DataFrame:
    """手工构造含一字涨停/跌停的行情：
    bar0 收 10.00（基准）→ bar1 一字涨停 11.00（+10%）→ bar2 正常 10.50
    → bar3 正常 10.20 → bar4 一字跌停 9.18（-10%）。
    """
    return pd.DataFrame(
        {
            "datetime": [20240101 + i for i in range(5)],
            "open": [10.00, 11.00, 10.50, 10.20, 9.18],
            "high": [10.20, 11.00, 10.60, 10.30, 9.18],
            "low": [9.90, 11.00, 10.40, 10.10, 9.18],
            "close": [10.00, 11.00, 10.50, 10.20, 9.18],
            "vol": [1e6] * 5,
            "amount": [1e7] * 5,
        }
    )


class TestPriceLimit:
    def test_buy_rejected_on_limit_up(self) -> None:
        """涨停 bar（次根一字板开盘）买入必须被拒绝。"""
        sim = OrderSimulator(_limit_df(), execution="next_open")
        trades = sim.simulate(
            signals=[Signal(datetime=20240101, direction="BUY", size=0)],
            cash=100000.0,
            position=0.0,
        )
        assert len(trades) == 1
        # 成交价 11.00 == 前收 10.00×1.1 → 涨停拒买
        assert trades[0].rejected is True
        assert trades[0].size == 0.0

    def test_buy_allowed_on_normal_bar(self) -> None:
        """普通 bar 买入照常成交（对照组：约束不过度）。"""
        sim = OrderSimulator(_limit_df(), execution="next_open")
        # 信号在 bar1，成交在 bar2（开盘 10.50 < 前收 11.00×1.1）→ 正常
        trades = sim.simulate(
            signals=[Signal(datetime=20240102, direction="BUY", size=0)],
            cash=100000.0,
            position=0.0,
        )
        assert len(trades) == 1
        assert trades[0].rejected is False
        assert trades[0].price == pytest.approx(10.50)

    def test_sell_rejected_on_limit_down(self) -> None:
        """跌停 bar 卖出必须被拒绝。"""
        sim = OrderSimulator(_limit_df(), execution="next_open")
        # 信号在 bar2，成交在 bar3？bar3 开盘 10.20，前收 10.50 → -2.9%，正常。
        # 信号在 bar3，成交在 bar4：开盘 9.18 == 前收 10.20×0.9 → 跌停拒卖
        trades = sim.simulate(
            signals=[Signal(datetime=20240104, direction="SELL", size=0)],
            cash=0.0,
            position=1000.0,
        )
        assert len(trades) == 1
        assert trades[0].rejected is True
        assert trades[0].size == 0.0

    def test_limit_disabled_restores_old_behavior(self) -> None:
        """关掉约束（respect_price_limit=False）后涨跌停日照常成交（开关两侧）。"""
        sim = OrderSimulator(_limit_df(), execution="next_open", respect_price_limit=False)
        trades = sim.simulate(
            signals=[Signal(datetime=20240101, direction="BUY", size=0)],
            cash=100000.0,
            position=0.0,
        )
        assert len(trades) == 1
        assert trades[0].rejected is False
        assert trades[0].price == pytest.approx(11.00)

    def test_limit_pct_custom(self) -> None:
        """自定义幅度（如 20% 创业板口径）：+10% 不再视为涨停。"""
        sim = OrderSimulator(_limit_df(), execution="next_open", limit_pct=0.20)
        trades = sim.simulate(
            signals=[Signal(datetime=20240101, direction="BUY", size=0)],
            cash=100000.0,
            position=0.0,
        )
        assert trades[0].rejected is False

    def test_engine_forwards_limit_params(self) -> None:
        """Engine 参数透传：涨跌停约束默认在整条链路生效。"""
        df = _limit_df()

        class AlwaysBuyStrategy(Strategy):
            """每根 bar 都发全仓买入信号（engine 转次根成交）。"""

            def init(self) -> None:
                pass

            def next(self) -> None:
                self.buy()

        engine = BacktestEngine(AlwaysBuyStrategy, cash=100000)
        result = engine.run(df)
        # bar1 是涨停 bar：bar0 的买入信号延迟到 bar1 成交必须被拒
        # （result.trades 是 DataFrame，rejected 列为 bool）
        assert "rejected" in result.trades.columns
        assert result.trades["rejected"].any()

    def test_first_bar_no_constraint(self) -> None:
        """首根 bar 无前收基准，不约束（边界）。"""
        df = _limit_df()
        sim = OrderSimulator(df, execution="next_open")
        # 直接在 bar0 成交（首根，无前收）：用限价单路径在当根成交
        trades = sim.simulate(
            signals=[Signal(datetime=20240101, direction="BUY", size=100, price=10.0)],
            cash=100000.0,
            position=0.0,
        )
        assert trades[0].rejected is False
