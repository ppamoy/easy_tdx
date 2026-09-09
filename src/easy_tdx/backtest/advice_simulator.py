"""V102 决策支持建议的执行模拟器。

把缠论模型给出的可执行建议（入场价/止损/止盈/最大持有根数）放到历史 K 线上
逐根回放，回答「按这条建议执行，这笔交易会以什么价格出场、赚还是亏」：

- 入场后从下一根 K 线开始扫描（信号当日已收盘，次日执行）
- 买入建议（direction="long"）：low <= 止损 → 亏损出场；high >= 止盈 → 盈利出场
- 卖出建议（direction="short"）：high >= 止损 → 亏损出场；low <= 止盈 → 盈利出场
- 超过 max_hold 根未触发 → 以最后一根收盘价结算
- 同一根 K 线同时触发止损与止盈时，止损优先（保守假设）

与回测引擎的区别：不模拟资金/仓位/滑点，只验证建议的价位可执行性与期望收益
特征，供用户核对模型给出的「入场/止损/止盈」是否合理、经历史回放是否有效。
"""

from __future__ import annotations

from typing import Any


def _invalid(entry_idx: int, entry_price: float) -> dict[str, Any]:
    return {
        "exit_idx": entry_idx,
        "exit_price": round(entry_price, 4),
        "exit_reason": "invalid",
        "return_pct": 0.0,
        "profit": 0.0,
    }


def simulate_advice_trade(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    *,
    entry_idx: int,
    entry_price: float,
    stop_loss: float,
    take_profit_1: float,
    max_hold: int = 10,
    direction: str = "long",
) -> dict[str, Any]:
    """模拟单笔按建议执行的交易。

    Args:
        highs: 最高价序列（与 K 线一一对应）
        lows: 最低价序列
        closes: 收盘价序列
        entry_idx: 入场信号所在的 K 线索引（下一根开始执行）
        entry_price: 建议入场价
        stop_loss: 建议止损价
        take_profit_1: 第一止盈价
        max_hold: 最大持有根数（超出未触发按收盘结算）
        direction: "long"（买入：止损<止盈）或 "short"（卖出：止损>止盈）

    Returns:
        dict：{exit_idx, exit_price, exit_reason, return_pct, profit}
    """
    n = len(closes)
    if entry_idx < 0 or entry_idx + 1 >= n or entry_price <= 0:
        return _invalid(entry_idx, entry_price)

    direction = str(direction or "long").lower()
    if direction not in ("long", "short"):
        return _invalid(entry_idx, entry_price)

    if direction == "long":
        if stop_loss <= 0 or take_profit_1 <= stop_loss:
            return _invalid(entry_idx, entry_price)
        stop_price = stop_loss
        tp_price = take_profit_1
    else:
        if stop_loss <= 0 or take_profit_1 >= stop_loss:
            return _invalid(entry_idx, entry_price)
        stop_price = stop_loss
        tp_price = take_profit_1

    exit_idx = min(entry_idx + max_hold, n - 1)
    exit_reason = "expire"
    exit_price = closes[exit_idx]
    mae_price = entry_price  # V439: 最大不利偏移跟踪（long 用最低，short 用最高）
    mfe_price = entry_price  # V440: 最大有利偏移跟踪（long 用最高，short 用最低）

    last_check = min(entry_idx + 1 + max_hold, n)
    for i in range(entry_idx + 1, last_check):
        if direction == "long":
            mae_price = min(mae_price, lows[i])
            mfe_price = max(mfe_price, highs[i])
            stop_hit = lows[i] <= stop_price
            tp_hit = highs[i] >= tp_price
        else:
            mae_price = max(mae_price, highs[i])
            mfe_price = min(mfe_price, lows[i])
            stop_hit = highs[i] >= stop_price
            tp_hit = lows[i] <= tp_price

        if stop_hit:
            exit_idx = i
            exit_price = stop_price
            exit_reason = "stop"
            break
        if tp_hit:
            exit_idx = i
            exit_price = tp_price
            exit_reason = "tp1"
            break
    else:
        exit_idx = min(entry_idx + max_hold, n - 1)
        exit_price = closes[exit_idx]
        exit_reason = "expire"

    raw_return = (exit_price - entry_price) / entry_price * 100.0
    return_pct = round(raw_return if direction == "long" else -raw_return, 2)
    # V439: 最大不利偏移 MAE（方向对齐后的最大浮亏百分比，负值）
    # V440: 最大有利偏移 MFE（方向对齐后的最大浮盈百分比，正值）
    if direction == "long":
        mae_pct = round((mae_price - entry_price) / entry_price * 100.0, 2)
        mfe_pct = round((mfe_price - entry_price) / entry_price * 100.0, 2)
    else:
        mae_pct = round(-(mae_price - entry_price) / entry_price * 100.0, 2)
        mfe_pct = round(-(mfe_price - entry_price) / entry_price * 100.0, 2)
    return {
        "exit_idx": exit_idx,
        "exit_price": round(exit_price, 4),
        "exit_reason": exit_reason,
        "holding_bars": exit_idx - entry_idx,
        "return_pct": return_pct,
        "mae_pct": mae_pct,
        "mfe_pct": mfe_pct,
        "profit": round((exit_price - entry_price) * (1 if direction == "long" else -1), 4),
    }


