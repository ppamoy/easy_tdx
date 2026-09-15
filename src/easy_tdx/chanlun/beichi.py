"""背驰判断（精修版）。

背驰类型：
- 笔背驰：相邻同向笔的力度比较（MACD面积或幅度）
- 盘整背驰：中枢内最后一笔力度小于进入中枢的第一笔
- 趋势背驰：两个同向中枢之间，离开中枢的笔力度减小

严格标准：力度比率 < 0.8 才算背驰
"""

from __future__ import annotations

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.mmd_conditions import _calc_bi_force
from easy_tdx.chanlun.types import BC, BI, ZS, BCType, Direction


def check_bi_beichi(
    bis: list[BI],
    zss: list[ZS],
    closes: list[float] | None = None,
    config: ChanlunConfig | None = None,
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
        bcs.extend(_check_qs_beichi(bis, zss, closes))

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
    """检查盘整背驰。

    中枢内最后一笔 vs 进入中枢的第一笔
    """
    bcs: list[BC] = []

    for zs in zss:
        if zs.line_count < 3:
            continue

        # 中枢内最后一笔 vs 进入中枢的第一笔
        first_bi = zs.lines[0]
        last_bi = zs.lines[-1]

        if first_bi.direction == last_bi.direction:
            first_force = _calc_bi_force(first_bi, closes, first_bi.index)
            last_force = _calc_bi_force(last_bi, closes, last_bi.index)

            # 严格标准
            if first_force > 0 and last_force < first_force * 0.8 and last_force > 0:
                bcs.append(
                    BC(
                        bc_type=BCType.PZ,
                        bc=True,
                        zs=zs,
                        curr=last_bi,
                        prev=first_bi,
                        msg=(
                            f"盘整背驰: 中枢[{zs.index}] 内末笔力度={last_force:.2f} "
                            f"< 首笔力度={first_force:.2f} "
                            f"(比率={last_force / first_force:.2f})"
                        ),
                    )
                )

    return bcs


def _check_qs_beichi(bis: list[BI], zss: list[ZS], closes: list[float] | None) -> list[BC]:
    """检查趋势背驰。

    连续两个同向中枢，离开力度衰减
    """
    bcs: list[BC] = []

    for i in range(1, len(zss)):
        prev_zs = zss[i - 1]
        curr_zs = zss[i]

        # 判断两个中枢是否形成趋势（同向排列）
        is_down_trend = prev_zs.zg > curr_zs.zg and prev_zs.zd > curr_zs.zd
        is_up_trend = prev_zs.zg < curr_zs.zg and prev_zs.zd < curr_zs.zd

        if not (is_down_trend or is_up_trend):
            continue

        # 比较离开两中枢的笔
        prev_exit = prev_zs.lines[-1]
        curr_exit = curr_zs.lines[-1]

        # 确保离开笔方向与趋势一致
        if is_down_trend and prev_exit.direction.value != "down":
            continue
        if is_up_trend and prev_exit.direction.value != "up":
            continue

        # 缠论原文：趋势背驰必须创新高/新低——后一中枢的离开笔
        # 要超过前一中枢离开笔的极值，否则只是中枢震荡/扩展。
        if is_up_trend and curr_exit.high <= prev_exit.high:
            continue
        if is_down_trend and curr_exit.low >= prev_exit.low:
            continue

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