"""线段计算（标准缠论特征序列版）。

线段定义：
- 由至少3笔构成
- 特征序列：相对当前线段方向的"反向笔"，构成特征K线序列
- 特征序列分型：线段结束的判定（向上线段出现顶分型结束，向下线段出现底分型结束）
- 相邻线段共享转折点（前一段的结束笔即后一段的起始笔），因此方向自然交替

标准算法（缠论新笔/老笔通用）：
1. 线段方向 = 起始笔方向
2. 特征序列 = 与线段方向相反的笔
3. 当特征序列出现分型（顶分型结束向上线段 / 底分型结束向下线段）时，线段结束
4. 下一线段从结束笔开始（共享转折点），方向与上一段相反
"""

from __future__ import annotations

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import BI, XD, Direction


def find_xds(
    bis: list[BI],
    config: ChanlunConfig | None = None,
) -> list[XD]:
    """从笔列表中计算线段（特征序列法，方向交替）。

    线段划分规则：
    - 向上线段：特征序列为向下笔，出现顶分型时结束
    - 向下线段：特征序列为向上笔，出现底分型时结束
    - 相邻线段共享转折点（结束笔即下一段起始笔）

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

    # 从第一笔开始划分，线段方向由起始笔方向决定
    start = 0
    while start < len(bis):
        seg_dir = bis[start].direction

        # 特征序列：与线段方向相反的笔
        # features 记录 (bi_index, bi)，用于分型判定
        features: list[tuple[int, BI]] = []
        end: int | None = None

        j = start + 1
        while j < len(bis):
            if bis[j].direction != seg_dir:
                # 反向笔加入特征序列
                features.append((j, bis[j]))
                # 最近3个特征笔形成分型 → 线段结束
                if len(features) >= 3 and _feature_fx_end_segment(features, seg_dir):
                    # 线段的终点 = 特征分型「中间元素」所在笔（features[-2]）的起点分型。
                    # 由于笔是首尾相连的，中间特征笔的起点 == 它前一支笔（同向笔）的终点，
                    # 因此线段包含 [start, mid_idx-1]，终点分型即 bis[mid_idx-1].end。
                    # 此前实现取 features[-1]（分型右笔）导致：
                    #   向上线段终点落到「向下笔的结束分型」（底分型），
                    #   且下一段 start=end 使相邻线段共享一整支笔而非转折点。
                    mid_idx = features[-2][0]
                    cand_end = mid_idx - 1
                    # 端点价格方向校验（与笔一致）：线段方向必须与端点分型价格一致。
                    # 若向上线段终点（顶分型）低于起点（底分型），说明起点极值已被
                    # 趋势穿越（长下跌中的弱反弹），此处不是真正的线段转折点，
                    # 继续延伸，避免画出「向下走的向上线段」。
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
            # 线段 [start, end]（end 为特征分型中间元素的前一支同向笔，
            # 其终点分型 == 中间特征笔的起点，即线段转折点/顶底分型）。
            # 下一段从中间特征笔开始：起点分型与上一段终点分型是同一个
            # （共享转折点），且方向自动交替。
            xds.append(_create_xd_from_bis(bis, start, end, len(xds), seg_dir))
            start = end + 1
        else:
            # 未形成分型：若剩余笔数足以成段则收尾，否则结束。
            # 缠论线段至少由 3 笔构成；且线段方向必须与首尾端点价格走势一致
            # （向上线段终点高于起点、向下线段终点低于起点），否则该“段”是
            # 方向标注与价格走势矛盾的伪线段，画出来没有参考价值。
            #
            # 关键：线段端点分型类型必须与线段方向匹配 —— 向上线段的终点必须是
            # 顶分型（取剩余笔中最高顶），向下线段的终点必须是底分型（取剩余笔中
            # 最低底）。旧实现直接取 bis[-1].end（最新分型），当收尾处于反向笔
            # 中时会把「向下线段」画到顶分型上（或向上线段画到底分型上），端点
            # 类型与方向矛盾，视觉上无参考价值。
            if len(bis) - start >= 3:
                if seg_dir == Direction.UP:
                    # 最高顶分型；相同价位取最后出现（延续到最远，保持首尾相连）
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
    """判断最近3个特征K线是否形成线段结束分型。

    向上线段结束：特征序列（向下笔）形成顶分型 —— 中间特征笔的高点最高
    向下线段结束：特征序列（向上笔）形成底分型 —— 中间特征笔的低点最低

    v87 改进：增加严格的高低点比较，避免平局情况导致误判。
    v89 改进：增加"中间元素必须严格高于/低于两边"的校验，防止平局分型。
    """
    if len(features) < 3:
        return False

    (_, left) = features[-3]
    (_, mid) = features[-2]
    (_, right) = features[-1]

    if seg_dir == Direction.UP:
        # 向上线段：向下笔特征序列，顶分型结束
        # 严格检查：中间笔的高点必须严格大于两边（不允许平局）
        return mid.high > left.high and mid.high > right.high
    else:
        # 向下线段：向上笔特征序列，底分型结束
        # 严格检查：中间笔的低点必须严格小于两边（不允许平局）
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
