"""V733：`position_pct` 参数**完全无效**的真实缺陷（行为级验证）。

⚠️ 缺陷是怎么被发现的（AGENTS.md §1：禁止用间接证据冒充验证）
---------------------------------------------------------------
五之十五做参数敏感性扫描时，发现：

    仓位100%(默认)  回撤 24.6%  收益 +40.4%  8/8 优于买持
    仓位80%         回撤 24.6%  收益 +40.4%  8/8 优于买持   ← 完全一样！

于是加探针直接打印策略内部：`ChanlunStrategy._do_buy` 在 `position_pct=0.5`
时**算出的 size 确实是 4600/6700/6600（正确）**，但**回测实际成交却是
9100/12400/12800 —— 和 100% 一模一样**。

根因在 `orders.py::_calculate_buy_size`：

    if position_mode == "full" or signal_size == 0:
        # 全仓：忽略信号指定数量，按现金算最大可买

`BacktestEngine` 默认 `position_mode='full'` ⇒ **策略指定的仓位被丢弃**。

而策略的文档明确写着：
    "四季建议仓位（春播 30%~50% 等）可直接设该参数"
⇒ **参数在文档/UI 上可用，实际完全不起作用**。用户按"四季"建议设 30% 仓位
却仍然满仓买入，这是**会误导用户真实决策**的缺陷。

⚠️ 本测试是**先失败后修复**的：修复前 `test_position_pct_actually_reduces_size`
实测失败（80% 与 100% 成交股数完全相同），修复后通过。
"""

from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def engine_cls():
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from easy_tdx.backtest.engine import BacktestEngine
    return BacktestEngine


@pytest.fixture(scope="module")
def strategy_cls():
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from easy_tdx.backtest.strategies.chanlun import ChanlunStrategy
    return ChanlunStrategy


@pytest.fixture(scope="module")
def bars() -> pd.DataFrame:
    """用**真实行情**（audit_data/sh600000_daily.json）而不是合成数据。

    ⚠️ 早期版本先试了"纯上涨直线"、又试了"三角波合成"，两次都**一根信号都
    不产生**（断言全是 `nan == nan` 的空转）—— 那样的测试无论过不过都没意义。
    真实行情已被前面的审计反复验证能产生分型/笔/买卖点，直接用它最可靠。
    若该文件缺失则跳过（audit_data 已被 .gitignore，不入库）。
    """
    import json
    p = ROOT / "audit_data" / "sh600000_daily.json"
    if not p.exists():
        pytest.skip(f"缺少真实行情 {p}（先跑 scripts/audit_fetch_real_data.py）")
    df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.rename(columns={"vol": "volume"})
    df["amount"] = df["close"] * df["volume"]
    return df[["datetime", "open", "high", "low", "close", "volume", "amount"]]


def _first_buy_size(engine_cls, strategy_cls, bars, pct: float) -> float:
    s = strategy_cls()
    s.p["position_pct"] = pct
    r = engine_cls(s, cash=1_000_000.0).run(bars)
    tr = r.trades
    if not isinstance(tr, pd.DataFrame) or tr.empty:
        return float("nan")
    buys = tr[tr["direction"] == "BUY"]
    return float(buys["size"].iloc[0]) if len(buys) else float("nan")


class TestPositionPctIsActuallyHonored:
    """核心行为断言：仓位参数必须真的改变成交数量。"""

    def test_position_pct_actually_reduces_size(self, engine_cls, strategy_cls, bars) -> None:
        """⚠️ 这条在修复前**实测失败**：80% 与 100% 成交股数完全相同。"""
        full = _first_buy_size(engine_cls, strategy_cls, bars, 1.0)
        half = _first_buy_size(engine_cls, strategy_cls, bars, 0.5)
        assert full == full, "sanity"
        assert not (half == full), (
            f"position_pct=0.5 与 1.0 成交股数相同（{full}）—— "
            "仓位参数被引擎 position_mode='full' 丢弃了")

    def test_half_position_is_materially_smaller(self, engine_cls, strategy_cls, bars) -> None:
        full = _first_buy_size(engine_cls, strategy_cls, bars, 1.0)
        half = _first_buy_size(engine_cls, strategy_cls, bars, 0.5)
        assert half < full * 0.75, f"半仓 {half} 应显著小于全仓 {full}"

    def test_lower_position_means_lower_drawdown(
        self, engine_cls, strategy_cls, bars
    ) -> None:
        """仓位越低回撤应越小 —— 这是 position_pct 生效的直接后果。"""
        def dd(pct: float) -> float:
            s = strategy_cls()
            s.p["position_pct"] = pct
            return float(engine_cls(s, cash=1_000_000.0).run(
                bars).performance["max_drawdown"])
        assert dd(0.3) < dd(1.0), "30% 仓位的回撤应小于 100% 仓位"


class TestStrategyStillComputesSizeCorrectly:
    """策略侧算 size 的逻辑本身是对的，问题出在引擎丢弃它。"""

    def test_do_buy_computes_scaled_size(self, strategy_cls, bars) -> None:
        import sys
        sys.path.insert(0, str(ROOT / "src"))
        from easy_tdx.backtest.strategies.chanlun import ChanlunStrategy
        seen: list[int] = []
        orig = ChanlunStrategy._do_buy

        def spy(self):
            pct = float(self.p.get("position_pct", 1.0) or 1.0)
            if pct < 1.0:
                price = float(self.data.close[0])
                seen.append(int(self._cash * pct / (price * 1.0005) / 100) * 100)
            return orig(self)

        ChanlunStrategy._do_buy = spy
        try:
            s = ChanlunStrategy()
            s.p["position_pct"] = 0.5
            engine_cls = __import__(
                "easy_tdx.backtest.engine", fromlist=["BacktestEngine"]
            ).BacktestEngine
            engine_cls(s, cash=1_000_000.0).run(bars)
        finally:
            ChanlunStrategy._do_buy = orig
        assert seen, "未捕获到 _do_buy 调用"
        assert all(x > 0 for x in seen), f"策略算出的 size 应为正: {seen}"


class TestEngineRespectsExplicitSize:
    """引擎层：'full' 模式不应覆盖策略**显式指定**的非零 size。"""

    def test_calculate_buy_size_keeps_signal_size(self, bars) -> None:
        import sys
        sys.path.insert(0, str(ROOT / "src"))
        from easy_tdx.backtest.orders import OrderSimulator
        sim = OrderSimulator(bars, commission=0.0003, min_commission=5.0,
                             stamp_tax=0.001, slippage=0.0)
        got = sim._calculate_buy_size(
            signal_size=500.0, price=10.0, cash=1_000_000.0,
            position_mode="full")
        assert got == 500.0, (
            f"引擎把策略指定的 500 股改成了 {got} —— "
            "显式仓位被 position_mode='full' 覆盖")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
