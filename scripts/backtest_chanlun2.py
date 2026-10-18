#!/usr/bin/env python3
"""chanlun2 模型回测：10只股票，日线，~12年。

策略：chanlun2 买卖点信号驱动
- buy1/buy2/buy3（含盘整背驰买）→ 满仓买入（若空仓）
- sell1/sell2/sell3（含盘整背驰卖）→ 清仓卖出（若持仓）
- 不做空、无杠杆、无滑点（简化基准对比）
- 对比基准：买入持有（首日收盘买入，末日收盘卖出）
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, "src")

from easy_tdx.chanlun2.analyser import analyze
from easy_tdx.chanlun2.types import KLine, MMDType

CACHE_D = Path("audit_data")

STOCKS = [
    ("SH", "600000", "浦发银行"),
    ("SH", "600036", "招商银行"),
    ("SH", "601318", "中国平安"),
    ("SH", "600276", "恒瑞医药"),
    ("SH", "600030", "中信证券"),
    ("SZ", "000333", "美的集团"),
    ("SZ", "000651", "格力电器"),
    ("SZ", "000725", "京东方A"),
    ("SZ", "300750", "宁德时代"),
    ("SZ", "002415", "海康威视"),
]


def load_klines(mkt, code):
    fp = CACHE_D / f"{mkt.lower()}{code}_daily.json"
    if not fp.exists():
        return None
    with open(fp) as f:
        data = json.load(f)
    return [
        KLine(
            index=i,
            dt=d["datetime"],
            open=float(d["open"]),
            high=float(d["high"]),
            low=float(d["low"]),
            close=float(d["close"]),
            volume=float(d.get("vol", 0)),
        )
        for i, d in enumerate(data)
    ]


def backtest_stock(klines):
    """单只股票回测：chanlun2 买卖点信号驱动。

    信号按 K 线位置排序，顺序执行：
    - 买点（buy1/buy2/buy3/panzheng_buy）→ 空仓则满仓买
    - 卖点（sell1/sell2/sell3/panzheng_sell）→ 持仓则清仓卖
    买卖价用信号点对应K线的收盘价（次日开盘更真实但简化用当日收盘）。
    """
    if not klines or len(klines) < 30:
        return None

    closes = [k.close for k in klines]
    result = analyze(klines, closes=closes)

    # 按K线位置排序买卖点
    mmds = sorted(result.mmds, key=lambda m: m.k_index)

    position = 0.0  # 持仓股数
    cash = 1.0  # 初始资金归一化
    entry_price = 0.0
    trades = 0
    wins = 0

    for m in mmds:
        if m.k_index >= len(klines):
            continue
        price = klines[m.k_index].close
        if m.mmd_type.is_buy:
            if position == 0:  # 空仓才买
                position = cash / price
                entry_price = price
                cash = 0.0
                trades += 1
        elif m.mmd_type.is_sell or m.mmd_type in (MMDType.PANZHENG_SELL,):
            if position > 0:  # 持仓才卖
                if price > entry_price:
                    wins += 1
                cash = position * price
                position = 0.0
                trades += 1
        # 盘整背驰买点也算买入信号
        if m.mmd_type == MMDType.PANZHENG_BUY and position == 0:
            position = cash / price
            entry_price = price
            cash = 0.0
            trades += 1

    # 末日若持仓按收盘平仓
    final_close = closes[-1]
    if position > 0:
        cash = position * final_close

    total_return = (cash - 1.0) / 1.0  # 归一化资金收益率
    # 买入持有收益
    bh_return = (final_close - closes[0]) / closes[0]

    # 信号统计
    buy_cnt = sum(1 for m in mmds if m.mmd_type.is_buy or m.mmd_type == MMDType.PANZHENG_BUY)
    sell_cnt = sum(1 for m in mmds if m.mmd_type.is_sell or m.mmd_type == MMDType.PANZHENG_SELL)

    return {
        "total_return": total_return,
        "buy_hold_return": bh_return,
        "excess": total_return - bh_return,
        "trades": trades,
        "wins": wins,
        "win_rate": wins / max(trades - (1 if position > 0 else 0), 1) if trades > 0 else 0,
        "buy_signals": buy_cnt,
        "sell_signals": sell_cnt,
        "bars": len(klines),
        "span_years": len(klines) / 250,
    }


def main():
    print(f"{'股票':<10} {'代码':<8} {'chanlun2':>10} {'买入持有':>10} {'超额':>10} {'交易':>5} {'胜率':>7} {'买信号':>5} {'卖信号':>5}")
    print("-" * 90)

    all_returns = []
    all_bh = []
    all_excess = []
    total_trades = 0
    total_wins = 0
    total_buy_sig = 0
    total_sell_sig = 0

    for mkt, code, name in STOCKS:
        klines = load_klines(mkt, code)
        if not klines:
            print(f"{name:<10} {code:<8} 无数据")
            continue
        r = backtest_stock(klines)
        if not r:
            print(f"{name:<10} {code:<8} 数据不足")
            continue

        all_returns.append(r["total_return"])
        all_bh.append(r["buy_hold_return"])
        all_excess.append(r["excess"])
        total_trades += r["trades"]
        total_wins += r["wins"]
        total_buy_sig += r["buy_signals"]
        total_sell_sig += r["sell_signals"]

        print(
            f"{name:<10} {code:<8} "
            f"{r['total_return']*100:>9.1f}% {r['buy_hold_return']*100:>9.1f}% "
            f"{r['excess']*100:>9.1f}% {r['trades']:>5} "
            f"{r['win_rate']*100:>6.0f}% {r['buy_signals']:>5} {r['sell_signals']:>5} "
            f"({r['bars']}根,{r['span_years']:.0f}年)"
        )

    print("-" * 90)
    n = len(all_returns)
    if n > 0:
        avg_ret = sum(all_returns) / n
        avg_bh = sum(all_bh) / n
        avg_exc = sum(all_excess) / n
        win_stocks = sum(1 for x in all_returns if x > 0)
        beat_bh = sum(1 for i in range(n) if all_returns[i] > all_bh[i])
        print(f"\n=== chanlun2 回测汇总（{n}只股票，{sum(r['bars'] for r in [backtest_stock(load_klines(m,c)) for m,c,_ in STOCKS] if r):,}根K线）===")
        print(f"平均收益率:     {avg_ret*100:>8.1f}%")
        print(f"平均买入持有:   {avg_bh*100:>8.1f}%")
        print(f"平均超额收益:   {avg_exc*100:>8.1f}%")
        print(f"正收益股票:     {win_stocks}/{n}")
        print(f"跑赢买入持有:   {beat_bh}/{n}")
        print(f"总交易次数:     {total_trades}")
        print(f"总胜率:          {total_wins/max(total_trades,1)*100:.0f}%")
        print(f"总买信号:        {total_buy_sig}")
        print(f"总卖信号:        {total_sell_sig}")


if __name__ == "__main__":
    main()
