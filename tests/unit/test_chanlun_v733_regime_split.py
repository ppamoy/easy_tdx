"""V733「中位数口径 + 分行情」脚本的契约测试。

⚠️ 背景：五之十三用 t 检验（均值口径）得出"所有策略 t 均为负"，但我发现
买持**均值 +34.9% / 中位 −2.3%** —— 少数暴涨票主导均值，t 检验因此系统性
压低所有策略的超额。五之十三已明确写"本轮未做公平检验"，本脚本补上。

本测试锁死：不能退回只用均值口径、必须做符号检验、必须声明分组有 look-ahead。
"""

from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
RS = SCRIPTS / "audit_regime_split.py"


def _src() -> str:
    return RS.read_text(encoding="utf-8")


class TestRegimeSplitExists:
    def test_script_present(self) -> None:
        assert RS.exists(), f"缺少 {RS}"

    def test_compares_against_buyhold(self) -> None:
        s = _src()
        assert "close" in s and "iloc[-1]" in s

    def test_includes_chanlun_and_controls(self) -> None:
        s = _src()
        assert "ChanlunStrategy" in s
        assert "MaCrossStrategy" in s


class TestMedianAndSignTest:
    """只用均值口径 = 上一轮已知的偏差来源，必须有替代。"""

    def test_uses_median(self) -> None:
        assert "median" in _src(), "必须用中位数口径"

    def test_has_sign_test(self) -> None:
        s = _src()
        assert "sign_test" in s
        assert "(pairs > 0).sum()" in s, "符号检验应只问'赢的比例'，不受极端值主导"

    def test_reports_win_fraction(self) -> None:
        s = _src()
        assert "跑赢买持" in s
        assert "60%" in s, "需给出判断跑赢比例的参考线"

    def test_keeps_t_statistic_too(self) -> None:
        """中位数不能取代 t 全貌，两个都报才不误导。"""
        s = _src()
        assert "sqrt" in s
        assert "t=" in s


class TestRegimeAnalysis:
    def test_splits_by_regime(self) -> None:
        s = _src()
        assert "BULL_CUT" in s and "BEAR_CUT" in s
        assert "上涨票" in s and "下跌票" in s

    def test_discloses_lookahead_in_grouping(self) -> None:
        """⚠️ 分组用样本内事后走势 ⇒ 有 look-ahead，必须声明。"""
        s = _src()
        assert "look-ahead" in s or "事后" in s
        assert "非样本外" in s or "不可当样本外证据" in s

    def test_declares_diagnostic_only(self) -> None:
        s = _src()
        assert "仅用于诊断" in s or "仅诊断" in s

    def test_pit_split_also_declared_in_sample(self) -> None:
        """PIT 分组虽是前段切分，仍是样本内 —— 必须声明，不能当样本外。"""
        s = _src()
        assert "样本内" in s and "切分" in s


class TestPitSafeRegimeAndDrawdown:
    """事后分组有 look-ahead ⇒ 必须同时给出 PIT 安全复核与回撤对照。"""

    def test_has_pit_safe_split(self) -> None:
        s = _src()
        assert "PIT" in s, "必须有只用前段走势打标签的 PIT 分组"
        assert "int(n * 0.4)" in s or "n * 0.4" in s

    def test_pit_label_uses_only_past(self) -> None:
        """标签只能用到 k 时刻为止的价格，不得用全序列。"""
        s = _src()
        assert "px[k] / px[0]" in s
        assert "px[-1] / px[0]" in s, "那是后续收益，只用于对比，不能用于打标签"

    def test_has_drawdown_comparison(self) -> None:
        s = _src()
        assert "max_drawdown" in s
        assert "最大回撤" in s

    def test_drawdown_conclusion_is_risk_not_return(self) -> None:
        """核心结论：价值在风险控制 —— 必须在脚本里写明。"""
        s = _src()
        assert "风险控制" in s and "收益增强" in s

    def test_drawdown_ratio_threshold_named(self) -> None:
        s = _src()
        assert "回撤更小" in s


class TestHonestLimitations:
    def test_declares_no_beta_neutralization(self) -> None:
        s = _src()
        assert "beta" in s.lower() and "中性化" in s

    def test_declares_default_params(self) -> None:
        s = _src()
        assert "默认参数" in s

    def test_docstring_records_mean_median_gap(self) -> None:
        """均值/中位差距是这个脚本存在的理由，必须留在文件里。"""
        s = _src()
        assert "34.9" in s and "2.3" in s


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
