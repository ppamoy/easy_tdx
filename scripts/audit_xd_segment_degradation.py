#!/usr/bin/env python3
"""第91课连带缺陷：`_valid_segment_end` 导致线段退化的影响面量化。

背景（CHANLUN_FIDELITY_AUDIT_V735.md §31.2）：
`xd.py _valid_segment_end` 要求线段终点必须偏离首笔起点极值
（向上段终点 > 起点，向下段终点 < 起点）。当首笔方向与整体趋势相反时，
该约束恒 False ⇒ 线段永远无法结束 ⇒ 整段数据只产出 1 条未完成线段。

本脚本逐只统计「线段 <= 1」的退化工标，边跑边打印（防超时丢结果）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402

DATA_DIR = ROOT / "audit_data"


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    files = sorted(DATA_DIR.glob("*.json"))[:limit]
    bad: list[tuple[str, int, int]] = []
    ok = 0
    for i, p in enumerate(files, 1):
        rows = json.loads(p.read_text(encoding="utf-8"))
        if len(rows) < 60:
            continue
        df = pd.DataFrame(rows)
        df["datetime"] = pd.to_datetime(df["datetime"])
        code = p.name.split("_")[0]
        r = ChanlunAnalyser(
            code=code, frequency="daily", config=ChanlunConfig()
        ).process_klines(df)
        n = len(r.xds)
        if n <= 1:
            bad.append((code, len(r.bis), n))
            print(f"  [退化] {code}: bis={len(r.bis)} xds={n}", flush=True)
        else:
            ok += 1
        if i % 10 == 0:
            tot = len(bad) + ok
            print(
                f"... 已处理 {i} 只：退化 {len(bad)}/{tot} = "
                f"{100.0 * len(bad) / tot:.1f}%",
                flush=True,
            )
    tot = len(bad) + ok
    print()
    print(f"=== 合计（前 {i} 只）===")
    print(f"线段 >=2 的: {ok}")
    print(f"线段 <=1（退化）: {len(bad)}  退化率 {100.0 * len(bad) / tot:.1f}%")
    print(f"退化工标: {[b[0] for b in bad]}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
