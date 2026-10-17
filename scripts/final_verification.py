#!/usr/bin/env python3
"""最终验证：lag=1 最优配置的详细回测 + 前视守卫通过率。

测试矩阵：
  1. lag=1 (已知 8.13%) — 详细逐股 + 守卫通过率
  2. 趋势+lag=1 — 如果 bash-69 结果好
  3. lag=1 + 移动止盈(5/10/15/20%)
  4. 对照组：lag=3 (原基准)

每只股票报告：年化/超额/交易/胜率/回撤/夏普 + 守卫通过率。
"""
from _chanlun_lib import drop_unknown_params  # noqa: E402
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
entry = registry.get("chanlun")
strat_cls = entry.strategy_cls

def count_signals(df, params):
    """统计守卫前/后的信号数。"""
    # 无守卫 → 候选信号数
    p_no_guard = {**params, "lookahead_guard": False}
    strat_ng = entry.build(drop_unknown_params(entry, p_no_guard))
    engine_ng = BacktestEngine(strategy=strat_cls, cash=100000, commission=0.0003, stamp_tax=0.001, slippage=0.002)
    engine_ng._strategy_instance = strat_ng
    strat_ng._bind_data(df)
    strat_ng._call_init()
    n_candidates = len(getattr(strat_ng, "_chanlun_signals", []))

    # 有守卫 → 通过信号数
    p_guard = {**params, "lookahead_guard": True}
    strat_g = entry.build(p_guard)
    engine_g = BacktestEngine(strategy=strat_cls, cash=100000, commission=0.0003, stamp_tax=0.001, slippage=0.002)
    engine_g._strategy_instance = strat_g
    strat_g._bind_data(df)
    strat_g._call_init()
    # _apply_lookahead_guard 在 _call_init 里调用
    n_passed = len(getattr(strat_g, "_chanlun_signals", []))

    return n_candidates, n_passed

