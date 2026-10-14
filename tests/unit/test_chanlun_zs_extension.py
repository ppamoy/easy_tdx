"""中枢延伸金标测试（V692，V730 按原文口径修正）。

缠论原文（第17/20课）：中枢 = 至少三个连续次级别走势的重叠区间；
ZG/ZD 由「前三个次级别走势」的明确重叠确定后即冻结（ZG = min(g1,g2,g3)，
ZD = max(d1,d2,d3)）；第四段起为中枢震荡延伸，只更新极值 GG/DD，不改变 ZG/ZD。
本用例锁定 find_zss 的冻结口径（config.zs_zd_lines，默认 3）与延伸行为，
防止后续改动破坏原文语义。
"""

from __future__ import annotations

from datetime import datetime

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import BI, FX, CLKline, Direction, FXType
from easy_tdx.chanlun.zs import find_zss


def _fx(fx_type: FXType, val: float, bar: int) -> FX:
    k = CLKline(
        k_index=bar,
        date=datetime(2020, 1, 1),
        open=0.0,
        close=0.0,
        high=0.0,
        low=0.0,
        amount=0.0,
        index=bar,
    )
    return FX(fx_type=fx_type, k=k, klines=[k], val=val, index=bar, done=True, bar_index=bar)


def _bi(
    index: int,
    direction: str,
    start_val: float,
    end_val: float,
    high: float,
    low: float,
) -> BI:
    d = Direction.UP if direction == "up" else Direction.DOWN
    s = _fx(FXType.DI if direction == "up" else FXType.DING, start_val, index * 10)
    e = _fx(FXType.DING if direction == "up" else FXType.DI, end_val, index * 10 + 5)
    return BI(start=s, end=e, direction=d, index=index, high=high, low=low)


def test_zs_extension_keeps_zg_zd_updates_gg_dd() -> None:
    """A、C 两段确定 ZG/ZD 并冻结；第4笔起延伸只更新 GG/DD。

    V733/V735（原文第20课「A、C 两段」口径）：
    bi0(A) [10,14]、bi1(B) [11,13]、bi2(C) [9,12]
      → ZG=min(A.high=14, C.high=12)=12, ZD=max(A.low=10, C.low=9)=10；
    bi3 为延伸（与 [10,12] 重叠），ZG/ZD 不再变化，只更新 GG/DD。

    ⚠️ 原断言 ZD=11 用的是「前三笔」max(10,11,9)，是**第20课之前**的旧口径。
    第20课明确：ZG=min(g1,g2)、ZD=max(d1,d2) 只取 A、C 两段（B 段不参与）。
    故 ZD 应为 max(10,9)=10。
    """
    bis = [
        _bi(0, "up", 10.0, 14.0, 14.0, 10.0),
        _bi(1, "down", 14.0, 12.0, 13.0, 11.0),
        _bi(2, "up", 12.0, 13.0, 12.0, 9.0),
        _bi(3, "down", 13.0, 10.0, 15.0, 8.0),  # 延伸仍回中枢区间，但极值更远
    ]
    zss = find_zss(bis, ChanlunConfig())
    assert len(zss) == 1
    zs = zss[0]
    assert zs.zg == 12.0
    assert zs.zd == 10.0
    assert zs.gg == 15.0
    assert zs.dd == 8.0
    assert zs.line_count == 4
