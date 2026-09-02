"""V102 决策支持建议的执行模拟器。

把缠论模型给出的可执行建议（入场价/止损/止盈/最大持有根数）放到历史 K 线上
逐根回放，回答「按这条建议执行，这笔交易会以什么价格出场、赚还是亏」：

- 入场后从下一根 K 线开始扫描（信号当日已收盘，次日执行）
- 某根 low <= stop_loss（向下穿越止损）→ 以止损价出场（止损优先，保守假设）
- 某根 high >= take_profit_1（向上穿越止盈）→ 以止盈价出场
- 超过 max_hold 根未触发 → 以最后一根收盘价结算

与回测引擎的区别：不模拟资金/仓位/滑点，只验证建议的价位可执行性与期望收益
特征，供用户核对模型给出的「入场/止损/止盈」是否合理、经历史回放是否有效。
"""

from __future__ import annotations

from typing import Any


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

    Returns:
        dict：{exit_idx, exit_price, exit_reason, return_pct, profit}
    """
    n = len(closes)
    if entry_idx < 0 or entry_idx + 1 >= n:
        return {
            "exit_idx": entry_idx,
            "exit_price": entry_price,
            "exit_reason": "invalid",
            "return_pct": 0.0,
            "profit": 0.0,
        }

    # 本模拟器面向买入类建议（止损在下方、止盈在上方）；
    # 卖出类建议先由上层换算为等价的「做多模拟」或直接跳过。
    if stop_loss <= 0 or take_profit_1 <= stop_loss:
        return {
            "exit_idx": entry_idx,
            "exit_price": entry_price,
            "exit_reason": "invalid",
            "return_pct": 0.0,
            "profit": 0.0,
        }

    stop_price = stop_loss
    tp_price = take_profit_1

    exit_idx = entry_idx + max_hold
    exit_reason = "expire"
    last_close = closes[min(exit_idx, n - 1)]
    # 到期结算价：最后一根被判断 K 线的收盘（若越界取序列末尾）
    for i in range(entry_idx + 1, min(entry_idx + 1 + max_hold, n)):
        if lows[i] <= stop_price:
            exit_idx = i
            exit_price = stop_price
            exit_reason = "stop"
            break
        if highs[i] >= tp_price:
            exit_idx = i
            exit_price = tp_price
            exit_reason = "tp1"
            break
    else:
        exit_idx = min(entry_idx + max_hold, n - 1)
        exit_price = last_close
        exit_reason = "expire"

    return_pct = round((exit_price - entry_price) / entry_price * 100.0, 2) if entry_price else 0.0
    return {
        "exit_idx": exit_idx,
        "exit_price": round(exit_price, 4),
        "exit_reason": exit_reason,
        "return_pct": return_pct,
        "profit": round(exit_price - entry_price, 4),
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
        advices: 每条含 entry_idx/entry_price/stop_loss/take_profit_1/max_hold

    Returns:
        dict：{trades: [单笔结果], count, win_rate, avg_return, total_return,
               stop_rate, tp_rate, expire_rate}
    """
    trades: list[dict[str, Any]] = []
    for adv in advices:
        idx = int(adv.get("entry_idx", -1))
        entry = float(adv.get("entry_price", 0.0) or 0.0)
        stop = float(adv.get("stop_loss", 0.0) or 0.0)
        tp1 = float(adv.get("take_profit_1", 0.0) or 0.0)
        hold = int(adv.get("max_hold", 10) or 10)
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
            )
        )

    if not trades:
        return {"trades": [], "count": 0, "win_rate": 0.0, "avg_return": 0.0, "total_return": 0.0}

    wins = [t for t in trades if t["return_pct"] > 0]
    avg = sum(t["return_pct"] for t in trades) / len(trades)
    total = sum(t["return_pct"] for t in trades)
    kinds = {"stop": 0, "tp1": 0, "expire": 0}
    for t in trades:
        kinds[t["exit_reason"]] = kinds.get(t["exit_reason"], 0) + 1

    return {
        "trades": trades,
        "count": len(trades),
        "win_rate": round(len(wins) / len(trades), 4),
        "avg_return": round(avg, 2),
        "total_return": round(total, 2),
        "stop_rate": round(kinds["stop"] / len(trades), 4),
        "tp_rate": round(kinds["tp1"] / len(trades), 4),
        "expire_rate": round(kinds["expire"] / len(trades), 4),
    }