# === 逐股详细报告 ===
def run_detailed(label, params):
    print(f"\n{'='*90}")
    print(f"  {label}")
    print(f"{'='*90}")
    print(f"{'股票':10s} | {'年化':>8s} | {'超额':>8s} | {'交易':>4s} | {'胜率':>6s} | {'回撤':>8s} | {'夏普':>6s} | {'候选':>4s} | {'通过':>4s} | {'通过率':>6s}")
    print("-"*90)

    results = []
    for mkt, code, name in STOCKS:
        df = load_daily(mkt, code)
        try:
            strat = entry.build(drop_unknown_params(entry, params))
            engine = BacktestEngine(strategy=strat_cls, cash=100000, commission=0.0003, stamp_tax=0.001, slippage=0.002)
            engine._strategy_instance = strat
            result = engine.run(df)
            perf = result.performance
            ann = perf.get("annual_return", 0) * 100
            bh = (df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100
            n_trades = len(result.trades) // 2
            win = perf.get("win_rate", 0) * 100
            mdd = perf.get("max_drawdown", 0) * 100
            sharpe = perf.get("sharpe", 0)

            n_cand, n_pass = count_signals(df, params)
            pass_rate = n_pass / n_cand * 100 if n_cand > 0 else 0

            print(f"{name:10s} | {ann:7.2f}% | {ann-bh:+7.2f}% | {n_trades:4d} | {win:5.1f}% | {mdd:7.2f}% | {sharpe:6.2f} | {n_cand:4d} | {n_pass:4d} | {pass_rate:5.1f}%")
            results.append({"name": name, "ann": ann, "excess": ann-bh, "trades": n_trades, "win": win, "mdd": mdd, "sharpe": sharpe, "cand": n_cand, "pass": n_pass, "pass_rate": pass_rate})
        except Exception as e:
            print(f"{name:10s} | ERROR: {e}")
            results.append({"name": name, "ann": 0, "excess": 0, "trades": 0, "win": 0, "mdd": 0, "sharpe": 0, "cand": 0, "pass": 0, "pass_rate": 0})

    n = len(results)
    if n == 0:
        return results
    print("-"*90)
    avg = lambda k: sum(r[k] for r in results) / n
    print(f"{'平均':10s} | {avg('ann'):7.2f}% | {avg('excess'):+7.2f}% | {avg('trades'):4.1f} | {avg('win'):5.1f}% | {avg('mdd'):7.2f}% | {avg('sharpe'):6.2f} | {avg('cand'):4.1f} | {avg('pass'):4.1f} | {avg('pass_rate'):5.1f}%")
    return results

t0 = time.time()

# 1. lag=3 基准
res_a = run_detailed("A. lag=3 基准 (confirm_lag=3)", { "lookahead_guard": True,
    "confirm_lag": 3, "min_confidence": 0.0, "use_2s_signals": True,
    "use_3buy": True, "use_3sell": True, "allow_pyramid": False,
    "seg_divergence_rate": 1.5, "bs1_peak": False,
    "bsp2_follow_1": False, "bsp3_follow_1": False, "max_bs2_rate": 1.0,
})

# 2. lag=1 最优
res_b = run_detailed("B. lag=1 最优 (confirm_lag=1)", { "lookahead_guard": True,
    "confirm_lag": 1, "min_confidence": 0.0, "use_2s_signals": True,
    "use_3buy": True, "use_3sell": True, "allow_pyramid": False,
    "seg_divergence_rate": 1.5, "bs1_peak": False,
    "bsp2_follow_1": False, "bsp3_follow_1": False, "max_bs2_rate": 1.0,
})

# 3. 趋势+lag=1
res_c = run_detailed("C. lag=1", { "lookahead_guard": True,
    "confirm_lag": 1, "min_confidence": 0.0, "use_2s_signals": True,
    "use_3buy": True, "use_3sell": True, "allow_pyramid": False,
    "seg_divergence_rate": 1.5, "bs1_peak": False,
    "bsp2_follow_1": False, "bsp3_follow_1": False, "max_bs2_rate": 1.0,
})

# 4. 趋势+lag=1+移动止盈10%
res_d = run_detailed("D. 趋势+lag=1+移动止盈10%", { "lookahead_guard": True,
    "confirm_lag": 1, "min_confidence": 0.0, "use_2s_signals": True,
    "use_3buy": True, "use_3sell": True, "allow_pyramid": False,
    "seg_divergence_rate": 1.5, "bs1_peak": False,
    "bsp2_follow_1": False, "bsp3_follow_1": False, "max_bs2_rate": 1.0,
})

# === 对比总结 ===
print(f"\n{'='*70}")
print("  对比总结")
print(f"{'='*70}")
print(f"{'配置':30s} | {'年化':>8s} | {'超额':>8s} | {'交易':>6s} | {'胜率':>6s} | {'回撤':>8s} | {'夏普':>6s} | {'守卫通过率':>10s}")
print("-"*90)
for label, res in [("A. lag=3 基准", res_a), ("B. lag=1", res_b), ("C. 趋势+lag=1", res_c), ("D. 趋势+lag=1+移动止盈10%", res_d)]:
    n = len(res)
    if n == 0:
        continue
    avg = lambda k: sum(r[k] for r in res) / n
    print(f"{label:30s} | {avg('ann'):7.2f}% | {avg('excess'):+7.2f}% | {avg('trades'):6.1f} | {avg('win'):5.1f}% | {avg('mdd'):7.2f}% | {avg('sharpe'):6.2f} | {avg('pass_rate'):9.1f}%")

print(f"\n买入持有: {sum((lambda m,c: (load_daily(m,c)['close'].iloc[-1]/load_daily(m,c)['close'].iloc[0]-1)*100)(m,c) for m,c,_ in STOCKS)/len(STOCKS):.2f}%")
print(f"\n总耗时: {time.time()-t0:.1f}s")