def simulate_advice_batch(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    advices: list[dict[str, Any]],
) -> dict[str, Any]:
    """批量模拟一组建议，输出聚合统计。

    Args:
        highs / lows / closes: K 线序列
        advices: 每条含 entry_idx/entry_price/stop_loss/take_profit_1/max_hold，
            可选 direction（long/short，默认 long）

    Returns:
        dict：{trades: [单笔结果], count, win_rate, avg_return, median_return,
               total_return, profit_factor, long_stats, short_stats,
               stop_rate, tp_rate, expire_rate}
    """
    trades: list[dict[str, Any]] = []
    trade_directions: list[str] = []  # V465: 与 trades 同步，供多空分组统计
    for adv in advices:
        idx = int(adv.get("entry_idx", -1))
        entry = float(adv.get("entry_price", 0.0) or 0.0)
        stop = float(adv.get("stop_loss", 0.0) or 0.0)
        tp1 = float(adv.get("take_profit_1", 0.0) or 0.0)
        hold = int(adv.get("max_hold", 10) or 10)
        direction = str(adv.get("direction", "long") or "long")
        if idx < 0 or entry <= 0 or stop <= 0 or tp1 <= 0:
            continue
        trades.append(
            simulate_advice_trade(
                highs,
                lows,
                closes,
                entry_idx=idx,
                entry_price=entry,
                stop_loss=stop,
                take_profit_1=tp1,
                max_hold=hold,
                direction=direction,
            )
        )
        trade_directions.append(direction)

    if not trades:
        return {"trades": [], "count": 0, "win_rate": 0.0, "avg_return": 0.0, "total_return": 0.0}

    wins = [t for t in trades if t["return_pct"] > 0]
    avg = sum(t["return_pct"] for t in trades) / len(trades)
    total = sum(t["return_pct"] for t in trades)
    # V463: 中位数收益（比均值稳健）
    n = len(trades)
    sorted_ret = sorted(t["return_pct"] for t in trades)
    mid = n // 2
    median_return = (
        sorted_ret[mid] if n % 2 == 1 else (sorted_ret[mid - 1] + sorted_ret[mid]) / 2
    )
    # V465: 多空分开统计（买点/卖点信号的不对称表现）
    def _dir_stats(rets: list[float]) -> dict[str, Any]:
        if not rets:
            return {"count": 0, "win_rate": 0.0, "avg_return": 0.0}
        return {
            "count": len(rets),
            "win_rate": round(sum(1 for r in rets if r > 0) / len(rets), 4),
            "avg_return": round(sum(rets) / len(rets), 2),
        }

    long_rets = [
        t["return_pct"] for t, d in zip(trades, trade_directions) if d == "long"
    ]
    short_rets = [
        t["return_pct"] for t, d in zip(trades, trade_directions) if d == "short"
    ]
    long_stats = _dir_stats(long_rets)
    short_stats = _dir_stats(short_rets)
    kinds = {"stop": 0, "tp1": 0, "expire": 0}
    for t in trades:
        kinds[t["exit_reason"]] = kinds.get(t["exit_reason"], 0) + 1

    # V435: 盈亏比 = 平均盈利 / 平均亏损（仅盈利取 999 避免 JSON inf）
    gains = [t["return_pct"] for t in trades if t["return_pct"] > 0]
    losses = [t["return_pct"] for t in trades if t["return_pct"] < 0]
    avg_gain = sum(gains) / len(gains) if gains else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    if avg_loss > 0:
        profit_factor = round(avg_gain / avg_loss, 2)
    elif avg_gain > 0:
        profit_factor = 999.0
    else:
        profit_factor = 0.0

    return {
        "trades": trades,
        "count": len(trades),
        "win_rate": round(len(wins) / len(trades), 4),
        "avg_return": round(avg, 2),
        "median_return": round(median_return, 2),
        "total_return": round(total, 2),
        "profit_factor": profit_factor,
        "long_stats": long_stats,
        "short_stats": short_stats,
        "stop_rate": round(kinds["stop"] / len(trades), 4),
        "tp_rate": round(kinds["tp1"] / len(trades), 4),
        "expire_rate": round(kinds["expire"] / len(trades), 4),
    }


