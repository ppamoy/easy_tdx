"""线段划分「笔破坏 / 假破坏」金标测试（V689，R2 假破坏恢复）。

缠论原文（第71-78课）：线段除由特征序列分型界定外，还可由反向走势笔越过线段
起点极值（笔破坏）提前结束。但笔破坏只是「预警 / 暂定」——若破坏后同向笔创出
超过线段终点的新高 / 新低，即为「假破坏」，原线段延续（延伸），不劈出新线段。
只有破坏成立（后续未创新极值）时，笔破坏暂定才转为正式结束。

本测试锁定：
- 假破坏恢复：破坏笔之后同向创新高/新低 → 线段延伸（笔破坏开关 ON/OFF 结果一致）。
- 真破坏：破坏笔之后未创新极值 → 线段在破坏笔之前结束（ON 早于 OFF 的收尾）。
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


def test_xd_false_breakthrough_up_recovers() -> None:
    """向上线段：向下笔跌破起点后，同向笔随即创新高 → 假破坏恢复，线段延伸。

    bi#5（向下 118→98）跌破起点 100（笔破坏预警），但 bi#6（向上 98→125）创出
    超过线段终点 118 的新高 → 假破坏，线段延伸到 125。笔破坏开关 ON/OFF 结果一致。
    """
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

    # 假破坏恢复：两者都延伸到新高 125（ON 不再提前结束在 118）
    assert len(default) == 1
    assert default[0].end.val == 125.0
    assert len(off) == 1
    assert off[0].end.val == 125.0


def test_xd_false_breakthrough_down_recovers() -> None:
    """向下线段：向上笔升破起点后，同向笔随即创新低 → 假破坏恢复，线段延伸。

    bi#5（向上 80→105）升破起点 100（笔破坏预警），但 bi#6（向下 105→70）创出
    超过线段终点 80 的新低 → 假破坏，线段延伸到 70。ON/OFF 一致。
    """
    bis = [
        _bi(0, "down", 100.0, 90.0, 100.0, 89.0),
        _bi(1, "up", 90.0, 94.0, 95.0, 89.0),
        _bi(2, "down", 94.0, 84.0, 95.0, 83.0),
        _bi(3, "up", 84.0, 88.0, 89.0, 83.0),
        _bi(4, "down", 88.0, 80.0, 89.0, 79.0),
        _bi(5, "up", 80.0, 105.0, 106.0, 79.0),
        _bi(6, "down", 105.0, 70.0, 106.0, 69.0),
    ]
    default = find_xds(bis, ChanlunConfig())
    off = find_xds(bis, ChanlunConfig(xd_bi_pohuai=False))

    # 假破坏恢复：两者都延伸到新低 70
    assert len(default) == 1
    assert default[0].end.val == 70.0
    assert len(off) == 1
    assert off[0].end.val == 70.0


def test_xd_genuine_pohuai_up_ends_early() -> None:
    """向上线段：向下笔跌破起点后，同向笔未创新高 → 真破坏，线段在破坏笔之前结束。

    bi#3（向下 115→95）跌破起点 100（笔破坏），bi#4（向上 95→108）未超过线段
    终点 115 → 破坏成立。笔破坏开启时线段结束在 bi#2（115）；关闭时无笔破坏、
    又无特征分型（仅 2 根向下笔），收尾取最后一根同向笔 bi#4（108）。ON 早于 OFF。
    """
    bis = [
        _bi(0, "up", 100.0, 110.0, 111.0, 100.0),
        _bi(1, "down", 110.0, 105.0, 111.0, 104.0),
        _bi(2, "up", 105.0, 115.0, 116.0, 104.0),
        _bi(3, "down", 115.0, 95.0, 116.0, 95.0),  # 跌破起点 100，笔破坏
        _bi(4, "up", 95.0, 108.0, 109.0, 94.0),  # 未超 115，破坏成立
    ]
    default = find_xds(bis, ChanlunConfig())
    off = find_xds(bis, ChanlunConfig(xd_bi_pohuai=False))

    # 真破坏：ON 在笔破坏处（115）结束；OFF 收尾到最后一根同向笔（108）
    assert len(default) == 1
    assert default[0].end.val == 115.0
    assert len(off) == 1
    assert off[0].end.val == 108.0


def test_xd_genuine_pohuai_down_ends_early() -> None:
    """向下线段：向上笔升破起点后，同向笔未创新低 → 真破坏，线段在破坏笔之前结束。

    bi#3（向上 80→105）升破起点 100（笔破坏），bi#4（向下 105→85）未低于线段
    终点 80 → 破坏成立。ON 结束在 bi#2（80）；OFF 收尾到 bi#4（85）。ON 早于 OFF。
    """
    bis = [
        _bi(0, "down", 100.0, 90.0, 100.0, 89.0),
        _bi(1, "up", 90.0, 94.0, 95.0, 89.0),
        _bi(2, "down", 94.0, 80.0, 95.0, 79.0),
        _bi(3, "up", 80.0, 105.0, 106.0, 79.0),  # 升破起点 100，笔破坏
        _bi(4, "down", 105.0, 85.0, 106.0, 84.0),  # 未破 80，破坏成立
    ]
    default = find_xds(bis, ChanlunConfig())
    off = find_xds(bis, ChanlunConfig(xd_bi_pohuai=False))

    # 真破坏：ON 在笔破坏处（80）结束；OFF 收尾到最后一根同向笔（85）
    assert len(default) == 1
    assert default[0].end.val == 80.0
    assert len(off) == 1
    assert off[0].end.val == 85.0
