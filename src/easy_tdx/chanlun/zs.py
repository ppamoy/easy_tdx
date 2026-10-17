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
from easy_tdx.chanlun.types import BI, FX, ZS

# V735 原文第33课：「中枢的延伸不能超过5段，也就是一旦出现6段的延伸，
# 加上形成中枢本身那三段，就构成更大级别的中枢了。」
# ⇒ 3（形成）+ 5（延伸）= 8 段为正常上限；第 9 段触发升级。
# 工程上：9 段时关闭当前中枢（而非原地升级为更大级别——那需递归架构），
# 让后续 笔/线段 形成新中枢。与原文阈值一致（3+6=9），但升级方式是近似。
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


def mark_upgraded_zss(zss: list[ZS]) -> int:
    """按第20课定理二标记「升级为更大级别中枢」的中枢。

    原文（第20课「缠中说禅走势中枢中心定理二」，逐字）：

      「前后同级别的两个缠中说禅走势中枢，后GG < 前DD 等价于下跌及其延续；
       后DD > 前GG 等价于上涨及其延续。后ZG < 前ZD 且后GG >= 前DD，
       或 后ZD > 前ZG 且 后DD =< 前GG，则等价于形成**高级别的走势中枢**。」

    原文（第33课，逐字）：

      「一般来说，中枢的延伸不能超过5段，也就是一旦出现6段的延伸，
       加上形成中枢本身那三段，就构成**更大级别的中枢**了。」

    实现口径：
      - 对相邻两中枢，若满足定理二的任一分支 ⇒ 后一个中枢**升级**
        （``upgraded=True``、``level`` 进一级、``upgrade_from`` 记录来源）；
      - **不合并段数**（那正是 V851 修掉的「同级别合并」错误：把两个同级别
        中枢的段数相加，既违反第33课 9 段上限，也不是原文的"升级"语义）；
      - 只做**标记**，不改 ZG/ZD/lines —— 中枢区间仍由各自的第20课口径确定。

    ⚠️ 与真正的「递归升级」的差距（已实测确认，不是推理）：
      原文的"更大级别中枢"意味着**换一把尺子**重新看这段走势（用更大级别的
      次级别走势类型重叠来定义区间），那需要走势类型级递归。
      本函数只把「这里发生了升级」这件事**显式记录下来**，让下游（买卖点判定、
      可视化、审计）能按原文口径区分「同级别中枢」与「升级中枢」，
      但**不重算区间**。这是当前架构下能做到的最接近原文的一步。

    Args:
        zss: 中枢列表（时间顺序）

    Returns:
        被标记为升级的中枢个数。
    """
    marked = 0
    for prev, cur in zip(zss, zss[1:]):
        # 定理二分支一：后ZG < 前ZD 且 后GG >= 前DD
        cond_a = cur.zg < prev.zd and cur.gg >= prev.dd
        # 定理二分支二：后ZD > 前ZG 且 后DD <= 前GG
        cond_b = cur.zd > prev.zg and cur.dd <= prev.gg
        if cond_a or cond_b:
            cur.upgraded = True
            cur.level = prev.level + 1
            if prev.index not in cur.upgrade_from:
                cur.upgrade_from.append(prev.index)
            # 前一个若本身也是升级而来，一并记录来源（传递性）
            for src in prev.upgrade_from:
                if src not in cur.upgrade_from:
                    cur.upgrade_from.append(src)
            marked += 1
    return marked


def _merge_overlapping_zss(zss: list[ZS]) -> list[ZS]:
    """合并相邻 [ZD, ZG] 重叠的中枢。

    ⚠️ V851 重核（推翻 V735 的"第19课"引文）：
    原注释引「第19课定理一：前后两个中枢不能有任何重叠，否则就只是一个
    更大级别的盘整」—— 该句在 108 课原文里 **grep 不到**。

    已全文检索「不能有任何重叠」，唯一命中是 **第20课 line 4**：
      「而在趋势里，同级别的前后缠中说禅走势中枢是不能有任何重叠的……
        如果三个连续次级别走势类型的重叠区间虽然不和前面的走势中枢有
        任何重叠，但围绕该中枢产生的波动触及前面走势中枢延续时的某个
        瞬间波动区间，这时候，就不能认为该走势类型是趋势，而只是产生
        一个**更大级别的**缠中说禅走势中枢。」
    ⇒ 原文口径：前后中枢重叠 ⇒ **升级为更大级别中枢**。

    本函数做的是 `prev.lines.extend(zs.lines)`：把两个**同级别**中枢的
    段数相加，造出同级别的超长中枢。这
      1) 违反第33课 line 7 的 3+6=9 段上限；
      2) 也不是第20课的"升级为更大级别"。

    实测（scripts/audit_g1_merge_overlap_impact.py，12 只真实日线 332 中枢）：
      A 无限延伸+合并开: >9段 81 (24.4%)，最长 37 段，合并触发 3 对
      B 硬关闭  +合并开: >9段 58 (17.8%)，最长 32 段，合并触发 77 对
      C 硬关闭  +合并关: >9段 0  ( 0.0%)，最长  9 段

    V851 决策：`zs_merge_overlap` 默认改为 False，本函数默认不再执行。
    保留本函数 + 开关，便于显式恢复旧行为与做对照组。
    """
    if len(zss) < 2:
        return zss
    result: list[ZS] = []
    for zs in zss:
        if result:
            prev = result[-1]
            if prev.zd < zs.zg and zs.zd < prev.zg:
                prev.lines.extend(zs.lines)
                prev.gg = max(prev.gg, zs.gg)
                prev.dd = min(prev.dd, zs.dd)
                prev.end = zs.end
                prev.done = zs.done
                continue
        result.append(zs)
    for i, zs in enumerate(result):
        zs.index = i
    return result


