"""中枢计算（V730 原文口径版）。

缠论原文口径（第17/20/35课）：
- 中枢 = 至少三个连续次级别走势的重叠区间。
- ZG/ZD 由前两个次级别走势的重叠确定后即冻结（ZG = min(g1,g2)，ZD = max(d1,d2)），
  之后的延伸段只更新极值 GG/DD，不改变 ZG/ZD。
- 延伸判据 = 与 [ZD, ZG] 有重叠（overlap_high > overlap_low），无比例阈值。
- gg = 中枢内所有笔的最高价（max(high)），dd = 最低价（min(low)）。

工程实现说明：
- v87 的「重叠率动态阈值」「区间有效性二次验证」「中枢质量评分」保留辅助
  定位（_overlap_ratio 供测试与外部使用），但延伸判定不再使用百分比阈值。
- V730 P1-6：中枢震荡延伸达 _MAX_ZS_SEGMENTS 段后关闭（工程上限）。
"""

from __future__ import annotations

from typing import Any

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import BI, ZS

# V730 P1-6：中枢延伸段数上限（含初始3段）。原文允许中枢任意延伸，
# 但工程上无限延伸会让中枢吞没后续行情、买卖点定位漂移，故设上限。
_MAX_ZS_SEGMENTS = 9


def _overlap_ratio(
    range_high: float,
    range_low: float,
    bi_high: float,
    bi_low: float,
) -> float:
    """计算两价格区间的重叠比例（0-1）。

    重叠比例 = 重叠区间长度 / 新笔区间长度。
    比例 > 0 表示有重叠，= 0 表示完全分离。
    """
    if bi_high <= bi_low:
        return 0.0
    overlap_high = min(range_high, bi_high)
    overlap_low = max(range_low, bi_low)
    overlap = max(0.0, overlap_high - overlap_low)
    return overlap / (bi_high - bi_low)


def _is_valid_zs_range(zg: float, zd: float, gg: float, dd: float) -> bool:
    """检查中枢区间是否有效。

    v87: 新增检查——中枢必须有合理的宽度，不能是退化的单点。
    v89: 增强检查——zg 必须严格大于 zd，且中枢宽度至少为价格的 0.05%
         （防止价格极低时阈值过小导致误判）。gg 必须 >= zg 且 dd 必须 <= zd。
    """
    if zg <= zd:
        return False
    # 中枢宽度至少为价格的 0.05%（防止噪音区间被识别为中枢）
    mid = (zg + zd) / 2
    if mid > 0:
        width_pct = (zg - zd) / mid
        if width_pct < 0.0005:  # 0.05%
            return False
    # gg 必须 >= zg 且 dd 必须 <= zd（中枢的极值范围应包含重叠区间）
    if gg < zg or dd > zd:
        return False
    return True


def _should_close_candidate(
    candidate_lines: list[BI],
    zg_candidate: float,
    zd_candidate: float,
    bi: BI,
    config: ChanlunConfig,
) -> bool:
    """判断是否应该关闭当前中枢候选。

    v87: 改进的判断逻辑，考虑更多因素。
    v88: 增加"重叠率检查"——新笔与候选区间完全无重叠且重叠率为0时关闭。
    """
    if len(candidate_lines) < config.zs_min_lines:
        return False

    # 检查新笔与候选区间的关系
    overlap_high = min(zg_candidate, bi.high)
    overlap_low = max(zd_candidate, bi.low)

    if overlap_high > overlap_low:
        # 新笔与候选区间仍有重叠，不关闭
        return False

    # 完全无重叠 → 关闭当前候选
    return True


