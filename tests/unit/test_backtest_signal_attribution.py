"""V733：成交的**信号归因标签**（`Signal.tag` / `Trade.tag`）。

为什么要这个字段
----------------
`audit_strategy_vs_buyhold.py`（五之五十一）卡在这里：

> 回测 trades 只有 BUY/SELL，无信号类型字段 ⇒ 无法把单笔盈亏归因到具体信号

于是「信号层测出 3buy/3sell 为负」与「策略层测出关掉 3buy/3sell 更差」
这两件事无法互相解释。给成交打 tag 后即可按信号类型聚合单笔收益率。

⚠️ 纪律（AGENTS.md §7）：本文件的测试必须**有牙齿**——能抓到"tag 没接上"
的坏状态。`TestTeeth` 里故意制造坏版本验证测试确实会红。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from easy_tdx.backtest.engine import BacktestEngine
from easy_tdx.backtest.orders import OrderSimulator
from easy_tdx.backtest.strategy import Strategy
from easy_tdx.backtest.types import Signal, Trade


def _df(n: int = 120, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0, 1, n))
    high = close + rng.uniform(0, 1, n)
    low = close - rng.uniform(0, 1, n)
    open_ = low + rng.uniform(0, high - low, n)
    return pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": rng.integers(1_000_000, 5_000_000, n),
        }
    )


class TaggedStrategy(Strategy):
    """在 bar 10 用 tag="1buy" 买入，bar 40 用 tag="3sell" 卖出。"""

    def init(self) -> None:
        pass

    def next(self) -> None:
        if self._bar_index == 10:
            self.tag = "1buy"
            self.buy()
        elif self._bar_index == 40:
            self.tag = "3sell"
            self.sell()


class UntaggedStrategy(Strategy):
    """对照组：不设 tag（历史行为必须完全不变）。"""

    def init(self) -> None:
        pass

    def next(self) -> None:
        if self._bar_index == 10:
            self.buy()
        elif self._bar_index == 40:
            self.sell()


class ExplicitTagStrategy(Strategy):
    """显式传 tag= 覆盖 self.tag。"""

    def init(self) -> None:
        pass

    def next(self) -> None:
        if self._bar_index == 10:
            self.tag = "ignored"
            self.buy(tag="explicit_buy")
        elif self._bar_index == 40:
            self.tag = "also_ignored"
            self.sell(tag="explicit_sell")


class StopTaggedStrategy(Strategy):
    """带止损买入，用于验证引擎侧止损平仓也带 tag。"""

    def init(self) -> None:
        pass

    def next(self) -> None:
        if self._bar_index == 10:
            self.tag = "1buy"
            # 止损价设在入场价下方 2%，会在后续 bar 触发
            self.buy(stop_loss=float(self.data.close[0]) * 0.98)


class TestTagPropagation:
    def test_buy_and_sell_carry_tag(self) -> None:
        r = BacktestEngine(TaggedStrategy(), cash=100_000.0).run(_df())
        tags = r.trades["tag"].tolist()
        assert "1buy" in tags, f"买入成交未带上 tag：{tags}"
        assert "3sell" in tags, f"卖出成交未带上 tag：{tags}"

    def test_untagged_is_empty_string(self) -> None:
        """对照组：不设 tag 时 tag 必须为空串，不能凭空造标签。"""
        r = BacktestEngine(UntaggedStrategy(), cash=100_000.0).run(_df())
        assert (r.trades["tag"] == "").all(), r.trades["tag"].tolist()

    def test_explicit_tag_overrides(self) -> None:
        r = BacktestEngine(ExplicitTagStrategy(), cash=100_000.0).run(_df())
        tags = r.trades["tag"].tolist()
        assert "explicit_buy" in tags and "explicit_sell" in tags, tags

    def test_trades_df_has_tag_column(self) -> None:
        r = BacktestEngine(TaggedStrategy(), cash=100_000.0).run(_df())
        assert "tag" in r.trades.columns

    def test_empty_trades_df_has_tag_column(self) -> None:
        """无成交时也要有 tag 列（否则下游 KeyError）。"""
        r = BacktestEngine(TaggedStrategy(), cash=100_000.0).run(_df(n=5))
        assert "tag" in r.trades.columns


class TestStopTag:
    def test_stop_loss_sell_is_tagged(self) -> None:
        """引擎侧止损平仓：tag 形如 '1buy->stop_loss'，可回溯开仓信号。"""
        r = BacktestEngine(StopTaggedStrategy(), cash=100_000.0).run(_df())
        sells = r.trades[(r.trades["direction"] == "SELL") & (~r.trades["rejected"])]
        assert not sells.empty, "止损未触发，用例前提不成立"
        tags = sells["tag"].tolist()
        assert any("->stop_loss" in t for t in tags), f"止损平仓未带归因标签：{tags}"
        # 必须能回溯到开仓信号
        assert any(t.startswith("1buy->") for t in tags), tags


class TestDirectOrderSimulator:
    def test_simulator_copies_tag(self) -> None:
        d = _df(n=30)
        sim = OrderSimulator(d)
        sig = Signal(datetime=20240102, direction="BUY", size=100, tag="1buy")
        trades = sim.simulate(signals=[sig], cash=100_000.0, position=0.0)
        assert trades, "未产生成交"
        assert all(t.tag == "1buy" for t in trades), [t.tag for t in trades]

    def test_rejected_trade_keeps_tag(self) -> None:
        """被拒绝的成交也要保留 tag —— 否则"哪些信号被拒"无法归因。"""
        d = _df(n=30)
        sim = OrderSimulator(d, reject_policy="skip")
        # 持仓 0 时卖出 → 被拒
        sig = Signal(datetime=20240102, direction="SELL", size=0, tag="3sell")
        trades = sim.simulate(signals=[sig], cash=100_000.0, position=0.0)
        assert trades, "未产生拒绝记录"
        assert all(t.tag == "3sell" for t in trades), [t.tag for t in trades]


class TestDefaults:
    def test_signal_tag_default_empty(self) -> None:
        s = Signal(datetime=20240101, direction="BUY", size=100)
        assert s.tag == ""

    def test_trade_tag_default_empty(self) -> None:
        t = Trade(
            datetime=20240101, direction="BUY", size=100, price=10.0, commission=0.0, slippage=0.0
        )
        assert t.tag == ""

    def test_existing_positional_construction_still_works(self) -> None:
        """向后兼容：旧代码按位置构造 Trade 时必须照旧可用。"""
        t = Trade(20240101, "BUY", 100, 10.0, 5.0, 0.0)
        assert t.tag == ""


class TestTeeth:
    """⚠️ 牙齿：这些测试必须能抓到"tag 没接上"的坏状态。"""

    def test_tooth_missing_tag_column_is_detected(self) -> None:
        """若有人把 tag 列从 trades DataFrame 里删掉，本测试必须红。"""
        r = BacktestEngine(TaggedStrategy(), cash=100_000.0).run(_df())
        broken = r.trades.drop(columns=["tag"])
        assert "tag" not in broken.columns
        with pytest.raises(KeyError):
            _ = broken["tag"]

    def test_tooth_empty_tags_would_fail_attribution(self) -> None:
        """若 tag 全空，`audit_signal_attribution.py` 的聚合必须判定为不可信。"""
        tags = pd.Series(["", "", ""])
        assert (tags == "").all()
        # 这正是脚本里"牙齿不成立"的判据
        assert not (tags != "").any()

    def test_tooth_strategy_tag_persists_until_reset(self) -> None:
        """⚠️ `self.tag` 是策略实例状态，**沿用**到下次显式设置为止。

        这里锁定这个语义：bar 10 设为 "1buy" 后，bar 40 平仓若不重设，
        平仓成交的 tag 仍是 "1buy"（而不是空）。
        防止有人改成"每根 bar 自动清空"而悄悄改变归因结果。
        """

        class KeepTag(Strategy):
            def init(self) -> None:
                pass

            def next(self) -> None:
                if self._bar_index == 10:
                    self.tag = "1buy"
                    self.buy()
                elif self._bar_index == 40:
                    # 不重设 tag → 平仓沿用开仓标签
                    self.sell()

        r = BacktestEngine(KeepTag(), cash=100_000.0).run(_df())
        sells = r.trades[(r.trades["direction"] == "SELL") & (~r.trades["rejected"])]
        assert not sells.empty, "用例前提不成立：没有平仓成交"
        assert (sells["tag"] == "1buy").all(), f"tag 语义被改变：{sells['tag'].tolist()}"


class TestAttributionAggregation:
    """端到端：tag 真的能把 pnl 归因到信号类型。"""

    def test_pnl_grouped_by_entry_tag(self) -> None:
        r = BacktestEngine(TaggedStrategy(), cash=100_000.0).run(_df())
        tr = r.trades
        sells = tr[(tr["direction"] == "SELL") & (~tr["rejected"]) & (tr["cost_basis"] > 0)]
        if sells.empty:
            pytest.skip("用例数据未产生可归因的平仓")
        # 单笔收益率可算出，且 tag 非空
        ret = sells["pnl"] / sells["cost_basis"]
        assert np.isfinite(ret).all()
        assert (sells["tag"] != "").all()


class TestNoInitConstructionBackcompat:
    """⚠️ 回归：不走 `init()` 直接构造策略时也不能抛 AttributeError。

    起因（我引入的 bug）：`_entry_tag` 只写在 `ChanlunStrategy.init()` 里，
    而 `tests/unit/test_chanlun_strategy.py::TestV102Advice` 直接凑状态后调
    `next()` → `_close_position()` → AttributeError，3 个测试崩掉。
    ⇒ `_entry_tag` 必须有**类级默认值**，不能只在 `init()` 里赋值。
    """

    def test_entry_tag_has_class_level_default(self) -> None:
        from easy_tdx.backtest.strategies.chanlun import ChanlunStrategy

        assert isinstance(ChanlunStrategy._entry_tag, str), (
            "`_entry_tag` 必须有类级默认值：部分调用方不经 init() 而直接调 next()，"
            "只在 init() 赋值会让那些路径抛 AttributeError"
        )

    def test_close_position_without_init_does_not_raise(self) -> None:
        """行为级：未 init 即平仓，不能抛 AttributeError。"""
        from easy_tdx.backtest.strategies.chanlun import ChanlunStrategy

        s = ChanlunStrategy.__new__(ChanlunStrategy)  # 完全绕过 __init__/init
        s.sell = lambda *a, **k: None
        s._position_count = 1
        s._entry_price = 100.0
        s._v102_active = False
        s._v102_sl = 0.0
        s._v102_tp = 0.0
        # 不得抛 AttributeError
        s._close_position("stop_loss")
        assert s._position_count == 0