def collect_signal_advices(
    result: Any,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    max_hold: int,
) -> list[dict[str, Any]]:
    """从缠论结果中提取 3买/3卖 信号的可回放建议（V102 条件266）。

    对每个 3买/3卖 信号，用截至信号日的行情窗口生成 入场/止损/止盈 建议，
    输出供 simulate_advice_batch 回放的建议条目（含方向 long/short）。

    Args:
        result: ChanlunAnalyser 的分析结果（含 mmds）
        closes / highs / lows: 与 K 线一一对应的价格序列
        max_hold: 建议最大持有根数

    Returns:
        list[dict]：每条含 entry_idx/entry_price/stop_loss/take_profit_1/max_hold/direction
    """
    from easy_tdx.chanlun.mmd_v102 import _calc_decision_support_enhanced
    from easy_tdx.chanlun.types import MMDType

    advices: list[dict[str, Any]] = []
    for mmd in result.mmds:
        if mmd.mmd_type not in (MMDType.BUY_3, MMDType.SELL_3) or mmd.bi is None:
            continue
        end_k = getattr(mmd.bi.end, "k", None)
        idx = getattr(end_k, "k_index", None)
        if idx is None:
            idx = getattr(mmd.bi.end, "index", None)
        if idx is None or idx < 0 or idx >= len(closes):
            continue
        window_end = min(idx + 1, len(closes))
        decision = _calc_decision_support_enhanced(
            mmd,
            closes[:window_end],
            highs[:window_end],
            lows[:window_end],
            None,
            None,
        )
        if not decision or not decision.get("entry_price") or decision["entry_price"] <= 0:
            continue
        advices.append(
            {
                "entry_idx": idx,
                "entry_price": decision["entry_price"],
                "stop_loss": decision["stop_loss"],
                "take_profit_1": decision["take_profit_1"],
                "max_hold": max_hold,
                "direction": "long" if mmd.mmd_type == MMDType.BUY_3 else "short",
            }
        )
    return advices


def simulate_advice_hold_sweep(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    advices: list[dict[str, Any]],
    holds: tuple[int, ...] = (3, 5, 10, 20),
) -> dict[str, dict[str, Any]]:
    """V444: 多持有期敏感性分析——同一批建议用不同 max_hold 模拟。

    返回 {持有根数: simulate_advice_batch 结果}，帮助评估建议对持有期的
    敏感性，选择合适的止盈/到期窗口。
    """
    out: dict[str, dict[str, Any]] = {}
    for h in holds:
        advices_h = [{**a, "max_hold": int(h)} for a in advices]
        out[str(h)] = simulate_advice_batch(highs, lows, closes, advices_h)
    return out


def summarize_batch(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """聚合多只标的的回放报告（批量实证汇总）。

    Args:
        reports: 每只标的的 simulate_advice_batch 结果（无交易则跳过该标的）

    Returns:
        dict：{symbols, advice_count, win_rate, avg_return, median_return,
               total_return, profit_factor, avg_mae_pct, avg_mfe_pct,
               stop_rate, tp_rate, expire_rate, positive_symbols}
    """
    merged: list[dict[str, Any]] = []
    symbol_count = 0
    positive_symbols = 0
    for r in reports:
        trades = r.get("trades") or []
        if not trades:
            continue
        symbol_count += 1
        merged.extend(trades)
        if sum(t["return_pct"] for t in trades) > 0:
            positive_symbols += 1

    if not merged:
        return {
            "symbols": 0,
            "advice_count": 0,
            "win_rate": 0.0,
            "avg_return": 0.0,
            "total_return": 0.0,
            "stop_rate": 0.0,
            "tp_rate": 0.0,
            "expire_rate": 0.0,
            "positive_symbols": 0,
        }

    n = len(merged)
    wins = [t for t in merged if t["return_pct"] > 0]
    avg = sum(t["return_pct"] for t in merged) / n
    total = sum(t["return_pct"] for t in merged)
    # V461: 中位数收益（比均值稳健，不受极值影响）
    sorted_ret = sorted(t["return_pct"] for t in merged)
    mid = n // 2
    median_return = (
        sorted_ret[mid] if n % 2 == 1 else (sorted_ret[mid - 1] + sorted_ret[mid]) / 2
    )
    kinds = {"stop": 0, "tp1": 0, "expire": 0}
    for t in merged:
        kinds[t["exit_reason"]] = kinds.get(t["exit_reason"], 0) + 1

    # V436: 聚合盈亏比 = 平均盈利 / 平均亏损
    gains = [t["return_pct"] for t in merged if t["return_pct"] > 0]
    losses = [t["return_pct"] for t in merged if t["return_pct"] < 0]
    avg_gain = sum(gains) / len(gains) if gains else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    if avg_loss > 0:
        profit_factor = round(avg_gain / avg_loss, 2)
    elif avg_gain > 0:
        profit_factor = 999.0
    else:
        profit_factor = 0.0

    # V442: 平均最大不利/有利偏移
    avg_mae_pct = round(sum(t.get("mae_pct", 0.0) for t in merged) / n, 2)
    avg_mfe_pct = round(sum(t.get("mfe_pct", 0.0) for t in merged) / n, 2)

    return {
        "symbols": symbol_count,
        "advice_count": n,
        "win_rate": round(len(wins) / n, 4),
        "avg_return": round(avg, 2),
        "median_return": round(median_return, 2),
        "total_return": round(total, 2),
        "profit_factor": profit_factor,
        "avg_mae_pct": avg_mae_pct,
        "avg_mfe_pct": avg_mfe_pct,
        "stop_rate": round(kinds["stop"] / n, 4),
        "tp_rate": round(kinds["tp1"] / n, 4),
        "expire_rate": round(kinds["expire"] / n, 4),
        "positive_symbols": positive_symbols,
    }
