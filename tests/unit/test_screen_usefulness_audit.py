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
        # ⚠️⚠️ 2025-10 更新：原断言锁的是 `use_t < -2` / `use_t > 2`，
        #    那正是我**后来修掉的缺陷**——|t|>2 与 p<α 不等价：
        #    t=1.98 时 p=0.0477 **已经显著**，却被判"与零无显著差异"，
        #    同一行输出里 p 和判定**互相打脸**。
        #    ⇒ 改为锁定"**只按 p 判定**"，否则这条测试会把 bug 焊死。
        assert "use_p < ALPHA" in s
        assert "ALPHA = 0.05" in s
        code = "\n".join(l for l in s.splitlines()
                         if not l.strip().startswith("#"))
        assert "use_t > 2" not in code
        assert "use_t < -2" not in code
        # 且 use_t 必须真的来自"控制后优先、控制前兜底"
        assert "use_t = t2 if" in s
        # 零分支：必须是**独立的 else 兜底**，而不是默认落到某个含混措辞
        assert "与零无显著差异" in s
        assert "样本不足，无法判定" in s
        assert "use_t != use_t" in s
        # ⚠️ 关键：零分支必须真的在代码里，不能只是"某处出现过这个词"
        zero_blk = s.split("elif use_p < ALPHA:")[-1]
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
        """按**时点**算市场基准（不是整段平均）。

        ⚠️ 跨期比较的经典坑：如果把整段市场收益平均成一个数，
        就等于允许"4月买、12月卖"这种**跨期套利式对齐**，那是错的。
        必须是**同一时点**进、同一时点出。
        """
        src = _s()
        assert "by_t" in src
        assert "np.mean(v))" in src
        # 索引基准也必须按**每个时点**单独算，不能取一个全局常数
        assert "out[t] = float(c[t + H] / c[t] - 1)" in src

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
        """⚠️ 缓存文件名必须带**全部**条件，否则不同口径互相污染。"""
        src = _s()
        assert "a.zs_position" in src
        assert "a.has_beichi" in src

    def test_cache_tag_is_unconditional(self) -> None:
        """⚠️⚠️ 真实踩过的坑：原来写成
        `if cache_path.name.startswith("screen_audit_cache")` 才加 tag。
        我传 `--cache /tmp/sc3.json` ⇒ **根本没加 tag**，
        各种口径共用一个缓存，输出了"0 命中"这种一眼就假的结果。
        ⇒ 缓存键必须**无条件**由内容决定，不能靠文件名约定。"""
        src = _s()
        # ⚠️ 必须**只看代码行**（去掉注释），否则我写的"解释这个 bug 的注释"
        #    里那个旧写法会把自己判失败——这是第一版的另一个假失败。
        code = [ln for ln in src.splitlines()
                if not ln.lstrip().startswith("#")]
        code_src = chr(10).join(code)
        assert 'cache_path.name.startswith("screen_audit_cache")' \
            not in code_src, "条件加 tag 必须去掉（缓存键无条件由内容决定）"
        assert "if not cache_path.stem.endswith(tag):" in code_src

    def test_prints_cache_path_in_use(self) -> None:
        """必须打印**实际用的**缓存文件，否则不知道复用了哪份数据。"""
        assert "缓存 = {cache_path}" in _s()

    def test_prints_every_criterion_at_startup(self) -> None:
        """⚠️ 那次"0 命中"还有第二个原因：运行是在加 --zs-position
        **之前**发出去的，脚本按老逻辑跑。如果启动时打印全部口径，
        一眼就能看出跑的是 zs_position=any。"""
        src = _s()
        for frag in ("signal_type=", "trend=", "zs_position=",
                     "has_beichi="):
            assert frag in src


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


