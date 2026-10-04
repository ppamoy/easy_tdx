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
        # 负分支：必须真的存在，且带 t<-2 条件
        assert "elif t < -2:" in s
        # 正分支
        assert "elif t > 2:" in s
        # 零分支：必须是**独立的 else 兜底**，而不是默认落到某个含混措辞
        assert "与零无显著差异" in s
        assert "样本不足，无法判定" in s
        # ⚠️ 关键：零分支必须真的在代码里，不能只是"某处出现过这个词"
        zero_blk = s.split("elif t > 2:")[-1]
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
