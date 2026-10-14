#!/usr/bin/env python3
"""ZG/ZD 口径对比实测（V850）：第20课 A/C 两段 vs 第18课 三段落差。

## 原文争议（本轮 108 课全量核对新发现）

**第18课（较早）**：
> 「次级别的连续三个走势类型A、B、C，分别的高、低点是a1\\a2,b1\\b2,c1\\c2。
>  则，中枢的区间就是（max（a2,b2,c2），min（a1,b1,c1））」

**第20课（较新，同一段里给了两个式子）**：
> 「则中枢的区间就是`[max（a2,b2,c2），min（a1,b1,c1）]`」
> 「但无论是哪种情况，中枢的公式都可以简化为`[max（a2,c2），min（a1,c1）]`」
> 「显然，`A`、`C`段，其方向与中枢形成的方向是一致的……
>   以后都把这些与中枢方向一致的次级别走势类型称为`Z走势段`……
>   而相应的高、低点分别记为`gn`、`dn`」
> 「特别地，再定义`ZG=min(g1、g2)`, `ZD=max(d1、d2)`，
>   显然，`[ZD，ZG]`就是缠中说禅走势中枢的区间」

### 关键推导

第20课先定义 **Z走势段 = 与中枢形成方向一致的次级别走势类型**。
在回升中枢里 A、C 向上、B 向下 ⇒ **Z走势段只有 A 和 C，B 不是 Z走势段**。
g1/g2 = A/C 的高，d1/d2 = A/C 的低。

⇒ 第20课的 `ZG=min(g1,g2)` **在定义上就把 B 段排除在外**。
   这不是"简化"，是 Z走势段定义的自然结果。
   第20课自称"可以简化"，是因为它同时断言两种形成方式下
   `a1=b1,b2=c2`（回升）或 `a2=b2,b1=c1`（回调）——即 B 被 A/C 包住，
   此时两个式子等价。

⇒ **当 B 越出 A/C 包络时，两个口径给出不同答案，第20课的 ZG/ZD 定义
   （A/C only）是新课程，按"以新课程为准"应优先。**

### 对 G1 的影响（必须实测，不能推理）

`find_zss` 用 `zg_candidate/zd_candidate` 做**重叠判定**：
口径越宽 ⇒ 越多笔被判"与中枢重叠" ⇒ 中枢越长 ⇒ 越容易超第33课 9 段上限。

所以 A/C 口径（更宽）可能**加剧** G1。本脚本实测两种口径：
- `ac`   ：ZG=min(A.high,C.high), ZD=max(A.low,C.low)      ← 当前代码
- `three`：ZG=min(A,B,C.high),  ZD=max(A,B,C.low)          ← 第18课口径

输出：中枢数、段数分布、>9 段占比、信号数。
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
from easy_tdx.chanlun.types import ZS  # noqa: E402

DATA_DIR = ROOT / "audit_data"
ORIGINAL_MAX_TOTAL_SEGMENTS = 9  # 第33课：3 形成 + 6 延伸触发


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


def find_zss_three(bis, config=None):
    """第18课口径：ZG/ZD 由前三笔共同确定（B 段参与）。"""
    if config is None:
        config = ChanlunConfig()
    if len(bis) < 3:
        return []

    zss: list[ZS] = []
    first_bi = bis[0]
    zg = first_bi.high
    zd = first_bi.low
    gg = first_bi.high
    dd = first_bi.low
    cand = [first_bi]
    c_start = first_bi.start
    c_end = first_bi.end

    for bi in bis[1:]:
        oh = min(zg, bi.high)
        ol = max(zd, bi.low)
        if oh > ol:
            cand.append(bi)
            if len(cand) <= 3:
                zg = oh
                zd = ol
            gg = max(gg, bi.high)
            dd = min(dd, bi.low)
            c_end = bi.end
        else:
            if len(cand) >= config.zs_min_lines:
                if zs_mod._is_valid_zs_range(zg, zd, gg, dd):
                    zss.append(
                        ZS(
                            lines=list(cand),
                            zg=zg,
                            zd=zd,
                            gg=gg,
                            dd=dd,
                            start=c_start,
                            end=c_end,
                            index=len(zss),
                            done=True,
                        )
                    )
            cand = [bi]
            zg = bi.high
            zd = bi.low
            gg = bi.high
            dd = bi.low
            c_start = bi.start
            c_end = bi.end

    if cand and len(cand) >= config.zs_min_lines:
        if zs_mod._is_valid_zs_range(zg, zd, gg, dd):
            zss.append(
                ZS(
                    lines=list(cand),
                    zg=zg,
                    zd=zd,
                    gg=gg,
                    dd=dd,
                    start=c_start,
                    end=c_end,
                    index=len(zss),
                    done=False,
                )
            )

    if getattr(config, "zs_merge_overlap", True):
        zss = zs_mod._merge_overlapping_zss(zss)
    return zss


def measure(data, caliber: str):
    """返回 (段数分布, 中枢数, 信号数)。"""
    dist: Counter = Counter()
    n_zs = 0
    n_sig = 0
    for code, df in data:
        cfg = ChanlunConfig()
        a = ChanlunAnalyser(code=code, frequency="daily", config=cfg)
        if caliber == "three":
            # 打补丁：把 find_zss 换成三端口径
            orig = zs_mod.find_zss
            zs_mod.find_zss = find_zss_three
            try:
                import easy_tdx.chanlun.analyser as an_mod

                saved = an_mod.find_zss
                an_mod.find_zss = find_zss_three
                try:
                    res = a.process_klines(df)
                finally:
                    an_mod.find_zss = saved
            finally:
                zs_mod.find_zss = orig
        else:
            res = a.process_klines(df)
        for z in res.zss:
            dist[z.line_count] += 1
            n_zs += 1
        n_sig += len(res.mmds)
    return dist, n_zs, n_sig


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12)
    args = ap.parse_args()

    data = load_all(limit=args.limit)
    print(f"ZG/ZD 口径对比实测 —— {len(data)} 只真实日线\n", flush=True)

    results = {}
    for caliber, label in [
        ("ac", "第20课 A/C 口径（当前代码）"),
        ("three", "第18课 三端口径"),
    ]:
        dist, n_zs, n_sig = measure(data, caliber)
        results[caliber] = (dist, n_zs, n_sig)
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

    d1, z1, s1 = results["ac"]
    d2, z2, s2 = results["three"]
    print("=" * 60, flush=True)
    print("对比：", flush=True)
    print(f"  中枢数:   {z1} (AC)  vs  {z2} (three)   差 {z2 - z1:+d}", flush=True)
    print(f"  信号数:   {s1} (AC)  vs  {s2} (three)   差 {s2 - s1:+d}", flush=True)
    o1 = sum(v for k, v in d1.items() if k > ORIGINAL_MAX_TOTAL_SEGMENTS)
    o2 = sum(v for k, v in d2.items() if k > ORIGINAL_MAX_TOTAL_SEGMENTS)
    print(
        f"  >9段中枢: {o1} ({o1 / z1 * 100:.1f}%) vs "
        f"{o2} ({o2 / z2 * 100:.1f}%)",
        flush=True,
    )
    print(
        f"  最长段数: {max(d1)} (AC) vs {max(d2)} (three)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
