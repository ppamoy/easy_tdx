"""线段计算（缠论特征序列版，含包含处理）。

线段定义：
- 由至少 3 笔构成。
- 特征序列：与当前线段方向相反的那些笔。
- 特征序列需先做「包含处理」（与 K 线包含处理同构），再判断顶/底分型。
- 向上线段：特征序列（向下笔）出现顶分型 → 线段结束。
- 向下线段：特征序列（向上笔）出现底分型 → 线段结束。
- 相邻线段共享转折点，方向自然交替。

说明：这是「特征序列 + 包含处理」的标准简化实现，未覆盖缠论原文中
线段划分的「笔破坏」与「多义性」全部情形；复杂走势仍可能比严格缠论更长/更粗。
"""

from __future__ import annotations

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import BI, XD, Direction


def _feature_included(a: BI, b: BI) -> bool:
    """判断两支特征笔是否存在包含关系（互为包含）。"""
    return (a.high >= b.high and a.low <= b.low) or (
        b.high >= a.high and b.low <= a.low
    )


def _merge_feature_sequence(
    features: list[tuple[int, BI]],
) -> list[tuple[list[int], float, float]]:
    """对特征序列做包含处理。

    返回 [(原始笔索引列表, 合并后 high, 合并后 low)]，与 K 线包含处理同构：
    - 向上合并取「高高」；
    - 向下合并取「低低」。
    """
    if not features:
        return []

    merged: list[tuple[list[int], float, float]] = [
        ([features[0][0]], features[0][1].high, features[0][1].low)
    ]

    for idx, bi in features[1:]:
        prev_idx, prev_high, prev_low = merged[-1]
        included = (bi.high >= prev_high and bi.low <= prev_low) or (
            prev_high >= bi.high and prev_low <= bi.low
        )
        if included:
            # 合并方向：与 K 线包含处理一致，看前一未合并元素的方向
            if len(merged) >= 2 and prev_high > merged[-2][1]:
                direction = "up"
            elif len(merged) >= 2 and prev_high < merged[-2][1]:
                direction = "down"
            else:
                direction = "up"
            if direction == "up":
                nh = max(prev_high, bi.high)
                nl = max(prev_low, bi.low)
            else:
                nh = min(prev_high, bi.high)
                nl = min(prev_low, bi.low)
            merged[-1] = (prev_idx + [idx], nh, nl)
        else:
            merged.append(([idx], bi.high, bi.low))

    return merged


def _merged_feature_fx(
    merged: list[tuple[list[int], float, float]],
    seg_dir: Direction,
) -> bool:
    """判断包含处理后的特征序列最近三元素是否形成线段结束分型。"""
    if len(merged) < 3:
        return False
    left = merged[-3]
    mid = merged[-2]
    right = merged[-1]
    if seg_dir == Direction.UP:
        # 向上线段：向下特征序列，中间元素高点最高 → 顶分型
        return mid[1] > left[1] and mid[1] > right[1]
    # 向下线段：向上特征序列，中间元素低点最低 → 底分型
    return mid[2] < left[2] and mid[2] < right[2]


