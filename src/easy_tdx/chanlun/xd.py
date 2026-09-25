"""线段计算（缠论特征序列版，含包含处理）。

线段定义：
- 由至少 3 笔构成。
- 特征序列：与当前线段方向相反的那些笔。
- 特征序列需先做「包含处理」（与 K 线包含处理同构），再判断顶/底分型。
- 向上线段：特征序列（向下笔）出现顶分型 → 线段结束。
- 向下线段：特征序列（向上笔）出现底分型 → 线段结束。
- 相邻线段共享转折点，方向自然交替。

说明：采用缠论原文的确定性取舍（XD_TIEBREAK_EARLIEST）与收尾同向端点规则，
保证同一输入永远同一次、端点落在特征序列转折点分型上且方向一致。
笔破坏由 config.xd_bi_pohuai 控制（默认 True，原文口径，见 bi-pohuai-default-on spec）。

假破坏 / 真破坏（线段延伸与确认，第71-78课）：笔破坏只是「暂定」结束，需确认：
- 真破坏确认：破坏笔之后出现更深的反向笔（越过破坏笔极值）→ 破坏方向仍在延续、
  破坏成立 → 线段在破坏笔之前结束（立即提交，优先于特征分型）。
- 假破坏恢复：破坏笔之后同向笔创出超过线段终点的新高/新低（候选假破坏），且无更
  深反向突破推翻 → 破坏笔只是途中回撤、原线段方向仍在延续 → 撤销暂定、线段延伸。
- 特征序列分型为「确认式」结束，立即提交（与真破坏确认并列，取最早端点）。

缺口与第二特征序列：特征序列出现区间缺口时，结束需「笔破坏」式确认
（分型后第 4 个特征元素跌破/升破分型极值）；收尾端点取最后一个已完成
且方向一致的同向笔端点（收尾不换取端点，见 line-segment-original-fidelity spec）。
"""

from __future__ import annotations

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import BI, XD, Direction

# 线段划分多义性的确定性取舍规则（V602）：
# 当同一段走势存在多个合法线段结束候选时，统一取「最早确认」的那个
# （特征序列分型/笔破坏确认首次成立的位置）。这保证同样数据、同样参数
# 永远得到同一划分，避免多义性导致的结果抖动。
XD_TIEBREAK_EARLIEST = True


def _feature_included(a: BI, b: BI) -> bool:
    """判断两支特征笔是否存在包含关系（互为包含）。"""
    return (a.high >= b.high and a.low <= b.low) or (b.high >= a.high and b.low <= a.low)


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


