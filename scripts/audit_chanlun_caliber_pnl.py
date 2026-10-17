#!/usr/bin/env python3
"""扣成本对照回测：2买/2卖 三种口径（A 原始≤40 / B 完全不限 / C 只第一笔回调）
到底哪个更赚？—— 决定 `mmd_2nd_span_max_bars` 默认值的**唯一依据**。

背景（docs/CHANLUN_FIDELITY_AUDIT_V734.md §3）：
  V734 发现 config.mmd_2nd_span_max_bars 长期形同虚设，真放开后信号数大变：
      A 原始≤40 合计135 / B 完全不限 263 / C 只第一笔 107（25 只日线）
  但**信号多 ≠ 更赚**。本脚本用 chanlun 原文口径（纯买卖点配对，止损止盈设 0
  截断）在带成本（佣金0.03% + 印花税0.1% + 滑点0.2%）下实测收益。

⚠️ 关键纪律（我踩过的坑，见 docs §6 教训 3）：
  **不能**靠 `BacktestEngine.run()` 跑 A/B —— 引擎内部用的是**已安装**的
  chanlun 模块，exec 出来的副本不参与。必须 patch 到引擎实际调用的路径上。

用法：  .venv/bin/python scripts/audit_chanlun_caliber_pnl.py --limit 25
"""

from __future__ import annotations

import argparse
import json
import sys
import types
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from _concurrency import resolve_workers  # noqa: E402

DATA_DIR = ROOT / "audit_data"
EXCLUDE = {"sh000300", "sh000001"}

# 成本（与 BacktestEngine 默认一致）
COMMISSION = 0.0003
STAMP = 0.001
SLIPPAGE = 0.002
ROUND_TRIP = COMMISSION * 2 + STAMP + SLIPPAGE * 2  # ≈ 0.56%

CALIBERS = {
    "A_≤40":      dict(limit=40,      first_only=False),
    "B_完全不限":  dict(limit=10**9,   first_only=False),
    "C_只第一笔":  dict(limit=10**9,   first_only=True),
}


def _build_caliber(limit, first_only):
    """exec 出一份改过的 mmd 模块。返回 module。"""
    src = (ROOT / "src/easy_tdx/chanlun/mmd.py").read_text(encoding="utf-8")
    anchor_cfg = "if _max_2nd_span > 0 and total_time > _max_2nd_span:"
    n = src.count(anchor_cfg)
    if n != 2:
        raise SystemExit(f"锚点命中 {n} 次（应 2：买侧+卖侧），源码已漂移")
    src = src.replace(anchor_cfg, f"if total_time > {limit}:")
    if first_only:
        ab = "for bi in bis[bis.index(leave_bi_up) + 1 :]:"
        as_ = "for bi in bis[bis.index(leave_bi_down) + 1 :]:"
        if src.count(ab) != 1 or src.count(as_) != 1:
            raise SystemExit("first_only 锚点不唯一")
        src = src.replace(ab, "for bi in bis[bis.index(leave_bi_up) + 1 : bis.index(leave_bi_up) + 2]:")
        src = src.replace(as_, "for bi in bis[bis.index(leave_bi_down) + 1 : bis.index(leave_bi_down) + 2]:")
    mod = types.ModuleType(f"mmd_cal_{limit}_{first_only}")
    mod.__file__ = "mmd.py"
    sys.modules[mod.__name__] = mod
    exec(compile(src, "mmd.py", "exec"), mod.__dict__)
    return mod


def _pairs_for_caliber(code, caliber):
    """在指定口径下跑一只标的，返回逐笔配对。"""
    from easy_tdx.backtest.engine import BacktestEngine
    import easy_tdx.chanlun.analyser as A

    from _chanlun_lib import make_original_strategy, pairs_from_trades

    mod = _build_caliber(caliber["limit"], caliber["first_only"])
    # patch 到 analyser 实际引用的符号上（教训 3）
    saved = A.find_mmds_v44
    A.find_mmds_v44 = mod.find_mmds_v44
    try:
        p = DATA_DIR / f"{code}_daily.json"
        df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
        df["datetime"] = pd.to_datetime(df["datetime"])
        s = make_original_strategy()
        r = BacktestEngine(
            s, cash=100000.0, commission=COMMISSION, stamp_tax=STAMP, slippage=SLIPPAGE
        ).run(df)
        return pairs_from_trades(r)
    finally:
        A.find_mmds_v44 = saved


def _summarize(pairs, label):
    if not pairs:
        return None
    d = pd.DataFrame(pairs)
    w = d[d["pnl_pct"] > 0]["pnl_pct"]
    l = d[d["pnl_pct"] <= 0]["pnl_pct"]
    net = d["pnl_pct"] - ROUND_TRIP * 100  # pnl_pct 是百分数
    return {
        "口径": label,
        "笔数": len(d),
        "胜率%": round(float((d["pnl_pct"] > 0).mean() * 100), 2),
        "毛均收益%": round(float(d["pnl_pct"].mean()), 3),
        "扣成本均%": round(float(net.mean()), 3),
        "扣成本总%": round(float(net.sum()), 2),
        "盈亏比": round(float(w.mean() / abs(l.mean())), 2) if len(l) and l.mean() != 0 else np.nan,
        "持有中位": int(d["holding_bars"].median()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args()
    workers = resolve_workers(args.workers)

    codes = sorted(
        p.name[: -len("_daily.json")]
        for p in DATA_DIR.glob("*_daily.json")
        if p.name[: -len("_daily.json")] not in EXCLUDE
    )[: args.limit]
    print(f"样本 {len(codes)} 只日线 | 成本：佣金{COMMISSION} 印花{STAMP} 滑点{SLIPPAGE} "
          f"⇒ 往返约 {ROUND_TRIP*100:.2f}%")

    from concurrent.futures import ProcessPoolExecutor

    rows = []
    detail = defaultdict(list)
    for name, cal in CALIBERS.items():
        allp = []
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for r in ex.map(_pairs_for_caliber_star, [(c, cal) for c in codes]):
                if r:
                    allp.extend(r)
        for r in allp:
            detail[name].append(r)
        s = _summarize(allp, name)
        if s:
            rows.append(s)
        print(f"  {name}: {len(allp)} 笔", flush=True)

    print("\n" + "=" * 78)
    print("【总体：各口径扣成本收益】")
    print("=" * 78)
    out = pd.DataFrame(rows)
    print(out.to_string(index=False))

    # 按买点类型拆（只关心 2类，因为只有它们受口径影响）
    print("\n" + "=" * 78)
    print("【按买点类型拆（口径只影响 2buy/2buy_s/2sell/2sell_s）】")
    print("=" * 78)
    for name in CALIBERS:
        d = pd.DataFrame(detail[name])
        if d.empty:
            continue
        sub = d[d["entry_type"].isin(["2buy", "2buy_s"])]
        if len(sub) == 0:
            print(f"{name}: 无 2类买点配对")
            continue
        net = sub["pnl_pct"] - ROUND_TRIP * 100
        print(f"{name:<12} 2类买点 n={len(sub):>4}  胜率{(sub['pnl_pct']>0).mean()*100:>5.1f}%  "
              f"毛均{sub['pnl_pct'].mean():>+7.2f}%  扣成本{net.mean():>+7.2f}%")

    print("\n判定：以「扣成本均%」为准，最高的口径胜出；若三者差异 <0.1pp 视为无差异。")
    return 0


def _pairs_for_caliber_star(t):
    return _pairs_for_caliber(*t)


if __name__ == "__main__":
    raise SystemExit(main())
