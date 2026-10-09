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


class TestNoPositionalPairing:
    """⚠️ 本轮实测抓到的真 bug：配对必须按 symbol，**不能按位置**。

    原 `run_all()` 用 `vals.append()` + 失败时 `continue`，某个策略在某只票上
    抛异常后该列表就比别人短；而 main() 用 `bh_all[:len(ch)]` **按位置截断**
    ⇒ 从第 k 只起，"策略收益"与"买持收益"来自**不同股票**，配对超额全错。

    实测证据（注入"缠论在第 3 只票失败"）：
        缠论[2]=+75.16% 来自 sh600016，买持[2]=+48.84% 来自 sh600011
    """

    def test_run_all_returns_symbol_keyed_mapping(self) -> None:
        s = _src()
        assert "dict[str, dict[str, float]]" in s, "run_all 必须返回 {策略: {symbol: ret}}"
        assert "out[label][sym] = ret" in s, "必须按 symbol 键写入，不能 append"

    def test_no_bh_positional_truncation(self) -> None:
        """`bh_all[: len(ch)]` 这种按位置截断是 bug 本体，不许再出现。"""
        s = _src()
        assert "bh_all[: len(ch)]" not in s, (
            "禁止按位置截断买持 —— 策略跑出部分时会把不同股票配对在一起"
        )
        assert "bh_all[:k]" not in s

    def test_pair_by_symbol_intersection(self) -> None:
        s = _src()
        assert "def pair(" in s, "必须有按 symbol 求交集的配对函数"
        assert "for s in bh_map if s in sm and s in df_map" in s, "配对必须取双侧的 symbol 交集"

    def test_drawdown_skips_unrun_symbols(self) -> None:
        """回撤对比同样要跳过策略没跑出来的标的。"""
        s = _src()
        assert "if sym not in dd_strat:" in s

    def test_failure_is_reported_not_silent(self) -> None:
        s = _src()
        assert "上失败，已跳过该标的" in s, "策略在某标的失败必须打印，不能静默"


class TestParallelization:
    """并行化后的契约：必须串行等价、必须有 --workers、必须有可 pickle 的顶层 worker。"""

    def test_has_workers_flag(self) -> None:
        s = _src()
        assert '"--workers"' in s, "应支持 --workers"
        assert "resolve_workers(" in s, "并行度必须走 _concurrency，不能硬编码 4/8"

    def test_no_hardcoded_worker_count(self) -> None:
        s = _src()
        for bad in ("max_workers=4", "max_workers=8", "workers=4", "workers=8"):
            assert bad not in s, f"不许硬编码并发数 {bad} —— 一律走 scripts/_concurrency.py"

    def test_worker_is_top_level(self) -> None:
        """ProcessPoolExecutor 要求 worker 是**顶层**函数（非嵌套/非 lambda）。"""
        s = _src()
        assert "\ndef _run_one(" in s, "_run_one 必须在模块顶层，否则无法 pickle"
        # 前面的字符是换行 ⇒ 顶格定义，不是缩进的嵌套函数
        idx = s.index("\ndef _run_one(")
        after = s[idx + 1 :]
        assert after.startswith("def _run_one("), "_run_one 必须是顶层（无缩进）"

    def test_worker_returns_symbol_labeled_result(self) -> None:
        """worker 返回值必须带 symbol ⇒ 结果按 symbol 归并，不依赖完成顺序。"""
        s = _src()
        # 失败出口：None；成功出口：带回 total_return 与 max_drawdown
        assert "return sym, label, None, None" in s, (
            "worker 的失败出口必须返回 (symbol, label, None, None)"
        )
        assert 'float(r.performance["total_return"])' in s, "worker 的成功出口必须带回 total_return"
        assert "sym, label, ret, dd = fut.result()" in s, (
            "必须解包 worker 的 symbol 再归位，不能依赖 as_completed 的完成顺序"
        )

    def test_tempdir_cleanup(self) -> None:
        s = _src()
        assert "shutil.rmtree(tmpdir" in s, "临时目录必须清理"
        assert "tempfile.mkdtemp" in s

    def test_strats_populated_for_worker(self) -> None:
        """worker 里用 STRATS[label] 反查类 ⇒ STRATS 必须预先填好，不能是空 dict。"""
        s = _src()
        assert "STRATS[label]" in s
        assert "STRATS: dict[str, type] = {}" not in s, (
            "STRATS 必须包含 CHANLUN + CONTROL，空 dict 会让 worker 全 KeyError"
        )


class TestNoDuplicateBacktestPass:
    """回撤必须复用 run_all 的产出，不许末尾再串行重跑一遍。

    原实现在末尾 `for df in dfs: BacktestEngine(...).run(df)` 只为了取
    max_drawdown —— 等于把同样的回测做了两遍（286 只约多花 20 分钟）。
    而 max_drawdown 本来就在同一份 r.performance 里，一次跑完带回即可。
    """

    def test_worker_returns_drawdown(self) -> None:
        s = _src()
        assert "max_drawdown" in s, "worker 必须顺带带回 max_drawdown"

    def test_run_all_returns_two_maps(self) -> None:
        s = _src()
        assert "return out, dds" in s, "run_all 必须同时返回 (收益表, 回撤表)"

    def test_drawdown_section_reuses_results(self) -> None:
        """末尾不得再有 `BacktestEngine(...).run(df)` 的重复回测。"""
        s = _src()
        # 只有 worker 里允许出现 .run(df)；main 里不得再有
        body = s[s.index("def main(") :]
        assert "BacktestEngine(" not in body, (
            "main() 里不许再跑 BacktestEngine —— 回撤应复用 run_all 的结果"
        )

    def test_drawdown_uses_dd_res(self) -> None:
        s = _src()
        assert "dd_res = run_all(" in s or "res, dd_res = run_all(" in s, (
            "main 必须接收 run_all 返回的第二张表（回撤）"
        )
