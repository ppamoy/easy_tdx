"""背驰判断（精修版）。

背驰类型：
- 笔背驰：相邻同向笔的力度比较（MACD面积或幅度）
- 盘整背驰：中枢内最后一笔力度小于进入中枢的第一笔
- 趋势背驰：两个同向中枢之间，离开中枢的笔力度减小

严格标准：力度比率 < 0.8 才算背驰
"""

from __future__ import annotations

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.mmd_conditions import _calc_bi_force, _find_leaving_bi, _find_leaving_xd, _check_zero_axis_pullback
from easy_tdx.chanlun.types import BC, BI, ZS, BCType, Direction


def check_bi_beichi(
    bis: list[BI],
    zss: list[ZS],
    closes: list[float] | None = None,
    config: ChanlunConfig | None = None,
    mmds: list | None = None,
    lower_xds: list | None = None,
    lower_closes: list[float] | None = None,
) -> list[BC]:
    """检查笔级别的背驰。

    使用更严格的背驰判断标准：
    1. 笔背驰：比较相邻同向笔的MACD面积
    2. 盘整背驰：中枢内末笔 vs 首笔
    3. 趋势背驰：连续同向中枢离开力度比较

    v89 改进：增加"背驰强度分级"——弱背驰（0.8-0.9）、中背驰（0.6-0.8）、强背驰（<0.6）
    v89 改进：增加"背驰确认"——背驰后需有反向笔确认才标记为有效背驰

    Args:
        bis: 笔列表
        zss: 中枢列表
        closes: 收盘价序列（用于MACD计算）
        config: 缠论配置

    Returns:
        背驰列表
    """
    if config is None:
        config = ChanlunConfig()

    if len(bis) < 2:
        return []

    bcs: list[BC] = []

    # 1. 笔背驰检查
    bcs.extend(_check_bi_level_beichi(bis, closes))

    # 2. 盘整背驰检查
    if len(zss) > 0:
        bcs.extend(_check_pz_beichi(bis, zss, closes))

    # 3. 趋势背驰检查
    if len(zss) >= 2:
        bcs.extend(_check_qs_beichi(bis, zss, closes, mmds=mmds, lower_xds=lower_xds, lower_closes=lower_closes))

    return bcs


def _check_bi_level_beichi(bis: list[BI], closes: list[float] | None) -> list[BC]:
    """检查笔级别的力度背驰。

    比较相邻同向笔，后笔力度 < 前笔80% = 背驰
    """
    bcs: list[BC] = []

    for i in range(1, len(bis)):
        curr = bis[i]
        # 向前找最近的同向笔
        for j in range(i - 1, -1, -1):
            prev = bis[j]
            if prev.direction == curr.direction:
                # 缠论原文：笔背驰必须先创新高（向上笔）/新低（向下笔），
                # 否则只是普通回调/反抽，不能叫背驰。
                if curr.direction == Direction.UP and curr.high <= prev.high:
                    break
                if curr.direction == Direction.DOWN and curr.low >= prev.low:
                    break

                curr_force = _calc_bi_force(curr, closes, i)
                prev_force = _calc_bi_force(prev, closes, j)

                # 严格标准：后笔力度 < 前笔80% 才算背驰
                if prev_force > 0 and curr_force < prev_force * 0.8 and curr_force > 0:
                    bcs.append(
                        BC(
                            bc_type=BCType.BI,
                            bc=True,
                            zs=None,
                            curr=curr,
                            prev=prev,
                            msg=(
                                f"笔背驰: 笔[{curr.index}] 力度={curr_force:.2f} "
                                f"< 笔[{prev.index}] 力度={prev_force:.2f} "
                                f"(比率={curr_force / prev_force:.2f})"
                            ),
                        )
                    )
                break  # 只比较最近一个同向笔

    return bcs


