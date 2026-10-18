"""区间套：跨周期精确定位（第83课走势结构的两重表里关系）。

原文区间套语义（第83课等）：
- 大级别买卖点的精确定位 = 次级别走势的买卖点 + 次次级别…逐级收敛。
- 例：日线 1 买（趋势背驰）的精确定位点，是该日线背驰笔区间内的
  30 分钟同方向买卖点；30 分钟买卖点又由 5 分钟精确定位。
- 防未来函数：次级别结构的结束时间不得晚于大级别信号结束时间。

与现有 ``chanlun.level_synth``（合成数据，自述「近似非真实 Tick」）和
``chanlun.qujiantao``（真跨周期）区别：
- chanlun2 ``level_synth`` 只接受**真实多周期 K 线**，逐周期跑 ``analyze``，
  按行情时间对齐，不合成、不递归同序列伪低级别。
- 产出精确定位点 + 跨周期确认链（nested），前端可展示逐级收敛。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .analyser import Chanlun2Result, analyze
from .types import KLine, MMD, MMDType


@dataclass
class NestedMMD:
    """跨周期精确定位结果（区间套）。

    high_mmd: 大级别买卖点
    low_mmd: 次级别同方向买卖点（精确定位）
    lower_chain: 更次级别的确认链（逐级收敛）
    precise_k_index: 精确定位K线（最末级确认点）
    precise_dt: 精确定位时间
    confirmed: 是否有跨周期确认
    """

    high_mmd: MMD
    low_mmd: Optional[MMD] = None
    lower_chain: list["NestedMMD"] = field(default_factory=list)
    precise_k_index: int = -1
    precise_dt: str = ""
    confirmed: bool = False
    levels: int = 1  # 收敛级数（1=单级别,2=次级别确认,3=次次级别…）


def _mmd_time_window(mmd: MMD, result: Chanlun2Result) -> tuple[str, str]:
    """大级别买卖点的锚定时间窗口（第83课：次级别需落在窗口内）。

    窗口 = 买卖点K线的前一根到该K线（防未来函数：不晚于信号结束）。
    """
    # 取买卖点K线在 merged 中的位置
    if mmd.k_index >= len(result.merged):
        return ("", "")
    end_k = result.merged[mmd.k_index] if mmd.k_index < len(result.merged) else None
    # 窗口起点：往前取一定范围（取该买卖点所属走势段的起点）
    # 简化：用 merged 的前一根到当前根的时间
    start_idx = max(0, mmd.k_index - 20)  # 往前20根作为窗口（可配置）
    start_k = result.merged[start_idx] if start_idx < len(result.merged) else None
    start_dt = start_k.dt_start if start_k else ""
    end_dt = end_k.dt_end if end_k else ""
    return (start_dt, end_dt)


def _mmd_in_window(
    low_mmd: MMD,
    low_result: Chanlun2Result,
    start_dt: str,
    end_dt: str,
    direction: object,
) -> bool:
    """次级别买卖点是否落在大级别时间窗口内且方向一致（第83课）。"""
    if low_mmd.k_index >= len(low_result.merged):
        return False
    low_k = low_result.merged[low_mmd.k_index]
    # 时间在窗口内（防未来函数：low结束不晚于high结束）
    if low_k.dt_start < start_dt or low_k.dt_end > end_dt:
        return False
    # 方向一致（买点对应向下结束，卖点对应向上结束）
    if low_mmd.direction != direction:
        return False
    return True


def refine_with_lower_level(
    high_result: Chanlun2Result,
    low_klines: list[KLine],
    lower_klines: Optional[list[KLine]] = None,
) -> list[NestedMMD]:
    """区间套精确定位（第83课）：大级别买卖点 × 次级别买卖点 × 次次级别。

    参数：
        high_result: 大级别 analyze 结果
        low_klines: 次级别真实K线（如日线+30分钟）
        lower_klines: 可选次次级别（如5分钟），用于更深收敛

    返回：每个大级别买卖点的 NestedMMD（含次级别确认链）。
    """
    low_result = analyze(low_klines) if low_klines else None
    lower_result = analyze(lower_klines) if lower_klines else None

    nested: list[NestedMMD] = []
    for hm in high_result.mmds:
        start_dt, end_dt = _mmd_time_window(hm, high_result)
        # 大级别买卖点方向（买=向下结束底，卖=向上结束顶）
        nm = NestedMMD(high_mmd=hm, levels=1)

        if low_result is not None:
            # 在次级别找同方向、时间窗口内的买卖点（第83课精确定位）
            for lm in low_result.mmds:
                if _mmd_in_window(lm, low_result, start_dt, end_dt, hm.direction):
                    nm.low_mmd = lm
                    nm.precise_k_index = lm.k_index
                    nm.precise_dt = lm.dt
                    nm.confirmed = True
                    nm.levels = 2

                    # 次次级别更深收敛（第83课逐级）
                    if lower_result is not None:
                        l_start, l_end = _mmd_time_window(lm, low_result)
                        for llm in lower_result.mmds:
                            if _mmd_in_window(
                                llm, lower_result, l_start, l_end, lm.direction
                            ):
                                inner = NestedMMD(
                                    high_mmd=lm,
                                    low_mmd=llm,
                                    precise_k_index=llm.k_index,
                                    precise_dt=llm.dt,
                                    confirmed=True,
                                    levels=3,
                                )
                                nm.lower_chain.append(inner)
                                # 精确定位取最末级
                                nm.precise_k_index = llm.k_index
                                nm.precise_dt = llm.dt
                                break
                    break  # 每个大级别买卖点取第一个次级别确认
        nested.append(nm)

    return nested


def interval_bag_summary(nested: list[NestedMMD]) -> list[dict]:
    """区间套结果摘要（供前端/API）。

    每个大级别买卖点：
    - high: 大级别类型/时间/价位
    - low: 次级别精确定位（时间/价位）
    - lower: 次次级别（若有）
    - levels: 收敛级数
    - confirmed: 是否跨周期确认
    """
    out = []
    for nm in nested:
        h = nm.high_mmd
        item = {
            "high_type": h.mmd_type.value,
            "high_k": h.k_index,
            "high_dt": h.dt,
            "high_price": h.price,
            "confirmed": nm.confirmed,
            "levels": nm.levels,
            "precise_dt": nm.precise_dt,
            "precise_k": nm.precise_k_index,
        }
        if nm.low_mmd:
            item["low_type"] = nm.low_mmd.mmd_type.value
            item["low_dt"] = nm.low_mmd.dt
            item["low_price"] = nm.low_mmd.price
        if nm.lower_chain:
            item["lower"] = [
                {
                    "type": c.low_mmd.mmd_type.value if c.low_mmd else None,
                    "dt": c.low_mmd.dt if c.low_mmd else "",
                    "price": c.low_mmd.price if c.low_mmd else 0.0,
                }
                for c in nm.lower_chain
            ]
        out.append(item)
    return out