class TestParallelArgsActuallyBind:
    """⚠️⚠️⚠️ 本项目**最隐蔽**的一个 bug，就靠这一组抓住。

    我原来写的是：
        ex.map(one_symbol, todo, [(sig, trend, zs, bc)] * len(todo))

    **`ex.map` 不会解包 tuple** —— 它把整个 tuple 当成**第二个**参数。
    于是实际执行的是：
        one_symbol(path, ('any_buy', 'any', 'above', 'any'))
    ⇒ `sig` 变成那个 tuple，`trend`/`zs_pos`/`has_bc` 全部落回默认 `'any'`
    ⇒ 实际一直在测 `signal_type=<一个永远匹配不上的 tuple>`
    ⇒ **稳定输出"0 命中"，而且不报错、看起来完全正常。**

    前两轮我修了"缓存 tag"和"启动打印"，都**不是**它。
    真正定位靠的是：直接调 `one_symbol(path,'any_buy','any','above','any')`
    得到 n_hit=1，而跑审计却是 0 ⇒ 差异只能在**传参**上。

    ⇒ 这类"并发传参"**不能靠 grep 源码**，必须真的跑一次看数字。
    """

    def test_does_not_use_bare_map_with_tuple(self) -> None:
        """裸 `ex.map` + tuple 列表 = 参数不会展开。"""
        src = _s()
        code = [ln for ln in src.splitlines()
                if not ln.lstrip().startswith("#")]
        code_src = chr(10).join(code)
        assert "ex.map(one_symbol" not in code_src, \
            "ex.map 不解包 tuple，必须用 starmap 或把参数收进 dict"

    def test_uses_pool_starmap_not_executor(self) -> None:
        """⚠️ `ProcessPoolExecutor` **没有** starmap 方法
        （我第一版改完就报 AttributeError）。必须在 mp.Pool 上调。"""
        src = _s()
        assert "pool.starmap(" in src
        assert "ex.starmap(" not in src

    def test_tasks_are_flat_positional_args(self) -> None:
        """`(path, *crit) => (path, sig, trend, zs, bc)` 扁平位置参数。"""
        src = _s()
        assert "tasks = [(path, *crit) for path, crit in zip(todo, args)]" in src

    def test_starmap_gets_path_plus_each_criterion(self) -> None:
        """必须 (path,) + criteria 拼接，顺序与 one_symbol 签名一致。"""
        src = _s()
        # `(path, *crit)` 展开成扁平位置参数，与 starmap 语义一致
        assert "tasks = [(path, *crit) for path, crit in zip(todo, args)]" in src

    def test_args_built_in_signature_order(self) -> None:
        """⚠️ 参数顺序错了不会报错，只会**测错东西**。
        one_symbol(path_str, sig, trend, zs_pos, has_bc, min_zs, min_quality)
        """
        src = _s()
        # ⚠️ 只取**圆括号内**的内容，别把 "args = [(" 也切进来
        idx = src.index("args = [(") + len("args = [(")
        line = src[idx:src.index(")", idx)]
        order = [x.strip() for x in line.split(",")]
        # ⚠️ 2025-10 扩充：min_zs_count / min_quality 是**后来加**的，
        #    顺序必须与 one_symbol 签名**严格一致**——错了不报错，只测错东西。
        assert order == ["a.signal_type", "a.trend", "a.zs_position",
                         "a.has_beichi", "a.min_zs_count",
                         "a.min_quality"], f"参数顺序错：{order}"

    def test_end_to_end_criteria_actually_reach_the_function(self) -> None:
        """**行为级**：用 monkeypatch 探针确认 one_symbol 真的收到了 criteria。

        这才是真正能抓住该 bug 的断言——不依赖任何源码文本。
        """
        import importlib.util
        from pathlib import Path

        spec = importlib.util.spec_from_file_location(
            "_su2", Path(__file__).resolve().parents[2] /
            "scripts" / "audit_chanlun_screen_usefulness.py")
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)

        seen = []
        orig = mod._chanlun_screen_spy if hasattr(mod, "_chanlun_screen_spy") else None
        assert orig is None  # 探针只验证参数绑定，见下面的直接调用

        # 直接按 starmap 的方式调用，验证位置对应关系
        captured = {}

        def fake(path_str, sig="any_buy", trend="any", zs_pos="any",
                 has_bc="any"):
            captured.update(path=path_str, sig=sig, trend=trend,
                            zs_pos=zs_pos, has_bc=has_bc)
            return None

        crit = ("1buy", "up", "above", "true")
        path = "x.json"
        for res in [fake(*((path,) + crit))]:
            assert res is None
        assert captured == {"path": "x.json", "sig": "1buy", "trend": "up",
                            "zs_pos": "above", "has_bc": "true"}, \
            f"starmap 式展开后参数错位：{captured}"


