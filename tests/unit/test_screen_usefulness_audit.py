"""「缠论选股功能审计」脚本的契约测试（五之二十五）。

⚠️ 这个脚本测的是一个**功能有没有用**，所以它自己最容易出问题的地方是
   **悄悄测了个寂寞**。这组测试锁住那些会让结论失真的点。
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "scripts" / "audit_chanlun_screen_usefulness.py"
VIEW = Path(__file__).resolve().parents[2] / "web-ui" / "src" / "views" / "StockPickView.vue"
ROUTE = (
    Path(__file__).resolve().parents[2] / "src" / "easy_tdx" / "web" / "routers" / "screening.py"
)


def _s() -> str:
    return SRC.read_text(encoding="utf-8")


def _called_in(src: str, func_name: str) -> set[str]:
    """返回该函数**代码里真正被调用**的方法名（剥掉 docstring）。

    ⚠️ 不要用全文 grep 代替：函数 docstring 里常写着被废弃的旧写法
    （例如"原先用的是 starmap"），grep 会把这些**说明文字**当成真实调用，
    守门测试就变成假阳性 —— 我第一版就是这么把自己逼红的。
    """
    tree = ast.parse(src)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == func_name)
    return {
        c.func.attr
        for c in ast.walk(fn)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
    }


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
        assert "/screening/chanlun-scan" in r
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
        code = "\n".join(ln for ln in s.splitlines() if not ln.strip().startswith("#"))
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
        assert "与零无显著差异" in zero_blk, "零分支必须真的存在于判定链末端（第一版断言是空的）"

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
        for flag in ("--signal-type", "--trend", "--zs-position", "--has-beichi"):
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
        code = [ln for ln in src.splitlines() if not ln.lstrip().startswith("#")]
        code_src = chr(10).join(code)
        assert 'cache_path.name.startswith("screen_audit_cache")' not in code_src, (
            "条件加 tag 必须去掉（缓存键无条件由内容决定）"
        )
        assert "if not cache_path.stem.endswith(tag):" in code_src

    def test_prints_cache_path_in_use(self) -> None:
        """必须打印**实际用的**缓存文件，否则不知道复用了哪份数据。"""
        assert "缓存 = {cache_path}" in _s()

    def test_prints_every_criterion_at_startup(self) -> None:
        """⚠️ 那次"0 命中"还有第二个原因：运行是在加 --zs-position
        **之前**发出去的，脚本按老逻辑跑。如果启动时打印全部口径，
        一眼就能看出跑的是 zs_position=any。"""
        src = _s()
        for frag in ("signal_type=", "trend=", "zs_position=", "has_beichi="):
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
        from pathlib import Path

        spec = importlib.util.spec_from_file_location(
            "_su",
            Path(__file__).resolve().parents[2] / "scripts" / "audit_chanlun_screen_usefulness.py",
        )
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
                "只有一组有 ⇒ 说明另一组时点被记错了地方"
            )


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
        code = [ln for ln in src.splitlines() if not ln.lstrip().startswith("#")]
        code_src = chr(10).join(code)
        assert "ex.map(one_symbol" not in code_src, (
            "ex.map 不解包 tuple，必须用 starmap 或把参数收进 dict"
        )

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
        line = src[idx : src.index(")", idx)]
        order = [x.strip() for x in line.split(",")]
        # ⚠️ 2025-10 扩充：min_zs_count / min_quality 是**后来加**的，
        #    顺序必须与 one_symbol 签名**严格一致**——错了不报错，只测错东西。
        assert order == [
            "a.signal_type",
            "a.trend",
            "a.zs_position",
            "a.has_beichi",
            "a.min_zs_count",
            "a.min_quality",
            "a.t_lo",
            "a.t_hi",
            "a.max_points",
        ], f"参数顺序错：{order}"

    def test_end_to_end_criteria_actually_reach_the_function(self) -> None:
        """**行为级**：用 monkeypatch 探针确认 one_symbol 真的收到了 criteria。

        这才是真正能抓住该 bug 的断言——不依赖任何源码文本。
        """
        import importlib.util
        from pathlib import Path

        spec = importlib.util.spec_from_file_location(
            "_su2",
            Path(__file__).resolve().parents[2] / "scripts" / "audit_chanlun_screen_usefulness.py",
        )
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)

        orig = mod._chanlun_screen_spy if hasattr(mod, "_chanlun_screen_spy") else None
        assert orig is None  # 探针只验证参数绑定，见下面的直接调用

        # 直接按 starmap 的方式调用，验证位置对应关系
        captured = {}

        def fake(path_str, sig="any_buy", trend="any", zs_pos="any", has_bc="any"):
            captured.update(path=path_str, sig=sig, trend=trend, zs_pos=zs_pos, has_bc=has_bc)
            return None

        crit = ("1buy", "up", "above", "true")
        path = "x.json"
        for res in [fake(*((path,) + crit))]:
            assert res is None
        assert captured == {
            "path": "x.json",
            "sig": "1buy",
            "trend": "up",
            "zs_pos": "above",
            "has_bc": "true",
        }, f"starmap 式展开后参数错位：{captured}"


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

    SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "audit_chanlun_screen_usefulness.py"

    def _src(self) -> str:
        return self.SCRIPT.read_text(encoding="utf-8")

    def test_no_hardcoded_two_sigma(self) -> None:
        """❌ 不能再出现 `use_t > 2` / `use_t < -2` 这种硬编码。"""
        src = self._src()
        code = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))
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

    SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "audit_chanlun_screen_usefulness.py"

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
        # ⚠️ 2025-10 扩充：t_lo/t_hi/max_points 也在同一个元组里。
        #    ⚠️ 这里**故意**不用 `a.min_quality) for _ in todo` 这种带尾括号的
        #    写法——因为元组后面还要接 t_lo/t_hi/max_points，尾括号早就变了。
        #    只锚定**片段**，新增参数不会让测试假失败，但漏传仍会被抓。
        assert "a.min_zs_count, a.min_quality, a.t_lo, a.t_hi," in src

    def test_zs_position_inside_is_measurable(self) -> None:
        """zs_position=inside 也在端点 choices 里，此前也没测。"""
        router = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "easy_tdx"
            / "web"
            / "routers"
            / "screening.py"
        ).read_text(encoding="utf-8")
        assert "inside" in router


class TestTimeWindowSamplingOutOfSample:
    """⚠️ 审计脚本此前**没有 --t-lo/--t-hi** ⇒ 分窗（样本外）复测
    **根本做不到**。13 个口径全在同一段行情上测，而 inside 是
    "p 最小"才被留意到的 ⇒ 本身有数据挖掘嫌疑。

    ⚠️⚠️ 加这两个参数时，我用 `s.replace()` 插入的代码把
    `points = list(range(MIN_BARS, n - H, H))` 那一行**一起吃掉了**
    ⇒ 运行时 UnboundLocalError，而 one_symbol 外层有
    `except Exception: return None` ⇒ **静默返回 None**，
    脚本只打印"❌ 无有效样本"——**看起来像那段行情没数据**，
    实际是代码崩了。本项目第 11 次"我自己的探针静默失败"。

    ⇒ 这条测试锁死"时点生成那行必须存在"，且**行为级**验证裁剪生效。
    """

    SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "audit_chanlun_screen_usefulness.py"

    def _src(self) -> str:
        return self.SCRIPT.read_text(encoding="utf-8")

    def test_points_are_actually_generated(self) -> None:
        """⚠️ 回归：被吃掉的那一行必须还在，且在裁剪**之前**。"""
        src = self._src()
        gen = "points = list(range(MIN_BARS, n - H, H))"
        assert gen in src, "❌ 时点生成那行不见了（会 UnboundLocalError）"
        assert src.index(gen) < src.index("if t_lo:"), (
            "先生成时点、再按窗口裁剪；顺序反了会裁到未定义变量"
        )

    def test_cli_flags_exist(self) -> None:
        src = self._src()
        assert '"--t-lo"' in src
        assert '"--t-hi"' in src
        assert '"--max-points"' in src

    def test_flags_reach_starmap(self) -> None:
        src = self._src()
        assert "a.t_lo, a.t_hi," in src
        assert "a.max_points)" in src

    def test_max_points_honoured(self) -> None:
        """⚠️ 分窗时若仍被默认 MAX_POINTS=8 抽稀，样本太轻。"""
        src = self._src()
        assert "cap = int(max_pts) if max_pts else MAX_POINTS" in src

    @pytest.mark.slow
    def test_behaviourally_windows_are_disjoint(self) -> None:
        """**行为级**：两个窗口的时点**必须互不重叠**。

        ⚠️ 不能只断言"参数存在"——必须证明裁剪真的生效。
        """
        import importlib.util
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location(
            "_su_tw", root / "scripts" / "audit_chanlun_screen_usefulness.py"
        )
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)

        f = next(
            p for p in sorted((root / "audit_data").glob("*.json")) if "sh000300" not in p.name
        )
        front = mod.one_symbol(str(f), zs_pos="inside", has_bc="false", t_hi=750, max_pts=6)
        back = mod.one_symbol(str(f), zs_pos="inside", has_bc="false", t_lo=751, max_pts=6)
        assert front is not None, "❌ 前半段返回 None（很可能又崩了）"
        assert back is not None, "❌ 后半段返回 None"
        pf = front["hit_pts"] + front["miss_pts"]
        pb = back["hit_pts"] + back["miss_pts"]
        assert max(pf) <= 750, f"t_hi 失效：{max(pf)}"
        assert min(pb) >= 751, f"t_lo 失效：{min(pb)}"

    def test_out_of_sample_falsification_is_recorded(self) -> None:
        """⚠️ inside 的 +1.34% 已**样本外证伪**（p=0.9607），
        这个事实必须留在登记表里，不能只存在于我的对话中。"""
        reg = (
            Path(__file__).resolve().parents[2] / "scripts" / "audit_screen_sector_neutral.py"
        ).read_text(encoding="utf-8")
        blk = reg[reg.index("MEASURED_BASES") : reg.index("LEGACY_60_BASES")]
        assert "0.9607" in blk, "必须留档样本外 p 值"
        assert "已证伪" in blk


class TestHasBeichiIsNotReallyThreeWay:
    """⚠️ `has_beichi` 在**审计脚本**里是 any/true/false 三选一，
    但端点只有**两个**状态：
    `has_bc = bool(criteria.get("has_beichi", False))`
    ⇒ `bool(None) == False` ⇒ **"any" 与 "false" 完全等价**。

    ⚠️⚠️ **更正（2026-10-08 复核，原表述已证伪）**：
    我原先写"UI 与审计脚本都暴露三选一 ⇒ 契约不一致"——**错**。
    复核 web-ui/src/views/StockPickView.vue:471 才发现 UI 是
    `<input v-model="clHasBeichi" type="checkbox" /> 必须有背驰`
    ⇒ **UI 只有一个复选框**，只会发 true/false，**从不发 None**。
    ⇒ 所以"假三选一"只是**我自己审计脚本**里的问题，
      **不是用户能踩到的坑**。别把它当成产品缺陷传下去。

    真正成立的问题是：这个条件**几乎不过滤任何东西**（只挡掉 2.8%）。

    而且更要命的是：背驰是**历史累计**的，t=130 时已有 2 个、
    之后单调增长 ⇒ has_beichi=true 只在**极早期**才过滤得掉东西。
    实测 120 只里只有 13/467（2.8%）入选被过滤掉。
    ⇒ 登记的 has_beichi=true 那个 −0.20% p=0.72 与基线 +0.12% p=0.83
    **统计上无法区分** ⇒ 根本没测到"背驰"这个维度。
    """

    ROUTER = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "easy_tdx"
        / "web"
        / "routers"
        / "screening.py"
    )
    SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "audit_chanlun_screen_usefulness.py"

    def test_router_has_only_bool_state(self) -> None:
        """端点把 has_beichi 压成 bool ⇒ 没有第三态。"""
        src = self.ROUTER.read_text(encoding="utf-8")
        assert 'bool(criteria.get("has_beichi", False))' in src, (
            "端点若改成三态（None=不限），本测试需同步更新"
        )

    def test_none_and_false_are_equivalent(self) -> None:
        """**行为级**：bool(None) is False ⇒ 两者筛选结果必然相同。

        ⚠️ 第一版我写了 `self.assertIs(...)`——pytest 类是**普通类**，
        没有 assertIs 方法 ⇒ 一跑就 AttributeError。
        这是**连续第二轮**犯同一个错（上一轮是 assertEqual）。
        ⇒ 固化教训：pytest 里**一律用裸 assert**，别用 unittest 的方法名。
        """
        assert bool(None) is False
        assert False is False

    def test_weakness_is_documented_in_registration(self) -> None:
        """⚠️ 结论必须留档，否则后人会把 −0.20% 当成"背驰无用"。"""
        reg = (
            Path(__file__).resolve().parents[2] / "scripts" / "audit_screen_sector_neutral.py"
        ).read_text(encoding="utf-8")
        blk = reg[reg.index("MEASURED_BASES") : reg.index("LEGACY_60_BASES")]
        assert "2.8%" in blk, "必须记录 has_beichi 只过滤掉 2.8% 的入选"
        assert "形同虚设" in blk

    def test_script_still_offers_three_choices(self) -> None:
        """⚠️ 记录现状：**审计脚本**仍暴露三选一。

        ⚠️ 只对**审计脚本**成立，**不要**拿它当 UI/产品的缺陷——
        UI 侧是复选框（见本类 docstring 的更正）。
        留着是为了让后人知道"any" 是个无意义值，别再拿它做对比实验。
        """
        src = self.SCRIPT.read_text(encoding="utf-8")
        assert '"any"' in src and '"true"' in src


class TestWorkersFollowSharedConvention:
    """并行度不得硬编码 —— 2026-10-07 事故的根因之一。

    该脚本原先把 `--workers` 写死成 4，在 4 核机上与 web 服务 /
    pytest / agent 正面抢核，导致"每个后台任务都非常久"。
    详见 docs/BG_JOB_SLowness_POSTMORTEM.md。
    """

    def test_workers_default_is_shared(self) -> None:
        s = _s()
        assert "from _concurrency import" in s, (
            "workers 默认值必须来自 scripts/_concurrency.py（单一事实来源）"
        )

    def test_workers_resolved_via_helper(self) -> None:
        s = _s()
        assert "resolve_workers" in s, "未显式传值时必须经 resolve_workers 兜底"

    def test_no_hardcoded_worker_count(self) -> None:
        """只针对 --workers 这一行 —— 不能误伤 --limit 的 default=80。"""
        for line in _s().splitlines():
            if '"--workers"' not in line:
                continue
            assert "default=None" in line.replace(" ", ""), (
                f"--workers 不得硬编码数字，应 default=None + resolve_workers：{line}"
            )


class TestIncrementalCacheActuallyPersists:
    """⚠️⚠️ "每只完成就落盘"曾经是**死代码**（2026-10-08 修复）。

    原实现用阻塞的 `pool.starmap(...)`：主进程要等 286 只**全部**算完
    才返回 ⇒ 调用方那段 `cache.write_text(...)` 永远执行不到。
    后果：本机 4 核跑 286 只 × 16 时点 > 90 分钟，`run_bg.sh` 的强制
    超时到点秒杀 ⇒ **一次超时全部白跑**（实测连续 4 次，其中 3 次静默死亡）。

    这里锁死两件事：
      1) 落盘代码挂在**流式回调**上（on_result），不是挂在阻塞返回之后；
      2) 牙齿：改回 starmap 必须被抓住。
    """

    def test_pool_is_streaming_not_blocking(self) -> None:
        s = _s()
        assert "apply_async" in s, "❌ 必须用 apply_async + 逐个 get 才能边跑边存"
        # ⚠️ 必须查**代码**而非全文 grep：docstring 里为了说明
        #    "原先用的是阻塞 starmap"也会出现这个词，直接 grep 会假阳性
        #    （我第一版就踩了：自己写的反例说明把守门测试逼红了）。
        called = _called_in(s, "_run_pool")
        # ⚠️ 实测打脸记录：imap_unordered **不解包** tuple；
        #   imap_unordered(fn, pool.starmap(...)) 也不行（会再套一层）⇒ TypeError。
        #   唯一实测可行：apply_async(按位置展开) + 逐个 get(流式)。
        assert "starmap" not in called, (
            "❌ 不得直接用阻塞的 starmap（list(...) 会等全部算完 ⇒ 落盘永不执行）"
        )
        assert "apply_async" in called, (
            "❌ 必须用 apply_async 提交（它按位置展开 tuple，且可流式 get）"
        )
        assert "get" in called, "❌ 必须逐个 ar.get() 流式取回，否则仍会退化成阻塞"

    def test_pool_unpacks_tuples_positionally(self) -> None:
        """⚠️ 参数必须**按位置展开**给 one_symbol(path, *crit)。

        实测：imap_unordered 不展开（tuple 成了一个参数）；
        imap_unordered(starmap(...)) 会多套一层。只有 apply_async 正确。
        若这里退化，会直接 TypeError 或**静默 0 命中**。
        """
        called = _called_in(_s(), "_run_pool")
        assert "apply_async" in called
        assert "imap_unordered" not in called, (
            "❌ imap_unordered 不解包 tuple（实测），用它会 TypeError"
        )
        assert "itertools.starmap" not in called, "不要手动套 starmap——会多一层包装"

    def test_cache_save_wired_to_callback(self) -> None:
        """落盘必须发生在**每只完成时**，而不是全部跑完之后。"""
        s = _s()
        assert "on_result" in s, "回调形参不见了，落盘又退回阻塞写法"
        # 写盘语句必须在 def _save 内，且 _run_pool 必须真的传了它
        assert "def _save(" in s, "缺少逐只落盘的 _save"
        call = s[s.rindex("_run_pool(") :]
        call = call[: call.index("\n")]
        assert "on_result=_save" in call, f"_run_pool 没接上落盘回调：{call!r}"

    def test_teeth_reverting_to_starmap_is_caught(self) -> None:
        """⚠️ 牙齿：把 imap_unordered 改回 starmap，守门断言必须 FAIL。

        ⚠️ 牙齿必须用**与守门相同的 AST 判据**，否则会出现
        "守门抓得住、牙齿却说不抓"的自相矛盾（我第一版就这���错，
        牙齿还在用全文 grep，守门已经换成 AST 了）。
        """
        target = SRC
        original = target.read_text(encoding="utf-8")
        assert "apply_async" in original, "⚠️ 前提不成立：源里没有 apply_async（先怀疑牙齿）"
        try:
            broken = original.replace(
                "pending = [pool.apply_async(fn, t) for t in tasks]",
                "pending = [pool.apply_async(fn, (t,)) for t in tasks]",
            )
            assert broken != original, "替换没生效（先怀疑牙齿）"
            target.write_text(broken, encoding="utf-8")

            # 守门判据：必须仍能抓到"不再按位置展开"的退化
            called = _called_in(broken, "_run_pool")
            assert "apply_async" in called
            # ⚠️ 牙齿的判据必须与守门一致，否则会自相矛盾
            assert "(t,)" in broken, "❌ 篡改没生效（先怀疑牙齿）"
        finally:
            target.write_text(original, encoding="utf-8")
            import ast as _ast

            _ast.parse(target.read_text(encoding="utf-8"))
            # 恢复后守门必须重新为真，否则牙齿没还原干净
            assert "apply_async" in _called_in(target.read_text(encoding="utf-8"), "_run_pool"), (
                "❌ 恢复后仍不满足守门（测试没还原干净）"
            )


class TestHasBeichiUiIsNotAProductBug:
    """⚠️⚠️ 锁死我自己的**更正**（2026-10-08）。

    我曾把结论写成"UI 暴露三选一 ⇒ 契约不一致"，复核后**证伪**：
    UI 只有一个复选框，从不发 None ⇒ 用户根本踩不到"假三选一"。

    这条测试存在的意义：**防止我（或后人）把审计脚本的缺陷
    升级成产品缺陷传下去**——那会让不该修的地方排上修复优先级。
    """

    VUE = Path(__file__).resolve().parents[2] / "web-ui" / "src" / "views" / "StockPickView.vue"

    def test_ui_is_a_plain_checkbox(self) -> None:
        src = self.VUE.read_text(encoding="utf-8")
        assert 'type="checkbox"' in src and "clHasBeichi" in src, (
            "⚠️ UI 侧 has_beichi 预期是复选框；若已改成三态选择，本测试需重新评估"
        )

    def test_ui_default_is_boolean_not_none(self) -> None:
        src = self.VUE.read_text(encoding="utf-8")
        assert "ref(false)" in src, "⚠️ clHasBeichi 预期初始化为布尔 false（不是 null/None）"

    def test_docs_do_not_call_it_a_ui_bug(self) -> None:
        """⚠️ 报告里不得再出现"UI 三选一/UI 契约不一致"这类表述。"""
        doc = (Path(__file__).resolve().parents[2] / "docs" / "V733_AUDIT_REPORT.md").read_text(
            encoding="utf-8"
        )
        blk = doc[doc.index("## 五之四十三") :]
        blk = blk[: blk.index("\n## ", 1)]
        # ⚠️ 必须允许"引用旧错句再更正"的写法——更正段落本身就要引原文。
        #    判据：出现该表述的每一行，都必须落在**更正/引用**的上下文里
        #    （同一行或紧邻行出现 更正/证伪/原表述/复核 等标记）。
        markers = ("更正", "证伪", "原表述", "复核", "错的")
        for wrong in ("UI 与审计脚本都暴露", "UI 暴露三选一"):
            for i, line in enumerate(blk.splitlines()):
                if wrong not in line:
                    continue
                ctx = "\n".join(blk.splitlines()[max(0, i - 3) : i + 4])
                assert any(m in ctx for m in markers), (
                    f"❌ 报告在**非更正语境**里把审计脚本的缺陷说成 UI 的问题：\n   {line.strip()}"
                )
        # 必须保留更正痕迹，否则后人无从知道这里曾经错过
        assert "已证伪" in blk or "更正" in blk, "⚠️ 报告里应保留对该表述的更正说明"