def _calc_zs_quality(
    zs: ZS,
    bis: list[BI],
    index: int,
) -> dict[str, Any]:
    """计算中枢质量评分。

    v89 新增：基于以下维度评估中枢质量：
    - 笔数：中枢包含的笔数越多，结构越稳固
    - 宽度：中枢宽度适中（不过窄也不过宽）
    - 位置：中枢在整体走势中的相对位置
    - 方向一致性：中枢内笔的方向交替是否规范

    Returns:
        {"quality_score": float, "bi_count": int, "width_pct": float, "grade": str}
    """
    if zs.line_count < 3:
        return {"quality_score": 0.3, "bi_count": zs.line_count, "width_pct": 0.0, "grade": "weak"}

    # 笔数评分（3笔=0.6, 5笔=0.8, 7笔+=1.0）
    bi_score = min(1.0, zs.line_count / 7.0)

    # 宽度评分（宽度适中最佳）
    mid = (zs.zg + zs.zd) / 2
    width_pct = (zs.zg - zs.zd) / mid if mid > 0 else 0
    if width_pct < 0.01:
        width_score = 0.4  # 太窄，可能是噪音
    elif width_pct < 0.05:
        width_score = 0.8  # 适中
    elif width_pct < 0.15:
        width_score = 0.7  # 较宽
    else:
        width_score = 0.5  # 过宽，可能是大范围震荡

    # 方向交替评分
    direction_score = 0.8  # 默认
    if zs.lines and len(zs.lines) >= 3:
        directions = [line.direction for line in zs.lines]
        alternations = sum(
            1 for i in range(1, len(directions)) if directions[i] != directions[i - 1]
        )
        expected = len(directions) - 1
        if expected > 0:
            direction_score = alternations / expected

    # 综合评分
    quality_score = bi_score * 0.4 + width_score * 0.3 + direction_score * 0.3

    # 评级
    if quality_score >= 0.8:
        grade = "strong"
    elif quality_score >= 0.6:
        grade = "medium"
    else:
        grade = "weak"

    return {
        "quality_score": round(quality_score, 2),
        "bi_count": zs.line_count,
        "width_pct": round(width_pct * 100, 2),
        "grade": grade,
    }