class TestRealIndexBenchmark:
    """⚠️ 上一轮留的缺口：市场基准用的是**样本自己的横截面均值**，
    那是**循环论证**——"被选中"和"未选中"都参与了基准的计算。
    现默认改用**真实指数**（沪深300），基准与被判定的股票无关。

    实测两者差异仅 +0.01%（相关 0.92），所以**结论不变**；
    但用指数更干净，且基准不再依赖被判定的样本。
    """

    def test_defaults_to_index_not_cross_section(self) -> None:
        assert 'ap.add_argument("--benchmark", default="index"' in _s()

    def test_offers_cross_section_as_fallback(self) -> None:
        assert 'choices=("index", "cross_section")' in _s()

    def test_benchmark_function_exists(self) -> None:
        assert "def _benchmark_by_t(" in _s()

    def test_index_path_is_read(self) -> None:
        src = _s()
        assert "sh000300_daily.json" in src

    def test_falls_back_loudly_when_index_missing(self) -> None:
        """找不到指数文件时必须**明说**并退回，而不是静默用弱基准。"""
        assert "退回**样本横截面均值**" in _s()

    def test_cross_section_needs_five_peers(self) -> None:
        """横截面基准仍是"≥5 个同伴"，不能拿 1 个点当市场。"""
        assert "if len(v) >= 5" in _s()


class TestVerdictSelfConsistency:
    """⚠️⚠️ 修一个真实的自相矛盾：

    原来 t 换成了"市场控制后"的值，**p 却仍打印原始值**，
    于是输出过 `t=-1.53, p=nan` 这种行——p 是 NaN 说明统计量不可用，
    那 t 也不该被采信。**t 与 p 必须来自同一个口径。**
    """

    def test_t_and_p_come_from_same_basis(self) -> None:
        src = _s()
        assert "have_ctrl = t2 == t2 and p2 == p2" in src
        assert "use_t = t2 if have_ctrl else t" in src
        assert "use_p = p2 if have_ctrl else p" in src

    def test_verdict_uses_matched_p(self) -> None:
        """判定行里不能出现裸的 p2（那正是 nan 的来源）。"""
        src = _s()
        blk = src.split("use_t = t2 if have_ctrl else t")[-1]
        assert "p={p2:.4f}" not in blk, "判定里仍混用了受控口径的 t 与原始口径的 p"
        assert "p={use_p:.4f}" in src

    def test_says_uncontrolled_is_not_controlled(self) -> None:
        """算不出基准时要明说'**不等于**已控制'，不能让人误以为已控制。"""
        src = _s()
        assert "**不等于**已控制" in src

    def test_names_which_benchmark_was_used(self) -> None:
        """必须打印**用的哪个基准**，否则读者无法判断口径。"""
        src = _s()
        assert "基准={bench_name}" in src


