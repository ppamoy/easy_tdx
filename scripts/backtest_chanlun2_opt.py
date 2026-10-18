#!/usr/bin/env python3
"""chanlun2 优化版回测：区间套过滤 + 分级仓位 + 止损 + 日线/30min双级别。

优化点（vs 朴素基线 backtest_chanlun2.py）：
1. 区间套过滤（日线级别）：日线买卖点需 30min 次级别同方向确认才交易
   ——只交易 nested.confirmed=True 的信号，减少假信号
2. 分级仓位：1买40%→2买加到70%→3买满仓；卖点分级减仓（非一把梭/一把清）
3. 止损：持仓跌破成本8%清仓（控制单笔亏损）
4. 支持 --level daily / 30min：30min直接交易（单级别，无区间套需5min数据）

用法：
  .venv/bin/python scripts/backtest_chanlun2_opt.py --level daily
  .venv/bin/python scripts/backtest_chanlun2_opt.py --level 30min
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")

from easy_tdx.chanlun2.analyser import analyze
from easy_tdx.chanlun2.level_synth import refine_with_lower_level, interval_bag_summary
from easy_tdx.chanlun2.types import KLine, MMDType

DAILY_D = Path("audit_data")
MIN_D = Path("audit_data_min")

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

# 分级仓位目标（买卖点对应的持仓比例上限）
POSITION_TARGET = {
    MMDType.BUY_1: 0.40,
    MMDType.BUY_2: 0.70,
    MMDType.BUY_3: 1.00,
    MMDType.PANZHENG_BUY: 0.20,
    MMDType.SELL_1: 0.60,   # sell1 减到60%
    MMDType.SELL_2: 0.30,
    MMDType.SELL_3: 0.00,
    MMDType.PANZHENG_SELL: 0.80,
}
STOP_LOSS_PCT = 0.08  # 跌破成本8%止损


def load_klines(mkt, code, level="daily"):
    if level == "daily":
        fp = DAILY_D / f"{mkt.lower()}{code}_daily.json"
    else:
        fp = MIN_D / f"{mkt.lower()}{code}_30min.json"
    if not fp.exists():
        return None
    with open(fp) as f:
        data = json.load(f)
    return [
        KLine(
            index=i, dt=d["datetime"],
            open=float(d["open"]), high=float(d["high"]),
            low=float(d["low"]), close=float(d["close"]),
            volume=float(d.get("vol", 0)),
        )
        for i, d in enumerate(data)
    ]


def backtest_optimized(klines, lower_klines=None, use_qujiantao=False):
    """优化回测：区间套过滤 + 分级仓位 + 止损。

    参数：
        klines: 主级别K线
        lower_klines: 次级别K线（区间套用，None=单级别）
        use_qujiantao: 是否启用区间套过滤（需 lower_klines）
    """
    if not klines or len(klines) < 30:
        return None

    # 重索引为0基（load_klines可能保留原始全量位置，截取后raw_indices越界致MACD失效）
    klines = [KLine(i, k.dt, k.open, k.high, k.low, k.close, k.volume) for i, k in enumerate(klines)]

    closes = [k.close for k in klines]
    # 归一化价格到首根=1.0，使 cash(初始1.0)与价格同尺度，仓位比例逻辑才正确
    base = closes[0] if closes[0] > 0 else 1.0
    norm_close = [c / base for c in closes]
    # 用归一化价格构 KLine 副本供分析+回测（不改原始 klines 的 OHLC 比例关系）
    norm_klines = [
        KLine(k.index, k.dt, k.open / base, k.high / base, k.low / base, k.close / base, k.volume)
        for k in klines
    ]
    result = analyze(norm_klines, closes=norm_close)
    mmds = sorted(result.mmds, key=lambda m: m.k_index)

    # MMD.k_index 是 merged 索引（0基，合并后），需映射到原始K线取价格
    # merged_k.raw_indices[-1] = 该合并K线最后一根原始K线的索引
    def _price_at(mmd_k_index):
        """取买卖点对应原始K线的收盘价（归一化后）。"""
        if 0 <= mmd_k_index < len(result.merged):
            raw_ks = result.merged[mmd_k_index].raw_indices
            if raw_ks:
                last_raw = raw_ks[-1]
                if 0 <= last_raw < len(norm_close):
                    return norm_close[last_raw]
        return 0.0

    def _bar_index_at(mmd_k_index):
        """取买卖点对应原始K线的索引（用于止损逐K线检查的时间对齐）。"""
        if 0 <= mmd_k_index < len(result.merged):
            raw_ks = result.merged[mmd_k_index].raw_indices
            if raw_ks:
                return raw_ks[-1]
        return mmd_k_index

    # 把 mmds 转为 (原始K线索引, MMD) 排序
    mmd_events = sorted(
        [(_bar_index_at(m.k_index), m) for m in mmds],
        key=lambda x: x[0],
    )

    # 区间套过滤：只保留 confirmed 的买卖点
    if use_qujiantao and lower_klines:
        nested = refine_with_lower_level(result, lower_klines)
        confirmed_ks = {
            nm.high_mmd.k_index
            for nm in nested
            if nm.confirmed
        }
        mmd_events = [(bi, m) for bi, m in mmd_events if m.k_index in confirmed_ks]

    # 逐K线模拟（买卖点信号在原始K线索引触发，止损逐根K线检查）
    target_pos = 0.0      # 目标持仓比例
    cur_pos = 0.0          # 当前持仓比例（0~1）
    avg_cost = 0.0         # 持仓均价（归一化价格）
    cash = 1.0             # 归一化资金
    trades = 0
    wins = 0
    # 按原始K线索引建事件表（同一天可能有多个信号，按顺序处理）
    mmd_by_k = {}
    for bi, m in mmd_events:
        mmd_by_k.setdefault(bi, []).append(m)

    for i in range(len(norm_klines)):
        k = norm_klines[i]
        # 1. 止损检查（每根K线最低价跌破止损线）
        if cur_pos > 0 and avg_cost > 0:
            stop_price = avg_cost * (1 - STOP_LOSS_PCT)
            if k.low <= stop_price:
                # 止损清仓（按止损价成交）
                cash += cur_pos * stop_price
                cur_pos = 0.0
                avg_cost = 0.0
                target_pos = 0.0
                trades += 1
                continue

        # 2. 买卖点信号触发（在原始K线索引 i）
        if i in mmd_by_k:
            for m in mmd_by_k[i]:
                price = k.close  # 该K线收盘价（归一化后，与cash同尺度）
                new_target = POSITION_TARGET.get(m.mmd_type, target_pos)

                if m.mmd_type.is_buy or m.mmd_type == MMDType.PANZHENG_BUY:
                    # 加仓到 new_target
                    if new_target > cur_pos:
                        buy_frac = new_target - cur_pos
                        cost_delta = buy_frac * price
                        if cash >= cost_delta:
                            new_pos = cur_pos + buy_frac
                            avg_cost = (avg_cost * cur_pos + price * buy_frac) / new_pos if new_pos > 0 else price
                            cash -= cost_delta
                            cur_pos = new_pos
                            target_pos = new_target
                            trades += 1
                elif m.mmd_type.is_sell or m.mmd_type == MMDType.PANZHENG_SELL:
                    # 减仓到 new_target
                    if new_target < cur_pos:
                        sell_frac = cur_pos - new_target
                        if sell_frac > 0:
                            cash += sell_frac * price
                            if price > avg_cost:
                                wins += 1
                            cur_pos = new_target
                            target_pos = new_target
                            trades += 1
                            if cur_pos == 0:
                                avg_cost = 0.0

    # 末日平仓（用归一化价格）
    final_close = norm_close[-1]
    if cur_pos > 0:
        cash += cur_pos * final_close
        if final_close > avg_cost:
            wins += 1

    total_return = (cash - 1.0)
    bh_return = (closes[-1] - closes[0]) / closes[0]  # 买入持有用真实价格（等价归一化）
    buy_cnt = sum(1 for m in mmds if m.mmd_type.is_buy or m.mmd_type == MMDType.PANZHENG_BUY)
    sell_cnt = sum(1 for m in mmds if m.mmd_type.is_sell or m.mmd_type == MMDType.PANZHENG_SELL)

    return {
        "total_return": total_return,
        "buy_hold_return": bh_return,
        "excess": total_return - bh_return,
        "trades": trades,
        "wins": wins,
        "win_rate": wins / max(trades, 1) if trades > 0 else 0,
        "buy_signals": buy_cnt,
        "sell_signals": sell_cnt,
        "total_signals": len(mmds),
        "bars": len(klines),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", default="daily", choices=("daily", "30min"))
    ap.add_argument("--no-qujiantao", action="store_true", help="日线级别关闭区间套过滤(对比)")
    a = ap.parse_args()

    use_qj = (a.level == "daily") and not a.no_qujiantao
    header = f"chanlun2优化回测 [{a.level}" + ("+区间套过滤" if use_qj else "") + "]"
    print(header)
    print(f"{'股票':<10} {'代码':<8} {'优化':>9} {'买入持有':>9} {'超额':>9} {'交易':>5} {'胜率':>6} {'信号':>5}")
    print("-" * 75)

    all_ret, all_bh, all_exc = [], [], []
    tot_trades, tot_wins, tot_sig = 0, 0, 0

    for mkt, code, name in STOCKS:
        klines = load_klines(mkt, code, a.level)
        if not klines:
            print(f"{name:<10} {code:<8} 无数据")
            continue

        lower_klines = None
        if use_qj:
            lower_klines = load_klines(mkt, code, "30min")

        r = backtest_optimized(klines, lower_klines, use_qj)
        if not r:
            print(f"{name:<10} {code:<8} 数据不足")
            continue

        all_ret.append(r["total_return"])
        all_bh.append(r["buy_hold_return"])
        all_exc.append(r["excess"])
        tot_trades += r["trades"]
        tot_wins += r["wins"]
        tot_sig += r["total_signals"]

        print(
            f"{name:<10} {code:<8} "
            f"{r['total_return']*100:>8.1f}% {r['buy_hold_return']*100:>8.1f}% "
            f"{r['excess']*100:>8.1f}% {r['trades']:>5} "
            f"{r['win_rate']*100:>5.0f}% {r['total_signals']:>5} "
            f"({r['bars']}根)"
        )

    print("-" * 75)
    n = len(all_ret)
    if n > 0:
        print(f"\n=== 汇总（{n}只）===")
        print(f"平均收益率:   {sum(all_ret)/n*100:>8.1f}%")
        print(f"平均买入持有: {sum(all_bh)/n*100:>8.1f}%")
        print(f"平均超额:     {sum(all_exc)/n*100:>8.1f}%")
        print(f"正收益股票:   {sum(1 for x in all_ret if x>0)}/{n}")
        print(f"跑赢买入持有: {sum(1 for i in range(n) if all_ret[i]>all_bh[i])}/{n}")
        print(f"总交易次数:   {tot_trades}")
        print(f"总胜率:        {tot_wins/max(tot_trades,1)*100:.0f}%")
        print(f"总信号数:      {tot_sig}")


if __name__ == "__main__":
    main()
