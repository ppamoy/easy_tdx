# src/easy_tdx/factor/engine.py
"""因子计算引擎 — 单股计算与截面批量计算。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from easy_tdx.factor.base import FACTORY_REGISTRY, Factor


def _resolve_factor(f: str | Factor) -> Factor:
    """将因子名或实例解析为 Factor 实例。"""
    if isinstance(f, Factor):
        return f
    name = f.strip()
    if name not in FACTORY_REGISTRY:
        raise ValueError(f"未知因子: {name!r}。可用因子: {sorted(FACTORY_REGISTRY.keys())}")
    return FACTORY_REGISTRY[name]()


def _datetime_to_int(dt_val: object) -> int:
    """将 datetime 值转为 YYYYMMDD 整数。"""
    if hasattr(dt_val, "strftime"):
        strftime = getattr(dt_val, "strftime")
        return int(strftime("%Y%m%d"))
    if isinstance(dt_val, int | float):
        return int(dt_val)
    return 0


_ALL_DATES: object = object()


def merge_fundamentals(
    data: dict[str, pd.DataFrame],
    frame: pd.DataFrame | None,
) -> dict[str, pd.DataFrame]:
    """V529: 把基本面指标帧的 eps/bps 合并进 OHLCV 数据，供 PE/PB 因子使用。

    打通因子引擎与基本面数据：``frame`` 为 ``build_indicator_frame`` 输出
    （含 code/eps/bps/report_date），对每只股票取其最新一期 eps/bps 作为
    常量列合并进它的 OHLCV DataFrame。之后即可对 ``pe_ratio``/``pb_ratio``
    做截面计算（V495 价值因子落地）。

    注意：本函数做「最新一期」简化，适用于**当前日期截面**的估值因子计算；
    历史截面需 point-in-time 截断（避免前视偏差），不在本函数职责内。

    Args:
        data: {code: OHLCV DataFrame}（须含 close 列）
        frame: 基本面指标帧（缺省/空则原样返回副本）

    Returns:
        每只股票 df 追加了 eps/bps 列（无对应财报时为 NaN）的新字典。
    """
    if frame is None or frame.empty:
        return {k: v.copy() for k, v in data.items()}
    out: dict[str, pd.DataFrame] = {}
    for code, df in data.items():
        sub = frame[frame["code"] == code]
        eps: float | None = None
        bps: float | None = None
        if not sub.empty:
            sub = sub.sort_values("report_date") if "report_date" in sub.columns else sub
            eps = sub["eps"].iloc[-1] if "eps" in sub.columns else None
            bps = sub["bps"].iloc[-1] if "bps" in sub.columns else None
        df2 = df.copy()
        df2["eps"] = eps
        df2["bps"] = bps
        out[code] = df2
    return out


class FactorEngine:
    """批量因子计算引擎。"""

    def compute_single(
        self,
        df: pd.DataFrame,
        factors: list[str | Factor],
    ) -> pd.DataFrame:
        """单股票多因子计算。"""
        if not factors:
            return df.copy()

        result = df.copy()
        for f in factors:
            factor = _resolve_factor(f)
            result[factor.name] = factor.compute(df)

        return result

    def compute_cross_section(
        self,
        data: dict[str, pd.DataFrame],
        factors: list[str | Factor],
        date: int | None = _ALL_DATES,  # type: ignore[assignment]
    ) -> pd.DataFrame:
        """多股票截面因子计算。

        Args:
            date: int 精确匹配日期；None 仅最新一行；默认(不传)全部日期。
        """
        if not data:
            return pd.DataFrame()

        filter_latest = date is None
        all_frames: list[pd.DataFrame] = []

        for code, df in data.items():
            if df.empty:
                continue

            computed = self.compute_single(df, factors)
            # V527: 兼容 date 列（get_security_bars 日线返回 date 而非 datetime），
            # 与回测引擎的「date → datetime」派生一致。
            dt_col = "datetime" if "datetime" in computed.columns else "date"
            computed["_date_int"] = computed[dt_col].apply(_datetime_to_int)

            if date is not None and date is not _ALL_DATES:
                computed = computed[computed["_date_int"] == date]
            elif filter_latest:
                computed = computed.iloc[[-1]]

            factor_names = [_resolve_factor(f).name for f in factors]
            keep_cols = ["_date_int"] + factor_names
            sub = computed[keep_cols].copy()
            sub["_code"] = code
            all_frames.append(sub)

        if not all_frames:
            return pd.DataFrame()

        combined = pd.concat(all_frames, ignore_index=True)
        combined = combined.rename(columns={"_date_int": "date", "_code": "code"})

        col_order = ["date", "code"] + [_resolve_factor(f).name for f in factors]
        combined = combined[col_order].sort_values(["date", "code"]).reset_index(drop=True)

        return combined

    def compute_forward_returns(
        self,
        data: dict[str, pd.DataFrame],
        period: int = 5,
    ) -> pd.DataFrame:
        """计算远期收益率。"""
        if not data:
            return pd.DataFrame()

        col_name = f"forward_{period}d"
        all_frames: list[pd.DataFrame] = []

        for code, df in data.items():
            if df.empty or len(df) < period + 1:
                continue

            close = df["close"].to_numpy()
            forward = np.full(len(close), np.nan)
            forward[: len(close) - period] = close[period:] / close[: len(close) - period] - 1

            # V527: 兼容 date 列（同上）
            dt_col = "datetime" if "datetime" in df.columns else "date"
            dates = df[dt_col].apply(_datetime_to_int)

            sub = pd.DataFrame(
                {
                    "date": dates,
                    "code": code,
                    col_name: forward,
                }
            )
            all_frames.append(sub)

        if not all_frames:
            return pd.DataFrame(columns=["date", "code", col_name])

        combined = pd.concat(all_frames, ignore_index=True)
        combined = combined.sort_values(["date", "code"]).reset_index(drop=True)
        return combined
