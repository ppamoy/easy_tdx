"""中枢计算（改进版）。

中枢定义：至少三笔（或线段）的价格区间有重叠。
- zg（上沿）= 重叠区间的最高点
- zd（下沿）= 重叠区间的最低点
- gg = 中枢内所有笔的最高价
- dd = 中枢内所有笔的最低价

标准中枢算法（改进版）：
1. 逐笔扫描，累积与当前区间有重叠的笔
2. 只有当新笔与现有中枢区间有重叠时才加入
3. 当某笔完全离开中枢区间后，关闭中枢
4. 中枢至少需要3笔才成立
"""

from __future__ import annotations

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import BI, ZS


def find_zss(
    bis: list[BI],
    config: ChanlunConfig | None = None,
) -> list[ZS]:
    """从笔列表中计算中枢（改进版）。

    算法：
    1. 逐笔扫描，维护当前中枢候选区间 [zg_candidate, zd_candidate]
    2. 新笔与当前区间有重叠 → 加入中枢，更新重叠区间
    3. 新笔完全离开当前区间 → 检查中枢是否成立（≥3笔），然后重置
    4. 最后一批笔也可能形成未完成中枢

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

        if overlap_high > overlap_low:
            # 有重叠，加入中枢候选
            candidate_lines.append(bi)
            zg_candidate = overlap_high
            zd_candidate = overlap_low
            gg_candidate = max(gg_candidate, bi.high)
            dd_candidate = min(dd_candidate, bi.low)
            candidate_end = bi.end
        else:
            # 无重叠，检查候选中枢是否成立
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
        zss.append(zs)

    return zss