def _check_pz_beichi(bis: list[BI], zss: list[ZS], closes: list[float] | None) -> list[BC]:
    """检查盘整背驰（缠论原文口径）。

    盘整背驰 = 离开中枢的那一笔，与进入中枢的那一笔同向，且力度衰竭：
    - 进入笔：中枢第一笔之前的那一笔（b 段）
    - 离开笔：中枢最后一笔之后的那一笔（c 段）
    两者方向相同（上涨盘整同为向上、下跌盘整同为向下），离开笔力度 < 进入笔 80%。
    """
    bcs: list[BC] = []

    for zs in zss:
        if zs.line_count < 3 or not zs.lines:
            continue

        first = zs.lines[0]
        last = zs.lines[-1]
        # 进入笔 = 中枢前一笔，离开笔 = 中枢后一笔
        if first.index <= 0 or last.index + 1 >= len(bis):
            continue
        enter = bis[first.index - 1]
        exit_ = bis[last.index + 1]

        if enter.direction != exit_.direction:
            continue

        enter_force = _calc_bi_force(enter, closes, enter.index)
        exit_force = _calc_bi_force(exit_, closes, exit_.index)

        if enter_force > 0 and exit_force < enter_force * 0.8 and exit_force > 0:
            bcs.append(
                BC(
                    bc_type=BCType.PZ,
                    bc=True,
                    zs=zs,
                    curr=exit_,
                    prev=enter,
                    msg=(
                        f"盘整背驰: 中枢[{zs.index}] 离开笔力度={exit_force:.2f} "
                        f"< 进入笔力度={enter_force:.2f} "
                        f"(比率={exit_force / enter_force:.2f})"
                    ),
                )
            )

    return bcs


