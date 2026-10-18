"""三类买卖点（第20/27/101课严格实现）。

- **第一类买卖点**（第27课）：趋势背驰构成；盘整背驰**不是**第一类买卖点（第53课），
  单独标 PANZHENG_BUY/SELL。
- **第二类买卖点**（第101课）：第一类买卖点的次级别回抽结束后再次探底；
  无固定 K 线根数限制（第101课原文）。
- **第三类买卖点**（第20/61课）：次级别走势离开中枢后**第一次**回试不跌破 ZG；
  至少 5 段次级别（前三段中枢，第四段离开，第五段 3 买卖点）。

关键修正（vs 现有 chanlun 偏差）：
- 1 买只认趋势背驰（第27课），盘整背驰单独标 PANZHENG_BUY（不混标 BUY_1）。
- 2 买无 K 线根数限制（第101课），非硬编码 30 根。
- 3 买卖「必须是第一次」回试（第20课），非按中枢数截断扫描。
- 3 买卖至少 5 段结构（第61课），非机械按笔索引推进。
"""

from __future__ import annotations

from .types import (
    Direction,
    Divergence,
    DivergenceKind,
    MMD,
    MMDType,
    Move,
    TrendSegment,
    ZS,
)
from .divergence import detect_divergence, detect_panzheng_divergence


def find_first_class_mmd(
    segments: list[TrendSegment],
) -> list[MMD]:
    """第一类买卖点（第27课：趋势背驰构成；盘整背驰≠1买）。

    在走势类型段序列中找 A/B/C 三段同向趋势，C 段背驰：
    - 趋势背驰（≥2中枢）⇒ BUY_1/SELL_1。
    - 盘整背驰（1中枢）⇒ PANZHENG_BUY/SELL（第53课不标1买）。
    """
    mmds: list[MMD] = []
    if len(segments) < 3:
        return mmds

    idx = 0
    for i in range(len(segments) - 2):
        seg_a = segments[i]
        seg_b = segments[i + 1]
        seg_c = segments[i + 2]
        zs_b = seg_b.zss[-1] if seg_b.zss else None

        div = detect_divergence(seg_a, seg_b, seg_c, zs_b=zs_b)
        if div is None:
            continue

        # 买卖点方向：C 段向上背驰⇒卖点（顶），向下⇒买点（底）
        if seg_c.direction == Direction.UP:
            mtype = MMDType.SELL_1 if div.kind == DivergenceKind.TREND else MMDType.PANZHENG_SELL
        else:
            mtype = MMDType.BUY_1 if div.kind == DivergenceKind.TREND else MMDType.PANZHENG_BUY

        end_move = seg_c.moves[-1] if seg_c.moves else None
        mmds.append(
            MMD(
                index=idx,
                mmd_type=mtype,
                k_index=end_move.end_k if end_move else seg_c.end_k,
                dt=end_move.end.dt if end_move else "",
                price=end_move.high if mtype.is_sell else end_move.low if end_move else 0.0,
                direction=seg_c.direction,
                divergence=div,
                note=f"{'趋势' if div.kind == DivergenceKind.TREND else '盘整'}背驰",
            )
        )
        idx += 1

    return mmds


def find_panzheng_mmd(segments: list[TrendSegment]) -> list[MMD]:
    """盘整背驰买卖点（第27课：盘整背驰≠1买，单独标注）。

    对每个 1 中枢的盘整段，检测 enter/exit 背驰。
    """
    mmds: list[MMD] = []
    idx = 0
    for seg in segments:
        if seg.kind.value != "panzheng":
            continue
        div = detect_panzheng_divergence(seg)
        if div is None:
            continue
        # 方向：盘整形成方向向上⇒回调后背驰=买点；向下⇒回升后背驰=卖点
        if seg.direction == Direction.UP:
            mtype = MMDType.PANZHENG_BUY
            price = div.move_c.low if div.move_c else 0.0
        else:
            mtype = MMDType.PANZHENG_SELL
            price = div.move_c.high if div.move_c else 0.0
        mmds.append(
            MMD(
                index=idx,
                mmd_type=mtype,
                k_index=div.move_c.end_k if div.move_c else seg.end_k,
                dt=div.move_c.end.dt if div.move_c else "",
                price=price,
                direction=seg.direction or Direction.DOWN,
                divergence=div,
                note="盘整背驰(1中枢)",
            )
        )
        idx += 1
    return mmds


