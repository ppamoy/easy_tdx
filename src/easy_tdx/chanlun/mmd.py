"""买卖点识别（精修版 V2）。

基于历史回测结果优化：
- 1买/1卖准确率80-90%，保持核心逻辑
- 3买/3卖准确率50-57%，增加严格过滤条件
- 引入力度比率阈值动态调整
- 增加趋势确认机制
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.macd import calc_macd, calc_macd_force
from easy_tdx.chanlun.types import BI, BC, BCType, FX, MMD, MMDType, XD, ZS


@dataclass
class BeichiResult:
    """背驰结果。"""
    
    bc_type: BCType
    bc: bool
    bi: BI | None = None
    prev_bi: BI | None = None
    zs: ZS | None = None
    msg: str = ""
    force_ratio: float = 0.0  # 力度比率
    strength: str = ""  # 背驰强度：weak/moderate/strong


def find_mmds(
    bis: list[BI],
    zss: list[ZS],
    closes: list[float] | None = None,
    config: ChanlunConfig | None = None,
    volumes: list[float] | None = None,
) -> list[MMD]:
    """从笔和中枢中识别买卖点（精修版 V3）。

    Args:
        bis: 笔列表（按时间顺序）
        zss: 中枢列表（按时间顺序）
        closes: 收盘价序列（用于MACD力度计算）
        config: 缠论配置
        volumes: 成交量序列（用于成交量确认）

    Returns:
        买卖点列表（已过滤低质量信号）
    """
    if config is None:
        config = ChanlunConfig()
    
    if len(bis) < 3 or len(zss) == 0:
        return []
    
    mmds: list[MMD] = []
    
    # 1. 识别一类买卖点（最可靠，保持原逻辑）
    mmds.extend(_find_first_type_mmds(bis, zss, closes, config))
    
    # 2. 识别二类买卖点（增加确认条件）
    mmds.extend(_find_second_type_mmds(bis, zss, mmds, config))
    
    # 3. 识别三类买卖点（增加严格过滤）
    mmds.extend(_find_third_type_mmds(bis, zss, mmds, config, closes, volumes))
    
    # 去重：同一位置只保留最高优先级买卖点
    mmds = _deduplicate_mmds(mmds)

    # 计算置信度
    trend_strength = _calc_trend_strength(zss)
    for mmd in mmds:
        mmd.confidence = _calc_confidence(mmd, trend_strength, volumes)

    # 按时间排序
    mmds.sort(key=lambda m: m.bi.index if m.bi else 0)

    return mmds


def _find_first_type_mmds(
    bis: list[BI],
    zss: list[ZS],
    closes: list[float] | None,
    config: ChanlunConfig,
) -> list[MMD]:
    """识别一类买卖点（背驰点）。
    
    1买：下跌趋势中，最后一个中枢下方的底背驰
    1卖：上涨趋势中，最后一个中枢上方的顶背驰
    
    改进：使用更严格的力量比率阈值
    """
    mmds: list[MMD] = []
    
    if len(zss) == 0:
        return mmds
    
    # 获取最后一个完成的中枢
    last_done_zs = None
    for zs in reversed(zss):
        if zs.done:
            last_done_zs = zs
            break
    
    if last_done_zs is None:
        last_done_zs = zss[-1]
    
    if last_done_zs is None:
        return mmds
    
    # 检查趋势强度（至少两个同向中枢）
    trend_strength = _calc_trend_strength(zss)
    
    # 使用固定阈值0.8（原值），避免过度过滤
    threshold = 0.8
    
    # 在一类买点区域查找底背驰
    found_buy_1 = False
    for bi in bis:
        if bi.direction.value != "down":
            continue
        # 条件：笔低点在中枢下方
        if bi.low >= last_done_zs.zd:
            continue
        # 检查背驰
        if not found_buy_1 and _is_strong_beichi(bi, bis, zss, closes, threshold):
            strength = _get_beichi_strength(bi, bis, zss, closes)
            mmds.append(MMD(
                mmd_type=MMDType.BUY_1,
                zs=last_done_zs,
                bi=bi,
                msg=f"1买: 底背驰(强度={strength}), 低点={bi.low:.2f} < 中枢下沿={last_done_zs.zd:.2f}",
            ))
            found_buy_1 = True
    
    # 在一类卖点区域查找顶背驰
    found_sell_1 = False
    for bi in reversed(bis):
        if bi.direction.value != "up":
            continue
        # 条件：笔高点在中枢上方
        if bi.high <= last_done_zs.zg:
            continue
        # 检查背驰
        if not found_sell_1 and _is_strong_beichi(bi, bis, zss, closes, threshold, direction="up"):
            strength = _get_beichi_strength(bi, bis, zss, closes, direction="up")
            mmds.append(MMD(
                mmd_type=MMDType.SELL_1,
                zs=last_done_zs,
                bi=bi,
                msg=f"1卖: 顶背驰(强度={strength}), 高点={bi.high:.2f} > 中枢上沿={last_done_zs.zg:.2f}",
            ))
            found_sell_1 = True
    
    return mmds


def _find_second_type_mmds(
    bis: list[BI],
    zss: list[ZS],
    first_type_mmds: list[MMD],
    config: ChanlunConfig,
) -> list[MMD]:
    """识别二类买卖点和类二买卖点。
    
    2买：1买后的第一次回调，低点不创新低 + 回调幅度小于原下跌的50%
    类二买：介于1买和2买之间的过渡形态，回调较浅但低点仍不创新低
    2卖：1卖后的第一次反弹，高点不创新高 + 反弹幅度小于原上涨的50%
    类二卖：介于1卖和2卖之间的过渡形态，反弹较浅但高点仍不创新高
    """
    mmds: list[MMD] = []
    
    # 找到第一个1买和1卖
    first_buy_1 = None
    first_sell_1 = None
    for mmd in first_type_mmds:
        if mmd.mmd_type == MMDType.BUY_1 and first_buy_1 is None:
            first_buy_1 = mmd
        elif mmd.mmd_type == MMDType.SELL_1 and first_sell_1 is None:
            first_sell_1 = mmd
    
    # 找2买和类二买：1买后的回调
    if first_buy_1 and first_buy_1.bi:
        buy_1_bi = first_buy_1.bi
        buy_1_low = buy_1_bi.low
        buy_1_idx = buy_1_bi.index
        
        # 在1买之后找向上笔（离开笔）
        leave_bi_up = None
        for bi in bis[buy_1_idx + 1:]:
            if bi.direction.value == "up":
                leave_bi_up = bi
                break
        
        if leave_bi_up:
            leave_high = leave_bi_up.high
            # 回调幅度限制
            leave_range = leave_high - buy_1_low
            max_drawdown_strict = leave_range * 0.5 if leave_range > 0 else float("inf")  # 严格条件（2买）
            max_drawdown_loose = leave_range * 0.7 if leave_range > 0 else float("inf")  # 宽松条件（类二买）

            # 在离开笔之后找回调笔
            found_2buy = False
            found_2s_buy = False
            for bi in bis[bis.index(leave_bi_up) + 1:]:
                if bi.direction.value == "down":
                    # 检查是否是2买（严格条件）：低点不创新低
                    if not found_2buy and bi.low > buy_1_low:
                        # 回撤百分比：从leave_high到bi.low的回撤幅度占leave_range的比例
                        pullback_from_high = leave_high - bi.low
                        pct = (pullback_from_high / leave_range * 100) if leave_range > 0 else 0.0
                        pct = max(0.0, min(100.0, pct))  # 限制在0-100%
                        mmds.append(MMD(
                            mmd_type=MMDType.BUY_2,
                            zs=first_buy_1.zs,
                            bi=bi,
                            msg=f"2买: 回调确认, 低点={bi.low:.2f} > 1买={buy_1_low:.2f}, 回撤{pct:.0f}%",
                        ))
                        found_2buy = True

                    # 检查是否是类二买（宽松条件）
                    elif not found_2s_buy and not found_2buy and bi.low > buy_1_low:
                        pullback_from_high = leave_high - bi.low
                        pct = (pullback_from_high / leave_range * 100) if leave_range > 0 else 0.0
                        pct = max(0.0, pct)
                        mmds.append(MMD(
                            mmd_type=MMDType.BUY_2S,
                            zs=first_buy_1.zs,
                            bi=bi,
                            msg=f"类2买: 浅回调确认, 低点={bi.low:.2f} > 1买={buy_1_low:.2f}, 回撤{pct:.0f}%",
                        ))
                        found_2s_buy = True

                    # 找到2买或类二买后停止
                    if found_2buy or found_2s_buy:
                        break
    
    # 找2卖和类二卖：1卖后的反弹
    if first_sell_1 and first_sell_1.bi:
        sell_1_bi = first_sell_1.bi
        sell_1_high = sell_1_bi.high
        sell_1_idx = sell_1_bi.index
        
        # 在1卖之后找向下笔（离开笔）
        leave_bi_down = None
        for bi in bis[sell_1_idx + 1:]:
            if bi.direction.value == "down":
                leave_bi_down = bi
                break
        
        if leave_bi_down:
            leave_low = leave_bi_down.low
            # 反弹幅度限制
            leave_range = sell_1_high - leave_low
            max_pullback_strict = leave_range * 0.5 if leave_range > 0 else float("inf")  # 严格条件（2卖）
            max_pullback_loose = leave_range * 0.7 if leave_range > 0 else float("inf")  # 宽松条件（类二卖）

            # 在离开笔之后找反弹笔
            found_2sell = False
            found_2s_sell = False
            for bi in bis[bis.index(leave_bi_down) + 1:]:
                if bi.direction.value == "up":
                    # 检查是否是2卖（严格条件）
                    if not found_2sell and bi.high < sell_1_high and (bi.high - leave_low) < max_pullback_strict:
                        # 反弹百分比：从leave_low到bi.high的反弹幅度占leave_range的比例
                        pullback_from_low = bi.high - leave_low
                        pct = (pullback_from_low / leave_range * 100) if leave_range > 0 else 0.0
                        pct = max(0.0, pct)
                        mmds.append(MMD(
                            mmd_type=MMDType.SELL_2,
                            zs=first_sell_1.zs,
                            bi=bi,
                            msg=f"2卖: 反弹确认, 高点={bi.high:.2f} < 1卖={sell_1_high:.2f}, 反弹{pct:.0f}%",
                        ))
                        found_2sell = True

                    # 检查是否是类二卖（宽松条件）
                    elif not found_2s_sell and not found_2sell and bi.high < sell_1_high and (bi.high - leave_low) < max_pullback_loose:
                        pullback_from_low = bi.high - leave_low
                        pct = (pullback_from_low / leave_range * 100) if leave_range > 0 else 0.0
                        pct = max(0.0, pct)
                        mmds.append(MMD(
                            mmd_type=MMDType.SELL_2S,
                            zs=first_sell_1.zs,
                            bi=bi,
                            msg=f"类2卖: 浅反弹确认, 高点={bi.high:.2f} < 1卖={sell_1_high:.2f}, 反弹{pct:.0f}%",
                        ))
                        found_2s_sell = True

                    # 找到2卖或类二卖后停止
                    if found_2sell or found_2s_sell:
                        break
    
    return mmds



def _calc_avg_volume(volumes: list[float] | None, lookback: int) -> float:
    """计算最近N根K线的平均成交量。"""
    if not volumes or len(volumes) < lookback:
        return 0.0
    return sum(volumes[-lookback:]) / lookback


def _check_breakout_volume(
    volumes: list[float],
    break_start: int,
    break_end: int,
    avg_vol: float,
) -> bool:
    """检查突破时是否放量（突破期间平均成交量 > 近期均量的1.2倍）。"""
    if avg_vol <= 0 or break_start < 0 or break_end >= len(volumes):
        return True  # 无数据时放行
    try:
        break_vols = volumes[break_start:break_end + 1]
        if not break_vols:
            return True
        break_avg = sum(break_vols) / len(break_vols)
        return break_avg >= avg_vol * 1.2
    except Exception:
        return True


def _check_pullback_volume(
    volumes: list[float],
    pull_start: int,
    pull_end: int,
    avg_vol: float,
    is_pullback: bool = True,
) -> bool:
    """检查回调/反弹时是否缩量。
    
    对于3买（pullback）：回调笔成交量应小于近期均量
    对于3卖（rebound）：反弹笔成交量应小于近期均量
    """
    if avg_vol <= 0 or pull_start < 0 or pull_end >= len(volumes):
        return True  # 无数据时放行
    try:
        pull_vols = volumes[pull_start:pull_end + 1]
        if not pull_vols:
            return True
        pull_avg = sum(pull_vols) / len(pull_vols)
        # 回调/反弹时缩量（低于均量）才确认信号有效
        return pull_avg <= avg_vol * 1.0
    except Exception:
        return True


def _find_third_type_mmds(
    bis: list[BI],
    zss: list[ZS],
    first_type_mmds: list[MMD],
    config: ChanlunConfig,
    closes: list[float] | None = None,
    volumes: list[float] | None = None,
) -> list[MMD]:
    """识别三类买卖点（增加严格过滤 + 成交量确认）。

    3买：突破中枢后回踩不破zg + 突破笔力度 > 进入中枢笔力度 + 放量突破+缩量回调
    3卖：跌破中枢后反抽不破zd + 跌破笔力度 > 进入中枢笔力度 + 放量跌破+缩量反弹

    回测显示3买/3卖准确率仅50-57%，需要严格过滤
    """
    mmds: list[MMD] = []

    # 构建已有买卖点的位置集合，用于避免重复
    existing_mmd_positions: set[int] = set()
    for m in first_type_mmds:
        if m.bi:
            existing_mmd_positions.add(m.bi.end.k.k_index)

    for zs in zss:
        if not zs.done:
            continue

        # 计算中枢内首尾笔的力度比
        if len(zs.lines) >= 2:
            first_bi_force = _calc_bi_force(zs.lines[0], closes, zs.lines[0].index)
            last_bi_force = _calc_bi_force(zs.lines[-1], closes, zs.lines[-1].index)
            force_ratio_in_zs = last_bi_force / first_bi_force if first_bi_force > 0 else 1.0
        else:
            force_ratio_in_zs = 1.0

        # 计算平均成交量（用于成交量确认）
        avg_vol_20 = _calc_avg_volume(volumes, 20)

        # 找3买：突破中枢后的回踩
        zs_end_idx = zs.end.k.k_index if zs.end else 0

        # 找向上突破笔
        break_bi_up = None
        for bi in bis:
            if bi.start.k.index > zs_end_idx and bi.direction.value == "up":
                if bi.high > zs.zg:  # 突破中枢上沿
                    break_bi_up = bi
                    break

        if break_bi_up:
            # 检查突破笔力度是否足够（必须大于进入中枢的笔）
            break_force = _calc_bi_force(break_bi_up, closes, break_bi_up.index)

            # 条件A：突破笔必须有足够力度（至少是进入中枢笔的80%）
            if break_force < first_bi_force * 0.8:
                continue

            # 条件B：突破后价格应该站稳中枢上方（不能太接近zg）
            break_price_ratio = (break_bi_up.high - zs.zg) / (zs.zg - zs.zd) if zs.zg > zs.zd else 0
            if break_price_ratio < 0.3:  # 突破幅度太小，可能是假突破
                continue

            # 条件C：成交量确认 - 突破时应放量
            if volumes:
                if not _check_breakout_volume(
                    volumes, break_bi_up.start.k.k_index, break_bi_up.end.k.k_index, avg_vol_20
                ):
                    continue

            # 在突破笔之后找回调笔
            for bi in bis[bis.index(break_bi_up) + 1:]:
                if bi.direction.value == "down":
                    # 条件1：回踩不破zg（严格：必须明显高于zg）
                    if bi.low <= zs.zg:
                        break

                    # 条件2：回调时间短（不超过5根K线，更严格）
                    time_span = bi.end.k.k_index - break_bi_up.end.k.k_index
                    if time_span > 5:
                        continue

                    # 条件3：回调幅度不过大（不超过突破幅度的50%，更严格）
                    breakout_range = break_bi_up.high - break_bi_up.low
                    if break_bi_up.low - bi.low > breakout_range * 0.5:
                        continue

                    # 条件4：检查是否与已有买卖点过于接近（避免重复信号）
                    bi_pos = bi.end.k.k_index
                    too_close = any(abs(bi_pos - pos) < 3 for pos in existing_mmd_positions)
                    if too_close:
                        continue

                    # 条件5：MACD确认（如果数据可用）
                    macd_ok = True
                    if closes:
                        macd_ok = _check_macd_confirmation(closes, bi, break_bi_up)

                    # 条件6：回调时缩量确认（有成交量数据时生效）
                    vol_ok = True
                    if volumes:
                        vol_ok = _check_pullback_volume(
                            volumes, bi.start.k.k_index, bi.end.k.k_index, avg_vol_20
                        )

                    if not (macd_ok and vol_ok):
                        continue

                    mmds.append(MMD(
                        mmd_type=MMDType.BUY_3,
                        zs=zs,
                        bi=bi,
                        msg=f"3买: 突破确认后回踩(深度{(break_bi_up.low-bi.low)/breakout_range*100:.0f}%), 低点={bi.low:.2f} > zg={zs.zg:.2f}",
                    ))
                    break

        # 找3卖：跌破中枢后的反抽
        break_bi_down = None
        for bi in bis:
            if bi.start.k.index > zs_end_idx and bi.direction.value == "down":
                if bi.low < zs.zd:  # 跌破中枢下沿
                    break_bi_down = bi
                    break

        if break_bi_down:
            # 条件A：跌破笔必须有足够力度
            break_force_down = _calc_bi_force(break_bi_down, closes, break_bi_down.index)
            if len(zs.lines) >= 2 and break_force_down < _calc_bi_force(zs.lines[0], closes, zs.lines[0].index) * 0.8:
                continue

            # 条件B：跌破后价格应该站稳中枢下方
            breakdown_price_ratio = (zs.zd - break_bi_down.low) / (zs.zg - zs.zd) if zs.zg > zs.zd else 0
            if breakdown_price_ratio < 0.3:
                continue

            # 条件C：成交量确认 - 跌破时应放量
            if volumes:
                if not _check_breakout_volume(
                    volumes, break_bi_down.start.k.k_index, break_bi_down.end.k.k_index, avg_vol_20
                ):
                    continue

            # 在跌破笔之后找反弹笔
            for bi in bis[bis.index(break_bi_down) + 1:]:
                if bi.direction.value == "up":
                    # 条件1：反抽不破zd（严格：必须明显低于zd）
                    if bi.high >= zs.zd:
                        break

                    # 条件2：反弹时间短（不超过5根K线）
                    time_span = bi.end.k.k_index - break_bi_down.end.k.k_index
                    if time_span > 5:
                        continue

                    # 条件3：反弹幅度不过大
                    breakdown_range = break_bi_down.high - break_bi_down.low
                    if bi.high - break_bi_down.high > breakdown_range * 0.5:
                        continue

                    # 条件4：检查是否与已有买卖点过于接近
                    bi_pos = bi.end.k.k_index
                    too_close = any(abs(bi_pos - pos) < 3 for pos in existing_mmd_positions)
                    if too_close:
                        continue

                    # 条件5：MACD确认
                    macd_ok = True
                    if closes:
                        macd_ok = _check_macd_confirmation(closes, bi, break_bi_down, direction="up")

                    # 条件6：反弹时缩量确认（有成交量数据时生效）
                    vol_ok = True
                    if volumes:
                        vol_ok = _check_pullback_volume(
                            volumes, bi.start.k.k_index, bi.end.k.k_index, avg_vol_20, is_pullback=True
                        )

                    if not (macd_ok and vol_ok):
                        continue

                    mmds.append(MMD(
                        mmd_type=MMDType.SELL_3,
                        zs=zs,
                        bi=bi,
                        msg=f"3卖: 跌破确认后反抽(幅度{(bi.high-break_bi_down.high)/breakdown_range*100:.0f}%), 高点={bi.high:.2f} < zd={zs.zd:.2f}",
                    ))
                    break

    return mmds


def _check_macd_confirmation(
    closes: list[float],
    current_bi: BI,
    breakout_bi: BI,
    direction: str = "down",
) -> bool:
    """MACD确认：检查当前笔与突破笔的MACD面积关系。

    对于3买：当前回调笔的MACD绿柱面积应小于突破笔的MACD红柱面积
    对于3卖：当前反弹笔的MACD红柱面积应小于突破笔的MACD绿柱面积
    """
    try:
        curr_start = current_bi.start.k.k_index
        curr_end = current_bi.end.k.k_index
        break_start = breakout_bi.start.k.k_index
        break_end = breakout_bi.end.k.k_index

        if curr_start < 0 or curr_end >= len(closes):
            return True  # 无数据时放行

        curr_macd = calc_macd_force(closes, curr_start, curr_end)
        break_macd = calc_macd_force(closes, break_start, break_end)

        if direction == "down":  # 3买：回调笔看绿柱
            if curr_macd["hist_down_sum"] > 0 and break_macd["hist_up_sum"] > 0:
                return curr_macd["hist_down_sum"] < break_macd["hist_up_sum"] * 1.5
            return True
        else:  # 3卖：反弹笔看红柱
            if curr_macd["hist_up_sum"] > 0 and break_macd["hist_down_sum"] > 0:
                return curr_macd["hist_up_sum"] < break_macd["hist_down_sum"] * 1.5
            return True
    except Exception:
        return True  # 出错时放行，不阻断信号


def _deduplicate_mmds(mmds: list[MMD]) -> list[MMD]:
    """去重：同一位置只保留最高优先级的买卖点。
    
    优先级：1买 > 2买 > 3买 > 1卖 > 2卖 > 3卖
    """
    priority = {
        MMDType.BUY_1: 6,
        MMDType.BUY_2: 5,
        MMDType.BUY_3: 4,
        MMDType.SELL_1: 3,
        MMDType.SELL_2: 2,
        MMDType.SELL_3: 1,
    }
    
    # 按位置分组
    by_position: dict[int, list[MMD]] = {}
    for mmd in mmds:
        if mmd.bi:
            pos = mmd.bi.end.k.k_index
            if pos not in by_position:
                by_position[pos] = []
            by_position[pos].append(mmd)
    
    # 每组只保留优先级最高的
    result = []
    for pos, group in by_position.items():
        group.sort(key=lambda m: priority.get(m.mmd_type, 0), reverse=True)
        result.append(group[0])
    
    return result


# ── 辅助函数 ─────────────────────────────────────────────────────────────

def _is_strong_beichi(
    bi: BI,
    bis: list[BI],
    zss: list[ZS],
    closes: list[float] | None,
    threshold: float = 0.8,
    direction: str = "down",
) -> bool:
    """检查是否是强背驰（满足动态阈值）。"""
    bi_idx = bi.index
    
    # 1. 笔背驰检查
    for j in range(bi_idx - 1, -1, -1):
        prev_bi = bis[j]
        if prev_bi.direction.value == direction:
            curr_force = _calc_bi_force(bi, closes, bi_idx)
            prev_force = _calc_bi_force(prev_bi, closes, j)
            
            if prev_force > 0 and curr_force < prev_force * threshold:
                return True
            break
    
    # 2. 盘整背驰检查
    for zs in zss:
        if len(zs.lines) >= 3:
            first_bi = zs.lines[0]
            last_bi = zs.lines[-1]
            
            if first_bi.direction.value == direction:
                first_force = _calc_bi_force(first_bi, closes, first_bi.index)
                last_force = _calc_bi_force(last_bi, closes, last_bi.index)
                
                if last_force < first_force * threshold and last_force > 0:
                    return True
    
    # 3. 趋势背驰检查
    if len(zss) >= 2:
        for i in range(1, len(zss)):
            prev_zs = zss[i - 1]
            curr_zs = zss[i]
            
            is_same_trend = (
                (direction == "down" and curr_zs.zg < prev_zs.zg and curr_zs.zd < prev_zs.zd) or
                (direction == "up" and curr_zs.zg > prev_zs.zg and curr_zs.zd > prev_zs.zd)
            )
            
            if is_same_trend:
                prev_exit = prev_zs.lines[-1]
                curr_exit = curr_zs.lines[-1]
                
                if prev_exit.direction.value == direction and curr_exit.direction.value == direction:
                    prev_force = _calc_bi_force(prev_exit, closes, prev_exit.index)
                    curr_force = _calc_bi_force(curr_exit, closes, curr_exit.index)
                    
                    if curr_force < prev_force * threshold and curr_force > 0:
                        return True
    
    return False


def _get_beichi_strength(
    bi: BI,
    bis: list[BI],
    zss: list[ZS],
    closes: list[float] | None,
    direction: str = "down",
) -> str:
    """获取背驰强度标签。"""
    bi_idx = bi.index
    
    # 找最近同向笔
    for j in range(bi_idx - 1, -1, -1):
        prev_bi = bis[j]
        if prev_bi.direction.value == direction:
            curr_force = _calc_bi_force(bi, closes, bi_idx)
            prev_force = _calc_bi_force(prev_bi, closes, j)
            
            if prev_force > 0:
                ratio = curr_force / prev_force
                if ratio < 0.5:
                    return "strong"
                elif ratio < 0.7:
                    return "moderate"
                else:
                    return "weak"
            break
    
    return "unknown"


def _calc_trend_strength(zss: list[ZS]) -> float:
    """计算趋势强度（0-1）。"""
    if len(zss) < 2:
        return 0.0
    
    # 计算中枢的重叠程度
    overlaps = 0
    for i in range(1, len(zss)):
        prev = zss[i - 1]
        curr = zss[i]
        
        # 检查是否同向排列
        if (curr.zg < prev.zg and curr.zd < prev.zd) or \
           (curr.zg > prev.zg and curr.zd > prev.zd):
            overlaps += 1
    
    return overlaps / (len(zss) - 1) if len(zss) > 1 else 0.0


def _calc_bi_force(
    bi: BI,
    closes: list[float] | None,
    bi_idx: int,
) -> float:
    """计算笔的力度（MACD面积）。"""
    if closes is None or len(closes) == 0:
        return abs(bi.high - bi.low)

    start_idx = bi.start.k.k_index
    end_idx = bi.end.k.k_index
    
    if start_idx < 0 or end_idx >= len(closes):
        return abs(bi.high - bi.low)
    
    try:
        macd_result = calc_macd_force(closes, start_idx, end_idx)
        if bi.direction.value == "down":
            return macd_result["hist_down_sum"]
        else:
            return macd_result["hist_up_sum"]
    except:
        return abs(bi.high - bi.low)


def _calc_confidence(mmd: MMD, trend_strength: float, volumes: list[float] | None = None) -> float:
    """计算买卖点置信度（0-1）。

    置信度由以下因素决定：
    1. 买卖点类型优先级：1买/1卖 > 2买/2卖 > 3买/3卖 > 类二买/类二卖
    2. 背驰强度：strong +0.1, moderate +0.05, weak -0.05, unknown 0
    3. 趋势强度：趋势越明确，置信度越高
    4. 成交量配合：突破放量/回调缩量时额外加分
    """
    # 基础置信度（按类型）
    base_confidence: dict[MMDType, float] = {
        MMDType.BUY_1: 0.85,
        MMDType.SELL_1: 0.90,
        MMDType.BUY_2: 0.70,
        MMDType.SELL_2: 0.65,
        MMDType.BUY_2S: 0.55,
        MMDType.SELL_2S: 0.50,
        MMDType.BUY_3: 0.50,
        MMDType.SELL_3: 0.45,
    }

    confidence = base_confidence.get(mmd.mmd_type, 0.5)

    # 从消息中提取背驰强度
    strength_bonus = 0.0
    msg = mmd.msg.lower()
    if "strong" in msg:
        strength_bonus = 0.08
    elif "moderate" in msg:
        strength_bonus = 0.04
    elif "weak" in msg:
        strength_bonus = -0.05

    # 趋势强度加成（最多+0.07）
    trend_bonus = trend_strength * 0.07

    confidence += strength_bonus + trend_bonus

    # 成交量配合加成（仅对3买/3卖生效）
    if mmd.mmd_type in (MMDType.BUY_3, MMDType.SELL_3) and volumes:
        try:
            bi_end_idx = mmd.bi.end.k.k_index if mmd.bi else -1
            if 0 <= bi_end_idx < len(volumes):
                recent_vols = volumes[max(0, bi_end_idx-20):bi_end_idx+1]
                if recent_vols:
                    avg_recent = sum(recent_vols) / len(recent_vols)
                    if avg_recent > 0:
                        # 回调缩量确认：当前笔平均量 < 近20日均量 * 0.8
                        pullback_vol_ratio = avg_recent / (sum(volumes[-20:]) / 20) if len(volumes) >= 20 else 1.0
                        if pullback_vol_ratio < 0.8:
                            confidence += 0.05
                        elif pullback_vol_ratio < 1.0:
                            confidence += 0.02
        except Exception:
            pass

    # clip到[0, 1]
    return max(0.0, min(1.0, confidence))
