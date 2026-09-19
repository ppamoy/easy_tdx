"""中枢最少段数金标测试（V699）。

缠论原文：走势中枢至少由连续三个次级别走势类型的重叠构成。
重叠但不足三段的区间不应被识别为中枢。
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


def test_zs_requires_at_least_three_segments() -> None:
    """三段重叠构成中枢；两段重叠不足以构成中枢。"""
    config = ChanlunConfig(zs_min_lines=3)
    bis3 = [
        _bi(0, "up", 10.0, 14.0, 14.0, 10.0),
        _bi(1, "down", 14.0, 13.0, 13.0, 11.0),
        _bi(2, "up", 13.0, 13.5, 13.5, 12.0),
    ]
    assert len(find_zss(bis3, config)) == 1

    bis2 = bis3[:2]
    assert find_zss(bis2, config) == []
