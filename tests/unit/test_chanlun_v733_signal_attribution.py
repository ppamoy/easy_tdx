"""V733 单笔盈亏归因脚本（`audit_signal_attribution.py`）的契约测试。

⚠️ 纪律（AGENTS.md §7）：脚本本身也要被审计。这里锁住三件事：
  1. 有牙齿：tag 全空 / 无已知信号类型时必须 exit 1，**不能空转通过**；
  2. 口径正确：单笔收益率 = pnl / cost_basis（不是 pnl / 初始资金）；
  3. 不过度解读：输出里必须写明「条件差 ≠ 干预差」。
"""

from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
SCRIPT = SCRIPTS / "audit_signal_attribution.py"


def _src() -> str:
    return SCRIPT.read_text(encoding="utf-8")


class TestScriptExists:
    def test_script_present(self) -> None:
        assert SCRIPT.exists(), f"缺少 {SCRIPT}"

    def test_has_limit_arg(self) -> None:
        assert "--limit" in _src()


class TestTeeth:
    """牙齿：坏状态必须被脚本自己抓住，而不是静默通过。"""

    def test_checks_tag_column_present(self) -> None:
        s = _src()
        assert 'if "tag" not in tr.columns:' in s, (
            "必须检查 trades 有 tag 列 —— 跑在旧代码上会全空，不能静默通过"
        )

    def test_fails_on_all_empty_tags(self) -> None:
        """tag 全空 ⇒ 归因无法进行，必须 exit 1（不能空转通过）。"""
        s = _src()
        assert 'X["tag"] != ""' in s and "tagged.empty" in s, "tag 全空时必须判定不可信并退出"
        # 且退出码必须是 1（不是 0）
        idx = s.index("tagged.empty")
        assert "return 1" in s[idx : idx + 300], "牙齿不成立时必须 return 1"

    def test_requires_known_entry_types(self) -> None:
        s = _src()
        assert '"1buy"' in s and '"3buy"' in s, "必须校验出现过已知开仓信号类型"

    def test_exit_code_1_on_bad_teeth(self) -> None:
        s = _src()
        assert "return 1" in s, "牙齿不成立时 exit 1，不能 return 0"


class TestConventions:
    def test_uses_cost_basis_not_cash(self) -> None:
        """单笔收益率必须除以**该笔持仓成本**，不是初始资金。"""
        s = _src()
        assert 'row["pnl"]) / float(row["cost_basis"])' in s
        assert "cost_basis" in s

    def test_filters_rejected_and_zero_basis(self) -> None:
        s = _src()
        assert "~tr[" in s and "rejected" in s
        assert 'cost_basis"] > 0' in s, "cost_basis=0 会导致除零/假收益率"

    def test_uses_entry_exit_separator(self) -> None:
        s = _src()
        assert 'SEP = "->"' in s
        assert "def _entry" in s and "def _exit" in s

    def test_no_forbidden_prefix_matching(self) -> None:
        """买卖方向判定不能用 startswith('buy')，会漏掉 2buy_s。"""
        s = _src()
        assert 'startswith("buy")' not in s


class TestHonestyGuards:
    def test_states_conditioning_not_intervention(self) -> None:
        """必须写明：这是条件差，不能当成"关掉信号会更好"的证据。"""
        s = _src()
        assert "条件差" in s and "干预差" in s

    def test_warns_per_trade_vs_total_return(self) -> None:
        s = _src()
        assert "单笔收益率" in s and "策略总收益" in s

    def test_warns_stop_takeprofit_winrate_is_tautology(self) -> None:
        """止盈胜率 100% / 止损胜率 0% 是同义反复，必须标注，
        否则读者会把它当成预测能力的证据。"""
        s = _src()
        assert "同义反复" in s


class TestSignificance:
    def test_reports_t_stat(self) -> None:
        s = _src()
        assert "def t_stat" in s
        assert "不显著" in s


