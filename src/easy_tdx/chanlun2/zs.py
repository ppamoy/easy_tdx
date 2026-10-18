"""缠中说禅走势中枢（第17/20课严格递归实现）。

第17课原文：「某级别走势类型中，被至少三个连续次级别走势类型所重叠的部分，
称为缠中说禅走势中枢。」递归终点：「对最后不能分解的级别，其中枢定义为
至少三个该级别单位 K 线重叠部分」。

第20课：
- 中枢区间 [ZD, ZG] = 前两 Z 走势段重叠：ZG=min(g1,g2), ZD=max(d1,d2)。
- 四指标：GG=max(gn), G=min(gn), D=max(dn), DD=min(dn)，n 遍历所有 Z 走势段。
- Z 走势段 = 与中枢方向一致的次级别走势类型。
- 中枢延伸 = 任意 [dn,gn] 与 [ZD,ZG] 有重叠（中心定理一）；
  若 dn>ZG 或 gn<ZD 则产生高级别中枢或趋势。
- 中枢形成两种：回升（A段向上，a1=b1,b2=c2）/ 回调（A段向下，a2=b2,b1=c1）。

关键修正（vs 现有 chanlun 偏差12）：
- 现有模型用「笔」构中枢，违背第91课「笔不能构中枢」。
- chanlun2 严格递归：高级别中枢 = 次级别走势类型(Move)重叠；
  最低级别中枢 = K 线(MergedK)重叠，不用笔。
"""

from __future__ import annotations

from typing import Union

from .types import Direction, MergedK, Move, ZS


def _move_high_low(m: Move) -> tuple[float, float]:
    """走势段的 (low, high) = (dn, gn)。"""
    return (m.low, m.high)


def _overlap_interval(a_lo: float, a_hi: float, b_lo: float, b_hi: float) -> tuple[float, float] | None:
    """两区间重叠部分，无重叠返回 None。"""
    lo = max(a_lo, b_lo)
    hi = min(a_hi, b_hi)
    if hi > lo:
        return (lo, hi)
    return None


def find_zs_lowest_level(merged: list[MergedK]) -> list[ZS]:
    """最低级别中枢（第17课递归终点）：至少三个该级别 K 线重叠部分。

    在合并后的 K 线序列中，找连续 3 根 K 线的价格重叠区间。
    Z 走势段用单根 K 线的 [low, high] 代替（最低级别无次级别走势类型）。
    """
    zss: list[ZS] = []
    if len(merged) < 3:
        return zss

    idx = 0
    i = 0
    while i < len(merged) - 2:
        k1 = merged[i]
        k2 = merged[i + 1]
        k3 = merged[i + 2]

        # 第20课：前两段重叠确定 [ZD, ZG]
        ov = _overlap_interval(k1.low, k1.high, k2.low, k2.high)
        if ov is None:
            i += 1
            continue
        zg = ov[1]  # min(g1, g2)
        zd = ov[0]  # max(d1, d2)

        # 第三根 K 线需与 [ZD, ZG] 有重叠才构成中枢（第17课：3个连续重叠）
        ov3 = _overlap_interval(zd, zg, k3.low, k3.high)
        if ov3 is None:
            # 第20课中心定理一：k3 离开中枢 ⇒ 不延伸，可能产生新中枢
            i += 1
            continue

        # 中枢形成，收集延伸段（后续 K 线与 [ZD,ZG] 有重叠则延伸）
        z_moves_ks: list[MergedK] = [k1, k2, k3]
        direction = Direction.UP if k3.high >= k1.high else Direction.DOWN
        j = i + 3
        while j < len(merged):
            kj = merged[j]
            # 第20课中心定理一：[dn,gn] 与 [ZD,ZG] 有重叠 ⇒ 延伸
            if _overlap_interval(zd, zg, kj.low, kj.high) is not None:
                z_moves_ks.append(kj)
                j += 1
            else:
                break

        # 计算四指标（第20课）：gn/dn 取每根 K 线的 high/low
        gn = [k.high for k in z_moves_ks]
        dn = [k.low for k in z_moves_ks]
        gg = max(gn)
        g = min(gn)
        d = max(dn)
        dd = min(dn)

        zss.append(
            ZS(
                index=idx,
                direction=direction,
                zg=zg,
                zd=zd,
                gg=gg,
                dd=dd,
                g=g,
                d=d,
                # 最低级别用 MergedK 列表表征 Z 段（类型上 Move 暂留空，递归层标识）
                z_moves=[],  # 最低级别无 Move，用 raw ks
                start_k=z_moves_ks[0].index,
                end_k=z_moves_ks[-1].index,
            )
        )
        # 修正：最低级别中枢记录 K 线区间（z_moves 留空，由调用方按级别处理）
        idx += 1
        i = j  # 跳到延伸结束处继续找下一个中枢

    return zss