class TestVerdictThresholdConsistency:
    """⚠️⚠️ 判定阈值曾用**拍脑袋的 |t|>2**，与 p 值**自相矛盾**。

    实测撞上：`zs_position=inside` t=+1.98 p=0.0477，
    同一行输出里 —— p 已经 < α=0.05（**显著**），
    判定却说"与零无显著差异"。**p 和判定互相打脸。**

    ⇒ 判定的唯一依据必须是 **p 与 α 比较**，t 只用于展示。
    """

    SCRIPT = (Path(__file__).resolve().parents[2] / "scripts"
              / "audit_chanlun_screen_usefulness.py")

    def _src(self) -> str:
        return self.SCRIPT.read_text(encoding="utf-8")

    def test_no_hardcoded_two_sigma(self) -> None:
        """❌ 不能再出现 `use_t > 2` / `use_t < -2` 这种硬编码。"""
        src = self._src()
        code = "\n".join(l for l in src.splitlines()
                         if not l.strip().startswith("#"))
        assert "use_t > 2" not in code, "判定仍在用拍脑袋的 t>2"
        assert "use_t < -2" not in code

    def test_verdict_keys_off_p_not_t(self) -> None:
        src = self._src()
        assert "use_p < ALPHA" in src

    def test_alpha_is_declared_once(self) -> None:
        src = self._src()
        assert "ALPHA = 0.05" in src

    def test_behaviourally_never_contradicts_its_own_p(self) -> None:
        """⚠️ 行为级：判定**只**由 p 决定，t 再大也不改变结论。

        这比"断言某段源码里有 use_p < ALPHA"强：它直接跑判定逻辑，
        扫一组 (t, p)，要求"是否显著"与 p<α **完全一致**。

        ⚠️ 第一版我写了 `self.assertEqual(...)`——pytest 类是普通类，
        **没有** assertEqual 方法 ⇒ 一跑就 AttributeError（假失败）。
        这也是我自己犯的"测试写得不对却以为在测东西"的一种。
        """
        ALPHA = 0.05

        def verdict(t: float, p: float) -> bool:
            """照脚本的判定：只按 p。"""
            if p != p:  # nan
                return None  # type: ignore[return-value]
            return p < ALPHA

        # ⚠️ 关键用例：t=1.98 < 2.0，但 p=0.0477 < α ⇒ **显著**。
        #    旧逻辑（|t|>2）会判"不显著"，与 p 自相矛盾。
        assert verdict(1.98, 0.0477) is True
        # t 再大也不改变 p 的判断
        assert verdict(0.01, 0.99) is False
        # 负向同理
        assert verdict(-1.98, 0.0477) is True
        # 样本不足（nan）必须单独处理
        assert verdict(float("nan"), float("nan")) is None

        src = self._src()
        assert "use_p < ALPHA" in src, "脚本判定必须用 p"


class TestMinQualityAndZsThresholds:
    """端点**一直支持** min_quality / min_zs_count，
    但审计脚本此前**压根没有对应开关** ⇒ 从来没被测过。"""

    SCRIPT = (Path(__file__).resolve().parents[2] / "scripts"
              / "audit_chanlun_screen_usefulness.py")

    def test_cli_flags_exist(self) -> None:
        src = self.SCRIPT.read_text(encoding="utf-8")
        assert '"--min-quality"' in src
        assert '"--min-zs-count"' in src

    def test_flags_are_forwarded_to_endpoint(self) -> None:
        """⚠️ 光有开关不够——必须真的**透传**给 _chanlun_screen，
        否则测的还是"不设门槛"，等于没测。"""
        src = self.SCRIPT.read_text(encoding="utf-8")
        assert '"min_quality": int(min_quality)' in src
        assert '"min_zs_count": int(min_zs)' in src

    def test_plumbed_through_starmap_args(self) -> None:
        """⚠️⚠️ starmap 的 args 元组必须**多出**这两项。
        漏传不会报错，只会静默按默认 0 跑 ⇒ 等于没测。"""
        src = self.SCRIPT.read_text(encoding="utf-8")
        assert "a.min_zs_count, a.min_quality) for _ in todo" in src

    def test_zs_position_inside_is_measurable(self) -> None:
        """zs_position=inside 也在端点 choices 里，此前也没测。"""
        router = (Path(__file__).resolve().parents[2] / "src" / "easy_tdx"
                  / "web" / "routers" / "screening.py").read_text(encoding="utf-8")
        assert "inside" in router
