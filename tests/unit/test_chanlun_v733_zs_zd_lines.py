"""V733 I8：中枢 ZG/ZD「冻结笔数」回归测试 —— 锁死缠论原文口径。

背景（实测，非推测）
--------------------
缠论原文（第17/20/35课）：中枢 = **至少三个连续次级别走势的重叠区间**。
因此 ZG = min(g1,g2,g3)、ZD = max(d1,d2,d3)，由**前三笔共同**确定后冻结，
第 4 笔起只更新 GG/DD。

V730 起的实现把冻结笔数写成了 **2**（`if len(candidate_lines) <= 2`），
于是第 3 笔虽然被计入 `candidate_lines`（使中枢达到 3 笔的成立条件），
却**没有参与 ZG/ZD 的计算**。实测后果（30 只真实日线，557 个含≥3笔中枢）：

    * 52.2% 的中枢**变窄**（改为 3 笔后）—— 说明旧行为让中枢**系统性偏宽**
    * 47.8% 不变，0% 变宽（单调，方向一致）
    * 宽度变化：中位 -4.0%，均值 -19.0%，最大 -97.6%
    * 按严格的 3 笔规则重算，**0 个**中枢变为非法（故这是准确性问题，非崩溃问题）

中枢偏宽会直接放松 3买/3卖 依赖 ZG/ZD 的「突破 / 回踩」阈值。实测改为 3 笔后：
3卖 +17/-13、3买 +12/-10、1买 +11/-3 …… 信号集合确有变化（总 955 → 979）。

本测试锁死
----------
1. 默认 `zs_zd_lines=3`（原文口径）：前三笔共同确定 ZG/ZD；
2. 显式 `zs_zd_lines=2`（旧行为）仍然可得 —— 开关两侧都测；
3. 第 4 笔及以后**只**更新 GG/DD，不动 ZG/ZD；
4. 牙齿验证：把冻结笔数改回 2 后，ZG/ZD 断言**必须失败**。
"""

from __future__ import annotations

import pytest

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import BI, CLKline, Direction, FX, FXType
from easy_tdx.chanlun.zs import find_zss


def _bi(index: int, direction: str, high: float, low: float) -> BI:
    start_fx = FX(
        fx_type=FXType.DI if direction == "up" else FXType.DING,
        k=CLKline(
            k_index=index * 10, date=None, open=low, close=high,  # type: ignore[arg-type]
            high=high, low=low, amount=0.0, index=index,
        ),
        klines=[], val=low if direction == "up" else high, index=index, done=True,
    )
    end_fx = FX(
        fx_type=FXType.DING if direction == "up" else FXType.DI,
        k=CLKline(
            k_index=index * 10 + 5, date=None, open=low, close=high,  # type: ignore[arg-type]
            high=high, low=low, amount=0.0, index=index,
        ),
        klines=[], val=high if direction == "up" else low, index=index, done=True,
    )
    return BI(
        index=index,
        direction=Direction.UP if direction == "up" else Direction.DOWN,
        high=high,
        low=low,
        start=start_fx,
        end=end_fx,
    )


def _bis() -> list[BI]:
    """三笔有明显重叠、且第3笔会**收窄**重叠区的构造。

    笔0: [10, 20]  → zg=20, zd=10
    笔1: [12, 22]  → 重叠 [12,20]
    笔2: [14, 18]  → 三笔重叠 [14,18]（比两笔重叠 [12,20] 更窄）
    笔3: [16, 26]  → 与 [14,18] 重叠 [16,18]（延伸，只更新 GG/DD）
    """
    return [
        _bi(0, "up", 20.0, 10.0),
        _bi(1, "down", 22.0, 12.0),
        _bi(2, "up", 18.0, 14.0),
        _bi(3, "down", 26.0, 16.0),
    ]


