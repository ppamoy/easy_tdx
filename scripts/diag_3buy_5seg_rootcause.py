#!/usr/bin/env python3
"""3买/3卖 结构诊断：定位「4 段」信号的根因。

第61课原文：
> 「一个第三类买卖点，至少需要有5段次级别的，前三段构成中枢，
>   第四段离开中枢，第5段构成第三类买卖点。」

第20课原文（离开的判定）：
> 「一个次级别走势类型向上离开缠中说禅走势中枢，然后以一个次级别走势类型回试」
> 中枢中心定理一：「若有Zn，使得dn>ZG或gn<ZD，则必然产生高级别的走势中枢」

⇒ 「离开」要求该段**整体**在 [ZD,ZG] 之外（dn>ZG 或 gn<ZD）；
   只是 high>ZG 但 low 仍在 [ZD,ZG] 内的段属于**中枢延伸**，不是离开。

本脚本对每个 3买/3卖 输出：
  - 段数（中枢首笔 → 回试笔）
  - 离开笔是否就是中枢最后一笔（zs.lines[-1]，即「一笔两用」）
  - 离开笔是否与 [ZD,ZG] 有重叠（若是 ⇒ 按原文不算离开）

用法：
  .venv/bin/python scripts/diag_3buy_5seg_rootcause.py [--limit N]
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
    if not data:
        print(f"❌ {DATA_DIR} 无数据")
        return 2

    n_total = 0
    n_4seg = 0
    cause: Counter[str] = Counter()
    examples: list[str] = []

    for code, df in data:
        res = ChanlunAnalyser(
            code=code, frequency="daily", config=ChanlunConfig()
        ).process_klines(df)
        bis = res.bis
        for m in res.mmds:
            if m.mmd_type not in (MMDType.BUY_3, MMDType.SELL_3) or not m.bi or not m.zs:
                continue
            zs = m.zs
            if not zs.lines:
                continue
            n_total += 1
            first = zs.lines[0].index
            retest = m.bi.index
            seg = retest - first + 1
            if seg >= 5:
                continue
            n_4seg += 1
            last_zs_bi = zs.lines[-1]
            is_buy = m.mmd_type == MMDType.BUY_3
            # 离开笔候选：中枢末笔（含）之后第一笔与信号同向且突破 zs.zg/zd 的笔
            breakout = None
            for bi in bis[last_zs_bi.index :]:
                if is_buy and bi.direction.value == "up" and bi.high > zs.zg:
                    breakout = bi
                    break
                if not is_buy and bi.direction.value == "down" and bi.low < zs.zd:
                    breakout = bi
                    break
                if bi.index > retest:
                    break
            if breakout is None:
                cause["未找到离开笔（判据复算失败）"] += 1
                continue
            # 原因 1：离开笔就是中枢最后一笔（一笔两用）
            if breakout.index == last_zs_bi.index:
                overlaps = (
                    min(zs.zg, breakout.high) > max(zs.zd, breakout.low)
                )
                if overlaps:
                    cause["离开笔=中枢末笔 且 该笔与[ZD,ZG]有重叠（按原文属延伸，非离开）"] += 1
                else:
                    cause["离开笔=中枢末笔 但 无重叠（几何上确已离开）"] += 1
            else:
                cause["离开笔在中枢之后（段数仍<5，需进一步查）"] += 1
            if len(examples) < 12:
                examples.append(
                    f"{code} {m.mmd_type.value} 段={seg} "
                    f"中枢笔={zs.line_count} 末笔idx={last_zs_bi.index}"
                    f"({'up' if last_zs_bi.direction.value=='up' else 'down'})"
                    f" 离开笔idx={breakout.index} 回试笔idx={retest} "
                    f"zg={zs.zg:.3f} zd={zs.zd:.3f} "
                    f"离开笔区间=[{breakout.low:.3f},{breakout.high:.3f}]"
                )

    print(f"3买/3卖 结构诊断 —— {len(data)} 只标的（真实日线）")
    print(f"总数: {n_total}   段数<5: {n_4seg} ({n_4seg / max(n_total,1) * 100:.1f}%)")
    print("\n根因分布:")
    for k, v in cause.most_common():
        print(f"  {v:>4} ({v / max(n_4seg,1) * 100:5.1f}%)  {k}")
    if examples:
        print("\n样例:")
        for e in examples:
            print("   " + e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
