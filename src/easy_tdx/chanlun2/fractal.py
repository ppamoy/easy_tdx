"""分型识别（第67课）。

第67课：连续三根（合并后）K 线构成分型：
- 顶分型：第二根 K 线高点是三根最高、低点也是三根最高。
- 底分型：第二根 K 线低点是三根最低、高点也是三根最低。

第65课强调：分型基于「合并后的 K 线」，且合并方向已确定，分型唯一、客观。
"""

from __future__ import annotations

from .types import Fractal, FractalType, MergedK


def find_fractals(merged: list[MergedK]) -> list[Fractal]:
    """从合并后的 K 线序列中识别顶底分型（第67课）。

    三根连续 MergedK，第二根为分型中根：
    - 顶：k2.high > k1.high 且 k2.high > k3.high 且 k2.low > k1.low 且 k2.low > k3.low
    - 底：k2.low < k1.low 且 k2.low < k3.low 且 k2.high < k1.high 且 k2.high < k3.high
    """
    fractals: list[Fractal] = []
    if len(merged) < 3:
        return fractals

    idx = 0
    for i in range(1, len(merged) - 1):
        k1 = merged[i - 1]
        k2 = merged[i]
        k3 = merged[i + 1]

        # 顶分型（第67课：第二根高低点均最高）
        if k2.high > k1.high and k2.high > k3.high and k2.low > k1.low and k2.low > k3.low:
            fractals.append(
                Fractal(
                    index=idx,
                    kind=FractalType.TOP,
                    value=k2.high,
                    k_index=k2.index,
                    dt=k2.dt_end,
                )
            )
            idx += 1
        # 底分型（第67课：第二根高低点均最低）
        elif k2.low < k1.low and k2.low < k3.low and k2.high < k1.high and k2.high < k3.high:
            fractals.append(
                Fractal(
                    index=idx,
                    kind=FractalType.BOTTOM,
                    value=k2.low,
                    k_index=k2.index,
                    dt=k2.dt_end,
                )
            )
            idx += 1

    return fractals
