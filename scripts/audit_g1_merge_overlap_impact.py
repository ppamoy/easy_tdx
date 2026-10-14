#!/usr/bin/env python3
"""G1 修复影响实测（V851）：`_merge_overlapping_zss` 是元凶。

## 原文依据

**第20课 line 4**（已 grep 全文，唯一命中「不能有任何重叠」的原文）：
> 「而在趋势里，同级别的前后缠中说禅走势中枢是不能有任何重叠的……
>   如果三个连续次级别走势类型的重叠区间虽然不和前面的走势中枢有任何重叠，
>   但围绕该中枢产生的波动触及前面走势中枢延续时的某个瞬间波动区间，
>   这时候，就不能认为该走势类型是趋势，而只是产生一个更大级别的
>   缠中说禅走势中枢。」

⇒ 前后中枢重叠 ⇒ **更大级别的中枢（升级）**，不是同级别更长的中枢。

**第33课 line 7**：上限 3+6=9 段。

`_merge_overlapping_zss` 的注释引用「第19课」的
"一个趋势中枢序列中，前后两个中枢不能有任何重叠，否则就只是一个更大级别的盘整"
—— 该句在 108 课原文里 grep 不到，出处存疑；
且 `prev.lines.extend(zs.lines)` 把两个同级别中枢段数**相加**，
既超第33课 9 段上限，也不是第20课的"升级"。

## 本脚本职责

量化三种配置：
  A) 当前：硬关闭关（无限延伸）+ 合并开
  B) 硬关闭开 + 合并开            ← 只改 zs_no_hard_close
  C) 硬关闭开 + 合并关            ← 真正符合原文

并统计有多少对中枢真的会触发合并（若极少，关掉合并代价小）。
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
from easy_tdx.chanlun import zs as zs_mod  # noqa: E402
import easy_tdx.chanlun.analyser as an_mod  # noqa: E402

DATA_DIR = ROOT / "audit_data"
ORIGINAL_MAX = 9


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


def measure(data, no_hard_close: bool, merge: bool):
    dist: Counter = Counter()
    n_zs = 0
    n_sig = 0
    merge_hits = 0
    saved = zs_mod._merge_overlapping_zss

    def counting_merge(zss):
        nonlocal merge_hits
        out = []
        for zs in zss:
            if out:
                prev = out[-1]
                if prev.zd < zs.zg and zs.zd < prev.zg:
                    merge_hits += 1
            out.append(zs)
        return saved(zss)

    for code, df in data:
        cfg = ChanlunConfig(zs_no_hard_close=no_hard_close)
        if merge:
            zs_mod._merge_overlapping_zss = counting_merge
        else:
            zs_mod._merge_overlapping_zss = lambda z: z
        try:
            a = ChanlunAnalyser(code=code, frequency="daily", config=cfg)
            r = a.process_klines(df)
        finally:
            zs_mod._merge_overlapping_zss = saved
        for z in r.zss:
            dist[z.line_count] += 1
            n_zs += 1
        n_sig += len(r.mmds)
    return dist, n_zs, n_sig, merge_hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12)
    args = ap.parse_args()

    data = load_all(limit=args.limit)
    print(f"G1 修复影响实测 —— {len(data)} 只真实日线\n", flush=True)

    configs = [
        (True, True, "A 当前：无限延伸 + 合并开"),
        (False, True, "B 硬关闭 + 合并开（只改开关，不够）"),
        (False, False, "C 硬关闭 + 合并关（符合原文）"),
    ]
    res = {}
    for nhc, mg, label in configs:
        dist, n_zs, n_sig, mh = measure(data, nhc, mg)
        res[label] = (dist, n_zs, n_sig)
        over = sum(v for k, v in dist.items() if k > ORIGINAL_MAX)
        print(f"【{label}】", flush=True)
        print(f"  中枢数 = {n_zs}", flush=True)
        print(f"  >9段 = {over} ({over / n_zs * 100:.1f}%)", flush=True)
        print(f"  最长 = {max(dist) if dist else 0} 段", flush=True)
        print(f"  信号数 = {n_sig}", flush=True)
        print(f"  触发合并的对数 = {mh}", flush=True)
        print(f"  分布 = {dict(sorted(dist.items()))}\n", flush=True)

    print("=" * 64, flush=True)
    dA, zA, sA = res[configs[0][2]]
    dC, zC, sC = res[configs[2][2]]
    oA = sum(v for k, v in dA.items() if k > ORIGINAL_MAX)
    oC = sum(v for k, v in dC.items() if k > ORIGINAL_MAX)
    print("A → C 对比：", flush=True)
    print(f"  中枢数:   {zA} → {zC}  差 {zC - zA:+d}", flush=True)
    print(f"  信号数:   {sA} → {sC}  差 {sC - sA:+d}", flush=True)
    print(f"  >9段中枢: {oA} ({oA / zA * 100:.1f}%) → {oC} ({oC / zC * 100:.1f}%)", flush=True)
    print(f"  最长段数: {max(dA)} → {max(dC)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