class TestAblation:
    """干预实验（真消融）必须存在且口径正确。

    起因：只有 `report()` 的条件差时，"3sell 有用"是**推理**出来的，
    不符合 AGENTS.md §3（先验证再下结论）。故必须有真消融分支。
    """

    def test_ablation_flag_exists(self) -> None:
        assert "--ablation" in _src()

    def test_has_total_returns_collector(self) -> None:
        assert "def total_returns" in _src()
        assert "def ablation" in _src()

    def test_uses_real_switch_not_filtering(self) -> None:
        """消融必须真的关掉开关，而不是事后把某些行过滤掉。

        事后过滤 = 假装 future trade 不存在，持仓序列已经变了，是假消融。
        """
        s = _src()
        assert '"use_3sell": False' in s, (
            "消融必须走策略真实开关 use_3sell=False；"
            "事后按 tag 过滤行不等于关掉信号（持仓序列已经不同了）"
        )

    def test_ablation_says_total_return_not_per_trade(self) -> None:
        s = _src()
        assert "总收益" in s and "未做复利" in s

    def test_no_hardcoded_workers(self) -> None:
        """AGENTS.md：禁止硬编码 workers=4/8（本机只有 4 核）。"""
        import re

        s = _src()
        bad = re.findall(r"workers\s*=\s*\d+|default\s*=\s*[48]\b", s)
        assert bad == [], f"硬编码了并行度/样本量回落值：{bad}"


class TestParallelEquivalence:
    """并行化后必须锁住：并行结果 == 串行结果，且失败要显式报数。

    背景：全 286 只串行要 ~70 分钟，故改成 ProcessPoolExecutor 并行。
    但并行化最容易引入两类静默错误：
      1. 结果随并行度变化（顺序依赖 / 共享状态污染）⇒ 结论不可复现；
      2. 异常被吞 ⇒ "全部标的失败"伪装成"样本少"。
    """

    def test_run_one_is_top_level_picklable(self) -> None:
        """worker 必须是顶层函数，否则 ProcessPoolExecutor 无法 pickle。"""
        s = _src()
        assert "def _run_one(" in s, "缺少顶层 worker 函数 _run_one"
        # 顶层：行首无缩进
        lines = [ln for ln in s.splitlines() if ln.startswith("def _run_one(")]
        assert lines, "_run_one 必须是顶层函数（不能是嵌套/方法）"

    def test_parallel_counts_failures_loudly(self) -> None:
        """失败必须计数并打印，不能 continue 吞掉。"""
        s = _src()
        assert "nerr" in s, "必须统计失败数"
        assert "只失败" in s, "失败数必须显式打印（否则全失败会伪装成样本少）"

    def test_workers_defaults_to_project_convention(self) -> None:
        """并行度取 _concurrency.resolve_workers，不得硬编码。"""
        s = _src()
        assert "from _concurrency import resolve_workers" in s
        assert "resolve_workers(None)" in s

    def test_has_workers_flag(self) -> None:
        assert '"--workers"' in _src() or "'--workers'" in _src()

    def test_serial_and_parallel_same_code_path(self) -> None:
        """串行与并行必须共用同一个 _run_one，避免两套逻辑算出不同结果。"""
        s = _src()
        assert "_run_one(" in s
        # 串行分支（workers<=1）与并行分支都要调 _run_one
        assert s.count("_run_one(") >= 2, "串行/并行两条路径都要走 _run_one"


class TestCacheResumability:
    """全 286 只串行 ~70 分钟、并行 ~36 分钟，超过常见 timeout ⇒ 必须可续跑。

    踩过的坑（本轮实测）：`ablation(fs, "3sell")` 忘了传 `cache_path`，
    结果消融那两组**完全没有缓存**，跑到超时进度全丢。这里锁死。
    """

    def test_ablation_call_passes_cache_path(self) -> None:
        s = _src()
        assert 'ablation(fs, "3sell", workers=a.workers, cache_path=cp)' in s, (
            "消融必须传 cache_path，否则该组无缓存，超时后进度全丢"
        )

    def test_cache_key_includes_kw(self) -> None:
        """缓存键必须含 kw，否则默认组与 use_3sell=False 组会互相污染。"""
        s = _src()
        assert "def _cache_key" in s
        assert '"kw"' in s and '"symbol"' in s, "缓存键需同时含 symbol 与 kw"

    def test_periodic_save(self) -> None:
        """必须周期性落盘，不能只在最后写一次（超时就全丢）。"""
        s = _src()
        assert "% 10 ==" in s or "% 10 == 0" in s, "需每 10 只落盘一次"

    def test_cache_arg_exists(self) -> None:
        assert '"--cache"' in _src()
