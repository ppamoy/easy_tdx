#!/usr/bin/env python3
"""第33课「中枢延伸不能超过5段」守门脚本（V840 沉淀）。

原文（第33课《走势的多义性》line 7，逐字）：

> 「一般来说，中枢的延伸不能超过5段，也就是一旦出现6段的延伸，加上形成中枢
>   本身那三段，就构成更大级别的中枢了。」

⇒ 上限 = 3（形成）+ 5（延伸）= **8 段**。

本脚本统计真实日线上中枢的笔数分布，量化「超过 8 段」的中枢占比。
**这是一个已知的、已定位但未修复的原文偏离**（见 CHANLUN_FIDELITY_AUDIT_V735.md
§30），脚本的作用是：

1. 量化偏离程度（防止「只说超标不说超多少」）；
2. 用 `--switch` 把偏离的两个来源分离（AGENTS.md §4 两侧测试）：
   - 来源① `zs_merge_overlap=True`（第19课定理一）把多个 9 段中枢合并
   - 来源② `_MAX_ZS_SEGMENTS=9` 硬关闭本身产出 9 段

退出码：0 = 无不超限中枢；1 = 有超限（当前代码必然 exit 1，这是**预期**的）
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

# 第33课原文口径：3 段形成 + 5 段延伸
ORIGINAL_MAX_SEGMENTS = 8


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


def measure(data, **cfg_kw) -> tuple[Counter, int]:
    dist: Counter = Counter()
    total = 0
    for code, df in data:
        cfg = ChanlunConfig(**cfg_kw)
        res = ChanlunAnalyser(
            code=code, frequency="daily", config=cfg
        ).process_klines(df)
        for zs in res.zss:
            dist[zs.line_count] += 1
            total += 1
    return dist, total


def report(label: str, dist: Counter, total: int) -> int:
    over = {k: v for k, v in sorted(dist.items()) if k > ORIGINAL_MAX_SEGMENTS}
    n_over = sum(over.values())
    longest = max(dist) if dist else 0
    print(f"\n【{label}】中枢总数={total}")
    print(f"  >8 段（超原文上限）: {n_over} ({n_over / total * 100:.1f}%)")
    print(f"  最长: {longest} 段")
    if over:
        print(f"  分布: {over}")
    return n_over


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument(
        "--switch",
        action="store_true",
        help="分离两个偏离来源（第19课 merge / 第33课 硬关闭）",
    )
    args = ap.parse_args()

    data = load_all(limit=args.limit)
    if not data:
        print(f"❌ {DATA_DIR} 无数据")
        return 2

    print(f"第33课「中枢延伸≤5段」守门 —— {len(data)} 只标的（真实日线）")
    print(f"原文上限: 3(形成) + 5(延伸) = {ORIGINAL_MAX_SEGMENTS} 段")

    if args.switch:
        dist, tot = measure(data)
        n = report("默认 (zs_no_hard_close=True, zs_merge_overlap=True)", dist, tot)

        dist2, tot2 = measure(data, zs_no_hard_close=False)
        n2 = report("zs_no_hard_close=False (保留 9 段硬关闭)", dist2, tot2)

        dist3, tot3 = measure(data, zs_no_hard_close=False, zs_merge_overlap=False)
        n3 = report(
            "zs_no_hard_close=False + zs_merge_overlap=False", dist3, tot3
        )

        print("\n结论：")
        print(f"  来源① 第19课 merge 合并的贡献: 最长 {max(dist)} → {max(dist3)} 段")
        print(f"  来源② 硬关闭本身的 9 段: 关掉 merge 后仍 >8 段的中枢 = {n3}")
        return 1 if (n or n2 or n3) else 0

    dist, tot = measure(data)
    n = report("默认配置", dist, tot)
    if n:
        print(
            f"\n❌ {n}/{tot} ({n / tot * 100:.1f}%) 个中枢超过第33课的 8 段上限。\n"
            "  这是**已定位但未修复**的原文偏离（CHANLUN_FIDELITY_AUDIT_V735.md §30）。\n"
            "  根因：原文要求「升级为更大级别中枢」，需走势类型级递归架构；\n"
            "        代码用 9 段硬关闭 + 相邻中枢合并两种笔级近似。\n"
            "  跑 --switch 可分离两个来源的贡献。"
        )
        return 1
    print("\n✅ 全部中枢均在 8 段以内")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