def find_zss(
    bis: list[BI],
    config: ChanlunConfig | None = None,
) -> list[ZS]:
    """从笔列表中计算中枢（第20课原文口径）。

    原文（第20课）：
        「再定义 ZG=min(g1、g2)，ZD=max(d1、d2)，显然，[ZD，ZG] 就是
        缠中说禅走势中枢的区间」
    其中 g1/d1、g2/d2 是**与中枢形成方向一致的两个 Z 走势段（A 段、C 段）**
    —— 即**第 1 笔和第 3 笔**，中间的反向笔（B 段）**不参与**。
    原文里**没有 g3**。

    中枢判定规则：
    1. 中枢 = 至少三个连续次级别走势的重叠区间。
    2. ZG/ZD 由第 1 笔和第 3 笔的重叠确定（min(高), max(低)），之后冻结。
    3. 之后每个同级别走势若与 [ZD, ZG] 有重叠（overlap_high > overlap_low，
       无比例阈值——原文只要求「重叠」，不要求达到某个百分比），
       则为中枢延伸，只更新 GG/DD，不改变 ZG/ZD。
    4. 某走势与 [ZD, ZG] 完全无重叠 → 中枢结束。
    5. 中枢震荡延伸达 _MAX_ZS_SEGMENTS 段后关闭（工程上限，防止无限延伸
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
    candidate_start: FX | None = first_bi.start
    candidate_end: FX | None = first_bi.end

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

            # 第20课原文：ZG = min(g1, g2)，ZD = max(d1, d2)
            # g1/d1 = 第1笔(A段)，g2/d2 = 第3笔(C段)，中间反向笔(B段)不参与。
            # 前2笔时用运行重叠（尚未形成中枢），第3笔加入时按原文重算并冻结。
            if len(candidate_lines) >= 3:
                a_bi = candidate_lines[0]
                c_bi = candidate_lines[2]
                zg_candidate = min(a_bi.high, c_bi.high)
                zd_candidate = max(a_bi.low, c_bi.low)
            else:
                zg_candidate = overlap_high
                zd_candidate = overlap_low
            # 第20课 line22 原文：「GG=max(gn)，DD=min(dn)，n遍历中枢中所有Zn」，
            # Zn = 与中枢方向一致的次级别走势类型（同向段 A/C/E…），反向段（B/D…）不参与。
            # 中枢方向 = 首笔方向（30课 line142：「一样有方向，例如…方向就是下上下」）。
            # 故 GG/DD 只累加 bi.direction == candidate_lines[0].direction 的同向段。
            # （此前对每根笔更新，使 GG 被反向段极值污染——已修；同步改固化测试。）
            if bi.direction == candidate_lines[0].direction:
                gg_candidate = max(gg_candidate, bi.high)
                dd_candidate = min(dd_candidate, bi.low)
            candidate_end = bi.end

            # V735/V850 原文第33课：「中枢的延伸不能超过5段，一旦出现6段的延伸，
            # 加上形成中枢本身那三段，就构成更大级别的中枢了。」
            # ⇒ 上限 = 3（形成）+ 6（延伸）= **9 段**（总段数，不是 8 段）。
            #    第32课「延伸不能超过9个次级别……9个30分钟的延伸，每三个又构成
            #    日线级别，三个日线级别自然就是周线级别」的算术自证 9 = 3+6；
            #    第59/36/99课同口径（见 docs/CHANLUN_108_LESSONS_RULE_TABLE_V850.md §3.1）。
            #
            # ⚠️ 实测偏离（scripts/guard_chanlun_lesson33_zs_extension_v850.py）：
            #    zs_no_hard_close=True 下 12 只真实日线 332 个中枢，81 个（24.4%）
            #    超过 9 段，最长 37 段 —— 即"中枢无限延伸"本身违反第33课。
            #    原文要求的是**升级为更大级别中枢**（需走势类型级递归），
            #    代码做不到，只能用工程上限兜底。
            #
            # 口径说明（V850 更正，原注释写反了）：
            #   zs_no_hard_close=True（默认）＝ **偏离原文**的工程折衷：
            #       不硬关闭，让中枢自然延伸到笔真正离开 [ZD,ZG]。
            #   zs_no_hard_close=False ＝ 9 段硬关闭（工程上限，数字贴近第33课，
            #       但仍非原文的"升级"语义）。
            if (
                not getattr(config, "zs_no_hard_close", True)
                and len(candidate_lines) >= config.zs_min_lines
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
                    direction=candidate_lines[0].direction.value,  # 30课L142 中枢方向=首笔方向
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
                        direction=candidate_lines[0].direction.value,  # 30课L142 中枢方向=首笔方向
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
                direction=candidate_lines[0].direction.value,  # 30课L142 中枢方向=首笔方向
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

    # V851 重核：原文第20课 line4（非"第19课定理一"——该引文 grep 不到）：
    # 「同级别的前后缠中说禅走势中枢是不能有任何重叠的……重叠就产生更大级别中枢」。
    # 合并相邻 [ZD, ZG] 重叠的中枢（消除残余 1.3% 重叠，无需次级别数据）。
    if getattr(config, "zs_merge_overlap", True):
        zss = _merge_overlapping_zss(zss)

    # V853 原文第20课定理二 / 第33课：满足「后ZG < 前ZD 且 后GG >= 前DD，
    # 或 后ZD > 前ZG 且 后DD <= 前GG」⇒ 形成**高级别的走势中枢**；
    # 第33课 9 段延伸超限 ⇒ 「构成更大级别的中枢」。
    # 默认开启（只打标记，不改区间/段数 ⇒ 不影响既有计数与信号）。
    if getattr(config, "zs_mark_upgrade", True):
        mark_upgraded_zss(zss)

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
