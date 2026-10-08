"""V733 像素级渲染验证脚本的**契约测试**。

这个脚本花了很多轮才调通，过程里最危险的一点是：
**探针失效被误读成"功能失效"**（AGENTS.md 案例 A 的同源错误）。
第一版探针依赖 `window.echarts`，而本项目用 `echarts/core` 按需引入、
根本不挂全局 ⇒ 探针恒定返回"找不到实例"，而页面其实 canvas=1 正常显示。
我差点据此断言"缠论图没渲染"。

所以本测试锁死的是**那些曾经真的坑到我**的性质：
不依赖拿不到的内部 API、探针异常必须可见、断言必须与缩放无关、牙齿必须可跑。
"""

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "e2e_chanlun_pixels.py"


def _src() -> str:
    return SCRIPT.read_text(encoding="utf-8")


class TestScriptExists:
    def test_script_present(self) -> None:
        assert SCRIPT.exists(), f"缺少 {SCRIPT}"


class TestNoDependencyOnUnexposedInternals:
    """⚠️ 这条最重要：第一版就是这样翻车的。"""

    def test_does_not_require_window_echarts(self) -> None:
        s = _src()
        assert "window.echarts.getInstanceByDom" not in s, (
            "本项目用 echarts/core 按需引入，不挂 window.echarts；依赖它会恒定失败"
        )

    def test_does_not_require_ec_inner_attr(self) -> None:
        """文档里可以提这个坑，但**探针 JS 里不能用**。"""
        s = _src()
        # 只允许出现在模块 docstring（说明为什么不用它）
        body = s.split('"""', 2)[-1]
        assert "__ec_inner_" not in body, (
            "实测容器 DOM 上没有 __ec_inner_（实例存在组件局部变量里），不能依赖"
        )

    def test_reads_real_pixels(self) -> None:
        s = _src()
        assert "getImageData" in s, "必须读真实像素，不能只数 DOM"

    def test_uses_actual_theme_colors(self) -> None:
        """红涨绿跌取自 echarts-setup.ts 的 UP_COLOR/DOWN_COLOR。"""
        s = _src()
        assert "0xef" in s and "0x41" in s and "0x46" in s
        assert "0x18" in s and "0xa0" in s and "0x58" in s


class TestProbeErrorsAreVisible:
    """⚠️ ev() 吞异常曾让"探针坏了"看起来像"功能坏了"。"""

    def test_checks_exception_details(self) -> None:
        s = _src()
        assert "exceptionDetails" in s

    def test_raises_on_js_exception(self) -> None:
        s = _src()
        assert "页面 JS 异常" in s

    def test_has_channel_self_test(self) -> None:
        """启动时先证明探针能报错，否则后面结果都不可信。"""
        s = _src()
        assert "BOOM" in s
        assert "探针通道" in s

    def test_enforces_json_contract(self) -> None:
        """探针必须返回 JSON 字符串；裸字符串会被吞成 {}。"""
        s = _src()
        assert "探针契约" in s

    def test_buffers_cdp_events(self) -> None:
        """⚠️ 等命令响应时会顺带收到事件，丢了网络探针恒为 0 条。"""
        s = _src()
        assert "events.append" in s


class TestAssertionsAreZoomIndependent:
    """⚠️ 段数/间距随 dataZoom 变化（实测 195→164→42→5 段）。"""

    def test_uses_color_switch_count(self) -> None:
        s = _src()
        assert "switches" in s
        assert "红绿交替" in s

    def test_does_not_assert_on_segment_spacing(self) -> None:
        s = _src()
        assert "相邻蜡烛左缘间距" not in s, "该断言依赖缩放级别，曾误判为'x 轴映射错位'"

    def test_waits_for_stable_render(self) -> None:
        """连续两次扫描一致才算稳定，避开动画中途。"""
        s = _src()
        assert "还在动画" in s or 'p2.get("red") != p1' in s


class TestTeethTest:
    """AGENTS.md §7：脚本必须先验证它确实能抓到。"""

    def test_has_teeth_probe(self) -> None:
        assert "PROBE_TEETH" in _src()

    def test_teeth_clears_canvas(self) -> None:
        s = _src()
        assert "clearRect" in s

    def test_teeth_uses_same_criteria(self) -> None:
        """牙齿必须用与主检测相同的判据，否则不算验证。"""
        s = _src()
        assert s.count("switches") >= 4

    def test_teeth_runs_in_same_round(self) -> None:
        """⚠️ 隔几秒再擦，前端已重挂载图表，牙齿会拿到 null 而形同虚设。"""
        s = _src()
        assert "同轮" in s

    def test_teeth_verdict_is_enforced(self) -> None:
        s = _src()
        assert "牙齿不成立" in s
        assert "检测器常真" in s


