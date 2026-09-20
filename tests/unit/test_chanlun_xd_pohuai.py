"""线段划分「笔破坏」金标测试（V689）。

缠论原文：线段除由特征序列分型界定外，还可由反向走势笔越过线段起点极值
（笔破坏）提前结束。本测试锁定 config.xd_bi_pohuai 开启/关闭的确定性差异，
默认关闭以兼容历史结果。
"""

from __future__ import annotations

from datetime import datetime

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import BI, FX, CLKline, Direction, FXType
from easy_tdx.chanlun.xd import find_xds


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


def test_xd_pohuai_up_break_below_start() -> None:
    """向上线段：向下笔跌破起点低点触发笔破坏，结束点早于默认收尾。"""
    bis = [
        _bi(0, "up", 100.0, 110.0, 112.0, 100.0),
        _bi(1, "down", 110.0, 105.0, 111.0, 104.0),
        _bi(2, "up", 105.0, 115.0, 116.0, 104.0),
        _bi(3, "down", 115.0, 109.0, 116.0, 108.0),
        _bi(4, "up", 109.0, 118.0, 119.0, 108.0),
        _bi(5, "down", 118.0, 98.0, 119.0, 98.0),
        _bi(6, "up", 98.0, 125.0, 126.0, 97.0),
    ]
    default = find_xds(bis, ChanlunConfig())  # 默认开启笔破坏
    off = find_xds(bis, ChanlunConfig(xd_bi_pohuai=False))

    # 默认（笔破坏开启）：跌破 100 起点后即结束，停在破坏笔之前的笔
    assert len(default) == 1
    assert default[0].end.val == 118.0
    # 显式关闭笔破坏：按特征序列/收尾继续延长
    assert len(off) == 1
    assert off[0].end.val == 125.0


def test_xd_pohuai_down_break_above_start() -> None:
    """向下线段：向上笔升破起点高点触发笔破坏，结束点早于默认收尾。"""
    bis = [
        _bi(0, "down", 100.0, 90.0, 100.0, 89.0),
        _bi(1, "up", 90.0, 94.0, 95.0, 89.0),
        _bi(2, "down", 94.0, 84.0, 95.0, 83.0),
        _bi(3, "up", 84.0, 88.0, 89.0, 83.0),
        _bi(4, "down", 88.0, 80.0, 89.0, 79.0),
        _bi(5, "up", 80.0, 105.0, 106.0, 79.0),
        _bi(6, "down", 105.0, 70.0, 106.0, 69.0),
    ]
    default = find_xds(bis, ChanlunConfig())  # 默认开启笔破坏
    off = find_xds(bis, ChanlunConfig(xd_bi_pohuai=False))

    assert len(default) == 1
    assert default[0].end.val == 80.0
    assert len(off) == 1
    assert off[0].end.val == 70.0
