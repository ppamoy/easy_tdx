"""笔计算。

笔的定义：
- 由相邻的顶底分型连接而成
- 顶→底 = 向下笔，底→顶 = 向上笔
- 新笔规则：分型之间至少有 1 根独立缠论 K 线（即分型中间 K 线的 index 差 > 2）
- 老笔规则：分型之间至少有 3 根缠论 K 线
- 简单笔规则：只要顶底交替即可

v2 改进：
- 增强 gap 计算：确保使用正确的 K 线索引
- 价格方向校验：确保笔的方向与价格走势一致
- 边界保护：防止极端情况下的计算错误
"""

from __future__ import annotations

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import BI, FX, Direction, FXType


def _can_form_bi(
    start: FX,
    end: FX,
    config: ChanlunConfig,
) -> bool:
    """判断两个分型是否可以构成一笔。"""
    # 顶底必须交替
    if start.fx_type == end.fx_type:
        return False

    # 分型之间缠论 K 线的间距
    # 分型由三根 K 线组成：[left, mid, right]
    # 独立 K 线数 = end.left.index - start.right.index + 1（如果 >0）
    # 防御性检查：确保索引有效
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
        # 新笔：至少1根独立K线
        return gap >= 1
    elif config.bi_type == "old":
        # 老笔：至少3根缠论K线在分型之间
        return gap >= 3
    else:
        # simple：只要顶底交替即可
        return True


def find_bis(
    fxs: list[FX],
    config: ChanlunConfig | None = None,
) -> list[BI]:
    """从分型列表中计算笔。

    算法（贪心，带 pending 保护）：
    1. 遍历分型列表，维护最后一个有效分型（start_fx）
    2. 如果当前分型与 start_fx 可以成笔，形成新笔
    3. 如果当前分型与 start_fx 同类型，取更极端的替换（顶取更高，底取更低）
    4. 如果当前分型与 start_fx 异类型但 gap 不够，记录为 pending_opposite
    5. 当存在 pending_opposite 时，不替换 start_fx，保留其在较前的位置，
       使后续异类型分型自然满足 gap 要求（避免"分型陷阱"）

    "分型陷阱"场景：持续下跌/上涨中，密集交替分型导致每次替换 start_fx
    都把 right_kline_index 前推，使下一个异类型分型的 gap 永远为 0。

    v2 改进：
    - 增加防御性检查，防止 None/空数据导致异常
    - 改进价格方向校验，确保笔的方向与价格走势一致
    - 正确处理边界情况（如只有2个分型）

    Args:
        fxs: 分型列表
        config: 缠论配置

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

        # 同类型分型：取更极端的
        if current_fx.fx_type == start_fx.fx_type:
            # 当存在 pending_opposite 时，不替换 start_fx。
            # 保留 start_fx 在较早位置，让后续异类型分型有机会满足 gap。
            # 若替换，right_kline_index 前推会导致 gap 反复为 0，卡死算法。
            if pending_opposite is not None:
                continue

            if start_fx.fx_type == FXType.DING and current_fx.val > start_fx.val:
                # 更极端的同型分型更新起点时，若上一笔终点就是旧起点
                # （即当前起点尚未成笔、仍是被趋势穿越中的转折点），
                # 同步延伸上一笔终点到新起点，保持笔序列首尾相连。
                if bis and bis[-1].end is start_fx:
                    bis[-1].end = current_fx
                    bis[-1].high = max(bis[-1].high, current_fx.val)
                    bis[-1].low = min(bis[-1].low, current_fx.val)
                start_fx = current_fx
            elif start_fx.fx_type == FXType.DI and current_fx.val < start_fx.val:
                if bis and bis[-1].end is start_fx:
                    bis[-1].end = current_fx
                    bis[-1].high = max(bis[-1].high, current_fx.val)
                    bis[-1].low = min(bis[-1].low, current_fx.val)
                start_fx = current_fx
            continue

        # 异类型分型，检查是否可以成笔
        if _can_form_bi(start_fx, current_fx, config):
            direction = Direction.UP if start_fx.fx_type == FXType.DI else Direction.DOWN

            # 端点价格方向校验（缠论笔的基本要求）：
            # 向上笔的终点顶分型必须高于起点底分型，向下笔反之。
            # 若终点没有越过起点极值，说明起点极值已被趋势穿越（例如底分型之后
            # 继续下跌、反弹顶分型仍低于起点低点），此时不应成笔——否则会产生
            # "顶分型低于起点底分型的伪向上笔"，方向标注与图上价格走势矛盾。
            current_price_ok = (
                current_fx.val > start_fx.val
                if direction == Direction.UP
                else current_fx.val < start_fx.val
            )
            if not current_price_ok:
                # 该失败只出现在"起点极值被穿越"的非陷阱路径：
                # 清空 pending 让后续更极端的同型分型能正确更新起点，
                # 避免起点停留在被穿越的高位/低位生成假笔。
                pending_opposite = None
                continue

            high = max(start_fx.val, current_fx.val)
            low = min(start_fx.val, current_fx.val)

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
        else:
            # gap 不够，记录为 pending
            pending_opposite = current_fx

    return bis