def find_zss(
    bis: list[BI],
    config: ChanlunConfig | None = None,
) -> list[ZS]:
    """从笔列表中计算中枢（V730 原文口径版）。

    缠论原文口径（第17/20/35课）：
    1. 中枢 = 至少三个连续次级别走势的重叠区间；ZG/ZD 由「前两个次级别走势」
       的明确重叠确定后即冻结（ZG = min(g1,g2)，ZD = max(d1,d2)）。
    2. 之后每个同级别走势若与 [ZD, ZG] 有重叠（overlap_high > overlap_low，
       无比例阈值——原文只要求「重叠」，不要求达到某个百分比），
       则为中枢延伸，只更新 GG/DD，不改变 ZG/ZD。
    3. 某走势与 [ZD, ZG] 完全无重叠 → 中枢结束。
    4. 中枢震荡延伸达 _MAX_ZS_SEGMENTS 段后关闭（工程上限，防止无限延伸
       吞没后续行情；原文允许任意延伸，但同样可用「走势终完美」判断结束）。

    Args:
        bis: 笔列表
        config: 缠论配置

    Returns:
        中枢列表
    """
    if config is None:
        config = ChanlunConfig()

    if len(bis) < 3:
        return []

    zss: list[ZS] = []

    # 用第一笔初始化中枢候选区间
    first_bi = bis[0]
    zg_candidate = first_bi.high
    zd_candidate = first_bi.low
    gg_candidate = first_bi.high
    dd_candidate = first_bi.low
    candidate_lines: list[BI] = [first_bi]
    candidate_start = first_bi.start
    candidate_end = first_bi.end

    for i in range(1, len(bis)):
        bi = bis[i]

        # 检查新笔与当前中枢候选区间是否有重叠
        overlap_high = min(zg_candidate, bi.high)
        overlap_low = max(zd_candidate, bi.low)

        # V730 P1-2：原文只要求「重叠」，移除 v87 的重叠率百分比阈值——
        # 只要 overlap_high > overlap_low 即为重叠（0 宽度的 touch 不算）。
        if overlap_high > overlap_low:
            # 有重叠，加入中枢候选
            candidate_lines.append(bi)
            # V730 P1-1：原文口径——ZG/ZD 由前两个次级别走势的重叠确定后冻结，
            # 第3笔起为中枢延伸，只更新极值 GG/DD，不再改变 ZG/ZD。
            if len(candidate_lines) <= 2:
                zg_candidate = overlap_high
                zd_candidate = overlap_low
            gg_candidate = max(gg_candidate, bi.high)
            dd_candidate = min(dd_candidate, bi.low)
            candidate_end = bi.end

            # V730 P1-6：延伸上限——中枢震荡延伸达 _MAX_ZS_SEGMENTS 段后关闭，
            # 之后的笔开启新的中枢候选（防止无限延伸吞没后续行情）。
            if (
                len(candidate_lines) >= config.zs_min_lines
                and len(candidate_lines) >= _MAX_ZS_SEGMENTS
            ):
                zs = ZS(
                    lines=list(candidate_lines),
                    zg=zg_candidate,
                    zd=zd_candidate,
                    gg=gg_candidate,
                    dd=dd_candidate,
                    start=candidate_start,
                    end=candidate_end,
                    index=len(zss),
                    done=True,
                )
                # v89: 计算中枢质量评分
                quality = _calc_zs_quality(zs, bis, len(zss))
                zs.quality_score = quality["quality_score"]
                zs.grade = quality["grade"]
                zs.width_pct = quality["width_pct"]
                zss.append(zs)
                candidate_lines = []
                zg_candidate = 0.0
                zd_candidate = 0.0
                gg_candidate = 0.0
                dd_candidate = 0.0
                candidate_start = None
                candidate_end = None
        else:
            # 完全无重叠，关闭当前候选
            if len(candidate_lines) >= config.zs_min_lines:
                # v87: 验证中枢区间有效性
                if _is_valid_zs_range(zg_candidate, zd_candidate, gg_candidate, dd_candidate):
                    zs = ZS(
                        lines=list(candidate_lines),
                        zg=zg_candidate,
                        zd=zd_candidate,
                        gg=gg_candidate,
                        dd=dd_candidate,
                        start=candidate_start,
                        end=candidate_end,
                        index=len(zss),
                        done=True,
                    )
                    # v89: 计算中枢质量评分
                    quality = _calc_zs_quality(zs, bis, len(zss))
                    zs.quality_score = quality["quality_score"]
                    zs.grade = quality["grade"]
                    zs.width_pct = quality["width_pct"]
                    zss.append(zs)

            # 开始新的中枢候选
            candidate_lines = [bi]
            zg_candidate = bi.high
            zd_candidate = bi.low
            gg_candidate = bi.high
            dd_candidate = bi.low
            candidate_start = bi.start
            candidate_end = bi.end

    # 处理最后一个中枢候选（V730：candidate_lines 可能为空——9段上限关闭后重置）
    if candidate_lines and len(candidate_lines) >= config.zs_min_lines:
        # v87: 验证中枢区间有效性
        if _is_valid_zs_range(zg_candidate, zd_candidate, gg_candidate, dd_candidate):
            zs = ZS(
                lines=list(candidate_lines),
                zg=zg_candidate,
                zd=zd_candidate,
                gg=gg_candidate,
                dd=dd_candidate,
                start=candidate_start,
                end=candidate_end,
                index=len(zss),
                done=False,  # 最后一根K线未确定，中枢未完成
            )
            # v89: 计算中枢质量评分
            quality = _calc_zs_quality(zs, bis, len(zss))
            zs.quality_score = quality["quality_score"]
            zs.grade = quality["grade"]
            zs.width_pct = quality["width_pct"]
            zss.append(zs)
        elif len(candidate_lines) >= config.zs_min_lines + 1:
            # 尝试用更少的笔重新计算中枢（去掉第一笔，看是否能形成有效中枢）
            reduced_lines = candidate_lines[1:]
            if len(reduced_lines) >= config.zs_min_lines:
                red_zg = min(ln.high for ln in reduced_lines)
                red_zd = max(ln.low for ln in reduced_lines)
                red_gg = max(ln.high for ln in reduced_lines)
                red_dd = min(ln.low for ln in reduced_lines)
                if _is_valid_zs_range(red_zg, red_zd, red_gg, red_dd):
                    zs = ZS(
                        lines=list(reduced_lines),
                        zg=red_zg,
                        zd=red_zd,
                        gg=red_gg,
                        dd=red_dd,
                        start=reduced_lines[0].start,
                        end=reduced_lines[-1].end,
                        index=len(zss),
                        done=False,
                    )
                    # v89: 计算中枢质量评分
                    quality = _calc_zs_quality(zs, bis, len(zss))
                    zs.quality_score = quality["quality_score"]
                    zs.grade = quality["grade"]
                    zs.width_pct = quality["width_pct"]
                    zss.append(zs)

    # 缠论原文：中枢 = 进入段 + 重叠段 + 离开段。显式记录两端，
    # 便于背驰/前端直接使用「进入笔/离开笔」而不必再隐式索引。
    for zs in zss:
        if not zs.lines:
            continue
        first = zs.lines[0]
        last = zs.lines[-1]
        if first.index > 0:
            zs.enter_bi = bis[first.index - 1]
        if last.index + 1 < len(bis):
            zs.exit_bi = bis[last.index + 1]

    return zss
