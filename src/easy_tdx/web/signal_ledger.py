"""信号 → N 根收益统一台账（V722，R4 口径统一）。

此前系统里有三处各自实现「信号之后 N 根收益」的口径：

1. `backtest/signal_accuracy.py :: compute_signal_accuracy_by_type`
   （/stock-pick/timing 的 signal_quality 面板）——收盘价对收盘价、
   信号后 N 根、随机入场基准对比；
2. `backtest/chanlun_validator.py`——止损止盈模拟（盘口高低价触发）；
3. accuracy 审计管道（本变更新增）。

本模块是**唯一实现**：面板与审计都必须调用这里，口径漂移在单测层被
拦截（同一输入两处消费输出必须逐值一致）。

设计：
- 收益定义：从信号 bar 的**下一根**开盘/收盘起算（避免信号 bar 收盘价
  未定的未来函数），默认 close-to-close；
- 超额：个股收益 − 同窗口指数收益（无指数数据时退化为绝对收益，
  excess=None）；
- 聚合：hit_rate / excess_hit_rate / avg_return / excess_avg_return。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class SignalReturnRecord:
    """单个信号的前瞻收益记录。"""

    signal_type: str
    bar_index: int
    direction: str  # buy / sell
    horizon: int
    ret_pct: float | None  # 信号方向的前瞻收益（buy 用涨、sell 用跌为正）
    raw_ret_pct: float | None  # 原始 N 根涨跌幅（方向无关）
    excess_pct: float | None  # 相对指数的超额（方向化）
    meta: dict[str, Any] = field(default_factory=dict)


def forward_returns(
    closes: list[float] | np.ndarray,
    bar_index: int,
    horizon: int,
    index_closes: list[float] | np.ndarray | None = None,
) -> tuple[float | None, float | None, float | None]:
    """信号 bar 之后 horizon 根的收益三元组。

    Returns:
        (方向无关原始收益%, 指数同窗收益%或None, 个股-指数超额%或None)
        数据不足时三者均为 None。
    """
    arr = np.asarray(closes, dtype=float)
    n = len(arr)
    j = bar_index + horizon
    if bar_index < 0 or bar_index >= n or j >= n:
        return (None, None, None)
    base = float(arr[bar_index])
    if base == 0:
        return (None, None, None)
    raw = (float(arr[j]) / base - 1) * 100
    bench: float | None = None
    excess: float | None = None
    if index_closes is not None and len(index_closes) == n:
        iarr = np.asarray(index_closes, dtype=float)
        ibase = float(iarr[bar_index])
        if ibase:
            bench = (float(iarr[j]) / ibase - 1) * 100
            excess = raw - bench
    return (raw, bench, excess)


def signal_returns(
    closes: list[float] | np.ndarray,
    signals: list[dict[str, Any]],
    horizons: tuple[int, ...] = (3, 5, 10, 20, 60),
    index_closes: list[float] | np.ndarray | None = None,
) -> list[SignalReturnRecord]:
    """对信号列表逐条计算前瞻收益记录（唯一口径实现）。

    Args:
        closes: 收盘价序列（与 K 线一一对应）。
        signals: [{"type": "1buy", "bar_index": int}, ...]；type 含
            "buy"/"b" 视为多头方向，否则空头。
        horizons: 前瞻窗口（根数）。
        index_closes: 可选指数收盘序列（等长），提供时计算超额。

    Returns:
        SignalReturnRecord 列表（跳过 bar_index 缺失与越界的信号）。
    """
    records: list[SignalReturnRecord] = []
    for sig in signals:
        bar_index = sig.get("bar_index")
        if bar_index is None:
            continue
        bar_index = int(bar_index)
        sig_type = str(sig.get("type", ""))
        direction = "buy" if ("buy" in sig_type.lower() or sig_type.lower().endswith("b")) else "sell"
        for h in horizons:
            raw, bench, excess = forward_returns(closes, bar_index, h, index_closes)
            if raw is None:
                continue
            sign = 1.0 if direction == "buy" else -1.0
            records.append(
                SignalReturnRecord(
                    signal_type=sig_type,
                    bar_index=bar_index,
                    direction=direction,
                    horizon=h,
                    ret_pct=round(sign * raw, 4),
                    raw_ret_pct=round(raw, 4),
                    excess_pct=round(sign * excess, 4) if excess is not None else None,
                    meta={"type": sig_type},
                )
            )
    return records


def aggregate_signal_returns(
    records: list[SignalReturnRecord],
    *,
    by_type: bool = True,
) -> dict[str, Any]:
    """聚合信号收益记录为命中率/平均收益统计（面板与审计共用）。

    Returns:
        {"overall": {...}, "by_type": {类型: {...}}}；
        每档含 signals/hit_rate/excess_hit_rate/avg_return/excess_avg_return。
    """
    def _agg(rs: list[SignalReturnRecord]) -> dict[str, Any]:
        if not rs:
            return {
                "signals": 0,
                "hit_rate": None,
                "excess_hit_rate": None,
                "avg_return": None,
                "excess_avg_return": None,
            }
        rets = [r.ret_pct for r in rs if r.ret_pct is not None]
        excess = [r.excess_pct for r in rs if r.excess_pct is not None]
        return {
            "signals": len(rs),
            "hit_rate": round(sum(1 for v in rets if v > 0) / len(rets), 4) if rets else None,
            "excess_hit_rate": (
                round(sum(1 for v in excess if v > 0) / len(excess), 4) if excess else None
            ),
            "avg_return": round(float(np.mean(rets)), 4) if rets else None,
            "excess_avg_return": round(float(np.mean(excess)), 4) if excess else None,
        }

    overall = _agg(records)
    grouped: dict[str, list[SignalReturnRecord]] = {}
    if by_type:
        for r in records:
            grouped.setdefault(r.signal_type, []).append(r)
    return {
        "overall": overall,
        "by_type": {t: _agg(rs) for t, rs in sorted(grouped.items())},
    }
