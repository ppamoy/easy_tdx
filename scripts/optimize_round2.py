#!/usr/bin/env python3
"""第二轮优化：基于 hold_in_higher_uptrend=6.40% 的最优配置，探索更多组合。

关键发现：
- hold_in_higher_uptrend=True → 6.40% (vs 4.10% baseline)
- 止损有害，不加
- 金字塔无效
- 正在等 lag=1 和 全开 结果

本轮测试：
1. 趋势持有 + seg_mmd (T3修复后信号更丰富)
2. 趋势持有 + lag=2
3. 趋势持有 + 只用1+2买卖（排除3买卖的噪音）
4. 趋势持有 + 只做多（不开空仓信号）
5. 趋势持有 + seg_mmd_hybrid (T1线段级 + T2T3笔级 + 趋势持有)
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

configs = [
    # 趋势持有是已知最优，作为基准
    ("趋势持有(基准)", {
        "hold_in_higher_uptrend": True, "confirm_lag": 3,
        "use_seg_mmd": False, "use_3buy": True, "use_3sell": True,
        "exit_stop_loss_pct": 0.0, "min_confidence": 0.0,
    }),
    # 趋势 + seg_mmd (T3修复后)
    ("趋势+seg_mmd", {
        "hold_in_higher_uptrend": True, "confirm_lag": 3,
        "use_seg_mmd": True, "seg_mmd_hybrid": False,
        "use_3buy": True, "use_3sell": True,
        "exit_stop_loss_pct": 0.0, "min_confidence": 0.0,
    }),
    # 趋势 + seg_mmd_hybrid (T1线段 + T2T3笔)
    ("趋势+hybrid", {
        "hold_in_higher_uptrend": True, "confirm_lag": 3,
        "use_seg_mmd": True, "seg_mmd_hybrid": True,
        "use_3buy": True, "use_3sell": True,
        "exit_stop_loss_pct": 0.0, "min_confidence": 0.0,
    }),
    # 趋势 + 只1+2买卖
    ("趋势+只1+2", {
        "hold_in_higher_uptrend": True, "confirm_lag": 3,
        "use_seg_mmd": False, "use_3buy": False, "use_3sell": False,
        "exit_stop_loss_pct": 0.0, "min_confidence": 0.0,
    }),
    # 趋势 + lag=2
    ("趋势+lag=2", {
        "hold_in_higher_uptrend": True, "confirm_lag": 2,
        "use_seg_mmd": False, "use_3buy": True, "use_3sell": True,
        "exit_stop_loss_pct": 0.0, "min_confidence": 0.0,
    }),
    # 趋势 + lag=1
    ("趋势+lag=1", {
        "hold_in_higher_uptrend": True, "confirm_lag": 1,
        "use_seg_mmd": False, "use_3buy": True, "use_3sell": True,
        "exit_stop_loss_pct": 0.0, "min_confidence": 0.0,
    }),
]

print(f"{'配置':16s} | {'年化':>8s} | {'超额':>8s} | {'交易':>6s} | {'胜率':>6s} | {'回撤':>8s} | {'夏普':>6s}")
print("-"*75)
sys.stdout.flush()

for label, extra in configs:
    params = {
        "zs_from_xd": False, "lookahead_guard": True,
        "use_2s_signals": True, "allow_pyramid": False,
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
    print(f"{label:16s} | {sum(anns)/n:7.2f}% | {sum(excesses)/n:+7.2f}% | {sum(trades)/n:6.1f} | {sum(wins)/n:5.1f}% | {sum(mdds)/n:7.2f}% | {sum(sharps)/n:6.2f}")
    sys.stdout.flush()

print("\nDone.")
