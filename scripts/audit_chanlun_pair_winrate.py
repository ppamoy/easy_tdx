#!/usr/bin/env python3
"""按「缠论原文口径」重测胜率：同一级别买点进、同一级别卖点出。

## 为什么要有这个脚本（我上一轮验证的漏洞）
缠论原文的交易规则是：**日线买点买入 → 日线卖点卖出**（级别内配对）。
但我上一轮用的 `ChanlunStrategy` 默认开了 `stop_loss_pct=0.08` /
`take_profit_pct=0.25`，且这两个检查在消费信号队列**之前**执行并 `return`
—— 仓位常在卖点出现前就被截断，"买点进卖点出"这条最基本的规则
**根本没跑出来**。

所以上一轮"胜率 40.9%"有可能是在骂一个**被百分比止损截断的变体**，
而不是缠论本身。本脚本按原口径（关掉百分比止损止盈）重测，并按
**买点类型 / 卖点类型 / 持有期**拆解胜率，定位到底是哪一类信号拖后腿。

## ⚠️ 历史变更（chanlun_pair 已废弃删除）
本脚本原先用 `ChanlunPairStrategy`（纯卖点出场，带 `pair_log`）重测。
该策略因「区间套过滤用 level_synth 合成数据，是伪区间套不符合原文」
被整体移除，缠论策略收敛为单一 `chanlun`（`stop_loss_pct` /
`take_profit_pct` 设为 0 即得原文口径）。现在改用
`ChanlunStrategy(stop_loss_pct=0, take_profit_pct=0)` + 引擎 `trades`
的 `tag` 字段自行配对（tag 沿用开仓信号类型，平仓时附 `->stop_loss`
之类的归因后缀）。

## 回答的问题
  Q1 纯卖点出场（缠论原口径）的胜率是多少？是否高于带止损止盈的变体？
  Q2 按买点类型拆：1buy / 2buy / 3buy 各自胜率与盈亏比？
     （缠论原文里 3buy 是"中枢突破后回踩"，条件最严格，本应最好）
  Q3 按卖点类型拆：哪种出场最赚？
  Q4 盈亏比：即使胜率 <50%，若盈亏比够高（赚的多、亏的少）仍可盈利。

用法：  .venv/bin/python scripts/audit_chanlun_pair_winrate.py --limit 0
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from _concurrency import resolve_workers  # noqa: E402
from easy_tdx.backtest.engine import BacktestEngine  # noqa: E402
from easy_tdx.backtest.strategies.chanlun import ChanlunStrategy  # noqa: E402

DATA_DIR = ROOT / "audit_data"
EXCLUDE = {"sh000300", "sh000001"}


def _mk_strategy():
    """原文口径：买卖点信号进出，关掉百分比止损止盈。"""
    return ChanlunStrategy(stop_loss_pct=0.0, take_profit_pct=0.0)


def _run_pair(args):
    """子进程：(code, strategy_name) → 配对交易记录 + 汇总绩效。"""
    code, which, slip = args
    p = DATA_DIR / f"{code}_daily.json"
    df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
    df["datetime"] = pd.to_datetime(df["datetime"])
    S = ChanlunStrategy if which == "pair" else ChanlunStrategy
    try:
        kw = {} if which == "pair" else {}
        r = BacktestEngine(S(**kw), cash=100000.0, slippage=slip).run(df)
        pf = r.performance
        bh = float(df["close"].iloc[-1] / df["close"].iloc[0] - 1)
        return {
            "symbol": code, "strat": float(pf["total_return"]),
            "buyhold": bh,
            "n_trades": int(pf.get("total_trades", 0) or 0),
            "win_rate": float(pf.get("win_rate", np.nan)),
        }
    except Exception as e:  # noqa: BLE001
        return {"symbol": code, "strat": np.nan, "buyhold": np.nan,
                "n_trades": 0, "win_rate": np.nan, "err": str(e)}


_SLIP = 0.002   # 子进程用的滑点（由 main 设置）


def _pairs_one(code: str, slip: float) -> list[dict]:
    """取一只标的的逐笔配对。

    曾经的 chanlun_pair 提供 `pair_log`；该策略已废弃删除，现在从引擎
    `trades` 自行配对：`tag` 沿用开仓信号类型（平仓时附
    `->stop_loss` / `->take_profit` 归因后缀），据此拆出入场/出场类型。
    """
    p = DATA_DIR / f"{code}_daily.json"
    df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
    df["datetime"] = pd.to_datetime(df["datetime"])
    r = BacktestEngine(_mk_strategy(), cash=100000.0, slippage=slip).run(df)
    t = r.trades
    if t is None or len(t) == 0:
        return []

    pairs: list[dict] = []
    entry_type = ""
    entry_bar = 0
    entry_price = 0.0
    for i, row in enumerate(t.itertuples(index=False)):
        tag = str(getattr(row, "tag", "") or "")
        direction = str(row.direction)
        if direction == "BUY":
            entry_type = tag.split("->")[0] or "?"
            entry_bar = i
            entry_price = float(row.price)
            continue
        if direction == "SELL" and entry_type:
            exit_type = tag.split("->")[0] if "->" in tag else tag
            exit_type = exit_type or "close"
            pairs.append({
                "entry_type": entry_type,
                "exit_type": exit_type,
                "entry_bar": entry_bar,
                "exit_bar": i,
                "holding_bars": i - entry_bar,
                "entry_price": entry_price,
                "exit_price": float(row.price),
                "pnl_pct": (float(row.price) / entry_price - 1) * 100
                if entry_price else 0.0,
            })
            entry_type = ""
    return pairs


def _pairs_job(code: str) -> list[dict]:
    """模块级包装（⚠️ ProcessPoolExecutor 不能 pickle 闭包/local 函数）。"""
    return _pairs_one(code, _SLIP)


def report_by_type(pairs: list[dict]) -> None:
    if not pairs:
        print("❌ 无配对记录")
        return
    d = pd.DataFrame(pairs)
    print(f"\n总配对笔数 {len(d)}")
    print("\n【按买点类型】")
    print("%-10s %6s %9s %9s %9s %9s" % ("买点", "笔数", "胜率", "平均收益", "平均盈利", "平均亏损"))
    print("-" * 60)
    for t, g in d.groupby("entry_type"):
        w = g[g["pnl_pct"] > 0]["pnl_pct"]
        l = g[g["pnl_pct"] <= 0]["pnl_pct"]
        wr = (g["pnl_pct"] > 0).mean() * 100
        pl = w.mean() / abs(l.mean()) if len(l) and l.mean() != 0 else float("nan")
        print("%-10s %6d %8.1f%% %8.2f%% %8.2f%% %8.2f%%  盈亏比%.2f" % (
            t, len(g), wr, g["pnl_pct"].mean(),
            w.mean() if len(w) else 0, l.mean() if len(l) else 0, pl))

    print("\n【按卖点类型】")
    print("%-10s %6s %9s %9s" % ("卖点", "笔数", "胜率", "平均收益"))
    print("-" * 60)
    for t, g in d.groupby("exit_type"):
        print("%-10s %6d %8.1f%% %8.2f%%" % (
            t, len(g), (g["pnl_pct"] > 0).mean() * 100, g["pnl_pct"].mean()))

    print("\n【按持有期分组】")
    bins = [(0, 5), (5, 10), (10, 20), (20, 40), (40, 60), (60, 10**9)]
    print("%-12s %6s %9s %9s" % ("持有bar", "笔数", "胜率", "平均收益"))
    print("-" * 60)
    for lo, hi in bins:
        g = d[(d["holding_bars"] >= lo) & (d["holding_bars"] < hi)]
        if len(g) == 0:
            continue
        lab = f"{lo}-{hi}" if hi < 10**8 else f"{lo}+"
        print("%-12s %6d %8.1f%% %8.2f%%" % (
            lab, len(g), (g["pnl_pct"] > 0).mean() * 100, g["pnl_pct"].mean()))

    print("\n【整体】")
    w = d[d["pnl_pct"] > 0]["pnl_pct"]
    l = d[d["pnl_pct"] <= 0]["pnl_pct"]
    print(f"  胜率      {(d['pnl_pct'] > 0).mean()*100:.1f}%")
    print(f"  平均收益  {d['pnl_pct'].mean():+.2f}%")
    print(f"  平均盈利  {w.mean():+.2f}%   平均亏损 {l.mean():+.2f}%")
    pl = w.mean() / abs(l.mean()) if len(l) and l.mean() != 0 else float("nan")
    print(f"  盈亏比    {pl:.2f}   （>1 表示赚的比亏的多，胜率<50% 也可能盈利）")
    print(f"  持有中位  {d['holding_bars'].median():.0f} 根")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--slippage", type=float, default=0.002)
    a = ap.parse_args()
    workers = resolve_workers(a.workers)

    codes = [p.stem.split("_")[0] for p in sorted(DATA_DIR.glob("*.json"))
             if p.stem.split("_")[0] not in EXCLUDE]
    codes = codes[:a.limit] if a.limit else codes

    print("缠论原文口径重测：买点进 → 卖点出（stop_loss/take_profit=0）")
    print(f"样本 {len(codes)} 只   并行度 {workers}\n")

    # 逐笔配对（CPU 密集，走进程池）
    global _SLIP
    _SLIP = a.slippage

    from concurrent.futures import ProcessPoolExecutor
    pairs: list[dict] = []

    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, pl in enumerate(ex.map(_pairs_job, codes, chunksize=1)):
            pairs.extend(pl)
            if (i + 1) % 50 == 0:
                print(f"  进度 {i+1}/{len(codes)}  累计配对 {len(pairs)}", flush=True)

    report_by_type(pairs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
