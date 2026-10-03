"""V733「参数敏感性」脚本的契约测试。

⚠️ 本测试源于一个**真实的静默无操作 bug**：
早期版本写的是
    if hasattr(s, k): setattr(s, k, v)
但策略参数存放在 **`s.p`（dict）**里，**不是**实例属性 ⇒
`hasattr(s, 'stop_loss_pct')` 恒为 **False** ⇒ 所有参数改动被静默跳过，
"参数敏感性扫描"实际测的**全是默认值**。

这正是 AGENTS.md §1「拿间接证据冒充验证」的典型：脚本跑完了、输出了表格，
看起来完全正常，但**它什么参数都没改**。本测试锁死正确写法。
"""

from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
PS = SCRIPTS / "audit_param_sensitivity.py"
ROOT = Path(__file__).resolve().parents[2]


def _src() -> str:
    return PS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def chanlun_cls():
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from easy_tdx.backtest.strategies.chanlun import ChanlunStrategy
    return ChanlunStrategy


class TestParamsActuallyApplied:
    """⚠️ 核心：参数必须真的写进 s.p，否则整轮扫描是假象。"""

    def test_writes_into_sp_dict(self) -> None:
        s = _src()
        assert "s.p[" in s, "必须写 s.p[k]（参数在 p 这个 dict 里）"

    def test_no_silent_hasattr_guard(self, chanlun_cls) -> None:
        """`if hasattr(s,k): setattr(...)` 是**静默无操作**，必须禁止。"""
        s = _src()
        assert "hasattr(s, k)" not in s, "hasattr 守卫会让参数改动被静默跳过"

    def test_params_are_not_instance_attrs(self, chanlun_cls) -> None:
        """记录真实结构：setattr 到实例上无效。"""
        st = chanlun_cls()
        assert not hasattr(st, "stop_loss_pct"), "若将来改为实例属性，需同步改脚本"
        assert "stop_loss_pct" in st.p

    def test_setattr_does_not_change_behavior(self, chanlun_cls) -> None:
        """牙齿：证明 setattr 路径确实是错的（否则这测试是摆设）。"""
        st = chanlun_cls()
        before = st.p["stop_loss_pct"]
        st.stop_loss_pct = 0.2          # noqa: B010 故意走错路径
        assert st.p["stop_loss_pct"] == before, "setattr 不影响 p，证明旧写法无效"

    def test_writing_sp_changes_value(self, chanlun_cls) -> None:
        st = chanlun_cls()
        st.p["stop_loss_pct"] = 0.2
        assert st.p["stop_loss_pct"] == 0.2


class TestScriptSelfCheck:
    """脚本必须在扫描前自证参数写入生效。"""

    def test_has_self_check(self) -> None:
        s = _src()
        assert "自检" in s

    def test_self_check_asserts(self) -> None:
        s = _src()
        assert 'assert probe_s.p["stop_loss_pct"] == 0.2' in s

    def test_unknown_params_reported(self) -> None:
        """参数名写错必须报出来，不能悄悄跳过。"""
        s = _src()
        assert "unknown" in s
        assert "未知参数" in s


class TestHonestControls:
    """低仓位也是"回撤小" —— 必须作为诚实基线一起报。"""

    def test_has_low_exposure_baseline(self) -> None:
        s = _src()
        assert "低暴露" in s
        assert "0.3" in s

    def test_low_exposure_called_out_as_leverage(self) -> None:
        s = _src()
        assert "杠杆" in s, "必须说明低仓位降回撤是杠杆效应、与信号无关"

    def test_compares_at_same_position(self) -> None:
        """同仓位对照才能排除低暴露假象。"""
        s = _src()
        assert "同仓位" in s
        assert "position_pct=1.0" in s or "position_pct == 1.0" in s \
            or "r[2] == 1.0" in s

    def test_sweeps_signal_switches_too(self) -> None:
        """不能只扫止损 —— 信号类开关也必须扫。"""
        s = _src()
        for k in ("use_3buy", "use_3sell", "bi_type"):
            assert k in s, f"未扫描信号类参数 {k}"

    def test_declares_grid_is_coarse(self) -> None:
        s = _src()
        assert "粗" in s, "必须声明参数网格较粗、未做全因子搜索"

    def test_declares_dd_only_comparison(self) -> None:
        s = _src()
        assert "不比收益" in s, "只比回撤不比收益会误导（低回撤可能收益也低）"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
