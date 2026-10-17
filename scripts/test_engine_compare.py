#!/usr/bin/env python3
"""正式回测引擎对比测试：zs_from_xd=True(原文) vs False(笔构中枢)。

用前视守卫(lookahead_guard)确保信号不依赖未来数据。
"""
import json, sys, time
from pathlib import Path
import pandas as pd

sys.path.insert(0, "/home/skp/workspace/easy_tdx/src")
from easy_tdx.backtest import BacktestEngine
from easy_tdx.backtest.strategies import get_registry

sys.path.insert(0, "/home/skp/workspace/easy_tdx/scripts")
from _chanlun_lib import drop_unknown_params  # noqa: E402

CACHE_D = Path("/home/skp/workspace/easy_tdx/audit_data")
STOCKS = [
    ("SH","600000","浦发银行"), ("SH","600036","招商银行"), ("SH","601318","中国平安"),
    ("SH","600276","恒瑞医药"), ("SH","600030","中信证券"), ("SZ","000333","美的集团"),
    ("SZ","000651","格力电器"), ("SZ","000725","京东方A"), ("SZ","300750","宁德时代"),
    ("SZ","002415","海康威视"),
]

def load(m, c):
    fp = CACHE_D / f"{m.lower()}{c}_daily.json"
    if not fp.is_file(): return None
    rows = json.loads(fp.read_text("utf-8"))
    df = pd.DataFrame(rows)
    for col in ("datetime","date"):
        if col in df.columns: df["datetime"]=pd.to_datetime(df[col]); break
    return df.sort_values("datetime").reset_index(drop=True)

def run_test(zfx, guard=True, lag=3):
    reg = get_registry()
    entry = reg.get("chanlun")

    print(f"\n{'='*100}")
    print(f"zs_from_xd={zfx}  lookahead_guard={guard}  confirm_lag={lag}")
    print(f"{'='*100}")
    print(f"{'股票':10s} | {'年化':>8s} | {'超额':>8s} | {'交易':>6s} | {'胜率':>6s} | {'终值':>12s} | {'买入持有':>8s} | {'耗时':>6s}")
    print("-"*85)

    tot_ann, tot_bh, tot_exc, tot_trd, tot_wr, n = 0,0,0,0,0,0

    for mkt, code, name in STOCKS:
        df = load(mkt, code)
        if df is None or len(df) < 100:
            print(f"{name:10s} | 跳过")
            continue
        t0 = time.time()
        strategy = entry.build(drop_unknown_params(entry, {
            "bi_type": "new",
            "lookahead_guard": guard,
            "confirm_lag": lag,
            "zs_from_xd": zfx,
        }))
        engine = BacktestEngine(
            strategy=strategy, cash=1_000_000,
            commission=0.0003, stamp_tax=0.001, slippage=0.002,
            execution="next_open",
        )
        result = engine.run(df)
        elapsed = time.time() - t0

        perf = result.performance
        ann = perf.get("annual_return", 0) * 100
        trd = perf.get("total_trades", 0)
        wr = perf.get("win_rate", 0) * 100 if trd > 0 else 0
        end_val = perf.get("end_value", 0)

        yr = (df.iloc[-1]["datetime"]-df.iloc[0]["datetime"]).days/365.25
        bh = ((float(df.iloc[-1]["close"])/float(df.iloc[0]["close"]))**(1/yr)-1)*100 if yr>0 else 0
        exc = ann - bh

        print(f"{name:10s} | {ann:7.2f}% | {exc:+7.2f}% | {trd:5d} | {wr:5.1f}% | {end_val:12.0f} | {bh:7.2f}% | {elapsed:5.1f}s")

        tot_ann += ann; tot_bh += bh; tot_exc += exc
        tot_trd += trd; tot_wr += wr; n += 1

    print("-"*85)
    print(f"{'平均':10s} | {tot_ann/n:7.2f}% | {tot_exc/n:+7.2f}% | {tot_trd/n:5.1f} | {tot_wr/n:5.1f}% | {'—':>12s} | {tot_bh/n:7.2f}% |")
    return {"ann": tot_ann/n, "exc": tot_exc/n, "trd": tot_trd/n, "wr": tot_wr/n, "bh": tot_bh/n, "n": n}

# === 对比测试 ===
results = {}
print("\n" + "="*100)
print("原文买卖点年化收益率 — 正式回测引擎对比（10只A股，日线，约6年）")
print("="*100)

# 1. 原文(线段构中枢) + 前视守卫
results["原文+守卫"] = run_test(zfx=True, guard=True, lag=3)

# 2. 笔构中枢(非原文) + 前视守卫
results["笔构+守卫"] = run_test(zfx=False, guard=True, lag=3)

# 3. 原文(线段构中枢) 无守卫（对照）
results["原文无守卫"] = run_test(zfx=True, guard=False, lag=3)

# 4. 笔构中枢(非原文) 无守卫（对照）
results["笔构无守卫"] = run_test(zfx=False, guard=False, lag=3)

# === 汇总 ===
print("\n" + "="*100)
print("汇总对比")
print("="*100)
print(f"{'方案':20s} | {'年化':>8s} | {'超额':>8s} | {'交易/股':>8s} | {'胜率':>6s} | {'买入持有':>8s}")
print("-"*65)
for name, r in results.items():
    print(f"{name:20s} | {r['ann']:7.2f}% | {r['exc']:+7.2f}% | {r['trd']:7.1f} | {r['wr']:5.1f}% | {r['bh']:7.2f}%")
print("="*100)
