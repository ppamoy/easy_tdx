#!/usr/bin/env python3
"""第三轮优化：基于 lag=1 (8.13%) 和 趋势持有 (6.40%) 的发现，测试更多组合。

关键发现：
- lag=1 alone: 8.13% ann, 58% win, 31.27% DD
- hold_in_higher_uptrend: 6.40% ann
- 趋势+lag=1: 待测

本轮新增移动止盈(trailing stop)测试。
"""
import json, sys, time
from pathlib import Path
import pandas as pd
sys.path.insert(0, "src")
from easy_tdx.backtest.engine import BacktestEngine
from easy_tdx.backtest.strategies.registry import get_registry

CACHE_D = Path("audit_data")
STOCKS = [
    ("SH","600000","浦发银行"), ("SH","600036","招商银行"), ("SH","601318","中国平安"),
    ("SH","600276","恒瑞医药"), ("SH","600030","中信证券"), ("SZ","000333","美的集团"),
    ("SZ","000651","格力电器"), ("SZ","000725","京东方A"), ("SZ","300750","宁德时代"),
    ("SZ","002415","海康威视"),
]

def load_daily(mkt, code):
    fp = CACHE_D / f"{mkt.lower()}{code}_daily.json"
    rows = json.loads(fp.read_text("utf-8"))
    df = pd.DataFrame(rows)
    for col in ("datetime","date"):
        if col in df.columns: df["datetime"]=pd.to_datetime(df[col]); break
    return df.sort_values("datetime").reset_index(drop=True)

registry = get_registry()
entry = registry.get("chanlun_pair")
strat_cls = entry.strategy_cls

# 最优组合探索
configs = [
    # 已知最优点
    ("lag=1(基准)", {"confirm_lag": 1, "hold_in_higher_uptrend": False, "exit_trailing_stop_pct": 0.0}),
    ("趋势+lag=1", {"confirm_lag": 1, "hold_in_higher_uptrend": True, "exit_trailing_stop_pct": 0.0}),
    # 移动止盈
    ("lag=1+移动止盈5%", {"confirm_lag": 1, "hold_in_higher_uptrend": False, "exit_trailing_stop_pct": 0.05}),
    ("lag=1+移动止盈10%", {"confirm_lag": 1, "hold_in_higher_uptrend": False, "exit_trailing_stop_pct": 0.10}),
    ("lag=1+移动止盈15%", {"confirm_lag": 1, "hold_in_higher_uptrend": False, "exit_trailing_stop_pct": 0.15}),
    ("趋势+lag=1+移动止盈10%", {"confirm_lag": 1, "hold_in_higher_uptrend": True, "exit_trailing_stop_pct": 0.10}),
    ("趋势+lag=1+移动止盈15%", {"confirm_lag": 1, "hold_in_higher_uptrend": True, "exit_trailing_stop_pct": 0.15}),
    ("趋势+lag=1+移动止盈20%", {"confirm_lag": 1, "hold_in_higher_uptrend": True, "exit_trailing_stop_pct": 0.20}),
]

print(f"{'配置':24s} | {'年化':>8s} | {'超额':>8s} | {'交易':>6s} | {'胜率':>6s} | {'回撤':>8s} | {'夏普':>6s}")
print("-"*80)
sys.stdout.flush()

for label, extra in configs:
    params = {
        "zs_from_xd": False, "use_seg_mmd": False,
        "lookahead_guard": True,
        "min_confidence": 0.0, "use_2s_signals": True,
        "use_3buy": True, "use_3sell": True, "allow_pyramid": False,
        "exit_stop_loss_pct": 0.0,
        "seg_divergence_rate": 1.5, "bs1_peak": False,
        "bsp2_follow_1": False, "bsp3_follow_1": False, "max_bs2_rate": 1.0,
        **extra,
    }
    anns, excesses, trades, wins, mdds, sharps = [], [], [], [], [], []
    for mkt, code, name in STOCKS:
        df = load_daily(mkt, code)
        try:
            strat = entry.build(params)
            engine = BacktestEngine(strategy=strat_cls, cash=100000, commission=0.0003, stamp_tax=0.001, slippage=0.002)
            engine._strategy_instance = strat
            result = engine.run(df)
            perf = result.performance
            ann = perf.get("annual_return", 0) * 100
            bh = (df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100
            anns.append(ann); excesses.append(ann - bh)
            trades.append(len(result.trades) // 2)
            wins.append(perf.get("win_rate", 0) * 100)
            mdds.append(perf.get("max_drawdown", 0) * 100)
            sharps.append(perf.get("sharpe", 0))
        except Exception:
            anns.append(0); excesses.append(0); trades.append(0); wins.append(0); mdds.append(0); sharps.append(0)
    n = len(STOCKS)
    print(f"{label:24s} | {sum(anns)/n:7.2f}% | {sum(excesses)/n:+7.2f}% | {sum(trades)/n:6.1f} | {sum(wins)/n:5.1f}% | {sum(mdds)/n:7.2f}% | {sum(sharps)/n:6.2f}")
    sys.stdout.flush()

print("\nDone.")
