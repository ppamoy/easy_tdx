#!/usr/bin/env python3
"""chanlun2 v3 优化回测：趋势过滤 + 信号质量 + ATR动态止损。

可配置开关，逐项测量各优化对收益率的贡献：
  --trend-filter    周线趋势过滤（只在周线上行时做多）
  --signal-quality  信号质量过滤（只做1买/2买/3买，过滤盘整背驰）
  --atr-stop        ATR动态止损（替代固定8%）
  --level daily/30min

用法：
  # 基线（无优化，对照）
  .venv/bin/python scripts/backtest_chanlun2_v3.py --level daily
  # 全部优化开启
  .venv/bin/python scripts/backtest_chanlun2_v3.py --level daily --trend-filter --signal-quality --atr-stop
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")

from easy_tdx.chanlun2.analyser import analyze
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

POSITION_TARGET = {
    MMDType.BUY_1: 0.50,
    MMDType.BUY_2: 0.80,
    MMDType.BUY_3: 1.00,
    MMDType.PANZHENG_BUY: 0.20,
    MMDType.SELL_1: 0.50,
    MMDType.SELL_2: 0.20,
    MMDType.SELL_3: 0.00,
    MMDType.PANZHENG_SELL: 0.80,
}


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
        KLine(index=i, dt=d["datetime"], open=float(d["open"]), high=float(d["high"]),
              low=float(d["low"]), close=float(d["close"]), volume=float(d.get("vol", 0)))
        for i, d in enumerate(data)
    ]


def _compute_atr(klines, period=14):
    """ATR(14)：真实波幅的移动平均。"""
    if len(klines) < period + 1:
        return [0.0] * len(klines)
    trs = [0.0]
    for i in range(1, len(klines)):
        k = klines[i]
        pk = klines[i - 1]
        tr = max(
            k.high - k.low,
            abs(k.high - pk.close),
            abs(k.low - pk.close),
        )
        trs.append(tr)
    atr = [0.0] * (period - 1)
    for i in range(period - 1, len(trs)):
        atr.append(sum(trs[i - period + 1 : i + 1]) / period)
    return atr


def _weekly_trend(daily_klines):
    """周线趋势：日线重采样为周线，close > MA10 周线 = 上行。

    返回与日线等长的布尔列表（True=周线上行），用日线对应的周判断。
    """
    import pandas as pd

    closes = [k.close for k in daily_klines]
    dts = pd.to_datetime([k.dt for k in daily_klines])
    s = pd.Series(closes, index=dts)
    weekly = s.resample("W-FRI").last().dropna()
    if len(weekly) < 10:
        return [True] * len(daily_klines)  # 数据不足默认允许
    ma10 = weekly.rolling(10).mean()
    is_up = (weekly > ma10).fillna(False)
    # 映射回每根日线：该日所属周是否上行
    week_end = weekly.index
    result = []
    for dt in dts:
        # 找该日所在或之前最近的周末
        mask = week_end <= dt
        if mask.any():
            wk = is_up[mask].iloc[-1] if mask.sum() > 0 else True
        else:
            wk = True
        result.append(bool(wk))
    return result


def backtest_v3(klines, trend_filter=False, signal_quality=False, atr_stop=False, trend_hold=False, stop_pct=0.08, trailing_stop=False):
    """v3 优化回测。

    开关：
        trend_filter: 周线上行时才执行买入
        signal_quality: 只做1买/2买/3买（过滤盘整背驰）
        atr_stop: ATR动态止损（2*ATR）替代固定8%
        trend_hold: 周线上行时忽略卖点（让利润奔跑，只在止损或周线转弱时退出）
    """
    if not klines or len(klines) < 30:
        return None

    # 重索引0基 + 归一化价格
    klines = [KLine(i, k.dt, k.open, k.high, k.low, k.close, k.volume) for i, k in enumerate(klines)]
    closes = [k.close for k in klines]
    base = closes[0] if closes[0] > 0 else 1.0
    norm_close = [c / base for c in closes]
    norm_klines = [KLine(k.index, k.dt, k.open / base, k.high / base, k.low / base, k.close / base, k.volume) for k in klines]

    # 周线趋势（趋势过滤用）
    trend_up = _weekly_trend(klines) if trend_filter else [True] * len(klines)

    # ATR（动态止损用）
    atr_series = _compute_atr(klines, 14) if atr_stop else None

    result = analyze(norm_klines, closes=norm_close)
    mmds = sorted(result.mmds, key=lambda m: m.k_index)

    # merged→原始K线映射
    def _bar_at(mk):
        if 0 <= mk < len(result.merged):
            rks = result.merged[mk].raw_indices
            if rks:
                return rks[-1]
        return mk

    mmd_events = sorted([(_bar_at(m.k_index), m) for m in mmds], key=lambda x: x[0])

    # 信号质量过滤：只保留1买/2买/3买（及对应卖点）
    if signal_quality:
        keep_types = {MMDType.BUY_1, MMDType.BUY_2, MMDType.BUY_3,
                      MMDType.SELL_1, MMDType.SELL_2, MMDType.SELL_3}
        mmd_events = [(bi, m) for bi, m in mmd_events if m.mmd_type in keep_types]

    # 逐K线模拟
    target_pos = 0.0
    cur_pos = 0.0
    avg_cost = 0.0
    cash = 1.0
    trades = 0
    wins = 0
    mmd_by_k = {}
    for bi, m in mmd_events:
        mmd_by_k.setdefault(bi, []).append(m)

    skip_buys = 0
    peak_equity = 1.0  # 峰值权益（算最大回撤用）
    max_dd = 0.0
    trail_peak = 0.0  # 移动止损峰值（局部变量，不跨调用泄漏）
    for i in range(len(norm_klines)):
        k = norm_klines[i]
        # 更新移动止损峰值（持仓时跟踪高点）
        if trailing_stop and cur_pos > 0 and avg_cost > 0:
            trail_peak = max(trail_peak, k.high)
        # 止损检查
        if cur_pos > 0 and avg_cost > 0:
            if trailing_stop and trail_peak > 0:
                stop_price = trail_peak * (1 - stop_pct)
            elif atr_stop and i < len(atr_series) and atr_series[i] > 0:
                stop_dist = 2 * (atr_series[i] / base)  # 归一化ATR
                stop_price = avg_cost - stop_dist
            else:
                stop_price = avg_cost * (1 - stop_pct)
            if k.low <= stop_price:
                cash += cur_pos * stop_price
                cur_pos = 0.0; avg_cost = 0.0; target_pos = 0.0; trail_peak = 0.0
                trades += 1
                continue

        # 当前权益 = cash + 持仓市值
        cur_equity = cash + cur_pos * k.close
        if cur_equity > peak_equity:
            peak_equity = cur_equity
        dd = (peak_equity - cur_equity) / peak_equity if peak_equity > 0 else 0
        if dd > max_dd:
            max_dd = dd

        # 信号触发
        if i in mmd_by_k:
            for m in mmd_by_k[i]:
                price = k.close
                new_target = POSITION_TARGET.get(m.mmd_type, target_pos)
                is_buy = m.mmd_type.is_buy or m.mmd_type == MMDType.PANZHENG_BUY

                # 趋势过滤：只在周线上行时买入
                if is_buy and trend_filter and i < len(trend_up) and not trend_up[i]:
                    skip_buys += 1
                    continue

                if is_buy:
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
                else:  # 卖
                    # 趋势持有：周线上行时忽略卖点（让利润奔跑）
                    if trend_hold and i < len(trend_up) and trend_up[i]:
                        continue
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

    final_close = norm_close[-1]
    if cur_pos > 0:
        cash += cur_pos * final_close
        if final_close > avg_cost:
            wins += 1

    total_return = cash - 1.0
    bh_return = (closes[-1] - closes[0]) / closes[0]
    buy_cnt = sum(1 for _, m in mmd_events if m.mmd_type.is_buy or m.mmd_type == MMDType.PANZHENG_BUY)

    return {
        "total_return": total_return,
        "buy_hold_return": bh_return,
        "excess": total_return - bh_return,
        "trades": trades,
        "wins": wins,
        "win_rate": wins / max(trades, 1) if trades > 0 else 0,
        "buy_signals": buy_cnt,
        "total_signals": len(mmd_events),
        "skip_buys": skip_buys,
        "bars": len(klines),
        "max_drawdown": max_dd,
    }


def run(label, **kw):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"{'股票':<10}{'代码':<8}{'收益':>9}{'买入持有':>9}{'超额':>9}{'回撤':>7}{'交易':>5}{'胜率':>6}{'信号':>5}{'过滤买':>7}")
    print("-" * 78)
    rets, bhs, dds = [], [], []
    tot_tr, tot_w, tot_skip = 0, 0, 0
    for mkt, code, name in STOCKS:
        kl = load_klines(mkt, code, kw.get("level", "daily"))
        if not kl:
            print(f"{name:<10}{code:<8} 无数据")
            continue
        r = backtest_v3(kl, trend_filter=kw.get("trend_filter", False),
                        signal_quality=kw.get("signal_quality", False),
                        atr_stop=kw.get("atr_stop", False),
                        trend_hold=kw.get("trend_hold", False),
                        stop_pct=kw.get("stop_pct", 0.08),
                        trailing_stop=kw.get("trailing_stop", False))
        if not r:
            print(f"{name:<10}{code:<8} 数据不足")
            continue
        rets.append(r["total_return"]); bhs.append(r["buy_hold_return"]); dds.append(r["max_drawdown"])
        tot_tr += r["trades"]; tot_w += r["wins"]; tot_skip += r["skip_buys"]
        print(f"{name:<10}{code:<8}{r['total_return']*100:>8.1f}%{r['buy_hold_return']*100:>8.1f}%"
              f"{r['excess']*100:>8.1f}%{r['max_drawdown']*100:>6.1f}%"
              f"{r['trades']:>5}{r['win_rate']*100:>5.0f}%"
              f"{r['total_signals']:>5}{r['skip_buys']:>7}")
    n = len(rets)
    if n:
        print("-" * 78)
        print(f"平均: {sum(rets)/n*100:.1f}%  买入持有: {sum(bhs)/n*100:.1f}%  "
              f"超额: {(sum(rets)-sum(bhs))/n*100:.1f}%  最大回撤: {sum(dds)/n*100:.1f}%  "
              f"正收益: {sum(1 for x in rets if x>0)}/{n}  "
              f"跑赢: {sum(1 for i in range(n) if rets[i]>bhs[i])}/{n}  "
              f"胜率: {tot_w/max(tot_tr,1)*100:.0f}%  过滤买: {tot_skip}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", default="daily", choices=("daily", "30min"))
    ap.add_argument("--trend-filter", action="store_true")
    ap.add_argument("--signal-quality", action="store_true")
    ap.add_argument("--atr-stop", action="store_true")
    ap.add_argument("--all", action="store_true", help="全部优化开启")
    ap.add_argument("--trend-hold", action="store_true", help="周线上行时忽略卖点(让利润奔跑)")
    ap.add_argument("--stop-pct", type=float, default=0.08, help="止损百分比 默认0.08即8pct")
    ap.add_argument("--trailing-stop", action="store_true", help="移动止损(跟踪峰值回撤)")
    a = ap.parse_args()
    if a.all:
        a.trend_filter = a.signal_quality = a.atr_stop = a.trend_hold = True

    opts = {"level": a.level, "trend_filter": a.trend_filter,
            "signal_quality": a.signal_quality, "atr_stop": a.atr_stop,
            "trend_hold": a.trend_hold, "stop_pct": a.stop_pct,
            "trailing_stop": a.trailing_stop}
    tags = []
    if a.trend_filter: tags.append("趋势过滤")
    if a.signal_quality: tags.append("信号质量")
    if a.atr_stop: tags.append("ATR止损")
    if a.trend_hold: tags.append("趋势持有")
    if a.trailing_stop: tags.append(f"移动止损{a.stop_pct*100:.0f}%")
    elif a.stop_pct != 0.08: tags.append(f"止损{a.stop_pct*100:.0f}%")
    label = f"[{a.level}]" + ("+".join(tags) if tags else "基线(无优化)")
    run(label, **opts)


if __name__ == "__main__":
    main()
