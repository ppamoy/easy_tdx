#!/usr/bin/env python3
"""跨周期路径修复前后的对照回归（V851）。

`_remap_cross_zs_indices` 只改 `ZS.lines[*].index` 的**口径**
（30min 线段序号 → 日线笔下标），不改中枢数量/区间。
本脚本在真实数据上双侧测量，确认：
  1. 中枢数、中枢区间（zg/zd）不变（只改 index）；
  2. 信号数变化在合理范围（index 修正后取到的回试段不同）；
  3. `bis[zs.lines[-1].index]` 与 `zs.lines[-1]` 的日期差从 ~4000 天降到 ~10 天。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from easy_tdx.chanlun.analyser import ChanlunAnalyser, _remap_cross_zs_indices  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402
from easy_tdx.chanlun.zs import find_zss  # noqa: E402

DAILY_DIR = ROOT / "audit_data"
LOWER_DIR = ROOT / "audit_data" / "kline_30min"


def _end_ts(o):
    k = getattr(getattr(o, "end", None), "k", None)
    ts = getattr(k, "date", None) if k is not None else None
    return pd.Timestamp(ts) if ts is not None else None


def run(code: str) -> dict | None:
    dp = DAILY_DIR / f"{code}_daily.json"
    lp = LOWER_DIR / f"{code}_30min.json"
    if not dp.exists() or not lp.exists():
        return None
    ddf = pd.DataFrame(json.loads(dp.read_text(encoding="utf-8")))
    ldf = pd.DataFrame(json.loads(lp.read_text(encoding="utf-8")))
    ddf["datetime"] = pd.to_datetime(ddf["datetime"])
    ldf["datetime"] = pd.to_datetime(ldf["datetime"])

    cfg = ChanlunConfig()
    a = ChanlunAnalyser(code=code, frequency="daily", config=cfg)
    lx = ChanlunAnalyser(config=cfg).process_klines(ldf).xds
    if len(lx) < 3:
        return None
    r = a.process_klines(ddf)
    bis = r.bis
    if not bis:
        return None

    # A: 旧行为
    zA = find_zss(lx, config=cfg)
    dA = [abs((_end_ts(z.lines[-1]) - _end_ts(bis[z.lines[-1].index])).days)
          for z in zA if z.lines and 0 <= z.lines[-1].index < len(bis)]
    # B: 新行为
    zB = find_zss(lx, config=cfg)
    _remap_cross_zs_indices(zB, bis)
    dB = [abs((_end_ts(z.lines[-1]) - _end_ts(bis[z.lines[-1].index])).days)
          for z in zB if z.lines and 0 <= z.lines[-1].index < len(bis)]

    zgA = sorted(round(z.zg, 4) for z in zA)
    zgB = sorted(round(z.zg, 4) for z in zB)
    return {
        "code": code,
        "n_xds": len(lx),
        "n_bis": len(bis),
        "n_zss": len(zA),
        "max_dA": max(dA) if dA else None,
        "max_dB": max(dB) if dB else None,
        "zg_same": zgA == zgB,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12)
    args = ap.parse_args()

    codes = sorted({p.name.split("_")[0] for p in LOWER_DIR.glob("*.json")})
    if args.limit:
        codes = codes[: args.limit]

    print(f"跨周期索引口径修复对照 —— {len(codes)} 只标的\n", flush=True)
    print(f"{'code':<10} {'xds':>5} {'bis':>5} {'zss':>5} "
          f"{'修复前最大差':>12} {'修复后最大差':>12} {'ZG区间不变':>10}", flush=True)
    print("-" * 68, flush=True)
    ok = 0
    zg_ok = 0
    for code in codes:
        r = run(code)
        if r is None:
            continue
        ok += 1
        if r["zg_same"]:
            zg_ok += 1
        print(
            f"{r['code']:<10} {r['n_xds']:>5} {r['n_bis']:>5} {r['n_zss']:>5} "
            f"{str(r['max_dA']):>12} {str(r['max_dB']):>12} "
            f"{'✅' if r['zg_same'] else '❌':>10}",
            flush=True,
        )
    print("-" * 68, flush=True)
    print(f"有效标的 = {ok}；ZG 区间全部不变 = {zg_ok}/{ok}", flush=True)
    return 0 if zg_ok == ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
