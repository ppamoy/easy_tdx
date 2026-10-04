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
        assert "window.echarts.getInstanceByDom" not in s, \
            "本项目用 echarts/core 按需引入，不挂 window.echarts；依赖它会恒定失败"

    def test_does_not_require_ec_inner_attr(self) -> None:
        """文档里可以提这个坑，但**探针 JS 里不能用**。"""
        s = _src()
        # 只允许出现在模块 docstring（说明为什么不用它）
        body = s.split('"""', 2)[-1]
        assert "__ec_inner_" not in body, \
            "实测容器 DOM 上没有 __ec_inner_（实例存在组件局部变量里），不能依赖"

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
        assert "相邻蜡烛左缘间距" not in s, \
            "该断言依赖缩放级别，曾误判为'x 轴映射错位'"

    def test_waits_for_stable_render(self) -> None:
        """连续两次扫描一致才算稳定，避开动画中途。"""
        s = _src()
        assert "还在动画" in s or "p2.get(\"red\") != p1" in s


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


class TestHonestLimitations:
    def test_declares_no_per_point_mapping(self) -> None:
        """不能声称做了逐点像素映射——本项目不暴露 ECharts 实例。"""
        s = _src()
        assert "不逐点核对" in s

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
