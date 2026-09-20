"""线段收尾端点金标测试（line-segment-original-fidelity 情景）。

锁定 find_xds 在特征序列未完成分型时，收尾线段端点：
- 必落在与线段同向的笔端点上；
- 端点分型与线段方向一致（向上段终点为顶分型/高点）；
- 不使用反向笔端点作为收尾候选。
"""

from __future__ import annotations

from datetime import datetime

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import BI, FX, CLKline, Direction, FXType
from easy_tdx.chanlun.xd import find_xds


def _mk_bi(
    index: int,
    direction: str,
    high: float,
    low: float,
    start_val: float = 0.0,
    end_val: float = 0.0,
) -> BI:
    k1 = CLKline(
        k_index=index * 10,
        date=datetime(2020, 1, 1),
        open=low,
        close=high,
        high=high,
        low=low,
        amount=0.0,
        index=index,
    )
    k2 = CLKline(
        k_index=index * 10 + 5,
        date=datetime(2020, 1, 1),
        open=low,
        close=high,
        high=high,
        low=low,
        amount=0.0,
        index=index,
    )
    start_fx = FX(
        fx_type=FXType.DI if direction == "up" else FXType.DING,
        k=k1,
        klines=[k1],
        val=start_val,
        index=index,
        done=True,
        bar_index=index * 10,
    )
    end_fx = FX(
        fx_type=FXType.DING if direction == "up" else FXType.DI,
        k=k2,
        klines=[k2],
        val=end_val,
        index=index,
        done=True,
        bar_index=index * 10 + 5,
    )
    return BI(
        start=start_fx,
        end=end_fx,
        direction=Direction.UP if direction == "up" else Direction.DOWN,
        index=index,
        high=high,
        low=low,
    )


def test_tail_endpoint_is_own_direction_pen() -> None:
    """特征序列不足分型时，收尾线段终点取同向笔结尾，保持方向一致。"""
    bis = [
        _mk_bi(0, "up", 112.0, 100.0, 100.0, 110.0),
        _mk_bi(1, "down", 111.0, 104.0, 110.0, 105.0),
        _mk_bi(2, "up", 116.0, 104.0, 105.0, 115.0),
        _mk_bi(3, "down", 116.0, 108.0, 115.0, 109.0),
        _mk_bi(4, "up", 119.0, 108.0, 109.0, 118.0),
        _mk_bi(5, "down", 119.0, 90.0, 118.0, 90.0),
    ]
    xds = find_xds(bis, ChanlunConfig())
    assert len(xds) == 1
    xd = xds[0]
    assert xd.direction == Direction.UP
    # 收尾端点应取同向笔 b4 的终点（118），而不是反向笔 b5 的低点 90。
    assert xd.end.val == 118.0
    assert xd.end.bar_index == 4 * 10 + 5
    assert xd.end.val > xd.start.val


def test_tail_starts_from_shared_pen_endpoint() -> None:
    """收尾生成的线段起点必须是笔端点分型，方便与下一段共享。"""
    bis = [
        _mk_bi(0, "up", 112.0, 100.0, 100.0, 110.0),
        _mk_bi(1, "down", 111.0, 104.0, 110.0, 105.0),
        _mk_bi(2, "up", 116.0, 104.0, 105.0, 115.0),
    ]
    xds = find_xds(bis, ChanlunConfig())
    assert len(xds) == 1
    assert xds[0].direction == Direction.UP
    assert xds[0].start.bar_index == 0 * 10
