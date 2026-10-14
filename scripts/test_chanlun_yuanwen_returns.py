#!/usr/bin/env python3
"""原文买卖点年化收益率实测脚本。

直接用 ChanlunAnalyser(zs_from_xd=True) 生成买卖点信号，
模拟交易（买入信号买入、卖出信号卖出），计算年化收益率，
对比买入持有基准。

成本模型：佣金0.03% + 印花税0.1%（卖出） + 滑点0.2%
信号延迟：确认 lag=3 根（笔端点后等3根K线才入场，防前视）
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# 必须用绝对路径
sys.path.insert(0, "/home/skp/workspace/easy_tdx/src")

from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig

PROJECT_ROOT = Path("/home/skp/workspace/easy_tdx")
CACHE_DAILY = PROJECT_ROOT / "audit_data"
CACHE_MIN = PROJECT_ROOT / "audit_data_min"

# 交易成本
COMMISSION = 0.0003   # 佣金（双边）
STAMP_TAX = 0.001     # 印花税（卖出）
SLIPPAGE = 0.002      # 滑点（双边）
CONFIRM_LAG = 3       # 信号确认延迟（根）

# 选取20只代表性股票（大盘/中盘/创业板/科创板）
TEST_STOCKS = [
    ("SH", "600000", "浦发银行"),
    ("SH", "600036", "招商银行"),
    ("SH", "600519", "贵州茅台"),
    ("SH", "601318", "中国平安"),
    ("SH", "601398", "工商银行"),
    ("SH", "600276", "恒瑞医药"),
    ("SH", "600030", "中信证券"),
    ("SH", "600887", "伊利股份"),
    ("SH", "688981", "中芯国际"),
    ("SH", "600585", "海螺水泥"),
    ("SZ", "000001", "平安银行"),
    ("SZ", "000333", "美的集团"),
    ("SZ", "000651", "格力电器"),
    ("SZ", "000858", "五粮液"),
    ("SZ", "002230", "科大讯飞"),
    ("SZ", "000725", "京东方A"),
    ("SZ", "300750", "宁德时代"),
    ("SZ", "002594", "比亚迪"),
    ("SZ", "000002", "万科A"),
    ("SZ", "002415", "海康威视"),
]


def load_daily(market: str, code: str) -> pd.DataFrame | None:
    fp = CACHE_DAILY / f"{market.lower()}{code}_daily.json"
    if not fp.is_file():
        return None
    rows = json.loads(fp.read_text(encoding="utf-8"))
    if not rows:
        return None
    df = pd.DataFrame(rows)
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"])
    elif "date" in df.columns:
        df["datetime"] = pd.to_datetime(df["date"])
    return df.sort_values("datetime").reset_index(drop=True)


def run_backtest_single(market: str, code: str, name: str) -> dict:
    """对单只股票运行原文买卖点回测。"""
    df = load_daily(market, code)
    if df is None or len(df) < 100:
        return {"symbol": f"{market}:{code}", "name": name, "error": "数据不足"}

    # 原文精确口径：zs_from_xd=True（第91课：线段构中枢）
    config = ChanlunConfig(zs_from_xd=True)
    analyser = ChanlunAnalyser(code=code, frequency="daily", config=config)
    result = analyser.process_klines(df)

    mmds = result.mmds
    bis = result.bis
    zss = result.zss

    # 构建信号队列：买入信号和卖出信号
    # 买入信号: 1buy, 2buy, 2buy_s, 3buy
    # 卖出信号: 1sell, 2sell, 2sell_s, 3sell
    signals = []
    for mmd in mmds:
        if mmd.bi is None:
            continue
        mmd_type = mmd.mmd_type.value  # e.g. "1buy", "3sell"
        # 笔结束日期 → bar index
        end_date_str = str(mmd.bi.end.k.date)[:10]
        # 在 df 中找到对应日期的 bar index
        mask = df["datetime"].dt.strftime("%Y-%m-%d") == end_date_str
        matches = df.index[mask]
        if len(matches) == 0:
            continue
        bar_idx = matches[0]
        is_buy = "buy" in mmd_type
        is_sell = "sell" in mmd_type
        if not (is_buy or is_sell):
            continue
        signals.append({
            "bar_idx": bar_idx,
            "type": mmd_type,
            "is_buy": is_buy,
            "is_sell": is_sell,
            "confidence": mmd.confidence,
        })

    # 按时间排序
    signals.sort(key=lambda s: s["bar_idx"])

    # 模拟交易
    cash = 1_000_000.0
    position = 0  # 持仓股数
    entry_price = 0.0
    trades = []

    # 应用确认延迟：信号在 bar_idx + CONFIRM_LAG 才生效
    for sig in signals:
        exec_bar = sig["bar_idx"] + CONFIRM_LAG
        if exec_bar >= len(df):
            continue  # 信号太晚，无法执行

        close = float(df.iloc[exec_bar]["close"])
        if close <= 0:
            continue

        if sig["is_buy"] and position == 0:
            # 买入
            buy_price = close * (1 + SLIPPAGE)  # 滑点
            shares = int(cash * (1 - COMMISSION) / (buy_price * 100)) * 100
            if shares <= 0:
                continue
            cost = shares * buy_price * (1 + COMMISSION)
            cash -= cost
            position = shares
            entry_price = buy_price
            trades.append({
                "type": "buy",
                "signal": sig["type"],
                "bar": exec_bar,
                "date": df.iloc[exec_bar]["datetime"].strftime("%Y-%m-%d"),
                "price": buy_price,
                "shares": shares,
            })

        elif sig["is_sell"] and position > 0:
            # 卖出
            sell_price = close * (1 - SLIPPAGE)  # 滑点
            proceeds = position * sell_price * (1 - COMMISSION - STAMP_TAX)
            cash += proceeds
            trades.append({
                "type": "sell",
                "signal": sig["type"],
                "bar": exec_bar,
                "date": df.iloc[exec_bar]["datetime"].strftime("%Y-%m-%d"),
                "price": sell_price,
                "shares": position,
                "pnl_pct": (sell_price / entry_price - 1) * 100,
            })
            position = 0
            entry_price = 0.0

    # 最后清仓（如果还持仓）
    final_close = float(df.iloc[-1]["close"])
    if position > 0:
        sell_price = final_close * (1 - SLIPPAGE)
        proceeds = position * sell_price * (1 - COMMISSION - STAMP_TAX)
        cash += proceeds
        trades.append({
            "type": "sell_end",
            "signal": "end",
            "bar": len(df) - 1,
            "date": df.iloc[-1]["datetime"].strftime("%Y-%m-%d"),
            "price": sell_price,
            "shares": position,
            "pnl_pct": (sell_price / entry_price - 1) * 100,
        })
        position = 0

    # 计算收益率
    total_return = (cash / 1_000_000.0 - 1) * 100

    # 计算年化收益率
    start_date = df.iloc[0]["datetime"]
    end_date = df.iloc[-1]["datetime"]
    years = (end_date - start_date).days / 365.25
    if years > 0:
        annualized = ((cash / 1_000_000.0) ** (1 / years) - 1) * 100
    else:
        annualized = 0.0

    # 买入持有基准
    bh_return = (final_close / float(df.iloc[0]["close"]) - 1) * 100
    if years > 0:
        bh_annual = ((final_close / float(df.iloc[0]["close"])) ** (1 / years) - 1) * 100
    else:
        bh_annual = 0.0

    # 交易统计
    buy_trades = [t for t in trades if t["type"] == "buy"]
    sell_trades = [t for t in trades if t["type"] in ("sell", "sell_end")]
    win_trades = [t for t in sell_trades if t.get("pnl_pct", 0) > 0]
    win_rate = len(win_trades) / len(sell_trades) * 100 if sell_trades else 0

    return {
        "symbol": f"{market}:{code}",
        "name": name,
        "bars": len(df),
        "years": round(years, 2),
        "bis": len(bis),
        "zss": len(zss),
        "signals": len(signals),
        "buy_signals": len([s for s in signals if s["is_buy"]]),
        "sell_signals": len([s for s in signals if s["is_sell"]]),
        "trades": len(trades),
        "completed_trades": len(sell_trades),
        "win_rate": round(win_rate, 1),
        "total_return": round(total_return, 2),
        "annualized": round(annualized, 2),
        "bh_return": round(bh_return, 2),
        "bh_annual": round(bh_annual, 2),
        "excess_return": round(annualized - bh_annual, 2),
        "final_cash": round(cash, 0),
    }


def main():
    print("=" * 100)
    print("原文买卖点年化收益率实测")
    print(f"模型: zs_from_xd=True（第91课：线段构中枢）")
    print(f"成本: 佣金{COMMISSION*100}% + 印花税{STAMP_TAX*100}% + 滑点{SLIPPAGE*100}%")
    print(f"确认延迟: {CONFIRM_LAG}根K线")
    print(f"测试股票: {len(TEST_STOCKS)}只")
    print("=" * 100)

    results = []
    for market, code, name in TEST_STOCKS:
        r = run_backtest_single(market, code, name)
        results.append(r)
        if "error" in r:
            print(f"  {r['symbol']:10s} {r['name']:8s}  跳过: {r['error']}")
        else:
            print(
                f"  {r['symbol']:10s} {r['name']:8s}  "
                f"笔={r['bis']:3d} 中枢={r['zss']:2d} 信号={r['signals']:3d} "
                f"交易={r['completed_trades']:2d}次 胜率={r['win_rate']:5.1f}%  "
                f"年化={r['annualized']:7.2f}%  买入持有={r['bh_annual']:7.2f}%  "
                f"超额={r['excess_return']:+7.2f}%"
            )

    # 汇总统计
    valid = [r for r in results if "error" not in r]
    if not valid:
        print("\n无有效结果")
        return

    avg_ann = sum(r["annualized"] for r in valid) / len(valid)
    avg_bh = sum(r["bh_annual"] for r in valid) / len(valid)
    avg_excess = avg_ann - avg_bh
    avg_win = sum(r["win_rate"] for r in valid) / len(valid)
    total_signals = sum(r["signals"] for r in valid)
    total_trades = sum(r["completed_trades"] for r in valid)
    win_count = sum(1 for r in valid if r["annualized"] > r["bh_annual"])
    positive_count = sum(1 for r in valid if r["annualized"] > 0)

    print("\n" + "=" * 100)
    print(f"汇总（{len(valid)}只股票）:")
    print(f"  平均年化收益率:     {avg_ann:7.2f}%")
    print(f"  买入持有年化:       {avg_bh:7.2f}%")
    print(f"  平均超额收益:       {avg_excess:+7.2f}%")
    print(f"  平均胜率:           {avg_win:7.1f}%")
    print(f"  总信号数:           {total_signals}")
    print(f"  总交易次数:         {total_trades}")
    print(f"  正收益股票:         {positive_count}/{len(valid)}")
    print(f"  跑赢买入持有:       {win_count}/{len(valid)}")
    print("=" * 100)


if __name__ == "__main__":
    main()
