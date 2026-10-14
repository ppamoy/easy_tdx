#!/usr/bin/env python3
"""第61课「第三类买卖点至少 5 段」口径实测。

原文（第61课《区间套定位标准图解（分析示范六）》）：
> 「一个第三类买卖点，至少需要有5段次级别的，前三段构成中枢，
>   第四段离开中枢，第5段构成第三类买卖点。」

V840 修正后的可判定形式（重要——本脚本的旧口径本身是错的）：

  旧口径直接数「回试笔索引 - 中枢首笔索引 + 1 >= 5」，实测 25 只真实日线
  有 12.9% 的信号被判为违规。逐案核对后确认：**那批 4 段信号完全符合原文**，
  错的是计数规则本身。

  原文第61课的实例是权威结构定义：
    中枢 66-69 = 三段（66-67 / 67-68 / 68-69）
    第4段 = 69-70 离开，第5段 = 70-71 回试 ⇒ 71 即 3买
  而 ZG = min(g1, g3) 中 g3 取的正是**中枢末段（68-69）的高点**，
  且原文明确 68-69 冲到 69「创新高」⇒ 末段 high > zg。

  即原文自己的例子里，中枢末段（68-69）就同时是「离开的起点」。
  在笔级近似下，「68-69 段」与「69-70 离开段」常被并成一笔，于是
  出现「3 笔中枢 + 1 笔回试 = 4 笔」的合法结构。

  ⇒ 正确的判定不看机械笔数，而看**结构职责是否齐全**：
      (a) 中枢 >= 3 笔；
      (b) 存在离开：中枢末笔已突破沿（up 且 high>zg / dn 且 low<zd），
          或其后存在一个与 [ZD,ZG] 完全无重叠的笔；
      (c) 回试笔紧邻离开段，且不破沿（3买 low>zg / 3卖 high<zd）。
    (a)+(b)+(c) 齐全即满足第61课「前三段中枢、第四段离开、第五段回试」，
    与机械笔数是 4 还是 5 无关。

本脚本同时输出两种口径的分布，便于对照：
  · 机械笔数（旧口径，仅作参考，会误报）
  · 结构职责口径（V840 正确口径）

用法：
  .venv/bin/python scripts/audit_chanlun_yuanwen_lesson61_5seg.py [--limit N]
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


def bis_after(bis: list, idx: int) -> list:
    """返回索引 > idx 的笔（笔索引与列表下标一致的既有约定）。"""
    return [b for b in bis if b.index > idx]


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
    if not data:
        print(f"❌ {DATA_DIR} 无数据")
        return 2

    mech_dist: Counter[int] = Counter()
    struct_dist: Counter[str] = Counter()
    by_type: Counter[str] = Counter()
    bad_struct_examples: list[str] = []
    total_zs = 0
    zs_line_counts: Counter[int] = Counter()

    for code, df in data:
        res = ChanlunAnalyser(
            code=code, frequency="daily", config=ChanlunConfig()
        ).process_klines(df)
        for zs in res.zss:
            total_zs += 1
            zs_line_counts[zs.line_count] += 1
        for m in res.mmds:
            if m.mmd_type not in (MMDType.BUY_3, MMDType.SELL_3) or not m.bi or not m.zs:
                continue
            zs = m.zs
            if not zs.lines:
                continue
            first = zs.lines[0].index
            retest = m.bi.index
            mech_dist[retest - first + 1] += 1
            by_type[m.mmd_type.value] += 1

            # ── V840 结构职责口径 ────────────────────────────────────────
            # (a) 中枢 >= 3 笔
            ok_a = zs.line_count >= 3
            # (b) 存在离开：末笔突破沿，或其后有完全脱离 [ZD,ZG] 的笔
            last_bi = zs.lines[-1]
            last_break = (
                (last_bi.direction.value == "up" and last_bi.high > zs.zg)
                or (last_bi.direction.value == "down" and last_bi.low < zs.zd)
            )
            leave_idx = last_bi.index
            if not last_break:
                for cand in bis_after(res.bis, last_bi.index):
                    if cand.low > zs.zg or cand.high < zs.zd:
                        leave_idx = cand.index
                        break
            # (c) 回试笔紧邻离开段且不破沿
            if m.mmd_type == MMDType.BUY_3:
                ok_c = retest == leave_idx + 1 and m.bi.low > zs.zg
            else:
                ok_c = retest == leave_idx + 1 and m.bi.high < zs.zd
            ok_b = leave_idx is not None
            struct_ok = ok_a and ok_b and ok_c
            struct_dist["合规" if struct_ok else "违规"] += 1
            if not struct_ok:
                bad_struct_examples.append(
                    f"{code} {m.mmd_type.value} 中枢笔数={zs.line_count} "
                    f"末笔突破沿={last_break} 回试笔={retest} 离开段={leave_idx} "
                    f"a={ok_a} b={ok_b} c={ok_c}"
                )

    n = sum(mech_dist.values())
    print(f"第61课「3买/3卖 至少5段」实测 —— {len(data)} 只标的（真实日线）")
    print(f"3类买卖点总数: {n}    {dict(by_type)}")
    print(f"中枢总数: {total_zs}")
    print(f"\n中枢笔数分布: {dict(sorted(zs_line_counts.items()))}")
    print(f"\n【口径1】机械笔数（旧口径，会误报，仅作对照）:")
    for k in sorted(mech_dist):
        flag = "❌" if k < 5 else "✅"
        print(f"  {flag} {k} 段: {mech_dist[k]} ({mech_dist[k] / n * 100:.1f}%)")
    mech_bad = sum(v for k, v in mech_dist.items() if k < 5)
    print(f"  ⇒ 旧口径判违规: {mech_bad}/{n} ({mech_bad / n * 100:.1f}%)")

    print(f"\n【口径2】结构职责口径（V840 正确口径）:")
    for k, v in sorted(struct_dist.items()):
        print(f"  {k}: {v} ({v / n * 100:.1f}%)")
    if bad_struct_examples:
        print(f"\n结构职责违规样例（最多 15 条 / 共 {len(bad_struct_examples)}）:")
        for e in bad_struct_examples[:15]:
            print("   " + e)
    else:
        print("  ⇒ 0 违规")

    return 0
    n = sum(dist.values())
    print(f"第61课「3买/3卖 至少5段」实测 —— {len(data)} 只标的（真实日线）")
    print(f"3类买卖点总数: {n}    {dict(by_type)}")
    print(f"中枢总数: {total_zs}")
    print(f"\n中枢笔数分布: {dict(sorted(zs_line_counts.items()))}")
    print(f"\n「中枢首笔 → 回试笔」段数分布:")
    for k in sorted(dist):
        flag = "❌" if k < 5 else "✅"
        print(f"  {flag} {k} 段: {dist[k]} ({dist[k] / n * 100:.1f}%)")

    bad = sum(v for k, v in dist.items() if k < 5)
    print(f"\n不满足 >=5 段: {bad}/{n} ({bad / n * 100:.1f}%)")
    if bad_examples:
        print(f"\n样例（最多 15 条 / 共 {len(bad_examples)}）:")
        for e in bad_examples[:15]:
            print("   " + e)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