def find_second_class_mmd(
    first_mmds: list[MMD],
    segments: list[TrendSegment],
    moves: list[Move],
) -> list[MMD]:
    """第二类买卖点（第101课：1买次级别回抽后再次探底，无根数限制）。

    第101课原文：「第一类买点的次级别回抽结束后再次探底」。
    - 找到第一类买卖点后，其后的次级别回抽（反向走势）结束，
      再次出现同向探底（不破1买低点）⇒ 第二类买卖点。
    - 无 K 线根数限制（第101课原文，vs 现有偏差13硬编码30根）。
    """
    mmds: list[MMD] = []
    idx = 0
    for fm in first_mmds:
        if not fm.mmd_type.is_first_class:
            continue  # 盘整背驰不产生2买（第53课）
        # 1买之后的次级别回抽：反向走势
        is_buy = fm.mmd_type == MMDType.BUY_1
        # 找1买之后的moves
        after_moves = [m for m in moves if m.start_k > fm.k_index]
        if len(after_moves) < 2:
            continue

        # 第101课：次级别回抽结束后再次探底
        # 回抽=反向走势（1买向上回抽、1卖向下回抽）
        # 再次探底=同向走势（不破1买点价位）
        found = False
        for j in range(len(after_moves) - 1):
            pullback = after_moves[j]  # 回抽段（反向）
            probe = after_moves[j + 1]  # 再次探底/探顶段（同向）
            # 回抽方向反向
            if is_buy and pullback.direction != Direction.UP:
                continue
            if not is_buy and pullback.direction != Direction.DOWN:
                continue
            # 再次探底方向同向且不破1买点
            if is_buy:
                if probe.direction != Direction.DOWN:
                    continue
                if probe.low < fm.price:
                    continue  # 破1买低点，不是2买
                mtype = MMDType.BUY_2
                price = probe.low
                dt = probe.end.dt
                k = probe.end_k
            else:
                if probe.direction != Direction.UP:
                    continue
                if probe.high > fm.price:
                    continue
                mtype = MMDType.SELL_2
                price = probe.high
                dt = probe.end.dt
                k = probe.end_k
            mmds.append(
                MMD(
                    index=idx,
                    mmd_type=mtype,
                    k_index=k,
                    dt=dt,
                    price=price,
                    direction=Direction.DOWN if is_buy else Direction.UP,
                    note="2买:1买次级别回抽后再次探底(第101课,无根数限制)",
                )
            )
            idx += 1
            found = True
            break  # 每个1买只产生一个2买（第一次回抽后探底）
        if found:
            continue
    return mmds


def find_third_class_mmd(
    segments: list[TrendSegment],
    moves: list[Move],
) -> list[MMD]:
    """第三类买卖点（第20/61课：第一次回试不破ZG，至少5段）。

    第20课：次级别走势离开中枢后，第一次回试不跌破 ZG ⇒ 3 买卖点。
    第61课：至少 5 段次级别（前三段中枢，第四段离开，第五段3买卖点）。
    - 「必须是第一次」回试（第20课 L36），非按中枢数截断扫描。
    """
    mmds: list[MMD] = []
    idx = 0
    # 遍历每个中枢，找其后的离开段+第一次回试
    for seg in segments:
        for zs in seg.zss:
            if zs.exit_move is None:
                continue
            exit_m = zs.exit_move
            # 离开方向
            is_up_leave = exit_m.direction == Direction.UP
            # 找离开段之后的第一次回试（反向走势）
            after = [m for m in moves if m.start_k >= exit_m.end_k and m.direction != exit_m.direction]
            if not after:
                continue
            first_retrace = after[0]  # 第20课「必须是第一次」

            # 第61课：至少5段结构校验（中枢3段+离开1段+回试1段）
            seg_moves_before = [m for m in moves if m.end_k <= first_retrace.end_k]
            if len(seg_moves_before) < 5:
                continue

            # 第20课：回试不跌破 ZG（向上离开⇒回试低点不破ZG⇒3买；向下离开⇒回试高点不破ZD⇒3卖）
            if is_up_leave:
                if first_retrace.low >= zs.zg:  # 不破ZG
                    mtype = MMDType.BUY_3
                    price = first_retrace.low
                else:
                    continue
            else:
                if first_retrace.high <= zs.zd:  # 不破ZD
                    mtype = MMDType.SELL_3
                    price = first_retrace.high
                else:
                    continue

            mmds.append(
                MMD(
                    index=idx,
                    mmd_type=mtype,
                    k_index=first_retrace.end_k,
                    dt=first_retrace.end.dt,
                    price=price,
                    direction=exit_m.direction,
                    zs=zs,
                    note="3买:第一次回试不破ZG(第20课)+至少5段(第61课)",
                )
            )
            idx += 1
    return mmds


def find_all_mmd(
    segments: list[TrendSegment],
    moves: list[Move],
) -> list[MMD]:
    """全部三类买卖点（整合入口）。"""
    mmds: list[MMD] = []
    # 第一类（趋势背驰1买 + 盘整背驰单独标）
    first = find_first_class_mmd(segments)
    panzheng = find_panzheng_mmd(segments)
    mmds.extend(first)
    mmds.extend(panzheng)
    # 第二类（1买次级别回抽后）
    second = find_second_class_mmd(first, segments, moves)
    mmds.extend(second)
    # 第三类（第一次回试不破ZG+5段）
    third = find_third_class_mmd(segments, moves)
    mmds.extend(third)
    # 按K线位置排序
    mmds.sort(key=lambda m: m.k_index)
    # 重新编号
    for i, m in enumerate(mmds):
        m.index = i
    return mmds
