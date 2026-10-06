"""「缠论选股功能审计」脚本的契约测试（五之二十五）。

⚠️ 这个脚本测的是一个**功能有没有用**，所以它自己最容易出问题的地方是
   **悄悄测了个寂寞**。这组测试锁住那些会让结论失真的点。
"""
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "scripts" / "audit_chanlun_screen_usefulness.py"
VIEW = Path(__file__).resolve().parents[2] / "web-ui" / "src" / "views" / "StockPickView.vue"
ROUTE = Path(__file__).resolve().parents[2] / "src" / "easy_tdx" / "web" / "routers" / "screening.py"


def _s() -> str:
    return SRC.read_text(encoding="utf-8")


class TestNoDataMustFail:
    def test_exits_2_without_data(self) -> None:
        """⚠️ AGENTS.md：不能拿空目录凑出一个"结论"。
        没有数据必须 exit 2 并明说，不能打印 0 个样本然后给判定。"""
        s = _s()
        assert "无数据，无法审计" in s
        assert "return 2" in s

    def test_tested_the_real_endpoint_logic(self) -> None:
        """⚠️ 必须复刻端点自己的判定函数，而不是重写一套自己的规则 ——
        那样测的就不是那个功能了。"""
        s = _s()
        assert "from easy_tdx.web.routers.screening import _chanlun_screen" in s
        assert "_chanlun_screen(" in s

    def test_endpoint_it_claims_to_test_exists(self) -> None:
        """被审计的端点不能被改名/删掉而测试还绿。"""
        r = ROUTE.read_text(encoding="utf-8")
        assert '/screening/chanlun-scan' in r
        assert "def _chanlun_screen(" in r

    def test_ui_tab_exists(self) -> None:
        assert "缠论选股" in VIEW.read_text(encoding="utf-8")


class TestNoFutureLeak:
    def test_slices_data_pit(self) -> None:
        """⚠️ 每个再平衡点只能喂 `df.iloc[:t+1]`。
        用全量数据判定 = 偷未来 = 整个审计作废。"""
        s = _s()
        assert "sub = df.iloc[: t + 1]" in s

    def test_forward_return_uses_future(self) -> None:
        """判定 PIT 之后，必须确认收益确实取了**未来** H 日，
        否则可能测的是"过去收益"。"""
        s = _s()
        assert "def _fwd(" in s
        assert "j = i + H" in s

    def test_holds_out_h_bars(self) -> None:
        """时点必须留够 H 根，否则最后几个点没有未来收益可取。"""
        s = _s()
        assert "n - H" in s


class TestHonestVerdict:
    def test_distinguishes_negative_from_zero(self) -> None:
        """⚠️ 本轮我真的偷懒过：第一版写 `❌ 无用/为负`，把
        '显著为负'(t<-2) 和 '与零无差异'(t≈0) 混为一谈。
        实测是后者(p=0.88) —— 措辞不同，含义完全不同。

        ⚠️⚠️ 这条断言我**第一版是空的**：只查"显著为负"和"与零无显著差异"
        两个词是否出现，而它们都在 `elif t < -2` 分支里 ——
        把我把"与零无显著差异"那个分支**整个删掉**时，测试照样绿
        （牙齿验证时才发现）。现在改为**分别锁定三个分支**。
        """
        s = _s()
        # ⚠️ 判定改用**市场控制后**的 use_t（见 TestMarketBetaControl），
        #    所以分支条件是 use_t 而不是 t。断言要跟着改，否则是**假失败**。
        assert "elif use_t < -2:" in s
        assert "elif use_t > 2:" in s
        # 且 use_t 必须真的来自"控制后优先、控制前兜底"
        assert "use_t = t2 if" in s
        # 零分支：必须是**独立的 else 兜底**，而不是默认落到某个含混措辞
        assert "与零无显著差异" in s
        assert "样本不足，无法判定" in s
        assert "use_t != use_t" in s
        # ⚠️ 关键：零分支必须真的在代码里，不能只是"某处出现过这个词"
        zero_blk = s.split("elif use_t > 2:")[-1]
        assert "与零无显著差异" in zero_blk, \
            "零分支必须真的存在于判定链末端（第一版断言是空的）"

    def test_does_not_claim_to_beat_buy_hold(self) -> None:
        """选股检验 ≠ 端到端策略(五之十八未证明跑赢买持)，
        脚本必须自己声明这个边界。"""
        s = _s()
        assert "与'择时'" in s or "与'择时'是两回事" in s
        assert "买入持有" in s

    def test_states_sample_caveat(self) -> None:
        s = _s()
        assert "口径提醒" in s


