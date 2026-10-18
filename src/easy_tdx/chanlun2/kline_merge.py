"""K 线合并（第65课：包含关系处理）。

第65课原文规则：
1. 包含关系：相邻两根 K 线 [d1,g1] 与 [d2,g2]，若 g2>=g1 且 d2<=d1（或反之）⇒ 包含。
2. 向上序列（gn>=gn-1）：n 个包含 K 线组等价于 [max(d), max(g)]；
   即合并取「较高 high、较高 low」（高高取高、低低取高）。
3. 向下序列（dn<=dn-1）：n 个包含 K 线组等价于 [min(d), min(g)]；
   即合并取「较低 high、较低 low」（高高低、低低低）。
4. 顺序原则：先用 1,2 根确认新 K 线，再用新 K 线与第 3 根比（结合律）。
5. 方向判断：当第 n 根与 n+1 根包含、但 n 与 n-1 不包含时，
   若 gn>=gn-1 则 n-1,n,n+1 向上；若 dn<=dn-1 则向下。
"""

from __future__ import annotations

from .types import Direction, KLine, MergedK


def _has_inclusion(a: MergedK, b: MergedK) -> bool:
    """第65课：两根 K 线是否有包含关系（g2>=g1 且 d2<=d1，或反之）。"""
    return (b.high >= a.high and b.low <= a.low) or (a.high >= b.high and a.low <= b.low)


def _merge_two(prev: MergedK, curr: MergedK, direction: Direction) -> MergedK:
    """第65课：按方向合并两根包含 K 线。

    向上序列：取 max(high), max(low)（高高取高、低低取高）；
    向下序列：取 min(high), min(low)（高高低、低低低）。
    """
    if direction == Direction.UP:
        new_high = max(prev.high, curr.high)
        new_low = max(prev.low, curr.low)
    else:
        new_high = min(prev.high, curr.high)
        new_low = min(prev.low, curr.low)
    # 合并后的 dt_start/dt_end 取区间；raw_indices 合并
    return MergedK(
        index=prev.index,  # 保留 prev 的序号（合并入前一根）
        dt_start=prev.dt_start,
        dt_end=curr.dt_end,
        high=new_high,
        low=new_low,
        raw_indices=prev.raw_indices + curr.raw_indices,
        direction=direction,
    )


def merge_klines(klines: list[KLine]) -> list[MergedK]:
    """K 线包含关系合并（第65课）。

    顺序原则：从左到右扫描，遇到包含关系则合并入前一根，用新 K 线继续与下一根比。
    方向判断：看前一根（已合并）与更前一根的关系确定向上/向下。
    """
    if len(klines) < 2:
        return [
            MergedK(
                index=i,
                dt_start=k.dt,
                dt_end=k.dt,
                high=k.high,
                low=k.low,
                raw_indices=[k.index],
            )
            for i, k in enumerate(klines)
        ]

    # 初始：每根原始 K 线先变成 MergedK
    merged: list[MergedK] = []
    for i, k in enumerate(klines):
        merged.append(
            MergedK(
                index=i,
                dt_start=k.dt,
                dt_end=k.dt,
                high=k.high,
                low=k.low,
                raw_indices=[k.index],
            )
        )

    # 第65课顺序原则：从左到右，遇到包含就合并入前一根
    result: list[MergedK] = [merged[0]]
    for i in range(1, len(merged)):
        curr = merged[i]
        prev = result[-1]
        if _has_inclusion(prev, curr):
            # 确定方向：看 result 里 prev 之前是否有元素
            if len(result) >= 2:
                # 第65课：gn>=gn-1 向上；dn<=dn-1 向下
                before_prev = result[-2]
                if prev.high >= before_prev.high:
                    direction = Direction.UP
                elif prev.low <= before_prev.low:
                    direction = Direction.DOWN
                else:
                    # 默认向上（边界情形，第65课原文 gn>=gn-1 与 dn<=dn-1 不可能同时不成立）
                    direction = Direction.UP
            else:
                # 只有一根时无法判断方向，默认向上
                direction = Direction.UP
            # 合并入前一根
            new_k = _merge_two(prev, curr, direction)
            result[-1] = new_k
        else:
            # 非包含：curr 独立成一根，方向由与 prev 的关系定
            if curr.high > prev.high:
                curr.direction = Direction.UP
            elif curr.low < prev.low:
                curr.direction = Direction.DOWN
            else:
                curr.direction = prev.direction
            result.append(curr)

    # 重新编号（合并后序号连续）
    for i, m in enumerate(result):
        m.index = i

    return result
