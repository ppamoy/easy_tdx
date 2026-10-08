"""V733 审计：负债率提示必须**引用**常量，不能写死数字。

动机（2026-10-08 实测）：``screener._risk_flags`` 里原先写成
``if float(debt) > 60:`` 并附写死的文案 ``"资产负债率偏高（超过60%）"``，
而同一模块第 35 行已经存在 ``_DEBT_MED = 60.0``。两者**值相同但互不相干**：
改常量不会改动这个提示，语义会悄悄分叉（本项目第 N 次「两处口径漂移」）。

这里的测试不重复上面这句形而上的话，而是**行为级**锁定联动关系：

1. 债务率刚过 ``_DEBT_MED`` ⇒ 必须报警，且文案里的数字必须跟着常量走；
2. 债务率刚好等于 ``_DEBT_MED`` ⇒ 不得报警（严格大于）；
3. **临时把常量改掉 ⇒ 报错门槛必须跟着移动**（这是真正的牙齿）：
   若有人再把 60 写死回去，第 3 条会立刻变红。
"""

from __future__ import annotations

import pytest

from easy_tdx.fundamental import screener as S
from easy_tdx.fundamental.screener import ScreenResult


def _sr(debt_ratio: float) -> ScreenResult:
    """构造一个只带 debt_ratio 的 ScreenResult（其余字段不参与 _risk_flags）。"""
    return ScreenResult(
        code="000001",
        market="SZ",
        category=S.GRAIN,
        scores={},
        details={},
        report_date=None,
        indicators={"debt_ratio": debt_ratio},
    )


class TestDebtFlagFollowsConstant:
    def test_just_above_med_flags(self) -> None:
        flags = S._risk_flags(_sr(S._DEBT_MED + 0.1))
        assert any("资产负债率偏高" in f for f in flags)

    def test_exactly_med_does_not_flag(self) -> None:
        """边界：等于 _DEBT_MED 不算偏高（代码是严格 >）。"""
        flags = S._risk_flags(_sr(S._DEBT_MED))
        assert not any("资产负债率偏高" in f for f in flags)

    def test_message_number_matches_constant(self) -> None:
        """文案里的百分比必须来自常量，避免文案与判定脱钩。"""
        flags = S._risk_flags(_sr(S._DEBT_MED + 0.1))
        hit = [f for f in flags if "资产负债率偏高" in f]
        assert hit, "应至少有一条负债提示"
        assert f"{S._DEBT_MED:.0f}" in hit[0], f"文案写死了数字，没跟 _DEBT_MED 走：{hit[0]}"

    def test_threshold_moves_when_constant_changes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """牙齿所在：改常量 ⇒ 判定门槛必须跟着移动。写死 60 会让这条失败。

        取 45.0 作为**鉴别值**：
        - 真实常量 60 ⇒ 45 不报警（对照组）
        - 把常量改成 30 ⇒ 45 必须报警
        两端都断言，才能证明「判定跟随常量」而不是恰好蒙对。
        """
        # 对照组：真实常量下 45 不报警
        assert not any("资产负债率偏高" in f for f in S._risk_flags(_sr(45.0)))

        monkeypatch.setattr(S, "_DEBT_MED", 30.0)
        # 常量下调后，同一个 45 必须报警
        assert any("资产负债率偏高" in f for f in S._risk_flags(_sr(45.0)))
