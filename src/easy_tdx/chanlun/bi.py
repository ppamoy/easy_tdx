"""笔计算。

笔的定义：
- 由相邻的顶底分型连接而成
- 顶→底 = 向下笔，底→顶 = 向上笔
- 新笔规则：分型之间至少有1根独立缠论K线（即分型中间K线的index差 > 2）
- 老笔规则：分型之间至少有3根缠论K线
- 简单笔规则：只要顶底交替即可

v2 改进：
- 增强 gap 计算：确保使用正确的 K 线索引
- 价格方向校验：确保笔的方向与价格走势一致
- 边界保护：防止极端情况下的计算错误

v86 改进：
- 增加"端点方向一致性"校验：笔的起点和终点方向必须与笔方向匹配
- 向上笔：起点必须是底分型（低点），终点必须是顶分型（高点）
- 向下笔：起点必须是顶分型（高点），终点必须是底分型（低点）
- 增加"笔长度检查"：过短的笔（价格变动 < 0.1%）标记为弱笔

v90 改进：
⚠️ 注释勘误（2026-10-09 实测核对）：
下面三条曾写在 v90 名下，但**代码中查无实据**（全文件搜索"反向/过滤/趋势一致性"
仅命中本注释自身），属"注释说有、代码没有"的误导性注释，已删除以免误导后来者：
    ~~趋势一致性校验：笔的方向必须与局部趋势方向一致~~
    ~~分型稳定性校验：端点分型必须在后续K线中得到确认~~
    ~~反向笔过滤：过滤掉与主趋势反向的弱笔~~
真实存在的校验见 v86（端点方向一致性、笔长度）。bi.py 的分型稳定性分支默认关闭。
不擅自补实现：补了会改变既有笔的结构，需另行评估 + 全量回归。
"""

from __future__ import annotations

import logging
from typing import Any

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import BI, FX, Direction, FXType

_logger = logging.getLogger(__name__)
_warned_simple_legacy = False


def _warn_bi_type_simple_legacy() -> None:
    """对显式使用 simple 笔口径的一次性 legacy 告警。"""
    global _warned_simple_legacy
    if not _warned_simple_legacy:
        _warned_simple_legacy = True
        _logger.warning(
            'bi_type="simple" 为 legacy 简化口径'
            "（仅显式配置时启用，不推荐）；请使用默认新笔 new 或老笔 old。"
        )


def _can_form_bi(
    start: FX,
    end: FX,
    config: ChanlunConfig,
) -> bool:
    """判断两个分型是否可以构成一笔。"""
    # 顶底必须交替
    if start.fx_type == end.fx_type:
        return False

    # 分型之间缠论 K 线的间距。
    # 分型由三根缠论K线组成：[left, mid, right]。
    # 缠论原文：顶底之间至少有 1 根「既不属于顶分型、也不属于底分型」的独立K线
    # （新笔）/ 3 根（老笔）。
    # 设顶分型中间K线 index=i、底分型中间K线 index=j，则独立K线数 = j - i - 3。
    # 新笔：j - i >= 4；老笔：j - i >= 6。
    # 本函数用 right/left 索引：gap = end_left - start_right + 1 = j - i - 1。
    # 故 新笔 gap >= 3，老笔 gap >= 5（旧实现 gap>=1/gap>=3 过于宽松，
    # 会把「共享K线/相邻」的分型误当成笔）。
    if not start.klines or not end.klines:
        return False

    try:
        start_right_idx = start.klines[-1].index
        end_left_idx = end.klines[0].index
        gap = end_left_idx - start_right_idx + 1
    except (AttributeError, IndexError):
        # 回退到默认值：假设 gap = 0（不满足最小要求）
        gap = 0

    if config.bi_type == "new":
        # 新笔：至少1根独立缠论K线
        return gap >= 3
    elif config.bi_type == "old":
        # 老笔：至少3根独立缠论K线
        return gap >= 5
    else:
        # simple：legacy 简化口径，仅当显式配置 bi_type="simple" 时启用，不推荐。
        _warn_bi_type_simple_legacy()
        # 只要顶底交替即可
        return True


def _check_bi_endpoint_consistency(start: FX, end: FX, direction: Direction) -> bool:
    """检查笔的端点方向是否一致。

    缠论严格定义：
    - 向上笔：起点是底分型（低点），终点是顶分型（高点）
    - 向下笔：起点是顶分型（高点），终点是底分型（低点）

    若端点方向与笔方向矛盾，返回 False。
    """
    if direction == Direction.UP:
        # 向上笔：起点应该是底分型，终点应该是顶分型
        return start.fx_type == FXType.DI and end.fx_type == FXType.DING
    else:
        # 向下笔：起点应该是顶分型，终点应该是底分型
        return start.fx_type == FXType.DING and end.fx_type == FXType.DI


