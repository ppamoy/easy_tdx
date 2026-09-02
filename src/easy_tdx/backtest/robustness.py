"""分段稳健性 / 过拟合检查。

目的：让用户通过历史回测验证「模型的准确度是否在不同行情阶段都成立」，
而不是只在某一段行情里好。把回测区间切成若干连续分段，对每段独立重跑
同一策略，比较各段的收益/胜率/信号命中率：

- 若各段表现一致（胜率与命中率离散度小、多数分段为正收益、跑赢买入持有），
  说明策略具备稳健性，模型可信度高；
- 若整段表现很好但分段的离散度很大、或仅少数分段为正收益/跑赢基准，
  提示可能存在过拟合（overfitting）——模型只是在某段行情里被调参调准了。

与 signal_accuracy（单次回测的择时命中率）互补：那回答「这次回测的信号准不准」，
本模块回答「这个策略换到不同时间段还准不准」。

输出为 JSON 兼容的纯 Python 类型。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from easy_tdx.backtest.engine import BacktestEngine
from easy_tdx.backtest.strategy import Strategy


def _segment_split(
    df: pd.DataFrame,
    segments: int,
) -> list[pd.DataFrame]:
    """把 DataFrame 均分为连续分段（各段顺序保持，index 重置）。

    Args:
        df: 原始 K 线 DataFrame
        segments: 分段数

    Returns:
        分段列表（每段独立 DataFrame）
    """
    n = len(df)
    size = n // segments
    if size < 2:
        return [df]
    out: list[pd.DataFrame] = []
    for i in range(segments):
        start = i * size
        end = n if i == segments - 1 else (i + 1) * size
        out.append(df.iloc[start:end].reset_index(drop=True))
    return out


def _seg_hit_rate(seg_result: Any) -> float | None:
    """取某段回测结果的 5 根前瞻命中率（缺则回退 3/10，取平均口径）。"""
    sa = getattr(seg_result, "signal_accuracy", None) or {}
    buy = sa.get("buy") or {}
    h = buy.get("horizons") or {}
    for key in ("5", "3", "10"):
        stats = h.get(key)
        if stats and stats.get("count", 0) > 0:
            return float(stats["hit_rate"])
    return None


def compute_segment_robustness(
    df: pd.DataFrame,
    strategy_factory: Callable[[], Strategy],
    segments: int = 3,
    cash: float = 1_000_000.0,
    commission: float = 0.0003,
    stamp_tax: float = 0.001,
    slippage: float = 0.0,
    execution: str = "next_open",
) -> dict[str, Any]:
    """把回测区间分段并逐段重跑同一策略，评估稳健性 / 过拟合风险。

    Args:
        df: 回测用 OHLCV DataFrame（与主回测相同，含 datetime/close 等列）
        strategy_factory: 返回全新策略实例的可调用对象（每段独立实例，避免
            段间状态串扰）。由调用方从注册表 build（与主回测同一策略/参数）。
        segments: 分段数（建议 2~5）
        cash/commission/stamp_tax/slippage/execution: 与主回测一致的资金与成本参数

    Returns:
        dict：{"segments": [...], "consistency": {...}, "overfit_likely": bool,
               "verdict": str, "note": str|None}
        数据不足以分段时返回含 note 的最小报告。
    """
    if df is None or len(df) == 0:
        return {
            "segments": [],
            "consistency": {},
            "overfit_likely": False,
            "verdict": "无数据，无法做分段稳健性检查",
            "note": "无数据",
        }

    n = len(df)
    if n < 60:
        return {
            "segments": [],
            "consistency": {},
            "overfit_likely": False,
            "verdict": "数据不足 60 根，无法可靠分段验证",
            "note": "数据量过小",
        }

    seg_dfs = _segment_split(df, segments)
    if len(seg_dfs) < 2:
        return {
            "segments": [],
            "consistency": {},
            "overfit_likely": False,
            "verdict": "数据无法切分，跳过稳健性检查",
            "note": "分段不足",
        }

    seg_reports: list[dict[str, Any]] = []
    for i, seg_df in enumerate(seg_dfs):
        # 段内数据太少（如 <30 根）则该段标记为跳过，不参与统计
        if len(seg_df) < 30:
            seg_reports.append(
                {
                    "label": f"分段{i + 1}",
                    "bars": len(seg_df),
                    "skipped": True,
                    "note": "段内数据不足",
                }
            )
            continue
        try:
            strategy = strategy_factory()
            engine = BacktestEngine(
                strategy=strategy,
                cash=cash,
                commission=commission,
                stamp_tax=stamp_tax,
                slippage=slippage,
                execution=execution,
            )
            seg_result = engine.run(seg_df)
            perf = seg_result.performance
            closes = seg_df["close"].to_numpy(dtype=float)
            buy_hold = float(closes[-1] / closes[0] - 1.0) if len(closes) > 1 and closes[0] else 0.0
            seg_reports.append(
                {
                    "label": f"分段{i + 1}",
                    "bars": len(seg_df),
                    "skipped": False,
                    "start": _fmt_first_dt(seg_df),
                    "end": _fmt_last_dt(seg_df),
                    "total_return": float(perf.get("total_return", 0.0)),
                    "win_rate": float(perf.get("win_rate", 0.0)),
                    "sharpe": float(perf.get("sharpe", 0.0)),
                    "max_drawdown": float(perf.get("max_drawdown", 0.0)),
                    "trades": int(perf.get("total_trades", 0)),
                    "hit_rate": _seg_hit_rate(seg_result),
                    "buy_hold_return": buy_hold,
                    "alpha": float(perf.get("total_return", 0.0)) - buy_hold,
                }
            )
        except Exception:
            seg_reports.append(
                {
                    "label": f"分段{i + 1}",
                    "bars": len(seg_df),
                    "skipped": True,
                    "note": "回测异常",
                }
            )

    valid = [s for s in seg_reports if not s.get("skipped")]
    if len(valid) < 2:
        return {
            "segments": seg_reports,
            "consistency": {},
            "overfit_likely": False,
            "verdict": "有效分段不足 2 段，无法评估稳健性",
            "note": "有效分段不足",
        }

    # ── 一致性统计 ───────────────────────────────────────────────────────────
    rets = np.asarray([s["total_return"] for s in valid], dtype=float)
    wins = np.asarray([s["win_rate"] for s in valid], dtype=float)
    hits = np.asarray(
        [s["hit_rate"] if s["hit_rate"] is not None else 0.0 for s in valid],
        dtype=float,
    )
    has_hit = any(s["hit_rate"] is not None for s in valid)
    alphas = np.asarray([s["alpha"] for s in valid], dtype=float)
    positive_ratio = float(np.mean(rets > 0))
    beat_bh_ratio = float(np.mean(alphas > 0))

    win_std = float(np.std(wins))
    win_cv = float(win_std / abs(np.mean(wins))) if abs(np.mean(wins)) > 1e-9 else 0.0
    hit_std = float(np.std(hits)) if has_hit else 0.0

    consistency: dict[str, Any] = {
        "segments_analyzed": len(valid),
        "positive_segment_ratio": positive_ratio,
        "beats_buy_hold_ratio": beat_bh_ratio,
        "win_rate_mean": float(np.mean(wins)),
        "win_rate_std": win_std,
        "win_rate_cv": win_cv,
        "hit_rate_mean": float(np.mean(hits)) if has_hit else None,
        "hit_rate_std": hit_std if has_hit else None,
        "return_mean": float(np.mean(rets)),
        "return_std": float(np.std(rets)),
        "best_segment": _best_segment_label(valid, rets),
        "worst_segment": _worst_segment_label(valid, rets),
    }

    # ── 过拟合判定 ───────────────────────────────────────────────────────────
    # 信号：多数分段不赚钱 / 不跑赢基准，或胜率离散度大 / 命中率离散度大
    signals: list[str] = []
    if positive_ratio < 0.6:
        signals.append(f"仅 {positive_ratio:.0%} 分段正收益")
    if beat_bh_ratio < 0.6:
        signals.append(f"仅 {beat_bh_ratio:.0%} 分段跑赢买入持有")
    if win_cv > 0.35 and len(valid) >= 3:
        signals.append(f"分段胜率离散度偏高(CV {win_cv:.2f})")
    if has_hit and hit_std > 0.15 and len(valid) >= 3:
        signals.append(f"分段命中率离散度偏高(σ {hit_std:.2f})")
    if len(valid) >= 3 and float(np.max(rets)) > 0 and float(np.min(rets)) < -0.15:
        signals.append("各段收益差距大(最好 vs 最差)")
    overfit = bool(signals) and len(valid) >= 2

    verdict = _build_verdict(valid, positive_ratio, beat_bh_ratio, win_cv, overfit)

    return {
        "segments": seg_reports,
        "consistency": consistency,
        "overfit_likely": overfit,
        "verdict": verdict,
        "note": None,
    }


def _fmt_first_dt(df: pd.DataFrame) -> str:
    col = "datetime" if "datetime" in df.columns else "date"
    if col in df.columns and len(df) > 0:
        return str(df[col].iloc[0])[:10]
    return ""


def _fmt_last_dt(df: pd.DataFrame) -> str:
    col = "datetime" if "datetime" in df.columns else "date"
    if col in df.columns and len(df) > 0:
        return str(df[col].iloc[-1])[:10]
    return ""


def _best_segment_label(valid: list[dict[str, Any]], rets: np.ndarray) -> str:
    if len(valid) == 0 or len(rets) == 0:
        return ""
    idx = int(np.argmax(rets))
    return str(valid[idx]["label"])


def _worst_segment_label(valid: list[dict[str, Any]], rets: np.ndarray) -> str:
    if len(valid) == 0 or len(rets) == 0:
        return ""
    idx = int(np.argmin(rets))
    return str(valid[idx]["label"])


def _build_verdict(
    valid: list[dict[str, Any]],
    positive_ratio: float,
    beat_bh_ratio: float,
    win_cv: float,
    overfit: bool,
) -> str:
    """根据一致性统计生成一句人类可读结论。"""
    n = len(valid)
    parts = [f"共 {n} 段"]
    parts.append(f"{positive_ratio:.0%} 段正收益")
    parts.append(f"{beat_bh_ratio:.0%} 段跑赢买入持有")
    joined = "；".join(parts) + "。"
    if overfit:
        return joined + "⚠ 各段表现不一致，存在过拟合/行情依赖风险，全时段成绩可能不可持续。"
    return joined + "各段表现较一致，模型稳健性尚可。"
