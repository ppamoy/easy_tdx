# src/easy_tdx/factor/analysis.py
"""因子有效性分析引擎。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# V567: 截面有效样本下限——相关性至少需 5 对，不足记 NaN
_MIN_IC_SAMPLES = 5


@dataclass
class FactorReport:
    """单因子分析报告。"""

    name: str
    ic_mean: float
    ic_std: float
    ir: float
    ic_positive_rate: float
    quantile_returns: dict[str, float]
    top_minus_bottom: float
    turnover_rate: float
    autocorr: float
    ic_series: pd.Series


class FactorAnalyzer:
    """因子有效性分析引擎。"""

    def __init__(
        self,
        factor_data: pd.DataFrame,
        return_data: pd.DataFrame,
        factor_col: str = "momentum_20d",
        return_col: str = "forward_5d",
        n_quantiles: int = 5,
    ) -> None:
        # V531: 分位数至少 2（1 分位/非正数无意义，pd.qcut 会报错或退化）
        if n_quantiles < 2:
            raise ValueError(f"n_quantiles 至少为 2，当前 {n_quantiles}")
        self._factor_col = factor_col
        self._return_col = return_col
        self._n_quantiles = n_quantiles
        self._merged = factor_data.merge(
            return_data[["date", "code", return_col]],
            on=["date", "code"],
            how="inner",
        )

    def compute_ic(self, method: str = "spearman") -> pd.Series:
        """逐截面计算 Rank IC。"""
        # V528: 方法校验前置 + scipy 可用性检查移出循环（原每截面重复 import，
        # 且拼写错误的方法名会静默回退 pearson）。
        if method not in ("spearman", "pearson"):
            raise ValueError(f"未知 IC 方法: {method!r}（可选: spearman, pearson）")
        if method == "spearman":
            try:
                import scipy  # noqa: F401  # pandas spearman lazy import
            except ImportError as e:
                raise ImportError(
                    "Rank IC (spearman) 需要 scipy，请执行 `pip install easy-tdx[science]`"
                ) from e
        dates = sorted(self._merged["date"].unique())
        ic_values: list[float] = []
        for date in dates:
            sub = self._merged[self._merged["date"] == date]
            valid = sub[[self._factor_col, self._return_col]].dropna()
            # V567: 截面有效样本不足 5 个时 IC 无统计意义，记 NaN（相关性至少需 5 对）
            if len(valid) < _MIN_IC_SAMPLES:
                ic_values.append(np.nan)
                continue
            corr = valid[self._factor_col].corr(valid[self._return_col], method=method)
            ic_values.append(corr)
        return pd.Series(ic_values, index=dates, name="IC")

    def compute_quantile_returns(self) -> pd.DataFrame:
        """分层收益分析。"""
        dates = sorted(self._merged["date"].unique())
        q_names = [f"q{i + 1}" for i in range(self._n_quantiles)]
        rows: list[list[float]] = []
        for date in dates:
            sub = self._merged[self._merged["date"] == date]
            valid = sub[[self._factor_col, self._return_col]].dropna()
            if len(valid) < self._n_quantiles:
                rows.append([np.nan] * self._n_quantiles)
                continue
            valid = valid.copy()
            valid["_q"] = pd.qcut(
                valid[self._factor_col],
                self._n_quantiles,
                labels=False,
                duplicates="drop",
            )
            means = valid.groupby("_q")[self._return_col].mean()
            rows.append([float(means.get(q, np.nan)) for q in range(self._n_quantiles)])
        return pd.DataFrame(rows, index=dates, columns=q_names)

    def compute_turnover(self) -> float:
        """因子换手率。"""
        dates = sorted(self._merged["date"].unique())
        if len(dates) < 2:
            return 0.0
        n_top = max(self._n_quantiles, 5)
        overlaps: list[float] = []
        prev_top: set[str] = set()
        for date in dates:
            sub = self._merged[self._merged["date"] == date]
            valid = sub[[self._factor_col, "code"]].dropna()
            if len(valid) < n_top:
                continue
            top = set(valid.nlargest(n_top, self._factor_col)["code"].tolist())
            if prev_top:
                overlaps.append(len(top & prev_top) / len(top | prev_top))
            prev_top = top
        if not overlaps:
            return 0.0
        return 1.0 - float(np.mean(overlaps))

    def compute_decay(self, max_lag: int = 10) -> pd.DataFrame:
        """因子衰减分析。"""
        ic_series = self.compute_ic()
        # V546: 守卫统一用有效截面（dropna），与 V536/V542 口径一致
        valid_ic = ic_series.dropna()
        autocorr_values: list[float] = []
        for lag in range(1, max_lag + 1):
            if lag < len(valid_ic):
                ac = valid_ic.autocorr(lag=lag)
                autocorr_values.append(ac if not np.isnan(ac) else 0.0)
            else:
                autocorr_values.append(0.0)
        return pd.DataFrame({"lag": range(1, max_lag + 1), "autocorr": autocorr_values})

    def full_report(self) -> FactorReport:
        """一键生成完整分析报告。"""
        ic_series = self.compute_ic()
        qr = self.compute_quantile_returns()

        # V523/V536: 所有 IC 派生指标统一只统计有效截面（dropna）——
        # 旧实现 ic_mean/ic_std 用总长度作守卫，在「1 有效 + N 个 NaN」时 ic_std
        # 会被算成 NaN（std 单样本），ir 随之退化；统一 dropna 后口径一致。
        valid_ic = ic_series.dropna()
        ic_mean = float(valid_ic.mean()) if len(valid_ic) > 0 else 0.0
        ic_std = float(valid_ic.std()) if len(valid_ic) > 1 else 0.0
        ir = ic_mean / ic_std if ic_std > 0 else 0.0
        # V523: IC 为正占比应只统计有效截面（dropna），旧实现 (ic_series > 0).mean()
        # 把 NaN 截面（样本不足）误当作「非正」，系统性低估 IC 为正占比。
        ic_positive_rate = float((valid_ic > 0).mean()) if len(valid_ic) > 0 else 0.0

        quantile_means = qr.mean()
        quantile_returns = {
            f"q{i + 1}": float(quantile_means.iloc[i]) for i in range(len(quantile_means))
        }
        # V518/V533: 顶底收益用实际有效的最高/最低分位。V518 已把硬编码 q5 改为
        # q{n_quantiles}；V533 进一步处理 qcut 因重复值丢弃分位的情形——此时
        # q{n_quantiles} 为 NaN，应回退到实际存在的最高分位，而非返回 NaN。
        valid_returns = {k: v for k, v in quantile_returns.items() if not np.isnan(v)}
        if len(valid_returns) >= 2:
            top_key = max(valid_returns, key=lambda k: int(k[1:]))
            bottom_key = min(valid_returns, key=lambda k: int(k[1:]))
            top_minus_bottom = valid_returns[top_key] - valid_returns[bottom_key]
        else:
            top_minus_bottom = 0.0

        turnover = self.compute_turnover()
        # V542: autocorr 守卫统一用有效截面（valid_ic），与 ic_mean/ic_std（V536）
        # 口径一致——旧实现用 ic_series 总长度 + isnan 兜底，语义等价但口径不一。
        autocorr = float(valid_ic.autocorr(lag=1)) if len(valid_ic) > 1 else 0.0

        return FactorReport(
            name=self._factor_col,
            ic_mean=ic_mean,
            ic_std=ic_std,
            ir=ir,
            ic_positive_rate=ic_positive_rate,
            quantile_returns=quantile_returns,
            top_minus_bottom=top_minus_bottom,
            turnover_rate=turnover,
            autocorr=autocorr if not np.isnan(autocorr) else 0.0,
            ic_series=ic_series,
        )
