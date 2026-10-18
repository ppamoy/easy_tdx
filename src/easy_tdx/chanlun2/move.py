"""笔 / 走势段（第62/77课）。

第62课笔的严格定义：
1. 两个**相邻**的顶和底之间构成一笔（隔了几个就不算）。
2. 顶和底之间必须至少有 1 根 K 线（不能共用、不能空）——遵守结合律。
3. 上升一笔 = 底分型 + 上升K线 + 顶分型；下降一笔 = 顶分型 + 下降K线 + 底分型。
4. 线段 = 至少三笔（第62课）。

chanlun2 的 ``Move`` 统一表示最小级别「笔」与递归高级别的「次级别走势类型」，
级别由所在分析层决定（递归合成时高级别中枢的 Z 走势段 = 次级别 Move）。
"""

from __future__ import annotations

from .types import Direction, Fractal, FractalType, MergedK, Move


def find_moves(fractals: list[Fractal], merged: list[MergedK]) -> list[Move]:
    """从分型序列中识别笔（第62课）。

    规则：
    - 相邻顶底分型方向交替（顶后必底、底后必顶）。
    - 顶底之间至少有 1 根 K 线（k_index 差 ≥ 2，即中间至少一根独立 K 线）。
    - 上升笔：底→顶；下降笔：顶→底。
    """
    if len(fractals) < 2:
        return []

    moves: list[Move] = []
    idx = 0
    i = 0
    while i < len(fractals) - 1:
        f1 = fractals[i]
        f2 = fractals[i + 1]

        # 第62课：必须方向相反（顶-底 或 底-顶）
        if f1.kind == f2.kind:
            # 同向分型：取更极端的保留，跳过较弱的（第62课结合律）
            if f1.kind == FractalType.TOP:
                if f2.value >= f1.value:
                    # f2 更高，跳过 f1
                    i += 1
                    continue
                # f1 更高，跳过 f2
                i += 1
                continue
            else:  # BOTTOM
                if f2.value <= f1.value:
                    i += 1
                    continue
                i += 1
                continue

        # 第62课：顶底之间至少有 1 根 K 线（k_index 差 ≥ 2）
        # f1.k_index 与 f2.k_index 之间应至少有1根独立K线
        if abs(f2.k_index - f1.k_index) < 2:
            # 中间无独立K线，违反结合律，跳过 f2 寻找下一个
            i += 1
            continue

        # 构造笔
        if f1.kind == FractalType.BOTTOM and f2.kind == FractalType.TOP:
            direction = Direction.UP
            start, end = f1, f2
        elif f1.kind == FractalType.TOP and f2.kind == FractalType.BOTTOM:
            direction = Direction.DOWN
            start, end = f1, f2
        else:
            i += 1
            continue

        # 段内高低点（在 [start_k, end_k] 区间内取 merged 的极值）
        sk = min(start.k_index, end.k_index)
        ek = max(start.k_index, end.k_index)
        seg_ks = [merged[j] for j in range(sk, ek + 1) if j < len(merged)]
        high = max((k.high for k in seg_ks), default=max(start.value, end.value))
        low = min((k.low for k in seg_ks), default=min(start.value, end.value))

        moves.append(
            Move(
                index=idx,
                direction=direction,
                start=start,
                end=end,
                start_k=start.k_index,
                end_k=end.k_index,
                high=high,
                low=low,
            )
        )
        idx += 1
        i += 1  # 移动到下一个分型对

    return moves