class TestResolutionGateHonesty:
    """⚠️ 本轮我自己踩的坑，值得单列一组。

    我加了"逐点核对"后，测出一致率 70.2% < 90%，差点判定
    「K 线顺序画错了」。**核查后证明是我测不准，不是图画错**：
    dataZoom(start=50,end=100) 下 800 根画在约 1000px 绘图区，
    每根仅 2.9px，**同色相邻蜡烛的像素会连成一片**，
    800 根只抽出 47 个可分辨段 —— 分辨率根本不够逐点比对。

    这正是 AGENTS.md §3：先验证，再下结论。测不准 ≠ 功能坏。
    """

    def test_reports_undeterminable_instead_of_guessing(self) -> None:
        s = _src()
        assert "不可判定" in s

    def test_states_it_is_not_a_chart_bug(self) -> None:
        """必须明确区分'测不准'与'图画错了'。"""
        s = _src()
        assert "分辨率不足，非图表错误" in s

    def test_explains_why_measurement_fails(self) -> None:
        s = _src()
        assert "粘连" in s

    def test_states_minimum_px_per_candle(self) -> None:
        s = _src()
        assert "≥6px" in s

    def test_gates_on_segment_count(self) -> None:
        """分辨率门槛必须真的生效（段数太少就不给准确率）。"""
        s = _src()
        assert "_nseg < _nbar * 0.3" in s

    def test_undeterminable_does_not_fail_the_gate(self) -> None:
        """⚠️ 关键：CI 里跑的就是这个脚本。
        "逐点核对不可判定"是**测量方法不行**，不是图表坏了 ——
        若它把 ok 置 False，CI 就会因为一个测不了的检查而常红，
        那还不如不测。这条锁死它只 WARN 不 FAIL。"""
        src = _src()
        blk = src[src.index("逐点核对**不可判定**") :]
        blk = blk[: blk.index("else:")]
        assert "ok = False" not in blk, (
            "不可判定分支不得置 ok=False，否则 CI 会因测不了的检查而常红"
        )

    def test_real_failures_still_fail(self) -> None:
        """但真正的失败（配色缺失/牙齿不成立）必须仍然会红。"""
        assert _src().count("ok = False") >= 3, "必须保留真正的失败出口，不能把门禁改成永绿"

    def test_does_not_count_pixel_columns_as_segments(self) -> None:
        """⚠️ cols 是每列一个色值，非零列数≈像素宽，**不是 K 线段数**。
        我第一版就是这么算错的，导致门槛失效、仍报 70.2% 假准确率。"""
        s = _src()
        wrong = 'sum(1 for c in (cols.get("cols") or []) if c)'
        assert wrong not in s, "非零列数是像素宽不是段数，会让分辨率门槛失效"


class TestAlignmentUsesRealChartData:
    def test_uses_pages_own_bars(self) -> None:
        """必须用页面实际渲染的那份数据，不能自己另查一个窗口。"""
        s = _src()
        assert "__barResponses" in s

    def test_intercepts_fetch_response_body(self) -> None:
        s = _src()
        assert "r.clone().json()" in s

    def test_derives_colors_from_real_ohlc(self) -> None:
        s = _src()
        assert "expected_colors" in s
        assert 'float(b["open"])' in s or "b['open']" in s

    def test_red_is_up_per_frontend_theme(self) -> None:
        """红涨绿跌取自 echarts-setup.ts 的 UP_COLOR。"""
        s = _src()
        assert "close" in s and ">= o" in s


class TestHonestLimitations:
    def test_declares_no_per_point_mapping(self) -> None:
        """不能声称做了逐点像素映射——本项目不暴露 ECharts 实例。"""
        s = _src()
        assert "不逐点核对" in s or "无法验证" in s

    def test_declares_single_browser(self) -> None:
        s = _src()
        assert "跨浏览器" in s

    def test_documents_the_pitfalls(self) -> None:
        s = _src()
        assert "案例 A" in s
        # 坑点至少记录 6 条（编号 1~6）
        for n in "123456":
            assert f"\n{n}. **" in s, f"缺少第 {n} 条坑的记录"


class TestExitCodes:
    def test_has_three_exit_codes(self) -> None:
        s = _src()
        assert "退出码" in s

    def test_returns_2_when_env_unavailable(self) -> None:
        assert "return 2" in _src()

    def test_env_failure_is_distinct_from_assertion_failure(self) -> None:
        """环境不可用 ≠ 断言失败，不能都返回 0 也不能都返回 1。"""
        s = _src()
        assert "环境不可用" in s


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
