"""分型识别。

顶分型：中间 K 线的高点和低点均为三根中最高。
底分型：中间 K 线的高点和低点均为三根中最低。

严格模式下不允许相等（使用 > 而非 >=）。
"""

from __future__ import annotations

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import FX, CLKline, FXType


def _fx_bar_index(mid: CLKline, is_ding: bool) -> int:
    """分型极值对应的原始 K 线索引。

    顶分型取中间缠论K线 high 的来源原始K线（high_k_index），
    底分型取中间缠论K线 low 的来源原始K线（low_k_index）。

    生产路径（merge_klines）始终正确维护 high_k_index/low_k_index；
    测试直接手构 CLKline 时未设置这两个字段，此时回退到 k_index
    （未合并单根K线两者的语义一致），保证 fixture 计算不产生退化索引。
    """
    if is_ding:
        return mid.high_k_index if mid.merged_count > 1 or mid.high_k_index else mid.k_index
    return mid.low_k_index if mid.merged_count > 1 or mid.low_k_index else mid.k_index


def find_fractals(
    cklines: list[CLKline],
    config: ChanlunConfig | None = None,
) -> list[FX]:
    """从缠论 K 线列表中识别分型。

    扫描每三根相邻的缠论 K 线，判断是否构成顶分型或底分型。

    Args:
        cklines: 合并后的缠论 K 线列表
        config: 缠论配置（默认使用 ChanlunConfig()）

    Returns:
        分型列表，按时间顺序排列
    """
    if config is None:
        config = ChanlunConfig()

    if len(cklines) < 3:
        return []

    fxs: list[FX] = []

    for i in range(len(cklines) - 2):
        left = cklines[i]
        mid = cklines[i + 1]
        right = cklines[i + 2]

        # 缠论原文（62课）：顶分型 = 中间K线高点最高 且 低点也最高；
        # 底分型 = 中间K线低点最低 且 高点也最低。旧实现只检查单一维度，
        # 会把「高点最高但低点不是最高」的K线误判为顶分型。
        if config.fx_strict:
            is_ding = (
                mid.high > left.high
                and mid.high > right.high
                and mid.low > left.low
                and mid.low > right.low
            )
            is_di = (
                mid.low < left.low
                and mid.low < right.low
                and mid.high < left.high
                and mid.high < right.high
            )
        else:
            is_ding = (
                mid.high >= left.high
                and mid.high >= right.high
                and mid.low >= left.low
                and mid.low >= right.low
            )
            is_di = (
                mid.low <= left.low
                and mid.low <= right.low
                and mid.high <= left.high
                and mid.high <= right.high
            )

        if is_ding and is_di:
            # 同时满足顶底分型条件（如十字星），跳过
            continue
        elif is_ding:
            fx = FX(
                fx_type=FXType.DING,
                k=mid,
                klines=[left, mid, right],
                val=mid.high,
                index=len(fxs),
                done=True,
                bar_index=_fx_bar_index(mid, is_ding=True),
            )
            fxs.append(fx)
        elif is_di:
            fx = FX(
                fx_type=FXType.DI,
                k=mid,
                klines=[left, mid, right],
                val=mid.low,
                index=len(fxs),
                done=True,
                bar_index=_fx_bar_index(mid, is_ding=False),
            )
            fxs.append(fx)

    return fxs
