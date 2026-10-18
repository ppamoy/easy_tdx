"""chanlun2 主分析入口（编排 K线→分型→笔→中枢→走势→背驰→买卖点）。

严格按108课原文递归流程，不混合笔构中枢（修复偏差12）。

分析流程（自底向上递归）：
1. K线合并（第65课包含关系）→ MergedK
2. 分型识别（第67课）→ Fractal
3. 笔（第62课相邻顶底）→ Move（最小级别）
4. MACD 填充（第24课：面积/dif/dea）→ Move.macd_area 等
5. 中枢（第17课递归）：
   - 最低级别：K线重叠构中枢（非笔构，修复偏差12）
   - 高级别：次级别走势类型(Move)重叠构中枢
6. 同级别分解（第38课）→ TrendSegment
7. 买卖点（第20/27/101课）→ MMD
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .kline_merge import merge_klines
from .fractal import find_fractals
from .move import find_moves
from .zs import find_zs_from_moves, find_zs_lowest_level
from .trend import decompose_same_level
from .mmd import find_all_mmd
from .types import KLine, MergedK, Move, MMD, TrendSegment, ZS, Direction


def _ema(values: list[float], period: int) -> list[float]:
    """EMA 计算（MACD 辅助）。"""
    if not values:
        return []
    k = 2 / (period + 1)
    result = [values[0]]
    for i in range(1, len(values)):
        result.append(values[i] * k + result[-1] * (1 - k))
    return result


def _compute_macd(closes: list[float]) -> list[tuple[float, float, float]]:
    """MACD：DIF=EMA12-EMA26, DEA=EMA9(DIF), HIST=DIF-DEA。返回每根K线的(dif,dea,hist)。"""
    if len(closes) < 26:
        return [(0.0, 0.0, 0.0)] * len(closes)
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    dif = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
    dea = _ema(dif, 9)
    hist = [d - e for d, e in zip(dif, dea)]
    return list(zip(dif, dea, hist))


def _fill_move_macd(
    moves: list[Move],
    merged: list[MergedK],
    closes: list[float],
) -> None:
    """为每个 Move 填充 MACD 面积/dif/dea（第24课）。

    面积 = 段内 hist 绝对值之和（红柱=正、绿柱=负）。
    dif_peak = 段内 dif 绝对值峰值。
    """
    macd_series = _compute_macd(closes)
    for m in moves:
        # 段内K线索引范围（merged.index 映射到 closes 的 raw_indices）
        raw_ks: list[int] = []
        for j in range(m.start_k, m.end_k + 1):
            if j < len(merged):
                raw_ks.extend(merged[j].raw_indices)
        if not raw_ks:
            continue
        seg_hist = [macd_series[k][2] for k in raw_ks if k < len(macd_series)]
        seg_dif = [macd_series[k][0] for k in raw_ks if k < len(macd_series)]
        seg_dea = [macd_series[k][1] for k in raw_ks if k < len(macd_series)]
        # 面积：红柱正面积 / 绿柱负面积（保留符号，调用方按方向取）
        m.macd_area = sum(seg_hist)
        m.dif_peak = max(seg_dif, key=abs) if seg_dif else 0.0
        m.dea_peak = max(seg_dea, key=abs) if seg_dea else 0.0


@dataclass
class Chanlun2Result:
    """完整分析结果。"""

    merged: list[MergedK]
    fractals: list
    moves: list[Move]
    zs_lowest: list[ZS]  # 最低级别中枢（K线重叠）
    zs_from_moves: list[ZS]  # 走势类型中枢（次级别走势重叠）
    segments: list[TrendSegment]  # 同级别分解走势类型段
    mmds: list[MMD]  # 三类买卖点


def analyze(
    klines: list[KLine],
    closes: Optional[list[float]] = None,
) -> Chanlun2Result:
    """chanlun2 主分析入口。

    参数：
        klines: 原始K线
        closes: 可选收盘价序列（用于MACD，缺省用 kline.close）
    """
    # 1. K线合并（第65课）
    merged = merge_klines(klines)

    # 2. 分型（第67课）
    fractals = find_fractals(merged)

    # 3. 笔（第62课）
    moves = find_moves(fractals, merged)

    # 4. MACD 填充（第24课）
    if closes is None:
        closes = [k.close for k in klines]
    _fill_move_macd(moves, merged, closes)

    # 5. 中枢（第17课递归）
    zs_lowest = find_zs_lowest_level(merged)  # 最低级别=K线重叠（非笔构）
    zs_from_moves = find_zs_from_moves(moves)  # 走势类型中枢

    # 6. 同级别分解（第38课）
    segments = decompose_same_level(moves)

    # 7. 买卖点（第20/27/101课）
    mmds = find_all_mmd(segments, moves)

    return Chanlun2Result(
        merged=merged,
        fractals=fractals,
        moves=moves,
        zs_lowest=zs_lowest,
        zs_from_moves=zs_from_moves,
        segments=segments,
        mmds=mmds,
    )
