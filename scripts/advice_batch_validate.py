#!/usr/bin/env python3
"""V102 建议批量实证：对多只标的跑 3买/3卖 建议回放，汇总「按建议执行」vs 买入持有。

运行方式：
    cd /home/skp/workspace/easy_tdx
    source .venv/bin/activate
    python scripts/advice_batch_validate.py SZ 000001 SH 600519
    # 或用文件：每行 'MARKET CODE'
    python scripts/advice_batch_validate.py --file symbols.txt
    python scripts/advice_batch_validate.py --max-hold 15

说明：
- 对每只标的拉日线 → 缠论分析 → 对 3买/3卖 信号生成 V102 建议（入场/止损/止盈）
  → 用 advice_simulator 逐笔回放（止损/止盈/到期）→ 输出该标的胜率/平均收益/出场分布
- 同时输出该标的整段「买入持有」收益作为大环境参照；
- 最后用 summarize_batch 聚合全部标的：总建议数/胜率/平均收益/正收益标的占比。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _run_symbol(
    client: object,
    market: str,
    code: str,
    period: str,
    count: int,
    max_hold: int,
) -> dict:
    """对单只标的执行 V102 建议回放，返回明细行（含买入持有对照）。"""
    from easy_tdx.backtest.advice_simulator import collect_signal_advices, simulate_advice_batch
    from easy_tdx.chanlun.analyser import ChanlunAnalyser
    from easy_tdx.cli.parsers import parse_market, parse_period

    symbol = f"{market}{code}"
    df = client.get_stock_kline(  # type: ignore[attr-defined]
        parse_market(market),
        code,
        period=parse_period(period),
        start=0,
        count=count,
    )
    if df is None or len(df) < 30:
        return {"symbol": symbol, "error": "行情数据不足（<30 根），无法回放建议"}

    analyser = ChanlunAnalyser(code=code, frequency=period)
    result = analyser.process_klines(df)
    closes = [float(k.close) for k in result.klines]
    highs = [float(k.high) for k in result.klines]
    lows = [float(k.low) for k in result.klines]
    buy_hold = round((closes[-1] / closes[0] - 1) * 100, 2) if closes and closes[0] > 0 else 0.0

    advices = collect_signal_advices(result, closes, highs, lows, max_hold)
    row: dict = {
        "symbol": symbol,
        "signal_count": len(result.mmds),
        "advice_count": len(advices),
        "buy_hold_return": buy_hold,
    }
    if not advices:
        return row

    report = simulate_advice_batch(highs, lows, closes, advices)
    for key in ("win_rate", "avg_return", "total_return", "stop_rate", "tp_rate", "expire_rate"):
        row[key] = report[key]
    row["report"] = report
    return row


def main() -> int:
    ap = argparse.ArgumentParser(
        description="V102 建议批量实证：多标的 3买/3卖 建议回放汇总 vs 买入持有",
    )
    ap.add_argument("symbols", nargs="*", help="标的列表，如 'SZ 000001 SH 600519'")
    ap.add_argument("--file", default=None, help="每行一个 'MARKET CODE' 的标的文件")
    ap.add_argument("--period", default="DAILY", help="K线周期")
    ap.add_argument("--count", type=int, default=500, help="K线数量")
    ap.add_argument("--max-hold", type=int, default=10, help="建议最大持有根数")
    args = ap.parse_args()

    symbols: list[tuple[str, str]] = []
    sym = args.symbols
    for i in range(0, len(sym) - 1, 2):
        symbols.append((sym[i].upper(), sym[i + 1]))
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) >= 2:
                    symbols.append((parts[0].upper(), parts[1]))
    if not symbols:
        symbols = [("SZ", "000001"), ("SH", "600519"), ("SZ", "000002")]

    from easy_tdx.backtest.advice_simulator import summarize_batch
    from easy_tdx.cli.conn import get_mac_client

    rows: list[dict] = []
    with get_mac_client() as client:
        for market, code in symbols:
            rows.append(_run_symbol(client, market, code, args.period, args.count, args.max_hold))

    summary = summarize_batch([r.get("report", {}) for r in rows])
    print(json.dumps({"rows": rows, "summary": summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