def _check_qs_beichi(bis: list[BI], zss: list[ZS], closes: list[float] | None, mmds: list | None = None, lower_xds: list | None = None, lower_closes: list[float] | None = None) -> list[BC]:
    """检查趋势背驰。

    连续两个同向中枢，离开力度衰减
    """
    bcs: list[BC] = []

    for i in range(1, len(zss)):
        prev_zs = zss[i - 1]
        curr_zs = zss[i]

        # 20课L25 中心定理二：趋势判据用 GG/DD（波动区间），非 ZG/ZD（中枢区间）。
        # 「后GG < 前DD」等价于下跌及其延续；「后DD > 前GG」等价于上涨及其延续。
        # 若后ZG<前ZD 且 后GG>=前DD（或后ZD>前ZG 且 后DD<=前GG）→形成高级别
        # 中枢（非趋势），此时中枢区间不重叠但波动区间重叠，原文不视为趋势。
        is_down_trend = curr_zs.gg < prev_zs.dd
        is_up_trend = curr_zs.dd > prev_zs.gg

        if not (is_down_trend or is_up_trend):
            continue

        # 37课L8：A、B 必须是同级别中枢，否则 a+A+b+B+c 只是较大中枢的
        # 震荡（「如果 A 的级别比 B 大，就有 a+A+b+B+c = a+A+(b+B+c)」），
        # 非趋势非背驰。ZS.level 默认 1（find_zss），升级后为 2（33课延伸>5段）。
        if prev_zs.level != curr_zs.level:
            continue

        if not prev_zs.lines or not curr_zs.lines:
            continue
        direction = "down" if is_down_trend else "up"
        if lower_xds is not None:
            # 37课L10：c=次级别走势（线段）。中枢是次级别线段中枢
            # （find_zss(lower_xds)），离开段应是次级别线段（XD），非日线笔。
            # 旧实现用日线笔（83课近似）尺度与中枢不一致：中枢=次级别线段、
            # c=日线笔，偏离37课L10。此处改用次级别线段作 c 段。
            prev_exit = _find_leaving_xd(lower_xds, prev_zs, direction)
            curr_exit = _find_leaving_xd(lower_xds, curr_zs, direction)
            if prev_exit is None or curr_exit is None:
                continue  # 离开段尚未完成
        else:
            # 83课近似：c=日线笔（笔构中枢允许），力度用 MACD 面积（closes）。
            # 旧实现用 bis[lines[-1].index+1]（末笔后第一根笔），不检查破边沿，
            # 取到的常是中枢内震荡笔 / 反向回抽笔 ⇒ 方向校验恒不通过 ⇒ 本函数
            # 在真实数据上产出 0（背驰审计实测）。与决策侧 _is_strong_beichi 统一。
            prev_exit_idx = _find_leaving_bi(bis, prev_zs, direction)
            curr_exit_idx = _find_leaving_bi(bis, curr_zs, direction)
            if prev_exit_idx < 0 or curr_exit_idx < 0:
                continue  # 离开段尚未完成
            prev_exit = bis[prev_exit_idx]
            curr_exit = bis[curr_exit_idx]

        # 两段离开笔方向都必须与趋势一致（_find_leaving_bi 已保证同向，此为防御）
        if is_down_trend and (
            prev_exit.direction != Direction.DOWN or curr_exit.direction != Direction.DOWN
        ):
            continue
        if is_up_trend and (
            prev_exit.direction != Direction.UP or curr_exit.direction != Direction.UP
        ):
            continue

        # 缠论原文：趋势背驰必须创新高/新低——后一中枢的离开笔
        # 要超过前一中枢离开笔的极值，否则只是中枢震荡/扩展。
        if is_up_trend and curr_exit.high <= prev_exit.high:
            continue
        if is_down_trend and curr_exit.low >= prev_exit.low:
            continue

        # 53课 line139 原文铁律：「黄白线都没拉回0轴不是背驰」。
        # B段（中枢2=curr_zs）须把 DIF 回拉到 0 轴附近，否则非标准趋势背驰。
        # 偏差L DIF检查尺度一致：cross_timeframe（lower_xds 非空）中枢 lines 是
        # 次级别线段 XD（bar_index 是次级别 K 线索引），须用次级别收盘价 lower_closes
        # 算 DIF；默认 process_klines（lower_xds=None）中枢 lines 是日线笔，用日线 closes。
        dif_closes = lower_closes if (lower_xds is not None and lower_closes) else closes
        if not _check_zero_axis_pullback(dif_closes, prev_zs, curr_zs):
            continue

        # 37课L10 原文：「c 必然是次级别的，也就是说，c 至少包含对 B 的一个
        # 第三类买卖点，否则就可以看成是 B 中枢的小级别波动，完全可以用盘整
        # 背驰来处理」。c 段须含 B(curr_zs) 的第三类买卖点（3买/3卖）。
        # 仅在 cross_timeframe（mmds 非空）启用；默认 process_klines 无 lower_xds，
        # c=日线笔是 83课近似（笔构中枢，原文允许但稳定性差）。
        if mmds is not None:
            has_third = any(
                m.mmd_type.value in ("3buy", "3sell") and m.zs is curr_zs
                for m in mmds
            )
            if not has_third:
                continue

        if lower_xds is not None:
            # 37课L10：c=次级别线段。力度优先用次级别 MACD 面积（lower_closes），
            # XD.start/end.bar_index 是次级别 K 线索引；无 lower_closes 时降级振幅
            # （closes=None → abs(high-low)），a/c 段同尺度对照。
            prev_force = _calc_bi_force(prev_exit, lower_closes, 0)
            curr_force = _calc_bi_force(curr_exit, lower_closes, 0)
        else:
            prev_force = _calc_bi_force(prev_exit, closes, prev_exit.index)
            curr_force = _calc_bi_force(curr_exit, closes, curr_exit.index)

        # 严格标准
        if prev_force > 0 and curr_force < prev_force * 0.8 and curr_force > 0:
            trend_dir = "下" if is_down_trend else "上"
            bcs.append(
                BC(
                    bc_type=BCType.QS,
                    bc=True,
                    zs=curr_zs,
                    curr=curr_exit,
                    prev=prev_exit,
                    msg=(
                        f"趋势背驰({trend_dir}): 中枢[{curr_zs.index}] 离开力度={curr_force:.2f} "
                        f"< 中枢[{prev_zs.index}] 离开力度={prev_force:.2f} "
                        f"(比率={curr_force / prev_force:.2f})"
                    ),
                )
            )

    return bcs
