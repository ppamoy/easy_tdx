"""V733「并行回撤审计」脚本的契约测试。

⚠️ 这个脚本的存在理由：五之十四的"下行保护"结论样本太小
（分区 n=30 / 低暴露基线 n=8 / 参数扫描 n=12），单次回测≈26s 跑不动大样本，
故用进程池并行。本测试锁死并行化最容易踩的三个坑：

1. **静默吞异常**：裸 `except` 会把真错误变成 nan，表现为"有效样本不足"，
   排查方向被完全带偏（第一版就是这样，我差点以为是数据问题）；
2. **结果错位**：并发完成顺序 ≠ 标的顺序，若按完成顺序拼数组，
   策略收益会和买持回撤**张冠李戴**（和曾经的 broadcast bug 同类）；
3. **位置参数接口错位**：`_one` 返回元组长度变化时，拆包会错。
"""

from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
DP = SCRIPTS / "audit_drawdown_parallel.py"


def _src() -> str:
    return DP.read_text(encoding="utf-8")


class TestParallelScriptExists:
    def test_script_present(self) -> None:
        assert DP.exists(), f"缺少 {DP}"

    def test_uses_process_pool(self) -> None:
        """回测是 CPU 密集纯 Python，GIL 内多线程无效，必须进程池。"""
        s = _src()
        assert "ProcessPoolExecutor" in s
        assert "ThreadPool" not in s, "多线程对 CPU 密集回测无效"

    def test_defaults_workers_to_cpu_count(self) -> None:
        assert "cpu_count" in _src()


class TestExceptionsAreNotSwallowed:
    def test_no_bare_except(self) -> None:
        """⚠️ 裸 except 会把真错误静默成 nan。"""
        s = _src()
        assert "except Exception as e" in s, "必须捕获并保留错误信息"

    def test_failure_reason_is_reported(self) -> None:
        s = _src()
        assert "失败原因" in s or "回测失败" in s
        assert "type(e).__name__" in s

    def test_short_data_is_reported(self) -> None:
        s = _src()
        assert "数据过短" in s, "数据过短也要给出原因，不能只给 nan"


class TestResultAlignment:
    """并发完成顺序 ≠ 标的顺序，必须按 idx 对齐。"""

    def test_indexes_by_idx(self) -> None:
        s = _src()
        assert "out[r[0]] = r" in s or "out[r[0]]" in s, \
            "结果必须以 idx 为键存入，不能靠完成顺序 append"

    def test_alignment_slicing_present(self) -> None:
        s = _src()
        assert "for i in range(len(jobs)) if i in out" in s, \
            "必须按 jobs 顺序重建数组，保证同标的对齐"

    def test_alignment_comment_present(self) -> None:
        s = _src()
        assert "对齐" in s


class TestReportsBothDrawdowns:
    def test_returns_buyhold_drawdown(self) -> None:
        """⚠️ 第一版只返回买持**收益**，回答不了'缠论回撤是否低于买持'。"""
        s = _src()
        assert "bh_dd" in s

    def test_compares_strategy_vs_buyhold_dd(self) -> None:
        s = _src()
        assert "dd < bh_dd" in s
        assert "回撤" in s

    def test_reports_win_fraction(self) -> None:
        assert "跑赢" in _src() or "回撤 < 买持" in _src()

    def test_has_threshold_verdict(self) -> None:
        """事先写死判定线，避免事后找理由。"""
        s = _src()
        assert "0.9" in s
        assert "判定" in s

    def test_reports_t_statistic(self) -> None:
        s = _src()
        assert "sqrt" in s and "t=" in s

    def test_requires_minimum_sample(self) -> None:
        s = _src()
        assert "有效样本仅" in s, "样本不足必须显式失败而不是硬出结论"


class TestHonestLimitations:
    def test_declares_estimates_runtime(self) -> None:
        s = _src()
        assert "26s" in s, "应说明单次回测耗时，便于估时"

    def test_declares_not_out_of_sample(self) -> None:
        s = _src()
        assert "未做样本外" in s or "不是策略建议" in s

    def test_declares_no_beta_neutralization(self) -> None:
        s = _src()
        assert "beta" in s.lower() and "中性化" in s

    def test_position_pct_is_parameterized(self) -> None:
        s = _src()
        assert "--position-pct" in s, "仓位必须可调（修复后才有意义）"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