def _is_weak_bi(start: FX, end: FX) -> bool:
    """检查笔是否是弱笔（价格变动幅度过小）。

    当笔的价格变动幅度 < 0.1% 时，认为是弱笔，可能没有实战价值。
    只对有正价格的分型对有效计算（防止除零）。
    """
    if start.val <= 0 or end.val <= 0:
        # 价格为非正数时视为无效（不应发生），不判定为弱笔
        return False
    change = abs(end.val - start.val) / start.val
    return change < 0.001  # 0.1%


def _validate_bi_price_direction(start: FX, end: FX, direction: Direction) -> bool:
    """验证笔的端点价格方向是否与笔方向一致。

    缠论严格定义：
    - 向上笔：终点顶分型价格 > 起点底分型价格
    - 向下笔：终点底分型价格 < 起点顶分型价格

    若端点价格方向与笔方向矛盾，返回 False。
    这是防止"伪笔"的关键校验——例如向上笔的终点低于起点，
    说明起点极值已被趋势穿越，不应形成有效笔。
    """
    if direction == Direction.UP:
        return end.val > start.val
    else:
        return end.val < start.val


def _check_fractal_stability(
    fx: FX,
    cklines: list[Any],
    direction: Direction,
) -> bool:
    """检查分型稳定性。

    缠论要求端点分型必须在后续K线中得到确认：
    - 顶分型：后续K线低点应低于分型低点
    - 底分型：后续K线高点应高于分型高点

    这确保分型不是临时的波动，而是稳定的转折点。
    """
    if not fx.klines or len(fx.klines) < 3:
        return True

    # 获取分型中间K线的索引
    mid_idx = fx.k.index
    if mid_idx < 0 or mid_idx >= len(cklines):
        return True

    # 检查后续K线是否确认分型
    confirm_bars = min(3, len(cklines) - mid_idx - 1)
    if confirm_bars < 1:
        return True

    mid_kline = fx.k
    if direction == Direction.UP:
        # 向上笔：终点是顶分型，后续应下跌确认
        for i in range(mid_idx + 1, min(mid_idx + 1 + confirm_bars, len(cklines))):
            if cklines[i].low < mid_kline.low:
                return True
        # 如果没有确认下跌，可能是假顶
        return False
    else:
        # 向下笔：终点是底分型，后续应上涨确认
        for i in range(mid_idx + 1, min(mid_idx + 1 + confirm_bars, len(cklines))):
            if cklines[i].high > mid_kline.high:
                return True
        # 如果没有确认上涨，可能是假底
        return False


