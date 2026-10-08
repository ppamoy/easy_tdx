"""笔背驰「必须创新极值」边界（V731 审计补测）。

已有 tests/unit/test_chanlun_beichi_edges.py 锁定了 _check_pz_beichi /
_check_qs_beichi 的防御分支（8 条），但**没有覆盖 `_check_bi_level_beichi`**
—— 而笔背驰是最基础的背驰类型，买卖点大量依赖它。

本文件锁定笔背驰的核心前提（缠论原文）：

    **背驰必须先创新高（向上笔）/ 新低（向下笔）**，
    否则只是普通回调/反抽，不能叫背驰。

实测数据（closes 为真衰竭形态：前段陡涨 10→14，后段缓涨创新高 14.5）：
    笔0 力度=5.6498、笔1 力度=0.5399、比值=0.096（远小于 0.8）
此时「是否创新高」是唯一决定因素：
    高点 14.5（创新高）→ 判背驰；14.0 / 13.5 / 13.0 → 不判。

注意一个**易踩的构造坑**：`_calc_bi_force` 按 `bi.start/end.bar_index` 窗口
取 closes 算 MACD，**与 bi.high/low 无关**。若用常数 closes，力度恒为 0，
`curr_force > 0` 不成立，所有场景都会返回"无背驰" —— 那是测试数据的问题，
不是代码行为。本文件用分段构造的真波动 closes，确保力度非零且真的衰竭。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from easy_tdx.chanlun.beichi import _check_bi_level_beichi
from easy_tdx.chanlun.mmd_conditions import _calc_bi_force
from easy_tdx.chanlun.types import BI, FX, Direction, FXType


def _real_exhaustion_closes() -> list[float]:
    """前段陡涨（力度大）、后段缓涨创新高（力度小）的真衰竭序列。"""
    closes: list[float] = []
    for i in range(31):  # bar 0-30: 10 -> 14 陡涨
        closes.append(10 + 4.0 * i / 30)
    for i in range(31, 41):  # bar 31-40: 回调
        closes.append(14 - 1.0 * (i - 30) / 10)
    for i in range(41, 71):  # bar 41-70: 缓涨到 14.5
        closes.append(13 + 1.5 * (i - 40) / 30)
    closes += [14.5] * 29  # 走平
    return closes


def _mk_bi(
    index: int,
    direction: str,
    s_bar: int,
    e_bar: int,
    closes: list[float],
    hi_override: float | None = None,
    lo_override: float | None = None,
) -> BI:
    """构造带 bar_index 的笔（力度窗口按 bar_index 取 closes）。"""
    hi = max(closes[s_bar : e_bar + 1])
    lo = min(closes[s_bar : e_bar + 1])
    if hi_override is not None:
        hi = hi_override
    if lo_override is not None:
        lo = lo_override

    def _fx(is_top: bool, bar: int) -> FX:
        f = FX(
            fx_type=FXType.DING if is_top else FXType.DI,
            k=type(
                "CLK",
                (),
                {"k_index": bar, "index": bar, "date": datetime(2025, 1, 1)},
            )(),
            klines=[],
            val=hi if is_top else lo,
            index=bar,
            done=True,
        )
        f.bar_index = bar
        return f

    up = direction == "up"
    b = BI(
        start=_fx(not up, s_bar),
        end=_fx(up, e_bar),
        direction=Direction.UP if up else Direction.DOWN,
        high=hi,
        low=lo,
    )
    b.start.bar_index = s_bar
    b.end.bar_index = e_bar
    b.index = index
    return b


class TestBiBeichiRequiresNewExtreme:
    """笔背驰必须先创新高/新低。"""

    def test_up_new_high_with_exhaustion_is_beichi(self) -> None:
        """对照组正向：创新高 + 力度衰竭 → 判背驰（证明数据构造有效）。"""
        closes = _real_exhaustion_closes()
        b0 = _mk_bi(0, "up", 0, 30, closes)
        b1 = _mk_bi(1, "up", 41, 70, closes)
        assert b1.high > b0.high, "构造前提：后笔必须创新高"
        f0 = _calc_bi_force(b0, closes, 0)
        f1 = _calc_bi_force(b1, closes, 1)
        assert f0 > 0 and f1 > 0, "构造前提：两段力度都必须非零"
        assert f1 / f0 < 0.8, f"构造前提：力度必须衰竭，实际比值 {f1 / f0:.3f}"

        res = _check_bi_level_beichi([b0, b1], closes)
        assert len(res) == 1, "创新高且力度衰竭时应判笔背驰"

    @pytest.mark.parametrize("hi", [14.0, 13.5, 13.0])
    def test_up_no_new_high_is_not_beichi(self, hi: float) -> None:
        """力度同样衰竭，但未创新高 → 不得判背驰。"""
        closes = _real_exhaustion_closes()
        b0 = _mk_bi(0, "up", 0, 30, closes)
        b1 = _mk_bi(1, "up", 41, 70, closes, hi_override=hi)
        assert b1.high <= b0.high, "构造前提：后笔未创新高"
        res = _check_bi_level_beichi([b0, b1], closes)
        assert len(res) == 0, f"未创新高（高点={hi}）不应判背驰"

    def test_down_no_new_low_is_not_beichi(self) -> None:
        """向下笔：未创新低 → 不得判背驰。"""
        closes = _real_exhaustion_closes()
        b0 = _mk_bi(0, "down", 0, 30, closes)
        b1 = _mk_bi(1, "down", 41, 70, closes, lo_override=11.0)
        assert b1.low >= b0.low, "构造前提：后笔未创新低"
        res = _check_bi_level_beichi([b0, b1], closes)
        assert len(res) == 0, "向下笔未创新低不应判背驰"


class TestBiBeichiConstantClosesPitfall:
    """常数 closes 会让力度恒 0 —— 那是数据问题，不是「无背驰」的结论。

    这条是**反向锁定**：提醒后来者不要拿全常数 closes 去断言"代码不判背驰"。
    """

    def test_constant_closes_yields_no_beichi_but_force_is_zero(self) -> None:
        closes = [10.0] * 200
        b0 = _mk_bi(0, "up", 0, 30, closes)
        b1 = _mk_bi(1, "up", 41, 70, closes, hi_override=15.0)
        res = _check_bi_level_beichi([b0, b1], closes)
        assert len(res) == 0
        # 力度恒 0 ⇒ 是数据无信息，而非"没有背驰"的证据
        assert _calc_bi_force(b0, closes, 0) == 0.0
