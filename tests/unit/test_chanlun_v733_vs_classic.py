"""V733「缠论 vs 经典策略」脚本的契约测试。

⚠️ 纪律：只报"平均收益排名"会是**危险**的结论 ——
   n 小时排名极易被少数暴赚票决定。所以本测试锁死三件事：
   1. 必须报 t 统计（显著性），不能只排名；
   2. 必须同时报夏普（收益排名可能是运气）；
   3. 必须显式声明"n 小时排名不等于显著"。
"""

from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
CVC = SCRIPTS / "audit_chanlun_vs_classic.py"


def _src() -> str:
    return CVC.read_text(encoding="utf-8")


class TestChanlunVsClassicExists:
    def test_script_present(self) -> None:
        assert CVC.exists(), f"缺少 {CVC}"

    def test_includes_chanlun_and_classics(self) -> None:
        s = _src()
        assert "ChanlunStrategy" in s
        # 必须真的导入多个经典策略，而不是只跑缠论自比
        for cls in ("MaCrossStrategy", "MacdStrategy", "RsiReversalStrategy"):
            assert cls in s, f"未纳入对照策略 {cls}"

    def test_uses_same_cost_model(self) -> None:
        """所有策略必须走同一个 BacktestEngine（成本口径一致才可比）。"""
        s = _src()
        assert "BacktestEngine(" in s
        assert "cash=100000.0" in s


class TestReportsSignificance:
    """只报排名 = 拿排名冒充结论。"""

    def test_reports_t_statistic(self) -> None:
        s = _src()
        assert "t=" in s or "t(超额)" in s
        assert "sqrt" in s, "必须算 t 统计的 sqrt(n)"

    def test_reports_sharpe(self) -> None:
        assert "夏普" in _src(), "必须报夏普 —— 收益排名可能是运气"

    def test_flags_non_significance(self) -> None:
        s = _src()
        assert "统计上不显著" in s, "t<2 时必须明说不显著"

    def test_reports_win_rate_vs_buyhold(self) -> None:
        assert "跑赢买持" in _src()


class TestNoOverclaiming:
    def test_declares_not_out_of_sample(self) -> None:
        s = _src()
        assert "不是" in s and "样本外" in s, "必须声明本轮不是样本外结论"

    def test_declares_small_sample(self) -> None:
        s = _src()
        assert "n 有限" in s or "n 小时" in s

    def test_docstring_warns_rank_fragility(self) -> None:
        """排名在 n 小时极易被少数暴赚票决定 —— 这条必须留在脚本里。"""
        s = _src()
        assert "带偏" in s or "运气" in s or "暴赚" in s

    def test_discloses_default_params(self) -> None:
        s = _src()
        assert "默认参数" in s
        assert "未调优" in s

    def test_declares_no_beta_neutralization(self) -> None:
        assert "beta" in _src().lower() and "中性化" in _src()


class TestBenchmarkIndexAlignment:
    """⚠️ 实测踩过的坑：成功回测数 < 样本数时，逐元素相减会炸。

    早期版本 `backtest()` 只返回跑出结果的收益（如 3 条），却和
    全样本买入持有（30 条）相减 →
    `ValueError: operands could not be broadcast together with (3,) (30,)`。
    """

    def test_backtest_returns_index_subset(self) -> None:
        s = _src()
        assert "idx" in s, "backtest 必须回传成功样本的 index 子集"

    def test_uses_indexed_benchmark(self) -> None:
        s = _src()
        assert "bh[idx]" in s, "必须只和同一子集的买入持有比较"

    def test_docstring_records_the_crash(self) -> None:
        s = _src()
        assert "broadcast" in s, "这个坑必须留在脚本里，否则会重犯"


class TestNoDoubleBacktest:
    def test_single_pass_per_strategy(self) -> None:
        """早期版本分两趟跑（收益一趟、夏普一趟），慢一倍。"""
        s = _src()
        assert "sharpe_of" not in s, "应一次回测同时取收益与夏普"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
