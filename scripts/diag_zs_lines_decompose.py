#!/usr/bin/env python3
"""拆解「4 段 3买」案例的中枢构成，定位 zs.lines 里那一笔两用的笔。

第61课原文：前三段构成中枢，第四段离开，第5段构成第三类买卖点。
⇒ 若回试笔 index == 中枢首笔 index + 3，则中枢只有 3 笔，
   其中一笔必然「既在中枢里又当离开笔」。

本脚本对每个 <5 段的 3买/3卖，逐笔打印中枢构成笔的方向/高低点，
并标出哪一笔是「离开笔」（即其 index == zs.lines[-1].index）。

用法：.venv/bin/python scripts/diag_zs_lines_decompose.py [--limit N]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402
from easy_tdx.chanlun.types import MMDType  # noqa: E402

DATA_DIR = ROOT / "audit_data"


def load_all(limit: int = 0) -> list[tuple[str, pd.DataFrame]]:
    out: list[tuple[str, pd.DataFrame]] = []
    for p in sorted(DATA_DIR.glob("*.json")):
        code = p.name.split("_")[0]
        rows = json.loads(p.read_text(encoding="utf-8"))
        if len(rows) < 60:
            continue
        df = pd.DataFrame(rows)
        df["datetime"] = pd.to_datetime(df["datetime"])
        out.append((code, df))
        if limit and len(out) >= limit:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    data = load_all(limit=args.limit)
    n_bad = 0
    n_total = 0
    cause: Counter[str] = Counter()
    shown = 0

    for code, df in data:
        res = ChanlunAnalyser(
            code=code, frequency="daily", config=ChanlunConfig()
        ).process_klines(df)
        for m in res.mmds:
            if m.mmd_type not in (MMDType.BUY_3, MMDType.SELL_3):
                continue
            if not m.bi or not m.zs or not m.zs.lines:
                continue
            zs = m.zs
            n_total += 1
            seg = m.bi.index - zs.lines[0].index + 1
            if seg >= 5:
                continue
            n_bad += 1
            last = zs.lines[-1]
            overlaps = min(zs.zg, last.high) > max(zs.zd, last.low)
            if last.index == m.bi.index - 1:
                cause["末笔=回试笔前一笔（末笔兼作离开笔）"] += 1
            elif overlaps:
                cause["末笔与[ZD,ZG]有重叠（属延伸段，非离开）"] += 1
            else:
                cause["其他"] += 1
            if shown < 6:
                shown += 1
                print(f"\n【{code} {m.mmd_type.value}】段数={seg} "
                      f"中枢笔数={zs.line_count} zg={zs.zg:.2f} zd={zs.zd:.2f}")
                for ln in zs.lines:
                    tag = " ← 离开笔(末笔)" if ln.index == last.index else ""
                    ov = "重叠" if min(zs.zg, ln.high) > max(zs.zd, ln.low) else "无重叠"
                    print(f"   bi[{ln.index:>3}] {ln.direction.value:>4} "
                          f"[{ln.low:>10.2f},{ln.high:>10.2f}] {ov}{tag}")
                print(f"   回试笔 bi[{m.bi.index}] {m.bi.direction.value} "
                      f"[{m.bi.low:.2f},{m.bi.high:.2f}]")

    print(f"\n3买/3卖 总数: {n_total}   <5 段: {n_bad} ({n_bad/max(n_total,1)*100:.1f}%)")
    print("根因分布:")
    for k, v in cause.most_common():
        print(f"  {v:>4} ({v/max(n_bad,1)*100:5.1f}%)  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
