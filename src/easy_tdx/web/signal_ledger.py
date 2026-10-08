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

⚠️ **全局单位契约（V736）：本模块所有前瞻收益一律是「小数」**
────────────────────────────────────────────────────────────
  0.2727 表示 +27.27%；-0.05 表示 -5%。**不是** 27.27 / -5。

历史 bug（已修）：``forward_returns`` 曾返回百分数（27.27），而下游
``backtest/signal_accuracy.py::_horizon_stats`` 与 ``audit/accuracy.py``
一直是小数口径 —— 相差 **100 倍**。修复前 ``compute_signal_accuracy_by_type``
已把台账的百分数直接喂进 ``_horizon_stats``（见 signal_accuracy.py 的
``_signal_type_stats``），导致 `by_type` 的 avg_return / median_return /
ranking.avg_return 被真实放大 100 倍，且 UI ``fmtPct`` 再乘一次 100。
统一到小数的实测依据：
- ``_horizon_stats`` / ``_safe_fwd`` 的随机基线（baseline_avg_return）本来
  就是小数，改百分数会让 avg_return 与 baseline_avg_return 在同 dict 内
  再错 100 倍（实测 verdict 打印 "+4545.45%" 而非 "+50.00%"）；
- 前端 ``fmtPct`` 约定 ``fmtPct(0.1234) === "12.34%"``（输入必须是小数）；
- 百分比（hit_rate 类）是比率 [0,1]，与收益小数量纲一致。
改本模块的单位换算会让 ``tests/unit/test_forward_return_unit_contract.py``
失败，那是护栏，不要绕过。
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
    # ⚠️ 字段名虽含 `_pct` 历史包袱，但**值是小数**：0.2727 == +27.27%。
    # 见 forward_returns 的单位契约 docstring。
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

    ⚠️ 单位契约（小数，非百分数）：返回值为**小数**。
    例：0.2727 表示 +27.27%；-0.05 表示 -5%。
    历史版本曾返回 27.27（百分数），与
    ``backtest/signal_accuracy.py::_horizon_stats`` 的口径相差 100 倍
    （后者一直是小数）。本次统一到小数，因为 pandas/numpy 生态、
    ``signal_accuracy`` 的 ``_safe_fwd``/``_horizon_stats`` 基线均值、
    以及前端 ``fmtPct``（``fmtPct(0.1234) === "12.34%"``）全部按小数口径；
    百分数在加减/二次聚合时会再错一次。
    跨实现喂数前请重读本段——单位不一致会让所有收益结论错 100 倍。

    Returns:
        (方向无关原始收益, 指数同窗收益或None, 个股-指数超额或None)
        单位统一为**小数**（0.2727 == +27.27%）；数据不足时三者均为 None。
    """
    arr = np.asarray(closes, dtype=float)
    n = len(arr)
    j = bar_index + horizon
    if bar_index < 0 or bar_index >= n or j >= n:
        return (None, None, None)
    base = float(arr[bar_index])
    if base == 0:
        return (None, None, None)
    raw = float(arr[j]) / base - 1.0
    bench: float | None = None
    excess: float | None = None
    if index_closes is not None and len(index_closes) == n:
        iarr = np.asarray(index_closes, dtype=float)
        ibase = float(iarr[bar_index])
        if ibase:
            bench = float(iarr[j]) / ibase - 1.0
            excess = raw - bench
    return (raw, bench, excess)


def signal_returns(
    closes: list[float] | np.ndarray,
    signals: list[dict[str, Any]],
    horizons: tuple[int, ...] = (3, 5, 10, 20, 60),
    index_closes: list[float] | np.ndarray | None = None,
) -> list[SignalReturnRecord]:
    """对信号列表逐条计算前瞻收益记录（唯一口径实现）。

    ⚠️ 单位契约（小数，非百分数）：产出记录的 ret_pct / raw_ret_pct /
    excess_pct **均为小数**（0.2727 == +27.27%）。与 forward_returns 同口径，
    与 ``backtest/signal_accuracy.py::_horizon_stats`` 也同为小数，可直接跨实现
    喂数。字段名里的 ``_pct`` 是历史包袱，不代表单位是百分数。

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
        direction = (
            "buy" if ("buy" in sig_type.lower() or sig_type.lower().endswith("b")) else "sell"
        )
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

    ⚠️ 单位契约（小数，非百分数）：avg_return / excess_avg_return **为小数**
    （0.0433 == +4.33%），与 ``backtest/signal_accuracy.py::_horizon_stats``
    的 avg_return 同口径，两者可直接对账。
    hit_rate / excess_hit_rate 是 [0,1] 区间的比率（非百分数）。

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
