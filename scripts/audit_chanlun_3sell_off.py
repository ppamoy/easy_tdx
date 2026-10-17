#!/usr/bin/env python3
"""检验假设：**3卖（3sell）是拖垮胜率的那类信号**。

## 假设来源
`audit_chanlun_pair_winrate.py` 全量 2802 笔配对按卖点类型拆开
（该脚本现走 chanlun 原文口径，配对由 trades 重组）：

| 卖点  | 笔数 | 胜率  | 平均收益 |
|-------|------|-------|----------|
| 1sell | 1014 | 82.9% | +18.59%  |
| 2sell |  149 | 14.1% | -5.55%   |
| **3sell** | **1639** | **26.8%** | **-5.14%** |

3卖 占了 58% 的平仓笔数，却是**负收益**。而原口径策略是多头只读，
3卖 出场 = 在下跌趋势中割肉。这提示：**大部分仓位被最差的那类信号平掉了**。

## ⚠️ 历史变更
原先用 ``ChanlunPairStrategy``（自带 ``pair_log``）；该策略已废弃删除
（区间套用 level_synth 合成数据，是伪区间套），现改用
``_chanlun_lib.make_original_strategy`` + ``pairs_from_trades``。

## 本脚本验证
对同一批标的，跑三个口径对比：
  A. 默认（3买/3卖 都开）
  B. 只关 3sell（保留 3buy）
  C. 3买/3卖 全关
看超额与胜率如何变化。若 B 明显优于 A，则假设成立 ——
即"胜率低"有一部分责任在**默认参数开了 3sell**，而非缠论理论本身。

## 抽样说明
`--step N` 按代码排序隔 N 个取一个，目的是**跨市场抽样**
（前段几乎全是 sh60xxxx、后段是 sz，若只取前 100 只就全是沪市，
基准超额≈0，看不出差异）。

用法：  .venv/bin/python scripts/audit_chanlun_3sell_off.py --step 5 --workers 2
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from _chanlun_lib import make_original_strategy, pairs_from_trades  # noqa: E402
from _concurrency import resolve_workers  # noqa: E402
from easy_tdx.backtest.engine import BacktestEngine  # noqa: E402

DATA_DIR = ROOT / "audit_data"

VARIANTS = (
    ("A 默认(3buy+3sell)", {}),
    ("B 只关3sell", {"use_3sell": False}),
    ("C 全关3buy3sell", {"use_3buy": False, "use_3sell": False}),
)

_SLIP = 0.002


def _job(code: str) -> tuple[str, dict, float]:
    """子进程：一只标的 × 全部口径。"""
    p = DATA_DIR / f"{code}_daily.json"
    df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
    df["datetime"] = pd.to_datetime(df["datetime"])
    bh = float(df["close"].iloc[-1] / df["close"].iloc[0] - 1)
    out: dict[str, tuple[float, float, int]] = {}
    for lab, kw in VARIANTS:
        try:
            r = BacktestEngine(
                make_original_strategy(**kw), cash=100000.0, slippage=_SLIP
            ).run(df)
            pf = r.performance
            out[lab] = (float(pf["total_return"]),
                        float(pf.get("win_rate", np.nan)),
                        int(pf.get("total_trades", 0) or 0))
        except Exception:  # noqa: BLE001
            out[lab] = (float("nan"), float("nan"), 0)
    return code, out, bh


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, default=5, help="隔 N 个取一个（跨市场抽样）")
    ap.add_argument("--limit", type=int, default=0, help="上限（0=不限）")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--slippage", type=float, default=0.002)
    a = ap.parse_args()

    global _SLIP
    _SLIP = a.slippage
    workers = resolve_workers(a.workers)

    codes = [p.split("/")[-1].split("_")[0]
             for p in sorted(glob.glob(str(DATA_DIR / "*.json")))]
    codes = [c for c in codes if c not in ("sh000300", "sh000001")]
    codes = codes[::a.step]
    if a.limit:
        codes = codes[:a.limit]

    n_sh = sum(1 for c in codes if c.startswith("sh"))
    print(f"样本 {len(codes)} 只（sh {n_sh} / sz {len(codes)-n_sh}，跨市场抽样 step={a.step}）")
    print(f"并行度 {workers}   每只跑 {len(VARIANTS)} 个口径\n")

    from concurrent.futures import ProcessPoolExecutor
    rows = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, (code, out, bh) in enumerate(ex.map(_job, codes, chunksize=1)):
            rows.append((code, out, bh))
            if (i + 1) % 20 == 0:
                print(f"  进度 {i+1}/{len(codes)}", flush=True)

    agg: dict[str, list[tuple[float, float, int]]] = defaultdict(list)
    for code, out, bh in rows:
        for lab, _kw in VARIANTS:
            v = out.get(lab)
            if v and not np.isnan(v[0]):
                agg[lab].append((v[0] - bh, v[1], v[2]))

    print("\n%-20s %6s %10s %8s %8s %8s" % ("口径", "n", "超额", "胜率", "t", "交易数"))
    print("-" * 72)
    for lab, _kw in VARIANTS:
        v = agg.get(lab, [])
        if not v:
            continue
        ex_ = np.array([x[0] for x in v])
        wr = np.array([x[1] for x in v])
        tr = np.array([x[2] for x in v])
        t = float(np.mean(ex_) / np.std(ex_, ddof=1) * np.sqrt(len(ex_))) \
            if len(ex_) > 2 and np.std(ex_, ddof=1) > 0 else float("nan")
        print("%-20s %6d %+9.2f%% %7.1f%% %8.2f %8.1f" % (
            lab, len(ex_), np.mean(ex_) * 100, np.nanmean(wr) * 100, t, np.mean(tr)))

    print("\n【判定】")
    a_ex = np.mean([x[0] for x in agg.get(VARIANTS[0][0], [(np.nan,)])])
    b_ex = np.mean([x[0] for x in agg.get(VARIANTS[1][0], [(np.nan,)])])
    if not (np.isnan(a_ex) or np.isnan(b_ex)):
        if b_ex > a_ex:
            print(f"  关掉 3sell 后超额 {a_ex*100:+.2f}% → {b_ex*100:+.2f}%"
                  f"（改善 {(b_ex-a_ex)*100:+.2f} 个百分点）")
            print("  ⇒ 假设成立：默认开启 3sell 确实拖累了表现。")
        else:
            print(f"  关掉 3sell 后超额 {a_ex*100:+.2f}% → {b_ex*100:+.2f}%"
                  f"（变差 {(b_ex-a_ex)*100:+.2f} 个百分点）")
            print("  ⇒ 假设不成立：3sell 不是主因（关掉反而不利）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
