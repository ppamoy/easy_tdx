#!/usr/bin/env python3
"""V733：级别联立（区间套）与多周期 —— 预测力是否比单周期更强？

缠论原文最有说服力的用法之一是「区间套」：高级别买点被低级别同方向背驰确认。
本项目提供三条路径：
  1. ``qujiantao.compute_qujiantao_cross_period``  **真·区间套**（需另一份真实
     低周期行情，如日线 + 30 分钟）
  2. ``qujiantao.qujiantao_for_result``            同序列递归级别
  3. ``level_synth.synthesize_lower_level``        合成低级别（自述只是近似）

V731 已实测：路径 2/3 **不是**真区间套（路径 2 确认率仅 3%）。
故本脚本**只用真实跨周期数据**：把同一标的的日线合成**周线**（真实聚合，
非近似），做日线信号 + 周线结构的真正跨周期确认。

要回答的问题
------------
Q-A：被区间套确认的信号，其前瞻收益是否**显著高于**未被确认的信号？
     （若否，区间套只是"看起来更有说服力"，没有增量信息）
Q-B：周线级别的信号本身，预测力是否强于日线？（多周期是否有价值）

用法：  .venv/bin/python scripts/audit_qujiantao_power.py
"""

from __future__ import annotations

import json
import sys
from math import erfc, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402
from easy_tdx.chanlun.qujiantao import compute_qujiantao_cross_period  # noqa: E402

DATA_DIR = ROOT / "audit_data"
HORIZONS = (10, 20, 60)
MIN_N = 30
BUY = {"1buy", "2buy", "2buy_s", "3buy"}  # V733：补入类二买（此前被漏掉）
SELL = {"1sell", "2sell", "2sell_s", "3sell"}  # V733：补入类二卖


def norm_p(z: float) -> float:
    return float(erfc(abs(z) / sqrt(2)))


def to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """日线 → 周线（真实聚合：open 取首、close 取末、high/low 取极值）。"""
    d = df.set_index("datetime")
    agg = d.resample("W").agg(
        {"open": "first", "close": "last", "high": "max", "low": "min", "vol": "sum"}
    ).dropna()
    return agg.reset_index()


def main() -> int:
    files = [p for p in sorted(DATA_DIR.glob("*.json"))
             if p.stem.split("_")[0] not in ("sh000300", "sh000001")]
    if not files:
        print(f"❌ {DATA_DIR} 无数据")
        return 2

    # 每只标的：日线信号（经周线结构做跨周期确认）+ 前瞻收益
    rows: list[dict] = []
    wk_rows: list[dict] = []
    n_ok = 0
    for p in files:
        code = p.stem.split("_")[0]
        df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
        df["datetime"] = pd.to_datetime(df["datetime"])
        if len(df) < 400:
            continue

        rd = ChanlunAnalyser(code=code, frequency="daily", config=ChanlunConfig()).process_klines(df)
        wdf = to_weekly(df)
        rw = ChanlunAnalyser(code=code, frequency="weekly", config=ChanlunConfig()).process_klines(wdf)
        n_ok += 1

        # 周线信号自身的前瞻收益（按周线 bar）
        wc = wdf["close"].to_numpy(dtype=float)
        for m in rw.mmds:
            if not m.bi:
                continue
            st = m.mmd_type.value.lower()
            if st not in BUY and st not in SELL:
                continue
            i = m.bi.end.bar_index
            is_buy = st in BUY
            rec = {"symbol": code, "type": st}
            for h in (4, 8, 12):  # 周
                if i + h >= len(wc):
                    continue
                r = wc[i + h] / wc[i] - 1.0
                rec[f"r{h}"] = float(r) if is_buy else float(-r)
            wk_rows.append(rec)

        # 日线信号 → 用**周线**结构做真跨周期确认
        conf = compute_qujiantao_cross_period(
            rd.mmds,
            bis_low=rw.bis, zss_low=rw.zss, bcs_low=rw.bcs, mmds_low=rw.mmds,
        )
        c = df["close"].to_numpy(dtype=float)
        for m, cf in zip(rd.mmds, conf):
            if not m.bi:
                continue
            st = m.mmd_type.value.lower()
            if st not in BUY and st not in SELL:
                continue
            i = m.bi.end.bar_index
            is_buy = st in BUY
            rec = {"symbol": code, "type": st,
                   "nested": bool(cf.get("nested")) if cf else None,
                   "score": float(cf.get("score", 0.0)) if cf else None}
            for h in HORIZONS:
                if i + h >= len(c):
                    continue
                r = c[i + h] / c[i] - 1.0
                rec[f"r{h}"] = float(r) if is_buy else float(-r)
            rows.append(rec)
        print(f"  {p.stem}  日线信号 {len(rd.mmds)}  周线信号 {len(rw.mmds)}")

    X = pd.DataFrame(rows)
    W = pd.DataFrame(wk_rows)
    print(f"\n标的 {n_ok}；日线信号 {len(X)}（含确认信息），周线信号 {len(W)}")

    # ── Q-A：区间套确认是否有增量 ──
    print("\n" + "=" * 92)
    print("Q-A  被周线结构「区间套确认」的日线信号，前瞻收益是否更高？")
    print("=" * 92)
    print(f"{'窗口':>5}{'确认n':>8}{'确认均值':>11}{'未确认n':>9}{'未确认均值':>12}{'差':>10}{'p':>10}  判定")
    print("-" * 92)
    for h in HORIZONS:
        col = f"r{h}"
        a = X[X["nested"] == True][col].dropna().to_numpy(dtype=float)  # noqa: E712
        b = X[X["nested"] == False][col].dropna().to_numpy(dtype=float)  # noqa: E712
        if len(a) < MIN_N or len(b) < MIN_N:
            print(f"{h:>5}{len(a):>8}{'—':>11}{len(b):>9}{'—':>12}  样本不足（各需 ≥{MIN_N}）")
            continue
        d = float(np.mean(a) - np.mean(b))
        # Welch t
        se = sqrt(np.var(a, ddof=1) / len(a) + np.var(b, ddof=1) / len(b))
        z = d / se if se > 0 else 0.0
        p = norm_p(z)
        mark = "✅确认更高" if (p < 0.05 and d > 0) else ("❌确认更低" if (p < 0.05 and d < 0) else "—无差异")
        print(f"{h:>5}{len(a):>8}{np.mean(a):>11.3%}{len(b):>9}{np.mean(b):>12.3%}{d:>+10.2%}{p:>10.4f}  {mark}")

    # ── Q-B：周线 vs 日线 ──
    print("\n" + "=" * 92)
    print("Q-B  周线信号自身的预测力（对比日线同类已测结果）")
    print("=" * 92)
    print(f"{'类型':<7}{'周数':>5}{'n':>6}{'均值':>10}{'胜率':>8}")
    print("-" * 92)
    for st in sorted(BUY | SELL):
        sub = W[W["type"] == st]
        if len(sub) < MIN_N:
            print(f"{st:<7}{'—':>5}{len(sub):>6}  样本不足")
            continue
        for h in (4, 8, 12):
            col = f"r{h}"
            v = sub[col].dropna().to_numpy(dtype=float)
            if len(v) < MIN_N:
                continue
            print(f"{st:<7}{h:>5}{len(v):>6}{np.mean(v):>10.3%}{(v > 0).mean():>8.1%}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