def find_zs_from_moves(moves: list[Move]) -> list[ZS]:
    """高级别中枢（第17课递归）：至少三个连续次级别走势类型(Move)重叠。

    第20课：前两 Z 走势段重叠确定 [ZD,ZG]，第三段需与区间重叠才成中枢。
    Z 走势段 = 与中枢方向一致的次级别走势类型。
    """
    zss: list[ZS] = []
    if len(moves) < 3:
        return zss

    idx = 0
    i = 0
    while i < len(moves) - 2:
        m1 = moves[i]
        m2 = moves[i + 1]
        m3 = moves[i + 2]

        # 第20课：前两段重叠确定 [ZD, ZG]
        # 第17课：次级别走势类型重叠
        lo1, hi1 = _move_high_low(m1)
        lo2, hi2 = _move_high_low(m2)
        ov = _overlap_interval(lo1, hi1, lo2, hi2)
        if ov is None:
            i += 1
            continue
        zg = ov[1]  # min(g1, g2)
        zd = ov[0]  # max(d1, d2)

        # 第三段需与 [ZD,ZG] 有重叠（第17课：3个连续重叠）
        lo3, hi3 = _move_high_low(m3)
        if _overlap_interval(zd, zg, lo3, hi3) is None:
            i += 1
            continue

        # 中枢形成方向（第20课：回升=向上，回调=向下）
        # Z 走势段 = 与中枢方向一致的段（m1/m3 同向）
        direction = m1.direction  # Z 段方向 = 中枢方向

        # 收集 Z 走势段（与方向一致）与延伸
        z_moves: list[Move] = [m1, m3]  # m1,m3 是 Z 段（同向）；m2 是反向连接
        # 中枢延伸：后续与 [ZD,ZG] 有重叠的段
        j = i + 3
        while j < len(moves):
            mj = moves[j]
            loj, hij = _move_high_low(mj)
            # 第20课中心定理一：[dn,gn] 与 [ZD,ZG] 有重叠 ⇒ 延伸
            if _overlap_interval(zd, zg, loj, hij) is not None:
                if mj.direction == direction:
                    z_moves.append(mj)
                j += 1
            else:
                break

        # 四指标（第20课）
        gn = [m.high for m in z_moves]
        dn = [m.low for m in z_moves]
        gg = max(gn)
        g = min(gn)
        d = max(dn)
        dd = min(dn)

        zs = ZS(
            index=idx,
            direction=direction,
            zg=zg,
            zd=zd,
            gg=gg,
            dd=dd,
            g=g,
            d=d,
            z_moves=z_moves,
            enter_move=m2,  # 进入段（反向连接）
            start_k=z_moves[0].start_k,
            end_k=z_moves[-1].end_k,
        )
        # 离开段：中枢延伸结束后第一段不与区间重叠的段（若存在）
        if j < len(moves):
            zs.exit_move = moves[j]

        zss.append(zs)
        idx += 1
        i = j

    return zss
