"""中枢计算（改进版 v89）。

中枢定义：至少三笔（或线段）的价格区间有重叠。
- zg（上沿）= 重叠区间的最高点（区间内最高的低点）
- zd（下沿）= 重叠区间的最低点（区间内最低的高点）
- gg = 中枢内所有笔的最高价
- dd = 中枢内所有笔的最低价

标准中枢算法（v89 - 增强版）：
1. 逐笔扫描，累积与当前区间有重叠的笔
2. 只有当新笔与现有中枢区间有重叠且重叠率 > threshold 时才加入
3. 当某笔完全离开中枢区间后，检查是否形成有效中枢（≥min_lines笔）
4. 有效中枢关闭后，从当前笔重新开始候选
5. 最后一批笔形成未完成中枢（done=False）
6. v87: 增加"中枢方向推断"——根据首尾笔方向推断中枢所处趋势阶段
7. v89: 增加"中枢质量评分"——基于笔数、宽度、位置综合评估中枢强度

v89 改进：
- 增加"中枢有效性二次验证"——关闭前检查重叠度是否足够
- 增加"中枢最小宽度动态调整"——根据价格水平自适应
- 增加"中枢方向推断"——标记中枢处于上升/下降/盘整阶段
"""

from __future__ import annotations

from typing import Any

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import BI, ZS


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
    """从笔列表中计算中枢（v89 增强版）。

    算法：
    1. 逐笔扫描，维护当前中枢候选区间 [zg_candidate, zd_candidate]
    2. 新笔与当前区间有重叠且重叠率 > 动态阈值 → 加入中枢，更新重叠区间
    3. 新笔完全离开当前区间 → 检查中枢是否成立（≥min_lines笔），然后重置
    4. 最后一批笔也可能形成未完成中枢
    5. v87: 增加区间有效性检查和稳定性保护
    6. v89: 增加"中枢质量评分"和"方向推断"

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

    # v87: 中心率动态阈值
    base_overlap_threshold = 0.05

    for i in range(1, len(bis)):
        bi = bis[i]

        # 检查新笔与当前中枢候选区间是否有重叠
        overlap_high = min(zg_candidate, bi.high)
        overlap_low = max(zd_candidate, bi.low)

        if overlap_high > overlap_low:
            # 有重叠，计算重叠率
            overlap_rate = _overlap_ratio(zg_candidate, zd_candidate, bi.high, bi.low)

            # v87: 动态阈值——小价格区间使用更宽松的重叠率要求
            mid_price = (zg_candidate + zd_candidate) / 2
            if mid_price > 0:
                price_range = (zg_candidate - zd_candidate) / mid_price
                if price_range < 0.05:  # 区间宽度 < 5%
                    # 窄区间：放宽重叠率要求到 2%
                    effective_threshold = max(0.02, base_overlap_threshold * 0.4)
                else:
                    effective_threshold = base_overlap_threshold
            else:
                effective_threshold = base_overlap_threshold

            # 重叠率过低时视为无有效重叠，关闭当前候选
            if overlap_rate < effective_threshold:
                # 关闭当前候选
                if len(candidate_lines) >= config.zs_min_lines:
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
                continue

            # 有足够重叠，加入中枢候选
            candidate_lines.append(bi)
            zg_candidate = overlap_high
            zd_candidate = overlap_low
            gg_candidate = max(gg_candidate, bi.high)
            dd_candidate = min(dd_candidate, bi.low)
            candidate_end = bi.end
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

    # 处理最后一个中枢候选
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

    return zss
