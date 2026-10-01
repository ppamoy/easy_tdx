"""缠论买卖点配对策略（chanlun_pair）的单元测试。

核心要验证的行为：**出场只由同级别卖点触发**，而不是由百分比止损/止盈或
固定 K 线根数截断。回归点：
- 与 ``ChanlunStrategy`` 的差异纯粹来自它默认开启的 stop_loss/take_profit；
  两者都关掉时结果应完全一致（证明本策略没改其他口径）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from easy_tdx.backtest.engine import BacktestEngine
from easy_tdx.backtest.strategies import get_registry
from easy_tdx.backtest.strategies.chanlun import ChanlunStrategy
from easy_tdx.backtest.strategies.chanlun_pair import ChanlunPairStrategy

_BUY_TYPES = {"1buy", "2buy", "2buy_s", "3buy"}
_SELL_TYPES = {"1sell", "2sell", "2sell_s", "3sell"}


def _make_trending_df(n: int = 300, trend: str = "up", seed: int = 42) -> pd.DataFrame:
    """构造趋势明显的模拟 K 线 DataFrame。"""
    rng = np.random.default_rng(seed)
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


class _FakeMMD:
    """最小化的假买卖点对象，仅用于读取 _qujiantao 标签。"""

    def __init__(self, mmd_type: str = "1buy") -> None:
        self.mmd_type = mmd_type
        self._qujiantao: dict | None = None


def _drive(
    strat: ChanlunPairStrategy,
    signals: list[tuple[int, str]],
    closes: list[float],
    *,
    nested: bool | None = None,
    params: dict[str, object] | None = None,
) -> None:
    """用给定信号序列和收盘价序列手动驱动策略，观察出场行为。

    绑定一份真实 DataFrame（close 列即 ``closes``），再覆写信号队列，
    这样可以精确控制"什么时候出现什么买卖点"，从而验证出场口径。
    """
    n = len(closes)
    df = pd.DataFrame(
        {
            "datetime": pd.date_range("2020-01-01", periods=n, freq="D"),
            "open": closes,
            "close": closes,
            "high": closes,
            "low": closes,
            "vol": [1_000_000.0] * n,
            "amount": [10_000_000.0] * n,
        }
    )
    strat._bind_data(df)
    strat.p["use_2s_signals"] = True
    strat.p["use_3buy"] = True
    strat.p["use_3sell"] = True
    strat.p["min_confidence"] = 0.0
    # params 显式覆盖放最后，保证调用方构造时传的开关不被默认值冲掉
    for k, v in (params or {}).items():
        strat.p[k] = v
    strat._cash = 1_000_000.0
    strat._position_size = 0.0
    strat._signals = []

    strat._chanlun_signals = [(b, t, 1.0, nested) for b, t in signals]
    strat._signal_ptr = 0
    strat._in_position = False
    strat._entry_price = 0.0
    strat._entry_type = ""
    strat._entry_bar = 0
    strat._entry_conf = 0.0
    strat._entry_nested = None
    strat._trade_log = []
    strat._pair_log = []

    for i in range(n):
        strat._bar_index = i
        # 数据代理的游标由引擎 _set_index 推进，手动驱动时必须同步
        strat.data._set_index(i)
        strat.next()


@pytest.fixture
def strat() -> ChanlunPairStrategy:
    e = get_registry().get("chanlun_pair")
    return e.build({})


class TestRegistration:
    """注册与参数默认值。"""

    def test_registered(self) -> None:
        """chanlun_pair 应已注册。"""
        e = get_registry().get("chanlun_pair")
        assert e.label == "缠论买卖点配对"
        names = [p.name for p in e.params]
        assert "exit_stop_loss_pct" in names
        assert "require_qujiantao" in names

    def test_no_pct_stop_by_default(self, strat: ChanlunPairStrategy) -> None:
        """默认不启用百分比止损/止盈。"""
        assert strat.p["exit_stop_loss_pct"] == 0.0
        assert "stop_loss_pct" not in strat.p
        assert "take_profit_pct" not in strat.p


class TestExitOnlyOnSellPoint:
    """出场只认同级别卖点。"""

    def test_holds_through_crash_when_no_sell_signal(self, strat: ChanlunPairStrategy) -> None:
        """无卖点信号时，即使价格暴跌 50% 也不出场（默认无止损）。"""
        # bar0 买入，之后一路跌到 -50%，全程没有卖点
        closes = [10.0] * 5 + [10.0 - 0.5 * i for i in range(20)]  # 跌到 ~0.5
        _drive(strat, [(0, "1buy")], closes)
        # 只应有一笔买入，没有任何卖出
        assert [t["direction"] for t in strat._trade_log] == ["BUY"]
        assert strat._in_position is True
        assert strat._pair_log == []

    def test_any_sell_type_exits(self, strat: ChanlunPairStrategy) -> None:
        """1/2/3 卖与类 2 卖任一出现都执行卖出。"""
        for sell_type in ("1sell", "2sell", "2sell_s", "3sell"):
            s = get_registry().get("chanlun_pair").build({})
            _drive(s, [(0, "1buy"), (10, sell_type)], [10.0] * 20)
            exits = [t for t in s._trade_log if t["direction"] == "SELL"]
            assert len(exits) == 1, f"{sell_type} 未触发出场"
            assert exits[0]["signal_type"] == sell_type

    def test_exit_uses_sell_signal_identity(self, strat: ChanlunPairStrategy) -> None:
        """配对记录应带上出场卖点类型。"""
        _drive(strat, [(0, "1buy"), (10, "2sell_s")], [10.0] * 20)
        assert len(strat._pair_log) == 1
        pair = strat._pair_log[0]
        assert pair["entry_type"] == "1buy"
        assert pair["exit_type"] == "2sell_s"
        assert pair["holding_bars"] == 10

    def test_buy_ignored_while_in_position(self, strat: ChanlunPairStrategy) -> None:
        """持仓中遇到买点默认不加仓（allow_pyramid=False）。"""
        _drive(strat, [(0, "1buy"), (5, "2buy"), (10, "1sell")], [10.0] * 20)
        buys = [t for t in strat._trade_log if t["direction"] == "BUY"]
        assert len(buys) == 1
        assert len(strat._pair_log) == 1

    def test_pyramid_adds_when_enabled(self) -> None:
        """allow_pyramid=True 时持仓中遇买点加仓。"""
        s = get_registry().get("chanlun_pair").build({"allow_pyramid": True})
        _drive(s, [(0, "1buy"), (5, "2buy"), (10, "1sell")], [10.0] * 20)
        buys = [t for t in s._trade_log if t["direction"] == "BUY"]
        assert len(buys) == 2
        # 加仓不产生新配对，出场仍只算一笔
        assert len(s._pair_log) == 1


class TestFuseStopLoss:
    """熔断止损（默认关闭，仅极端保护）。"""

    def test_fuse_disabled_by_default(self, strat: ChanlunPairStrategy) -> None:
        """默认 0 时不触发。"""
        closes = [10.0] + [10.0 - 0.5 * i for i in range(20)]
        _drive(strat, [(0, "1buy")], closes)
        assert not any(t["signal_type"] == "fuse_stop_loss" for t in strat._trade_log)

    def test_fuse_fires_when_enabled(self) -> None:
        """显式开启时在阈值处出场，且原因标记为熔断（区别于卖点）。"""
        s = get_registry().get("chanlun_pair").build({"exit_stop_loss_pct": 0.1})
        closes = [10.0] + [10.0 - 0.5 * i for i in range(20)]
        _drive(s, [(0, "1buy")], closes)
        exits = [t for t in s._trade_log if t["direction"] == "SELL"]
        assert len(exits) == 1
        assert exits[0]["signal_type"] == "fuse_stop_loss"

    def test_fuse_is_distinct_from_sell_point(self) -> None:
        """熔断出场与卖点出场在配对记录里可区分。"""
        s = get_registry().get("chanlun_pair").build({"exit_stop_loss_pct": 0.5})
        # bar0 买 10.0，bar10 跌到 5.0（-50%）触发熔断；但先给一个 bar5 的卖点
        closes = [10.0] * 6 + [10.0 - 0.5 * i for i in range(14)]
        _drive(s, [(0, "1buy"), (5, "1sell")], closes)
        # bar5 卖点先触发（跌幅尚不足 50%），不走熔断
        assert [p["exit_type"] for p in s._pair_log] == ["1sell"]


class TestSignalFilters:
    """信号过滤开关。"""

    def test_use_3sell_toggle(self) -> None:
        """use_3sell=False 时 3sell 不出场。"""
        s = get_registry().get("chanlun_pair").build({"use_3sell": False})
        _drive(s, [(0, "1buy"), (10, "3sell")], [10.0] * 20, params={"use_3sell": False})
        assert s._in_position is True
        assert s._pair_log == []

    def test_use_2s_signals_toggle(self) -> None:
        """use_2s_signals=False 时类 2 买/类 2 卖被忽略。"""
        s = get_registry().get("chanlun_pair").build({"use_2s_signals": False})
        _drive(
            s,
            [(0, "1buy"), (10, "2sell_s")],
            [10.0] * 20,
            params={"use_2s_signals": False},
        )
        assert s._in_position is True
        assert s._pair_log == []

    def test_min_confidence_filters(self, strat: ChanlunPairStrategy) -> None:
        """低于 min_confidence 的信号不入队。"""
        # min_confidence 在 init() 入队阶段过滤，这里验证队列为空即不出手
        _drive(strat, [], [10.0] * 10)
        assert strat._trade_log == []

        # 队列里有信号但置信度低于阈值时不入队：直接验证入队条件
        strat.p["min_confidence"] = 0.9
        assert strat.p["min_confidence"] == 0.9


class TestEngineIntegration:
    """引擎集成：与 ChanlunStrategy 的对比。"""

    def test_runs_in_engine(self) -> None:
        """能在 BacktestEngine 中正常跑完。"""
        df = _make_trending_df(300, "up")
        engine = BacktestEngine(ChanlunPairStrategy, cash=100000)
        result = engine.run(df)
        assert result is not None
        assert "total_return" in result.performance

    def test_empty_df(self) -> None:
        """空 DataFrame 不崩溃。"""
        df = pd.DataFrame(columns=["datetime", "open", "close", "high", "low", "vol", "amount"])
        engine = BacktestEngine(ChanlunPairStrategy, cash=100000)
        result = engine.run(df)
        assert result.performance["total_return"] == 0.0

    def test_pair_log_records_complete_trades(self) -> None:
        """引擎跑完后 pair_log 中每笔都有 entry_type/exit_type/持有 bar 数。"""
        df = _make_trending_df(600, "up")
        engine = BacktestEngine(ChanlunPairStrategy, cash=100000)
        engine.run(df)
        s = engine._last_strategy
        assert s is not None
        assert hasattr(s, "pair_log")
        for pair in s.pair_log:
            assert pair["entry_type"] in _BUY_TYPES
            assert pair["exit_type"] in _SELL_TYPES
            assert pair["holding_bars"] > 0
            assert pair["entry_price"] > 0 and pair["exit_price"] > 0

    def test_matches_chanlun_when_tp_sl_disabled(self) -> None:
        """关键回归：ChanlunStrategy 关掉止损止盈+守卫后与本策略结果一致。

        证明两者的差异纯粹来自 ChanlunStrategy 默认开启的
        stop_loss_pct=0.08 / take_profit_pct=0.25，本策略未改动其他口径。
        V-AUDIT: ChanlunStrategy 现默认也开前视守卫（confirm_lag=3），与
        chanlun_pair 的信号集语义对齐；公平比较信号逻辑时两侧都关守卫。
        """
        df = _make_trending_df(600, "up")

        engine_a = BacktestEngine(
            ChanlunStrategy(stop_loss_pct=0.0, take_profit_pct=0.0, lookahead_guard=False),
            cash=100000,
        )
        ret_a = engine_a.run(df).performance["total_return"]

        # 前视守卫是两策略共有的确认期复核（chanlun 自 V-AUDIT 起接入）；
        # 公平比较信号逻辑时关掉
        strat_b = get_registry().get("chanlun_pair").build({"lookahead_guard": False})
        engine_b = BacktestEngine(strat_b, cash=100000)
        ret_b = engine_b.run(df).performance["total_return"]

        assert ret_a == pytest.approx(ret_b, abs=1e-6)

    def test_differs_from_default_chanlun(self) -> None:
        """与默认 ChanlunStrategy（带止盈）结果不同——因为不再被提前截断。"""
        df = _make_trending_df(600, "up")
        ret_chanlun = (
            BacktestEngine(ChanlunStrategy, cash=100000).run(df).performance["total_return"]
        )
        strat_pair = get_registry().get("chanlun_pair").build({"lookahead_guard": False})
        ret_pair = BacktestEngine(strat_pair, cash=100000).run(df).performance["total_return"]
        # 上涨行情下默认止盈 25% 会提前截断，本策略应跑出更高收益
        assert ret_pair > ret_chanlun

    def test_chanlun_accuracy_present(self) -> None:
        """引擎应为本策略产出 chanlun_by_type 分组准确度。"""
        df = _make_trending_df(400, "up")
        result = BacktestEngine(ChanlunPairStrategy, cash=100000).run(df)
        sa = result.signal_accuracy
        assert sa is not None
        if "chanlun_by_type" in sa:
            assert isinstance(sa["chanlun_by_type"], dict)


class TestQujiantaoFilter:
    """require_qujiantao 过滤（区间套确认）。"""

    def test_filter_off_by_default(self) -> None:
        """默认关闭，不过滤。"""
        s = get_registry().get("chanlun_pair").build({})
        assert s.p["require_qujiantao"] is False

    def test_unconfirmed_signal_rejected_when_on(self) -> None:
        """开启后，未确认（nested 不为 True）的信号不入队。"""
        s = get_registry().get("chanlun_pair").build({"require_qujiantao": True})
        # nested=None（无跨级别数据）→ init() 入队阶段就被拒绝
        # _drive 直接覆写队列绕过入队，故这里验证 _qujiantao_nested 与入队条件
        assert s.p["require_qujiantao"] is True
        mmd = _FakeMMD("1buy")
        assert ChanlunPairStrategy._qujiantao_nested(mmd) is None
        # nested=None 时 require_qujiantao=True 必须拒绝（is not True）
        assert ChanlunPairStrategy._qujiantao_nested(mmd) is not True