def find_xds(
    bis: list[BI],
    config: ChanlunConfig | None = None,
) -> list[XD]:
    """从笔列表中计算线段（特征序列 + 包含处理，方向交替）。

    Args:
        bis: 笔列表（方向交替排列）
        config: 缠论配置

    Returns:
        线段列表
    """
    if config is None:
        config = ChanlunConfig()

    if len(bis) < 3:
        return []

    xds: list[XD] = []

    start = 0
    while start < len(bis):
        seg_dir = bis[start].direction
        features: list[tuple[int, BI]] = []
        end: int | None = None

        j = start + 1
        has_gap = False
        while j < len(bis):
            if bis[j].direction != seg_dir:
                features.append((j, bis[j]))
                # 特征序列第一、第二元素之间是否有缺口（区间不重叠）
                if len(features) == 2:
                    a = features[0][1]
                    b = features[1][1]
                    has_gap = not (min(a.high, b.high) > max(a.low, b.low))

                if len(features) >= 3:
                    merged = _merge_feature_sequence(features)
                    mid_orig_idx: int | None = None
                    if has_gap and len(merged) >= 4:
                        # 特征序列有缺口：线段结束需要「笔破坏」确认——
                        # 顶/底分型之后出现的第 4 个特征元素跌破/升破分型极值。
                        left, mid, right = merged[-4], merged[-3], merged[-2]
                        confirm = merged[-1]
                        if seg_dir == Direction.UP:
                            top_ok = mid[1] > left[1] and mid[1] > right[1]
                            top_low = min(left[2], mid[2], right[2])
                            if top_ok and confirm[2] < top_low:
                                mid_orig_idx = mid[0][0]
                        else:
                            bottom_ok = mid[2] < left[2] and mid[2] < right[2]
                            bottom_high = max(left[1], mid[1], right[1])
                            if bottom_ok and confirm[1] > bottom_high:
                                mid_orig_idx = mid[0][0]
                    elif not has_gap and _merged_feature_fx(merged, seg_dir):
                        mid_orig_idx = merged[-2][0][0]

                    if mid_orig_idx is not None:
                        # 线段终点 = 特征分型「中间元素」的第一支原始特征笔的
                        # 前一支同向笔（笔首尾相连，即线段转折点）。
                        cand_end = mid_orig_idx - 1
                        seg_start_val = bis[start].start.val
                        seg_end_val = bis[cand_end].end.val
                        seg_ok = (
                            seg_end_val > seg_start_val
                            if seg_dir == Direction.UP
                            else seg_end_val < seg_start_val
                        )
                        if seg_ok:
                            end = cand_end
                            break
            j += 1

        if end is not None:
            xds.append(_create_xd_from_bis(bis, start, end, len(xds), seg_dir))
            start = end + 1
        else:
            # 收尾：剩余笔数足够时，向上段取剩余笔中最高顶、向下段取最低底。
            if len(bis) - start >= 3:
                if seg_dir == Direction.UP:
                    cand_end = max(
                        range(start, len(bis)),
                        key=lambda i: (bis[i].end.val, i),
                    )
                else:
                    cand_end = min(
                        range(start, len(bis)),
                        key=lambda i: (bis[i].end.val, i),
                    )
                seg_start_val = bis[start].start.val
                seg_end_val = bis[cand_end].end.val
                seg_ok = (
                    seg_end_val > seg_start_val
                    if seg_dir == Direction.UP
                    else seg_end_val < seg_start_val
                )
                if seg_ok:
                    xds.append(_create_xd_from_bis(bis, start, cand_end, len(xds), seg_dir))
            start = len(bis)

    return xds


def _feature_fx_end_segment(
    features: list[tuple[int, BI]],
    seg_dir: Direction,
) -> bool:
    """判断最近 3 个特征笔是否形成线段结束分型（无包含处理的原始版本）。

    保留用于直接单测；find_xds 实际走 _merge_feature_sequence + _merged_feature_fx。
    """
    if len(features) < 3:
        return False
    (_, left) = features[-3]
    (_, mid) = features[-2]
    (_, right) = features[-1]
    if seg_dir == Direction.UP:
        return mid.high > left.high and mid.high > right.high
    return mid.low < left.low and mid.low < right.low


def _create_xd_from_bis(
    bis: list[BI],
    start_bi_idx: int,
    end_bi_idx: int,
    index: int,
    direction: Direction,
) -> XD:
    """从笔列表创建线段对象。"""
    start_bi = bis[start_bi_idx]
    end_bi = bis[end_bi_idx]
    high = max(bi.high for bi in bis[start_bi_idx : end_bi_idx + 1])
    low = min(bi.low for bi in bis[start_bi_idx : end_bi_idx + 1])
    return XD(
        start=start_bi.start,
        end=end_bi.end,
        direction=direction,
        index=index,
        high=high,
        low=low,
    )