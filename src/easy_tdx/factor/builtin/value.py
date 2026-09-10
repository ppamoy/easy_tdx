"""价值类因子（PE/PB 估值）。

PE/PB 需要基本面数据（每股收益 / 每股净资产）。因子契约只接收 OHLCV
DataFrame，因此：
- 若 df 未携带 ``eps``（PE）/ ``bps``（PB）列，返回全 NaN（数据缺失）；
- 若 df 携带这些列（基本面增强后的 DataFrame），按元素计算
  ``close / eps`` 与 ``close / bps``，非正分母（亏损 / 无净资产）置 NaN。

这样价值因子不再是死占位：与 fundamental 指标帧（eps/bps）合并后即可真实计算。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from easy_tdx.factor.base import Factor, register_factor


@register_factor
class PERatio(Factor):
    name = "pe_ratio"
    category = "value"
    description = "市盈率（close / EPS；需 df 携带 eps 列，亏损或缺失为 NaN）"
    inputs = ("close",)

    def compute(self, df: pd.DataFrame) -> pd.Series:
        if "eps" not in df.columns:
            return pd.Series(np.nan, index=df.index, dtype=np.float64)
        close = df["close"].to_numpy(dtype=np.float64)
        eps = df["eps"].to_numpy(dtype=np.float64)
        with np.errstate(divide="ignore", invalid="ignore"):
            pe = close / eps
        pe = np.where((eps > 0) & np.isfinite(pe), pe, np.nan)
        return pd.Series(pe, index=df.index, dtype=np.float64)


@register_factor
class PBRatio(Factor):
    name = "pb_ratio"
    category = "value"
    description = "市净率（close / 每股净资产；需 df 携带 bps 列，非正或缺失为 NaN）"
    inputs = ("close",)

    def compute(self, df: pd.DataFrame) -> pd.Series:
        if "bps" not in df.columns:
            return pd.Series(np.nan, index=df.index, dtype=np.float64)
        close = df["close"].to_numpy(dtype=np.float64)
        bps = df["bps"].to_numpy(dtype=np.float64)
        with np.errstate(divide="ignore", invalid="ignore"):
            pb = close / bps
        pb = np.where((bps > 0) & np.isfinite(pb), pb, np.nan)
        return pd.Series(pb, index=df.index, dtype=np.float64)