class TestZsZdLinesDefault:
    """默认必须是原文口径（3 笔）。"""

    def test_default_is_three(self) -> None:
        assert ChanlunConfig().zs_zd_lines == 3, "默认必须为缠论原文的 3 笔口径"

    def test_three_lines_determine_zd(self) -> None:
        """ZG/ZD 由前三笔共同确定：ZG=min(20,22,18)=18，ZD=max(10,12,14)=14。"""
        zss = find_zss(_bis(), config=ChanlunConfig())
        assert zss, "应识别出中枢"
        zs = zss[0]
        assert zs.zg == pytest.approx(18.0), f"ZG 应为 18（三笔共同），实得 {zs.zg}"
        assert zs.zd == pytest.approx(14.0), f"ZD 应为 14（三笔共同），实得 {zs.zd}"

    def test_gg_dd_from_all_lines(self) -> None:
        """GG/DD 由**全部**构成笔决定（含第4笔）：GG=26, DD=10。"""
        zss = find_zss(_bis(), config=ChanlunConfig())
        zs = zss[0]
        assert zs.gg == pytest.approx(26.0), f"GG 应为 26，实得 {zs.gg}"
        assert zs.dd == pytest.approx(10.0), f"DD 应为 10，实得 {zs.dd}"

    def test_fourth_bi_only_extends(self) -> None:
        """第4笔只更新 GG/DD，不动 ZG/ZD —— 减去第4笔后 ZG/ZD 应不变。"""
        zs4 = find_zss(_bis(), config=ChanlunConfig())[0]
        zs3 = find_zss(_bis()[:3], config=ChanlunConfig())[0]
        assert zs4.zg == pytest.approx(zs3.zg), "第4笔不应改变 ZG"
        assert zs4.zd == pytest.approx(zs3.zd), "第4笔不应改变 ZD"
        # 但 GG 确实被第4笔更新了
        assert zs4.gg > zs3.gg, "第4笔应更新 GG"


class TestZsZdLinesSwitch:
    """开关两侧都必须可用（改了分支就要测两侧）。"""

    def test_two_lines_keeps_legacy_behavior(self) -> None:
        """zs_zd_lines=2 → 旧行为：ZG=min(20,22)=20，ZD=max(10,12)=12。"""
        zss = find_zss(_bis(), config=ChanlunConfig(zs_zd_lines=2))
        zs = zss[0]
        assert zs.zg == pytest.approx(20.0), f"旧行为 ZG 应为 20，实得 {zs.zg}"
        assert zs.zd == pytest.approx(12.0), f"旧行为 ZD 应为 12，实得 {zs.zd}"

    def test_two_vs_three_differ(self) -> None:
        """两种口径必须**真的不同**（否则开关形同虚设）。"""
        a = find_zss(_bis(), config=ChanlunConfig(zs_zd_lines=2))[0]
        b = find_zss(_bis(), config=ChanlunConfig(zs_zd_lines=3))[0]
        assert (a.zg, a.zd) != (b.zg, b.zd), "2 笔与 3 笔口径结果相同 → 开关无效"

    def test_three_is_narrower_or_equal(self) -> None:
        """3 笔口径的中枢不可能比 2 笔更宽（数学必然：多求一次交集）。"""
        a = find_zss(_bis(), config=ChanlunConfig(zs_zd_lines=2))[0]
        b = find_zss(_bis(), config=ChanlunConfig(zs_zd_lines=3))[0]
        assert b.zg <= a.zg + 1e-9, "3 笔 ZG 不应高于 2 笔 ZG"
        assert b.zd >= a.zd - 1e-9, "3 笔 ZD 不应低于 2 笔 ZD"


class TestZsZdLinesTeeth:
    """牙齿验证：证明上面的断言真的在测 zs_zd_lines。"""

    def test_teeth_default_two_breaks_assertion(self) -> None:
        """把默认改成 2，原文口径断言必须失败 —— 否则测试没牙齿。"""
        zss = find_zss(_bis(), config=ChanlunConfig(zs_zd_lines=2))
        zs = zss[0]
        broken = (zs.zg != pytest.approx(18.0)) or (zs.zd != pytest.approx(14.0))
        assert broken, (
            "把冻结笔数改为 2 后 ZG/ZD 仍是三笔口径的结果 —— "
            "test_three_lines_determine_zd 没有牙齿，未真正覆盖 zs_zd_lines"
        )
