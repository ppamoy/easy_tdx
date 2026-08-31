"""选股结果前瞻收益验证。

目标：让用户通过历史回测验证「选股模型选出来的股票，是否真的跑赢没选中的股票」，
而不是只看模型打了多少分。对一个历史选股日，把当天被选中的股票与整个扫描池
（含未被选中的）分别统计选股日后 N 个交易日的收益与命中率：

- 选中组平均前瞻收益 vs 池平均前瞻收益 → 超额收益（选股贡献）
- 选中组命中率（前瞻收益 > 0 的比例）vs 池命中率 → 超额命中率
- 结论：选中股票是否显著好于「闭眼随机从池里挑」

与回测信号准确度（V95/V96）互补：那边验证「择时/买卖点准不准」，本模块
验证「选股准不准」。纯计算模块，行情获取在路由层完成，便于单测。
"""

from __future__ import annotations

from typing import Any

import numpy as np

# 默认前瞻窗口（交易日根数）
DEFAULT_HORIZONS: tuple[int, ...] = (5, 10, 20, 60)


def _find_selection_index(dates: list[str], target: str) -> int | None:
    """找选股日对应 bar 索引：精确匹配选股日，否则取其后最近的交易日。

    Args:
        dates: 交易日字符串列表（YYYY-MM-DD）
        target: 选股日（YYYY-MM-DD）

    Returns:
        bar 索引；找不到（全部早于选股日）返回 None
    """
    if not dates:
        return None
    for i, d in enumerate(dates):
        if d >= target:
            return i
    return None


def _symbol_forward_returns(
    dates: list[str],
    closes: list[float],
    target: str,
    horizons: tuple[int, ...],
) -> dict[int, float | None]:
    """单只股票在选股日之后的各窗口前瞻收益。"""
    idx = _find_selection_index(dates, target)
    out: dict[int, float | None] = {}
    n = len(closes)
    for h in horizons:
        if idx is None or idx + h >= n:
            out[h] = None
            continue
        base = closes[idx]
        if not base:
            out[h] = None
            continue
        out[h] = float(closes[idx + h] / base - 1.0)
    return out


def compute_screening_verify(
    bars_by_symbol: dict[str, dict[str, Any]],
    selected_symbols: list[str],
    target_date: str,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[str, Any]:
    """计算选股结果前瞻收益验证报告。

    Args:
        bars_by_symbol: {symbol: {"datetime": [str...], "close": [float...]}}，
            覆盖整个扫描池（含选中的与未选中的）。
        selected_symbols: 选股日被模型选中的股票代码列表（须是池的子集）。
        target_date: 选股日 YYYY-MM-DD。
        horizons: 前瞻窗口（交易日根数）

    Returns:
        dict：{"date", "pool_size", "selected_size",
              "horizons": {h: {selected_avg, selected_hit, pool_avg, pool_hit,
                               excess_return, excess_hit_rate, selected_n, pool_n}},
              "verdict", "per_symbol": [...]}
        数据不足时相应统计为 0/None。
    """
    selected_set = set(selected_symbols)
    horizons_out: dict[str, Any] = {}
    per_symbol: list[dict[str, Any]] = []

    for symbol, bars in bars_by_symbol.items():
        dates = [str(d)[:10] for d in bars.get("datetime", [])]
        closes = [float(c) for c in bars.get("close", [])]
        fwd = _symbol_forward_returns(dates, closes, target_date, horizons)
        is_selected = symbol in selected_set
        per_symbol.append(
            {
                "symbol": symbol,
                "selected": is_selected,
                "has_selection_bar": any(v is not None for v in fwd.values()),
                "forward": {str(h): v for h, v in fwd.items()},
            }
        )

    for h in horizons:
        sel_rets = [
            p["forward"][str(h)]
            for p in per_symbol
            if p["selected"] and p["forward"][str(h)] is not None
        ]
        pool_rets = [
            p["forward"][str(h)]
            for p in per_symbol
            if p["forward"][str(h)] is not None
        ]
        sel_arr = np.asarray(sel_rets, dtype=float) if sel_rets else np.asarray([], dtype=float)
        pool_arr = np.asarray(pool_rets, dtype=float) if pool_rets else np.asarray([], dtype=float)
        entry: dict[str, Any] = {
            "selected_avg_return": float(np.mean(sel_arr)) if len(sel_arr) else None,
            "selected_hit_rate": float(np.mean(sel_arr > 0)) if len(sel_arr) else None,
            "selected_n": int(len(sel_arr)),
            "pool_avg_return": float(np.mean(pool_arr)) if len(pool_arr) else None,
            "pool_hit_rate": float(np.mean(pool_arr > 0)) if len(pool_arr) else None,
            "pool_n": int(len(pool_arr)),
        }
        if len(sel_arr) and len(pool_arr):
            entry["excess_return"] = float(np.mean(sel_arr) - np.mean(pool_arr))
            entry["excess_hit_rate"] = float(np.mean(sel_arr > 0) - np.mean(pool_arr > 0))
        else:
            entry["excess_return"] = None
            entry["excess_hit_rate"] = None
        horizons_out[str(h)] = entry

    verdict = _build_verify_verdict(horizons_out)
    return {
        "date": target_date,
        "pool_size": len(bars_by_symbol),
        "selected_size": len(selected_set),
        "horizons": horizons_out,
        "verdict": verdict,
        "per_symbol": per_symbol,
    }


def _build_verify_verdict(horizons_out: dict[str, Any]) -> str:
    """根据 10 日窗口（缺则 5/20）生成一句结论。"""
    h = horizons_out.get("10") or horizons_out.get("5") or horizons_out.get("20")
    if not h or h.get("selected_n", 0) == 0:
        return "选股日之后无足够行情样本，无法验证选股效果"
    if h.get("excess_return") is None or h.get("excess_hit_rate") is None:
        return "选中与未选中样本不足，无法可靠对比"
    excess_ret = float(h["excess_return"])
    excess_hit = float(h["excess_hit_rate"])
    sel_avg = float(h["selected_avg_return"])
    pool_avg = float(h["pool_avg_return"])
    n_sel = int(h["selected_n"])
    parts = [f"选中 {n_sel} 只，平均前瞻收益 {sel_avg:+.2%}（池平均 {pool_avg:+.2%}）"]
    if excess_ret > 0.01 and excess_hit > 0.03:
        grade = "选中股票显著跑赢未选中股票，选股模型具备参考价值"
    elif excess_ret > 0:
        grade = "选中股票略优于池平均，选股贡献有限但为正"
    elif excess_ret > -0.01:
        grade = "选中与未选中差异不大，选股择股贡献有限"
    else:
        grade = "选中股票跑输未选中股票，选股模型可能不具优势"
    parts.append(grade)
    parts.append(f"超额命中率 {excess_hit:+.1%}")
    return "；".join(parts) + "。"
