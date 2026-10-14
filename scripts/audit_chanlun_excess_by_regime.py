#!/usr/bin/env python3
"""把策略层的超额拆到「市场状态」上，看结论是不是被某一段/某一批标的撑起来的。

## 为什么必须做这一步
`audit_can_chanlun_make_money.py` 第二层给出全样本 超额 +16.14%、t=+2.79，
看上去"显著"。但按代码排序切前后半段时出现**剧烈分裂**：
  前半段（几乎全是 sh60xxxx 沪市主板）超额 +1.71%  t=+0.24
  后半段（几乎全是 sz 深市/创业板）  超额 +30.50% t=+3.59
⇒ 所谓"显著"很可能只是**样本构成（沪 vs 深）**的差异，不是模型能力。

本脚本回答三个问题：
  Q1 真实时间维度：把样本期按年份切开，超额是否稳定为正？
     （用真实回测区间，而不是按文件名排序）
  Q2 市场状态维度：熊市段（沪深300 下跌）与牛市段分别如何？
     若"超额"只来自熊市的空仓避跌，那是**少亏**不是**会赚**，
     而 A 股散户真正想要的是牛市里跟得上。
  Q3 板块维度：sh / sz / 创业板 分别如何？

用法：  .venv/bin/python scripts/audit_chanlun_excess_by_regime.py
       （默认读 /tmp/strategy_par.csv，可用 --csv 指定）
"""

from __future__ import annotations

import argparse
import json
import sys
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


def _run_one(args: tuple[str, pd.Timestamp, pd.Timestamp, float]):
    """子进程：在指定日期窗口内跑一只标的。"""
    code, start, end, slip = args
    p = DATA_DIR / f"{code}_daily.json"
    df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
    df["datetime"] = pd.to_datetime(df["datetime"])
    sub = df[(df["datetime"] >= start) & (df["datetime"] <= end)].reset_index(drop=True)
    if len(sub) < 60:
        return {"symbol": code, "strat": np.nan, "buyhold": np.nan, "n": 0}
    try:
        r = BacktestEngine(ChanlunStrategy(), cash=100000.0, slippage=slip).run(sub)
        strat = float(r.performance["total_return"])
        bh = float(sub["close"].iloc[-1] / sub["close"].iloc[0] - 1)
        return {"symbol": code, "strat": strat, "buyhold": bh, "n": len(sub)}
    except Exception:  # noqa: BLE001
        return {"symbol": code, "strat": np.nan, "buyhold": np.nan, "n": 0}


def t_stat(x: np.ndarray) -> float:
    if len(x) < 3 or np.std(x, ddof=1) == 0:
        return float("nan")
    return float(np.mean(x) / np.std(x, ddof=1) * np.sqrt(len(x)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--slippage", type=float, default=0.002)
    a = ap.parse_args()
    workers = resolve_workers(a.workers)

    codes = [p.stem.split("_")[0] for p in sorted(DATA_DIR.glob("*.json"))
             if p.stem.split("_")[0] not in ("sh000300", "sh000001")]

    # 用沪深300 划分牛熊段（真实时间维度）
    bench = pd.DataFrame(json.loads(
        (DATA_DIR / "sh000300_daily.json").read_text(encoding="utf-8")))
    bench["datetime"] = pd.to_datetime(bench["datetime"])

    windows: list[tuple[str, pd.Timestamp, pd.Timestamp]] = []
    for y in range(2021, 2027):
        s = bench[bench["datetime"].dt.year == y]
        if len(s) < 60:
            continue
        windows.append((str(y), s["datetime"].min(), s["datetime"].max()))

    print("【真实时间维度】逐年窗口（每只标的在同年区间内独立回测）")
    print("=" * 84)
    print("%-8s %6s %10s %10s %10s %8s %8s" % (
        "年份", "标的", "策略均值", "买入持有", "超额", "t", "跑赢%"))
    print("-" * 84)

    from concurrent.futures import ProcessPoolExecutor
    for name, s0, s1 in windows:
        jobs = [(c, s0, s1, a.slippage) for c in codes]
        with ProcessPoolExecutor(max_workers=workers) as ex:
            rows = list(ex.map(_run_one, jobs, chunksize=4))
        d = pd.DataFrame(rows).dropna(subset=["strat"])
        if len(d) < 10:
            print(f"{name}: 样本不足")
            continue
        x = (d["strat"] - d["buyhold"]).to_numpy()
        print("%-8s %6d %9.2f%% %9.2f%% %9.2f%% %8.2f %7.0f%%" % (
            name, len(d), d["strat"].mean() * 100, d["buyhold"].mean() * 100,
            x.mean() * 100, t_stat(x), (x > 0).mean() * 100))

    # 市场状态：按沪深300 该年涨跌分牛熊
    print("\n【市场状态维度】熊市 vs 牛市")
    print("-" * 84)
    bear_jobs, bull_jobs = [], []
    bear_names, bull_names = [], []
    for name, s0, s1 in windows:
        s = bench[(bench["datetime"] >= s0) & (bench["datetime"] <= s1)]
        ret = float(s["close"].iloc[-1] / s["close"].iloc[0] - 1)
        tgt = bear_jobs if ret < 0 else bull_jobs
        tgt.extend([(c, s0, s1, a.slippage) for c in codes])
        (bear_names if ret < 0 else bull_names).append(f"{name}({ret*100:+.1f}%)")

    for label, jobs, names in (("熊市段", bear_jobs, bear_names),
                               ("牛市段", bull_jobs, bull_names)):
        if not jobs:
            continue
        with ProcessPoolExecutor(max_workers=workers) as ex:
            rows = list(ex.map(_run_one, jobs, chunksize=4))
        d = pd.DataFrame(rows).dropna(subset=["strat"])
        x = (d["strat"] - d["buyhold"]).to_numpy()
        print(f"\n{label}  含 {'/'.join(names)}   n={len(d)}")
        print(f"  策略均值 {d['strat'].mean()*100:+7.2f}%   "
              f"买入持有 {d['buyhold'].mean()*100:+7.2f}%")
        print(f"  超额     {x.mean()*100:+7.2f}%   t={t_stat(x):+.2f}   "
              f"跑赢 {(x > 0).mean()*100:.0f}%")

    print("\n" + "=" * 84)
    print("读法：")
    print("  * 若熊市段超额为正、牛市段超额为负 ⇒ 策略只是「熊市少亏」，")
    print("    代价是牛市跟不上 —— 长期复利未必划算。")
    print("  * 若逐年符号翻转 ⇒ 结论不可外推。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