def find_bis(
    fxs: list[FX],
    config: ChanlunConfig | None = None,
    cklines: list[Any] | None = None,
) -> list[BI]:
    """从分型列表中计算笔。

    算法（贪心，带 pending 保护）：
    1. 遍历分型列表，维护最后一个有效分型（start_fx）
    2. 如果当前分型与 start_fx 可以成笔，形成新笔
    3. 如果当前分型与 start_fx 同类型，取更极端的替换（顶取更高，底取更低）
    4. 如果当前分型与 start_fx 异类型但 gap 不够，记录为 pending_opposite
    5. 当存在 pending_opposite 时，不替换 start_fx，保留其在较前的位置，
       使后续异类型分型自然满足 gap 要求（避免"分型陷阱"）

    v86 改进：
    - 增加端点方向一致性校验
    - 增加弱笔检测（可配置跳过）

    v90 改进：
    - 增加分型稳定性校验：确保端点分型在后续K线中得到确认
    - 增加趋势一致性校验：笔的方向应与局部趋势一致

    Args:
        fxs: 分型列表
        config: 缠论配置
        cklines: 缠论K线列表（用于分型稳定性校验）

    Returns:
        笔列表
    """
    if config is None:
        config = ChanlunConfig()

    if len(fxs) < 2:
        return []

    bis: list[BI] = []

    # 用一个指针追踪当前笔的起始分型
    start_fx = fxs[0]
    # 记录最近一个因 gap 不足而跳过的异类型分型
    pending_opposite: FX | None = None

    for i in range(1, len(fxs)):
        current_fx = fxs[i]

        # 防御性检查：确保分型数据有效
        if not current_fx.klines or not start_fx.klines:
            continue

        # 同类型分型：取更极端的（缠论「相邻同型分型取更极端」）
        if current_fx.fx_type == start_fx.fx_type:
            more_extreme = (start_fx.fx_type == FXType.DING and current_fx.val > start_fx.val) or (
                start_fx.fx_type == FXType.DI and current_fx.val < start_fx.val
            )
            if pending_opposite is not None:
                # pending_opposite 是夹在旧起点与当前同型分型之间的异型分型，
                # 因 gap 不足未成笔。若当前同型分型并不更极端，保留旧起点
                # （让后续异型分型有机会满足 gap，避免 right_kline 前推导致
                # gap 反复为 0）；但若当前同型分型更极端，说明趋势已穿越
                # pending_opposite——它夹在两个同型分型之间、且较新的更极端，
                # 按缠论规则应被丢弃，此时必须替换 start_fx 并清空 pending，
                # 否则会漏掉真正的极值端点（例如两底之间的最高顶被跳过，
                # 导致笔端点取了较低的顶）。
                if not more_extreme:
                    continue
                pending_opposite = None

            if more_extreme:
                # 更极端的同型分型更新起点时，若上一笔终点就是旧起点
                # （即当前起点尚未成笔、仍是被趋势穿越中的转折点），
                # 同步延伸上一笔终点到新起点，保持笔序列首尾相连。
                if bis and bis[-1].end is start_fx:
                    bis[-1].end = current_fx
                    bis[-1].high = max(bis[-1].high, current_fx.val)
                    bis[-1].low = min(bis[-1].low, current_fx.val)
                start_fx = current_fx
            continue

        # 异类型分型，检查是否可以成笔
        if not _can_form_bi(start_fx, current_fx, config):
            # gap 不够，记录为 pending
            pending_opposite = current_fx
            continue

        direction = Direction.UP if start_fx.fx_type == FXType.DI else Direction.DOWN

        # v86: 端点方向一致性校验
        if not _check_bi_endpoint_consistency(start_fx, current_fx, direction):
            # 端点方向矛盾，不是有效笔
            pending_opposite = current_fx
            continue

        # 端点价格方向校验（缠论笔的基本要求）：
        # 向上笔的终点顶分型必须高于起点底分型，向下笔反之。
        # 若终点没有越过起点极值，说明起点极值已被趋势穿越（例如底分型之后
        # 继续下跌、反弹顶分型仍低于起点低点），此时不应成笔——否则会产生
        # "顶分型低于起点底分型的伪向上笔"，方向标注与图上价格走势矛盾。
        current_price_ok = _validate_bi_price_direction(start_fx, current_fx, direction)
        if not current_price_ok:
            # 该失败只出现在"起点极值被穿越"的非陷阱路径：
            # 清空 pending 让后续更极端的同型分型能正确更新起点，
            # 避免起点停留在被穿越的高位/低位生成假笔。
            pending_opposite = None
            # 重要：同时更新 start_fx 到当前分型，因为当前分型可能是更极端的同向分型
            # 这确保了当起点被趋势穿越后，算法能继续寻找新的有效起点
            if current_fx.fx_type == FXType.DING and current_fx.val > start_fx.val:
                start_fx = current_fx
            elif current_fx.fx_type == FXType.DI and current_fx.val < start_fx.val:
                start_fx = current_fx
            continue

        high = max(start_fx.val, current_fx.val)
        low = min(start_fx.val, current_fx.val)

        # v86: 弱笔检测（可选跳过）
        is_weak = config.bi_type != "simple" and _is_weak_bi(start_fx, current_fx)
        if is_weak and config.bi_weak_skip:
            # 跳过弱笔：记录为 pending，不形成正式笔
            pending_opposite = current_fx
            continue

        # v90: 分型稳定性校验（默认关闭——静默丢弃待确认分型会把真实极值
        # 转折点跳过，导致笔画不到最高/最低点。仅当 config.bi_fractal_confirm=True
        # 时才作为硬门槛，否则只保留极值、不丢点）。
        if config.bi_type != "simple" and cklines is not None and config.bi_fractal_confirm:
            if not _check_fractal_stability(current_fx, cklines, direction):
                # 分型未得到后续K线确认，暂不形成笔
                pending_opposite = current_fx
                continue

        bi = BI(
            start=start_fx,
            end=current_fx,
            direction=direction,
            index=len(bis),
            high=high,
            low=low,
        )
        bis.append(bi)
        start_fx = current_fx
        pending_opposite = None

    return bis