class TestMarketBetaControl:
    """⚠️⚠️ 本轮**最关键**的一组。

    `zs_position=above` 原始口径差 **+3.71%、t=+3.16、p=0.002**
    ——看着像个重大发现。但 2024-2025 A股整体上行，
    "站上中枢"的股票天然涨得多。
    换成"相对**同期全市场均值**"后只剩 **+1.61%、p=0.15 ⇒ 不显著**。

    不做这一步，就会把**大盘涨幅记在信号账上**。
    这是整个审计里最容易骗过自己的地方。
    """

    def test_computes_same_period_market_mean(self) -> None:
        src = _s()
        assert "by_t" in src
        assert "mkt = {t: float(np.mean(v))" in src

    def test_requires_five_peers_per_timepoint(self) -> None:
        src = _s()
        assert "if len(v) >= 5" in src

    def test_subtracts_market_mean_per_timepoint(self) -> None:
        src = _s()
        assert "def _rel(" in src
        assert "x - mkt[t]" in src

    def test_stores_timepoints_per_bucket(self) -> None:
        """⚠️ 没有时点就无法对齐"同期"——必须**分别**记 hit/miss 的时点。
        我第一版想用一个 pts 混着记，hit 和 miss 的对应关系就乱了。"""
        src = _s()
        assert '"hit_pts"' in src
        assert '"miss_pts"' in src

    def test_verdict_uses_controlled_result_when_available(self) -> None:
        """⚠️ 若能算市场基准，判定**必须**以控制后的结果为准。
        否则原始那个 p=0.002 会被当成"可用"。"""
        src = _s()
        assert "use_t = t2 if" in src
        assert "判定以**市场控制后**为准" in src

    def test_says_loudly_when_control_unavailable(self) -> None:
        """算不出基准时必须**明说**结论只能按原始口径读，
        不能默默当成已控制。"""
        src = _s()
        assert "无法做 beta 调整" in src
        assert "结论只能按**原始**口径读" in src


class TestStructuralCriteriaSupported:
    def test_all_endpoint_criteria_exposed(self) -> None:
        """端点 `_chanlun_screen` 支持 4 个维度，之前只测了 1 个。"""
        src = _s()
        for flag in ("--signal-type", "--trend", "--zs-position",
                     "--has-beichi"):
            assert flag in src

    def test_passes_them_to_endpoint_not_reimplementing(self) -> None:
        """⚠️ 仍然必须**透传给端点函数**，不能自己写一套判定 ——
        否则测的就不是那个功能了（第一版就犯过）。"""
        src = _s()
        assert '"trend": trend' in src
        assert '"zs_position": zs_pos' in src

    def test_has_beichi_tri_state(self) -> None:
        """has_beichi 是 bool，筛选上却是三态（不限/要/不要）。"""
        src = _s()
        assert 'has_bc == "any"' in src
        assert 'has_bc == "true"' in src

    def test_cache_tag_covers_all_criteria(self) -> None:
        """⚠️ 缓存文件名必须带**全部**条件，否则不同口径互相污染
        （这是第一版已有的隐患，补齐维度后更容易踩）。"""
        src = _s()
        assert "a.zs_position" in src
        assert "a.has_beichi" in src


