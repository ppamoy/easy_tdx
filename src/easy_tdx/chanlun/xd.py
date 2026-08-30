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
                    end = features[-1][0]
                    break
            j += 1

        if end is not None:
            # 线段 [start, end]，下一段从 end 开始（共享转折点 → 方向交替）
            xds.append(_create_xd_from_bis(bis, start, end, len(xds), seg_dir))
            start = end
        else:
            # 未形成分型：若剩余笔数足以成段则收尾，否则结束
            if len(bis) - start >= 2:
                xds.append(_create_xd_from_bis(bis, start, len(bis) - 1, len(xds), seg_dir))
            start = len(bis)

    return xds


def _feature_fx_end_segment(
    features: list[tuple[int, BI]],
    seg_dir: Direction,
) -> bool:
    """判断最近3个特征K线是否形成线段结束分型。

    向上线段结束：特征序列（向下笔）形成顶分型 —— 中间特征笔的高点最高
    向下线段结束：特征序列（向上笔）形成底分型 —— 中间特征笔的低点最低
    """
    if len(features) < 3:
        return False

    (_, left) = features[-3]
    (_, mid) = features[-2]
    (_, right) = features[-1]

    if seg_dir == Direction.UP:
        # 向上线段：向下笔特征序列，顶分型结束
        return mid.high > left.high and mid.high > right.high
    else:
        # 向下线段：向上笔特征序列，底分型结束
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
