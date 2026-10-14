#!/usr/bin/env python3
"""G1 修法影响实测（V851）：把 `zs_no_hard_close` 默认改为 False 会怎样。

## 原文依据（两课，逐字）

**第33课 line 7**（非同级别分解）：
> 「一般来说，中枢的延伸不能超过5段，也就是一旦出现6段的延伸，
>   加上形成中枢本身那三段，就构成更大级别的中枢了。」
⇒ 上限 = 3 + 6 = **9 段**。

**第38课 line 8**（同级别分解，较新）：
> 「在这种同级别的分解中，是不需要中枢延伸或扩展的概念的……
>   如果这5分钟次级别延伸出6段，那么就当成两个30分钟盘整类型的连接，
>   在这种分解中，是允许盘整+盘整情况的。」
⇒ 上限同为 9 段；超限处置 = **切成两个盘整连接**（非升级）。

两课上限数字一致（9），仅超限后处置不同。按"以新课程为准"取第38课口径。

## 当前偏离

`zs_no_hard_close=True`（默认）⇒ 中枢无限延伸。
实测（scripts/guard_chanlun_lesson33_zs_extension_v850.py）：
12 只真实日线 332 个中枢，**81 个（24.4%）超过 9 段，最长 37 段**。

## 本脚本职责

量化把默认改成 `zs_no_hard_close=False`（9 段硬关闭）的影响：
中枢数、段数分布、>9 段数量、信号数。
**必须先测再决策**，不能先改再看。
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

DATA_DIR = ROOT / "audit_data"
ORIGINAL_MAX_TOTAL_SEGMENTS = 9  # 第33课：3 形成 + 6 延伸


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


def measure(data, no_hard_close: bool):
    dist: Counter = Counter()
    n_zs = 0
    n_sig = 0
    for code, df in data:
        cfg = ChanlunConfig(zs_no_hard_close=no_hard_close)
        a = ChanlunAnalyser(code=code, frequency="daily", config=cfg)
        r = a.process_klines(df)
        for z in r.zss:
            dist[z.line_count] += 1
            n_zs += 1
        n_sig += len(r.mmds)
    return dist, n_zs, n_sig


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12)
    args = ap.parse_args()

    data = load_all(limit=args.limit)
    print(f"G1 修法影响实测 —— {len(data)} 只真实日线\n", flush=True)

    results = {}
    for flag, label in [
        (True, "当前默认 zs_no_hard_close=True（无限延伸）"),
        (False, "候选修法 zs_no_hard_close=False（9段硬关闭）"),
    ]:
        dist, n_zs, n_sig = measure(data, flag)
        results[flag] = (dist, n_zs, n_sig)
        over = sum(v for k, v in dist.items() if k > ORIGINAL_MAX_TOTAL_SEGMENTS)
        longest = max(dist) if dist else 0
        print(f"【{label}】", flush=True)
        print(f"  中枢总数 = {n_zs}", flush=True)
        print(
            f"  >{ORIGINAL_MAX_TOTAL_SEGMENTS} 段 = {over} "
            f"({over / n_zs * 100:.1f}%)",
            flush=True,
        )
        print(f"  最长 = {longest} 段", flush=True)
        print(f"  信号总数 = {n_sig}", flush=True)
        print(f"  分布 = {dict(sorted(dist.items()))}\n", flush=True)

    d1, z1, s1 = results[True]
    d2, z2, s2 = results[False]
    o1 = sum(v for k, v in d1.items() if k > ORIGINAL_MAX_TOTAL_SEGMENTS)
    o2 = sum(v for k, v in d2.items() if k > ORIGINAL_MAX_TOTAL_SEGMENTS)
    print("=" * 60, flush=True)
    print("对比：", flush=True)
    print(f"  中枢数:   {z1} → {z2}  差 {z2 - z1:+d}", flush=True)
    print(f"  信号数:   {s1} → {s2}  差 {s2 - s1:+d}", flush=True)
    print(
        f"  >9段中枢: {o1} ({o1 / z1 * 100:.1f}%) → "
        f"{o2} ({o2 / z2 * 100:.1f}%)",
        flush=True,
    )
    print(f"  最长段数: {max(d1)} → {max(d2)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