class TestNoWarningSpam:
    def test_suppresses_expected_runtime_warnings(self) -> None:
        """样本不足时 numpy 会刷一串 RuntimeWarning，那是**预期路径**，
        不该把输出刷满。"""
        src = _s()
        assert "warnings.catch_warnings()" in src
        assert 'simplefilter("ignore", RuntimeWarning)' in src

    def test_nan_does_not_pretend_to_be_a_verdict(self) -> None:
        """样本不足 ⇒ 报"样本不足，无法判定"，不能吐一个 nan% 结论。"""
        src = _s()
        assert "⚠️ 样本不足，无法判定" in src


class TestResumable:
    def test_caches_incrementally(self) -> None:
        """⚠️ 第一次跑 80 只直接超时**全丢**（每时点重跑完整缠论很贵）。
        必须每只完成即落盘。"""
        s = _s()
        assert "cache.write_text" in s

    def test_reuses_cache(self) -> None:
        s = _s()
        assert "复用缓存" in s
        assert "if cache.exists()" in s

    def test_cache_split_by_signal_type(self) -> None:
        """⚠️ 两种口径共用一个缓存会**互相污染** ——
        any_buy 的结果会被当成 1buy 复用。"""
        s = _s()
        assert "a.signal_type" in s
        assert "cache_path.with_name" in s

    def test_bounds_recompute_points(self) -> None:
        """时点数必须有上限，否则单只成本失控。"""
        s = _s()
        assert "MAX_POINTS" in s


class TestConfigurable:
    def test_signal_type_is_a_flag(self) -> None:
        """必须能换口径测，否则只能证明端点**默认**那一种没用。"""
        s = _s()
        assert "--signal-type" in s

    def test_saves_machine_readable_result(self) -> None:
        s = _s()
        assert "json.dumps" in s


class TestTimepointAlignmentBehaviour:
    """⚠️⚠️ 上面那组"牙齿2"暴露了一个**纯文本断言抓不到**的 bug。

    我把 `(hit_pts if ok else miss_pts).append(t)` 改成
    `hit_pts.append(t)`（永远记进 hit_pts）——**所有字符串断言照样全绿**，
    因为代码文本几乎没变。但这样 `miss_pts` 永远是空的 ⇒
    市场基准只用"命中组"算 ⇒ **控制本身是错的**。

    ⇒ 结论：涉及**数据流对齐**的东西，**不能只靠 grep 源码**。
    必须用真实数据跑一遍，验证对齐关系确实成立。
    """

    def test_hit_and_miss_timepoints_are_mutually_exclusive(self) -> None:
        """用一只真实标的跑 one_symbol，验证
        len(hit_pts) == len(hit) 且 len(miss_pts) == len(miss)。"""
        import importlib.util
        import json
        from pathlib import Path

        spec = importlib.util.spec_from_file_location(
            "_su", Path(__file__).resolve().parents[2] /
            "scripts" / "audit_chanlun_screen_usefulness.py")
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)

        data = Path(__file__).resolve().parents[2] / "audit_data"
        files = sorted(data.glob("*.json"))
        if not files:
            import pytest
            pytest.skip("audit_data/ 无数据")

        r = mod.one_symbol(str(files[0]))
        if r is None:
            import pytest
            pytest.skip(f"{files[0].name} 样本不足")

        assert len(r["hit_pts"]) == len(r["hit"]), "hit_pts 与 hit 长度不符"
        assert len(r["miss_pts"]) == len(r["miss"]), "miss_pts 与 miss 长度不符"
        # ⚠️ 关键：两组时点**不能重叠**。若实现退化成"全记进 hit_pts"，
        #    miss_pts 会是空的（下面的合计检查会抓到）。
        assert (len(r["hit_pts"]) + len(r["miss_pts"])) > 0
        if r["hit"] and r["miss"]:
            assert r["hit_pts"] and r["miss_pts"], (
                "命中与未命中**都**有样本时，两组时点都必须有内容；"
                "只有一组有 ⇒ 说明另一组时点被记错了地方")