def _valid_segment_end(
    bis: list[BI],
    start: int,
    cand_end: int,
    seg_dir: Direction,
) -> bool:
    """校验候选线段终点与方向一致（向上段终点高于起点、向下段反之）。"""
    seg_start_val = bis[start].start.val
    seg_end_val = bis[cand_end].end.val
    if seg_dir == Direction.UP:
        return seg_end_val > seg_start_val
    return seg_end_val < seg_start_val


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
        seg_dir_is_up = seg_dir == Direction.UP
        features: list[tuple[int, BI]] = []
        # 两种暂定结束：
        #   confirmed_end   —— 特征序列分型 / 真破坏确认（确认式，立即提交）
        #   provisional_end —— 笔破坏（暂定式，可被「假破坏」撤销）
        confirmed_end: int | None = None
        provisional_end: int | None = None
        # 线段终点极值水位：向上段取已见最高顶（up-bi 的 end.val），向下段取已见最低底。
        end_extreme = bis[start].end.val
        # 假破坏恢复状态（缠论第71-78课：线段破坏需确认）：
        #   breakthrough_extreme —— 破坏笔的极值（向上段=向下笔 low，向下段=向上笔 high）。
        #     其后若出现更深的同向破坏笔（越过该极值），则破坏「成立」（真破坏）→ 线段在
        #     破坏笔之前结束；反之原线段方向仍在延续。
        #   seg_new —— 破坏暂定后，同向笔是否创出超过终点水位的新极值（候选「假破坏」）。
        #     此为「待定」信号，不立即撤销——须等到收尾时再据真破坏是否确认来裁决。
        breakthrough_extreme: float | None = None
        seg_new = False

        j = start + 1
        # V730 P1-3/P1-4（缠论第67/71课口径）：
        #   缺口判定随每个特征序列分型进行——比较「分型左元素 vs 中元素」区间是否重叠
        #   （旧实现在首两个特征元素间一次性判定，与分型无对应关系，已废弃）。
        #   带缺口的分型不立即结束线段：进入 gap_pending 待确认状态，由「第二特征序列」
        #   （分型中间元素之后、与线段同向的笔构成的序列）裁决——第二特征序列出现分型
        #   → 确认结束；同向笔创出超过分型顶点的新极值 → 分型无效、线段延续。
        gap_pending: int | None = None
        gap_fx_extreme: float | None = None
        second_features: list[tuple[int, BI]] = []
        while j < len(bis):
            bi = bis[j]
            same_dir = bi.direction == seg_dir

            if gap_pending is not None:
                # V730 P1-4 第三出口（第71课）：缺口待确认期间，股价直接击穿
                # 第一特征序列分型的极值（向上段=分型三元素最低点，向下段=最高点）
                # → 线段在分型中元素处结束（旧实现的「第4特征元素跌破」为此 clause
                # 的粗糙近似，现改为按真实价格击穿判定）。
                # 注意：此出口只做确认；分型无效化的唯一路径是同向笔创出超过
                # 分型顶点的新极值（见同向分支），反向笔的高点高于分型低点是常态，
                # 不构成无效化。
                if (seg_dir_is_up and bi.low < gap_fx_extreme) or (
                    not seg_dir_is_up and bi.high > gap_fx_extreme
                ):
                    cand_end = gap_pending - 1
                    if _valid_segment_end(bis, start, cand_end, seg_dir):
                        confirmed_end = cand_end
                        break
                    # 候选终点与方向矛盾（退化形态）→ 放弃该待确认分型，恢复常规扫描
                    gap_pending = None
                    gap_fx_extreme = None
                    second_features = []

            if same_dir:
                # ── 缺口待确认期间：同向笔构成第二特征序列（第71课）──
                if gap_pending is not None:
                    if (seg_dir_is_up and bi.end.val > end_extreme) or (
                        not seg_dir_is_up and bi.end.val < end_extreme
                    ):
                        # 创出超过分型顶点的新极值 → 待确认分型无效，线段延续；
                        # 落入下方常规同向逻辑（更新水位 / 假破坏判定）。
                        gap_pending = None
                        gap_fx_extreme = None
                        second_features = []
                    else:
                        second_features.append((j, bi))
                        if len(second_features) >= 3:
                            m2 = _merge_feature_sequence(second_features)
                            # 第二特征序列属于「反向候选线段」，其结束分型按候选
                            # 方向判定（向上段→候选向下段→其特征序列出底分型）。
                            opp_dir = Direction.DOWN if seg_dir_is_up else Direction.UP
                            if _merged_feature_fx(m2, opp_dir):
                                # 第二特征序列分型成立 → 缺口场景线段结束确认
                                cand_end = gap_pending - 1
                                if _valid_segment_end(bis, start, cand_end, seg_dir):
                                    confirmed_end = cand_end
                                    break
                                # 候选终点与方向矛盾 → 放弃该待确认分型，恢复常规扫描
                                gap_pending = None
                                gap_fx_extreme = None
                                second_features = []
                        j += 1
                        continue
                # 同向笔：先据当前水位判断是否候选假破坏（新极值），再更新水位。
                if (
                    provisional_end is not None
                    and not seg_new
                    and (
                        (seg_dir_is_up and bi.end.val > end_extreme)
                        or (not seg_dir_is_up and bi.end.val < end_extreme)
                    )
                ):
                    seg_new = True
                if seg_dir_is_up:
                    end_extreme = max(end_extreme, bi.end.val)
                else:
                    end_extreme = min(end_extreme, bi.end.val)
            else:
                # ── 真破坏确认（笔破坏成立）──
                # 笔破坏暂定后，若后续反向笔越过破坏笔极值（更深突破），说明破坏方向仍在
                # 延续、破坏成立 → 线段在破坏笔之前结束（cand_end = 破坏笔前一笔）。此为
                # 确认式，立即提交，优先于特征序列分型（XD_TIEBREAK_EARLIEST：更早的端点）。
                if (
                    provisional_end is not None
                    and breakthrough_extreme is not None
                    and (
                        (seg_dir_is_up and bi.low < breakthrough_extreme)
                        or (not seg_dir_is_up and bi.high > breakthrough_extreme)
                    )
                ):
                    confirmed_end = provisional_end
                    break
                features.append((j, bi))
                # 缠论原文：线段由「至少 3 笔 + 特征序列分型」界定，也可由「笔破坏」结束。
                # 笔破坏为暂定式：反向走势笔越过线段起点极值时记为暂定结束（cand_end = 破坏笔前一笔），
                # 不立即提交；其后若反向笔再创新极值（更深突破）→ 真破坏确认（见上方）；
                # 若同向笔创出超过终点的新极值且无更深突破 → 假破坏，撤销、线段延伸（见收尾裁决）。
                if (
                    config.xd_bi_pohuai
                    and j >= start + 3
                    and provisional_end is None
                    and confirmed_end is None
                ):
                    breakout_feat = bi
                    cand_end = j - 1
                    if seg_dir_is_up and breakout_feat.low < bis[start].start.val:
                        if _valid_segment_end(bis, start, cand_end, seg_dir):
                            provisional_end = cand_end
                            breakthrough_extreme = breakout_feat.low
                    elif not seg_dir_is_up and breakout_feat.high > bis[start].start.val:
                        if _valid_segment_end(bis, start, cand_end, seg_dir):
                            provisional_end = cand_end
                            breakthrough_extreme = breakout_feat.high

                if len(features) >= 3 and gap_pending is None:
                    # V730 P1-4：缺口待确认期间第一特征序列分型检测暂停（否则会把
                    # gap_pending 重置、覆盖第二特征序列的确认进度）。
                    merged = _merge_feature_sequence(features)
                    mid_orig_idx: int | None = None
                    if _merged_feature_fx(merged, seg_dir):
                        # V730 P1-3：缺口判定随分型进行——比较「分型左元素 vs 中元素」
                        # （merged[-3] vs merged[-2]）区间是否重叠（原文第67课）。
                        left_m, mid_m = merged[-3], merged[-2]
                        has_gap = not (min(left_m[1], mid_m[1]) > max(left_m[2], mid_m[2]))
                        if has_gap:
                            # V730 P1-4（原文第71课）：带缺口分型不立即结束，
                            # 由第二特征序列（分型中元素之后的同向笔）确认，
                            # 或待确认期间价格击穿分型极值确认（见同向/反向入口处）。
                            gap_pending = merged[-2][0][0]
                            # 清空上一轮待确认可能残留的第二特征序列（状态卫生）
                            second_features = []
                            gap_fx_extreme = min(left_m[2], mid_m[2], merged[-1][2]) if seg_dir_is_up else max(
                                left_m[1], mid_m[1], merged[-1][1]
                            )
                        else:
                            mid_orig_idx = merged[-2][0][0]

                    if mid_orig_idx is not None:
                        cand_end = mid_orig_idx - 1
                        if _valid_segment_end(bis, start, cand_end, seg_dir):
                            # 特征序列分型 = 确认式结束，立即提交（XD_TIEBREAK_EARLIEST）。
                            confirmed_end = cand_end
                            break
            j += 1

        # 收尾裁决：确认式（特征分型 / 真破坏确认）优先于暂定式（笔破坏）。
        # 笔破坏暂定若出现候选假破坏（同向笔创出超过终点的新极值）且未被真破坏确认
        # （更深突破）推翻 → 撤销暂定、线段延伸（落入收尾同向端点）；否则暂定转为正式结束。
        if provisional_end is not None and seg_new and confirmed_end is None:
            provisional_end = None
        end = confirmed_end if confirmed_end is not None else provisional_end
        if end is not None:
            xds.append(_create_xd_from_bis(bis, start, end, len(xds), seg_dir))
            start = end + 1
        else:
            # 收尾（数据用尽）：取「最后一个已完成且方向一致的同向笔」端点
            # （line-segment-original-fidelity：收尾不换取端点——禁止 max/min 换出
            # 非共享端点；max/min 选点会把终点挪到早已过去的笔上，与「未完成段」
            # 的原文语义不符）。端点必落在某笔端点分型上，与下一段共享时不断裂。
            # 原文分歧备注：缠论原文对未完成线段并无收尾规定，此处为工程化的
            # 确定性延伸（显式标注，非静默近似）。
            if len(bis) - start >= 3:
                tail_end: int | None = None
                for i in range(len(bis) - 1, start - 1, -1):
                    if bis[i].direction != seg_dir:
                        continue
                    if not _valid_segment_end(bis, start, i, seg_dir):
                        continue
                    tail_end = i
                    break
                if tail_end is not None:
                    xds.append(_create_xd_from_bis(bis, start, tail_end, len(xds), seg_dir))
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
