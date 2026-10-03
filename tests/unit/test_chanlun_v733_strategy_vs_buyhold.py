"""V733「策略 vs 买入持有」脚本的契约测试。

⚠️ 纪律：脚本本身也要被审计。
   本脚本记录了两次自我推翻（改默认值直觉错、"关掉更好"也不真），
   这里锁死这些结论不会被后来的改动悄悄抹掉。
"""

from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
SVB = SCRIPTS / "audit_strategy_vs_buyhold.py"


def _src() -> str:
    return SVB.read_text(encoding="utf-8")


class TestStrategyVsBuyholdScript:
    def test_script_present(self) -> None:
        assert SVB.exists(), f"缺少 {SVB}"

    def test_uses_real_backtest_engine(self) -> None:
        s = _src()
        assert "BacktestEngine" in s
        assert "ChanlunStrategy" in s

    def test_compares_against_buy_and_hold(self) -> None:
        """必须真的算买入持有，否则'跑赢'无从谈起。"""
        s = _src()
        assert "close" in s and "iloc[-1]" in s

    def test_reports_t_statistic(self) -> None:
        """只报平均超额是不够的 —— 必须报 t 统计判断显著性。"""
        s = _src()
        assert "t_stat" in s
        assert "sqrt" in s

    def test_does_not_tune_parameters(self) -> None:
        """用默认参数（不调优）是刻意的：避免把过拟合包装成策略有效。"""
        s = _src()
        assert "未调优" in s


class TestHonestyAboutLimitations:
    def test_declares_bet_not_neutralized(self) -> None:
        s = _src()
        assert "beta" in s.lower()
        assert "中性化" in s

    def test_declares_trade_log_lacks_signal_type(self) -> None:
        """实测 trades 只有 BUY/SELL，无法归因到具体信号 —— 必须写明。"""
        s = _src()
        assert "BUY/SELL" in s
        assert "无信号类型" in s

    def test_does_not_claim_defaults_should_change(self) -> None:
        """核心教训：证据不足时**不得**建议改默认值。"""
        s = _src()
        assert "不足以支持改默认值" in s

    def test_docstring_records_both_refutations(self) -> None:
        """两次自我推翻必须留在脚本里，否则后人重犯同样的错。"""
        s = _src()
        assert "直觉错" in s or "直觉是错的" in s
        assert "t≈0.7" in s or "t=+0.7" in s or "t≈0.71" in s


class TestExcludeIndex:
    def test_excludes_index_from_stock_universe(self) -> None:
        """指数不该和个股一起算"择时"（含 sh000001/sh000300）。"""
        s = _src()
        assert "EXCLUDE" in s
        assert "sh000300" in s


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
