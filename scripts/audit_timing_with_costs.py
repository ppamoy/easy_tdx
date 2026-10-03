#!/usr/bin/env python3
"""V733：缠论择时 —— 扣掉交易成本后还剩多少？

两处修正（都是我自己上一版写错的）
----------------------------------
1. **基准口径**：第一版用「全样本局部极值」作基准。全样本基准把牛/熊/震荡
   混在一起，实测会系统性偏乐观 —— 3buy 在全样本基准下 +0.66%（"显著为正"），
   换成**同一滚动窗内**的局部极值基准变成 **-1.22%（符号翻转）**。
   本版改为同窗基准，与 `audit_rolling_oos.py` 一致。

2. **类二买/类二卖被漏掉**：第一版的 BUY/SELL 集合只有 1/2/3 类，
   `2buy_s`/`2sell_s`（类二买/类二卖）被静默跳过。

成本口径：按**单边**计入一次交易。A 股现实成本
  印花税卖出 0.05% + 佣金双边各 ~0.025% + 滑点 0~0.15%。

用法：  .venv/bin/python scripts/audit_timing_with_costs.py
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

DATA_DIR = ROOT / "audit_data"
HORIZONS = (5, 10, 20, 60)
N_WINDOWS = 6
MIN_N = 30
PIVOT = 5
BUY = {"1buy", "2buy", "2buy_s", "3buy"}
SELL = {"1sell", "2sell", "2sell_s", "3sell"}

COST_SCENARIOS = {
    "乐观 0.05%": 0.0005,
    "中性 0.10%": 0.0010,
    "保守 0.20%": 0.0020,
}


def norm_p(z: float) -> float:
    return float(erfc(abs(z) / sqrt(2)))


def pivot_indices(c: np.ndarray, w: int, low: bool, lo: int, hi: int) -> np.ndarray:
    out = []
    for i in range(max(w, lo), min(len(c) - w, hi)):
        seg = c[i - w : i + w + 1]
        if low and c[i] == seg.min():
            out.append(i)
        elif (not low) and c[i] == seg.max():
            out.append(i)
    return np.array(out, dtype=int)


def main() -> int:
    files = [p for p in sorted(DATA_DIR.glob("*.json"))
             if p.stem.split("_")[0] not in ("sh000300", "sh000001")]
    if not files:
        print(f"❌ {DATA_DIR} 无数据")
        return 2

    # 收集 (type, horizon, 信号收益, 同窗基准收益)
    rows: list[dict] = []
    for p in files:
        code = p.stem.split("_")[0]
        df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
        df["datetime"] = pd.to_datetime(df["datetime"])
        c = df["close"].to_numpy(dtype=float)
        n = len(c)
        if n < 500:
            continue
        res = ChanlunAnalyser(code=code, frequency="daily", config=ChanlunConfig()).process_klines(df)
        usable = n - max(HORIZONS)
        edges = np.linspace(0, usable, N_WINDOWS + 1).astype(int)

        for m in res.mmds:
            if not m.bi:
                continue
            st = m.mmd_type.value.lower()
            if st not in BUY and st not in SELL:
                continue
            i = m.bi.end.bar_index
            # ⚠️ 必须用「含 buy」判方向：若用「以 buy 结尾」，2buy_s 会被漏掉
            is_buy = "buy" in st
            w = int(np.searchsorted(edges[1:], i, side="right"))
            if w >= N_WINDOWS:
                continue
            lo, hi = int(edges[w]), int(edges[w + 1])
            rec: dict = {"type": st, "win": w}
            for h in HORIZONS:
                if i + h >= n:
                    continue
                r = c[i + h] / c[i] - 1.0
                if not is_buy:
                    r = -r
                cand = pivot_indices(c, PIVOT, low=is_buy, lo=lo, hi=hi)
                cand = cand[(cand + h) < n]
                if len(cand) < 5:
                    continue
                rr = c[cand + h] / c[cand] - 1.0
                if not is_buy:
                    rr = -rr
                rec[f"r{h}"] = float(r)
                rec[f"b{h}"] = float(np.mean(rr))
            rows.append(rec)
        print(f"  {p.stem}")

    X = pd.DataFrame(rows)
    print(f"\n总信号 {len(X)}（含类二买/类二卖，基准 = 同滚动窗局部极值）")

    print("\n" + "=" * 112)
    print("扣成本后的净超额（基准 = 同一滚动窗内的局部极值；cost = 单边）")
    print("=" * 112)
    print(f"{'类型':<9}{'窗口':>5}{'n':>6}{'毛超额':>9}"
          + "".join(f"{k:>14}" for k in COST_SCENARIOS))
    print("-" * 112)

    survive = {k: 0 for k in COST_SCENARIOS}
    total = 0
    for st in sorted(BUY | SELL):
        sub = X[X["type"] == st]
        if len(sub) < MIN_N:
            continue
        for h in HORIZONS:
            rc, bc = f"r{h}", f"b{h}"
            d = sub[[rc, bc]].dropna()
            if len(d) < MIN_N:
                continue
            diff = (d[rc] - d[bc]).to_numpy(dtype=float)
            gross = float(np.mean(diff))
            se = float(np.std(diff, ddof=1)) / sqrt(len(diff))
            p = norm_p(gross / se if se > 0 else 0.0)
            total += 1
            cells = []
            for name, cost in COST_SCENARIOS.items():
                net = gross - cost
                ok = (p < 0.05) and net > 0
                if ok:
                    survive[name] += 1
                cells.append(f"{net:>+9.2%}{'✅' if ok else ' '}")
            print(f"{st:<9}{h:>5}{len(d):>6}{gross:>+9.2%}" + "".join(f"{x:>14}" for x in cells))

    print("\n" + "-" * 112)
    print(f"总组合 {total}；毛超额>0 且 p<0.05 的组合中，扣成本后仍为正的：")
    for k, v in survive.items():
        print(f"  {k}: {v}/{total}")
    print("\n⚠️ 每笔只计一次单边成本（买或卖各一次）。完整往返（买+卖）需再翻倍。")
    print("⚠️ 未计冲击成本，实盘可用容量未知。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
