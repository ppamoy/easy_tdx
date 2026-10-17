#!/usr/bin/env python3
"""线段级别买卖点回测脚本。

对比：
  A. 笔级别买卖点 (use_seg_mmd=False) — 原有行为
  B. 线段级别买卖点 (use_seg_mmd=True) — chan.py 式买卖点

两组都开启前视守卫，10只股票，日线，~6年。
"""

from _chanlun_lib import drop_unknown_params  # noqa: E402
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, "src")

from easy_tdx.backtest.engine import BacktestEngine
from easy_tdx.backtest.strategies.registry import get_registry

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


def load_daily(mkt, code):
    fp = CACHE_D / f"{mkt.lower()}{code}_daily.json"
    if not fp.is_file():
        return None
    rows = json.loads(fp.read_text("utf-8"))
    df = pd.DataFrame(rows)
    for col in ("datetime", "date"):
        if col in df.columns:
            df["datetime"] = pd.to_datetime(df[col])
            break
    return df.sort_values("datetime").reset_index(drop=True)


def run_backtest(use_seg_mmd, label):
    """跑一组回测。"""
    registry = get_registry()
    entry = registry.get("chanlun")
    strat_cls = entry.strategy_cls

    results = []
    print(f"\n{'='*80}")
    print(f"  {label}")
    print(f"{'='*80}")
    print(f"{'股票':10s} | {'年化':>8s} | {'超额':>8s} | {'交易':>4s} | {'胜率':>6s} | {'回撤':>8s} | {'夏普':>6s}")
    print("-" * 70)

    for mkt, code, name in STOCKS:
        df = load_daily(mkt, code)
        if df is None:
            continue

        params = {
            "zs_from_xd": False,
            "use_seg_mmd": use_seg_mmd,
            "lookahead_guard": True,
            "confirm_lag": 3,
            "min_confidence": 0.0,
            "use_2s_signals": True,
            "use_3buy": True,
            "use_3sell": True,
            "allow_pyramid": False,
            "seg_divergence_rate": 1.5,
            "bs1_peak": False,
            "bsp2_follow_1": False,
            "bsp3_follow_1": False,
            "max_bs2_rate": 1.0,
        }

        try:
            engine = BacktestEngine(
                strategy=strat_cls,
                cash=100000,
                commission=0.0003,
                stamp_tax=0.001,
                slippage=0.002,
            )
            # 注入策略参数：engine 内部创建策略实例时使用
            # 但 engine 用 strategy class 初始化，参数在 _call_init 里从 self.p 取
            # 需要先创建实例
            strat = entry.build(drop_unknown_params(entry, params))
            engine._strategy_instance = strat
            result = engine.run(df)

            perf = result.performance
            trades_df = result.trades

            ann = perf.get("annual_return", 0) * 100
            total_ret = perf.get("total_return", 0) * 100
            mdd = perf.get("max_drawdown", 0) * 100
            sharpe = perf.get("sharpe", 0)
            win_rate = perf.get("win_rate", 0) * 100

            # 计算买入持有收益
            bh_ret = (df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100
            excess = ann - bh_ret

            n_trades = len(trades_df) // 2 if len(trades_df) > 0 else 0

            print(f"{name:10s} | {ann:7.2f}% | {excess:+7.2f}% | {n_trades:4d} | {win_rate:5.1f}% | {mdd:7.2f}% | {sharpe:6.2f}")

            results.append({
                "name": name,
                "ann": ann,
                "excess": excess,
                "trades": n_trades,
                "win_rate": win_rate,
                "mdd": mdd,
                "sharpe": sharpe,
                "bh": bh_ret,
            })
        except Exception as e:
            import traceback
            print(f"{name:10s} | ERROR: {e}")
            traceback.print_exc()
            results.append({"name": name, "ann": 0, "excess": 0, "trades": 0, "win_rate": 0, "mdd": 0, "sharpe": 0, "bh": 0})

    # 汇总
    n = len(results)
    if n == 0:
        return results
    avg_ann = sum(r["ann"] for r in results) / n
    avg_excess = sum(r["excess"] for r in results) / n
    avg_trades = sum(r["trades"] for r in results) / n
    avg_win = sum(r["win_rate"] for r in results) / n
    avg_mdd = sum(r["mdd"] for r in results) / n
    avg_sharpe = sum(r["sharpe"] for r in results) / n
    avg_bh = sum(r["bh"] for r in results) / n
    print("-" * 70)
    print(f"{'平均':10s} | {avg_ann:7.2f}% | {avg_excess:+7.2f}% | {avg_trades:4.1f} | {avg_win:5.1f}% | {avg_mdd:7.2f}% | {avg_sharpe:6.2f}")
    print(f"{'买入持有':10s} | {avg_bh:7.2f}%")
    return results


def main():
    t0 = time.time()
    # A. 笔级别买卖点（原有行为）
    res_a = run_backtest(False, "A. 笔级别买卖点 (use_seg_mmd=False, zs_from_xd=False)")
    # B. 线段级别买卖点（chan.py 式）
    res_b = run_backtest(True, "B. 线段级别买卖点 (use_seg_mmd=True, 参考 chan.py)")

    print(f"\n{'='*70}")
    print("  对比总结")
    print(f"{'='*70}")
    if res_a and res_b:
        print(f"{'指标':12s} | {'笔级别':>12s} | {'线段级别':>12s} | {'差异':>12s}")
        print("-" * 55)
        for key, label in [("ann", "年化%"), ("excess", "超额%"), ("trades", "交易/股"), ("win_rate", "胜率%"), ("mdd", "回撤%"), ("sharpe", "夏普")]:
            a = sum(r[key] for r in res_a) / len(res_a)
            b = sum(r[key] for r in res_b) / len(res_b)
            diff = b - a
            print(f"{label:12s} | {a:12.2f} | {b:12.2f} | {diff:+12.2f}")
    print(f"\n总耗时: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
