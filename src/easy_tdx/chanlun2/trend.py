"""走势类型分解（第17/38课）。

第17课：所有走势=趋势+盘整；趋势=≥2依次同向中枢（上涨/下跌），盘整=1中枢。
第38课：同级别分解——把任何图形分解成一段段走势类型的连接；
  「对30分钟来说，只要5分钟级别的三段上下上或下上下类型有价格区间的重合就构成中枢」
  「如果这5分钟次级别延伸出6段，那么就当成两个30分钟盘整类型的连接」
  「操作中只选择其中的上涨和盘整类型，而避开所有下跌类型」

第38课关键修正（vs 现有 same_level 偏差）：
- 中枢段数固定「三段」（不是 config.zs_min_lines 可变 3~5）。
- 走势类型含趋势（≥2中枢）与盘整（1中枢），不存在 ``kind="none"`` 自创类别；
  不足3段的是「未完成走势类型片段」(TrendKind.INCOMPLETE)。
- 「延伸出6段才拆成两个盘整」——条件是延伸（第4-6段与中枢区间重合），
  不是机械按3切块。
"""

from __future__ import annotations

from .types import Direction, Move, TrendKind, TrendSegment, ZS
from .zs import find_zs_from_moves


def decompose_same_level(moves: list[Move]) -> list[TrendSegment]:
    """同级别分解（第38课）：把走势序列分解成走势类型段的连接。

    算法（第38课）：
    1. 从左到右扫描，取连续 3 段构成中枢（第38课「三段」固定）。
    2. 中枢形成后，检查后续段是否与 [ZD,ZG] 重合（延伸条件，第20课中心定理一）：
       - 延伸出6段（中枢3段+延伸3段重合）⇒ 第38课「当成两个盘整类型的连接」拆分。
       - 第4段不与中枢重合（离开）⇒ 当前段收尾，开始新走势类型。
    3. 走势类型含中枢数判定：≥2=趋势，1=盘整。
    """
    segments: list[TrendSegment] = []
    if len(moves) < 3:
        # 不足3段，作为未完成片段（第38课无none类别）
        if moves:
            seg = TrendSegment(
                index=0,
                kind=TrendKind.INCOMPLETE,
                direction=None,
                moves=list(moves),
                start_k=moves[0].start_k,
                end_k=moves[-1].end_k,
                high=max(m.high for m in moves),
                low=min(m.low for m in moves),
            )
            segments.append(seg)
        return segments

    idx = 0
    i = 0
    n = len(moves)
    while i < n:
        # 取连续3段尝试构中枢（第38课「三段」）
        if i + 3 > n:
            # 剩余不足3段，作为未完成片段挂入
            rem = moves[i:]
            if rem:
                seg = TrendSegment(
                    index=idx,
                    kind=TrendKind.INCOMPLETE,
                    direction=None,
                    moves=list(rem),
                    start_k=rem[0].start_k,
                    end_k=rem[-1].end_k,
                    high=max(m.high for m in rem),
                    low=min(m.low for m in rem),
                )
                segments.append(seg)
                idx += 1
            break

        seg_moves = moves[i : i + 3]
        # 构中枢
        zss_in_seg = find_zs_from_moves(seg_moves)
        if not zss_in_seg:
            # 3段构不成中枢，整段作为未完成片段
            seg = TrendSegment(
                index=idx,
                kind=TrendKind.INCOMPLETE,
                direction=None,
                moves=list(seg_moves),
                start_k=seg_moves[0].start_k,
                end_k=seg_moves[-1].end_k,
                high=max(m.high for m in seg_moves),
                low=min(m.low for m in seg_moves),
            )
            segments.append(seg)
            idx += 1
            i += 3
            continue

        zs0 = zss_in_seg[0]
        # 中枢方向 = Z段方向
        seg_dir = zs0.direction

        # 第38课延伸判定：后续段与 [ZD,ZG] 重合则延伸
        j = i + 3
        while j < n:
            mj = moves[j]
            # 第20课中心定理一：[dn,gn] 与 [ZD,ZG] 有重叠 ⇒ 延伸
            if zs0.overlaps_interval(mj.low, mj.high):
                j += 1
            else:
                break

        # 第38课「延伸出6段才拆成两个盘整」：若延伸段数≥3（中枢3+延伸3=6段）则拆
        extend_count = j - (i + 3)
        if extend_count >= 3:
            # 拆成两个盘整：当前3段为一个盘整，延伸段从下一段起新走势类型
            seg_moves_a = moves[i : i + 3]
            seg = TrendSegment(
                index=idx,
                kind=TrendKind.PANZHENG,  # 1中枢=盘整（第17课）
                direction=seg_dir,
                moves=list(seg_moves_a),
                zss=[zs0],
                start_k=seg_moves_a[0].start_k,
                end_k=seg_moves_a[-1].end_k,
                high=max(m.high for m in seg_moves_a),
                low=min(m.low for m in seg_moves_a),
            )
            segments.append(seg)
            idx += 1
            i = i + 3  # 从延伸段开始新走势类型
            continue

        # 正常收尾：当前走势类型含中枢，可能含多个同向中枢（趋势）
        # 继续扫描后续段是否构成新的同向不重叠中枢（趋势=≥2中枢）
        all_seg_moves = list(moves[i:j])
        all_zss = find_zs_from_moves(all_seg_moves)

        # 判定走势类型（第17课）
        zs_cnt = len(all_zss)
        if zs_cnt >= 2:
            # ≥2同向中枢=趋势（第17课）
            kind = (
                TrendKind.TREND_UP
                if seg_dir == Direction.UP
                else TrendKind.TREND_DOWN
            )
        elif zs_cnt == 1:
            kind = TrendKind.PANZHENG  # 1中枢=盘整
        else:
            kind = TrendKind.INCOMPLETE

        seg = TrendSegment(
            index=idx,
            kind=kind,
            direction=seg_dir,
            moves=all_seg_moves,
            zss=all_zss,
            start_k=all_seg_moves[0].start_k,
            end_k=all_seg_moves[-1].end_k,
            high=max(m.high for m in all_seg_moves),
            low=min(m.low for m in all_seg_moves),
        )
        segments.append(seg)
        idx += 1
        i = j

    return segments
