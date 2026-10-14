"""中枢 ZG/ZD 缠论原文（第20课）口径回归测试。

原文判据（第20课，正文与评论区两处一致）
----------------------------------------
> 特别地，再定义 `ZG=min(g1、g2)`，`ZD=max(d1、d2)`，显然，`[ZD，ZG]`
> 就是缠中说禅走势中枢的区间

原文紧接着说明："`A`、`C`段，其方向与中枢形成的方向是一致的……
以后都把这些与中枢方向一致的次级别走势类型称为`Z走势段`"。

⇒ **ZG/ZD 只取与中枢方向一致的 A、C 两段（第 1 笔和第 3 笔）**，
   中间的反向笔（B 段）**不参与**。原文里**没有 g3**。

本测试锁死
----------
1. ZG/ZD 等于第 1、3 笔的重叠（中间笔不参与）；
2. 中间反向笔的高/低不影响 ZG/ZD；
3. 牙齿验证：把 AC 分支改成用第 1、2 笔后，断言**必须失败**。
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
            k_index=index * 10,
            date=None,
            open=low,
            close=high,  # type: ignore[arg-type]
            high=high,
            low=low,
            amount=0.0,
            index=index,
        ),
        klines=[],
        val=low if direction == "up" else high,
        index=index,
        done=True,
    )
    end_fx = FX(
        fx_type=FXType.DING if direction == "up" else FXType.DI,
        k=CLKline(
            k_index=index * 10 + 5,
            date=None,
            open=low,
            close=high,  # type: ignore[arg-type]
            high=high,
            low=low,
            amount=0.0,
            index=index,
        ),
        klines=[],
        val=high if direction == "up" else low,
        index=index,
        done=True,
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
    """构造一个「中间笔会收窄重叠」的中枢。

    笔0 (up): [10, 30]
    笔1 (down): [12, 22]   ← 中间反向笔，其 low=12 > 笔0.low=10
    笔2 (up): [14, 26]

    原文 AC（只第 1、3 笔）：
        zg = min(30, 26)    = 26
        zd = max(10, 14)    = 14      ⇒ [14, 26]，宽 12

    中间笔参与时（非原文）：
        zg = min(30, 22, 26) = 22
        zd = max(10, 12, 14) = 14      ⇒ [14, 22]，宽 8

    ⇒ 原文更宽（中间反向笔不参与，不再收窄）。
    """
    return [
        _bi(0, "up", 30.0, 10.0),
        _bi(1, "down", 22.0, 12.0),
        _bi(2, "up", 26.0, 14.0),
    ]


def test_zg_zd_uses_first_and_third_bi_only() -> None:
    """第20课原文：ZG=min(g1,g2)、ZD=max(d1,d2)，只用第 1、3 笔。"""
    zss = find_zss(_bis(), ChanlunConfig())
    assert len(zss) == 1
    # 原文：zg=min(30,26)=26，zd=max(10,14)=14
    assert zss[0].zg == pytest.approx(26.0)
    assert zss[0].zd == pytest.approx(14.0)


def test_middle_bi_does_not_affect_zg_zd() -> None:
    """中间反向笔（B段）的高/低不影响 ZG/ZD。

    构造：中间笔 high=22（低于第1、3笔的high），但不参与计算。
    """
    zss = find_zss(_bis(), ChanlunConfig())
    assert len(zss) == 1
    # 如果中间笔参与，zg 会是 22；原文口径下 zg=26
    assert zss[0].zg == pytest.approx(26.0)
    # 如果中间笔参与，zd 会是 14（碰巧相同，但验证 zg 受影响即可）


def test_middle_bi_completely_wrapped_no_difference() -> None:
    """中间笔完全包住（不收窄）时，原文口径与任意口径相同。"""
    bis = [
        _bi(0, "up", 30.0, 10.0),
        _bi(1, "down", 28.0, 8.0),  # 中间笔完全包住，不收窄
        _bi(2, "up", 26.0, 12.0),
    ]
    zss = find_zss(bis, ChanlunConfig())
    assert len(zss) == 1
    # 原文：zg=min(30,26)=26, zd=max(10,12)=12
    assert zss[0].zg == pytest.approx(26.0)
    assert zss[0].zd == pytest.approx(12.0)


def test_zg_zd_frozen_after_third_bi() -> None:
    """ZG/ZD 在第3笔确定后冻结，后续延伸笔只更新 GG/DD。"""
    # 第4笔扩展但不改变 ZG/ZD
    bis = [
        _bi(0, "up", 30.0, 10.0),
        _bi(1, "down", 22.0, 12.0),
        _bi(2, "up", 26.0, 14.0),
        _bi(3, "down", 25.0, 15.0),  # 延伸笔，与 [14,26] 有重叠
    ]
    zss = find_zss(bis, ChanlunConfig())
    # ZG/ZD 仍由第1、3笔决定
    assert len(zss) >= 1
    zs0 = zss[0]
    assert zs0.zg == pytest.approx(26.0)  # min(30, 26)
    assert zs0.zd == pytest.approx(14.0)  # max(10, 14)
    # GG/DD 应被第4笔更新（GG≥所有笔最高、DD≤所有笔最低）
    assert zs0.gg >= 30.0
    assert zs0.dd <= 10.0
