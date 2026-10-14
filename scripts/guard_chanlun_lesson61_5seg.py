#!/usr/bin/env python3
"""第61课「3买/3卖 至少5段」结构职责守门脚本（V840 沉淀）。

背景（AGENTS.md §7 沉淀要求）：我曾据「第61课至少5段」判定「中枢末笔兼任
离开段」是缺陷，据此改代码后召回崩到 10/356。逐案核对才发现**计数口径本身
是误报** —— 原文 66-69 例里中枢末段（68-69）就是离开的起点。为防再犯，
把正确判据固化成可复用守门脚本，并用已知坏版本回归验证过它确实能抓到。

正确判据（结构职责口径，与机械笔数是 4 还是 5 无关）：
  (a) 中枢 >= 3 笔
  (b) 存在离开：中枢末笔已突破沿（up 且 high>zg / dn 且 low<zd），
      或其后存在一个与 [ZD,ZG] 完全无重叠的笔
  (c) 回试笔紧邻离开段，且不破沿（3买 low>zg / 3卖 high<zd）

另检一条独立不变量（V840 踩坑后补）：3买/3卖 的**回试笔**不得越过下一个
中枢的首笔索引 —— 越过即回试笔落进新中枢地盘，ZG/ZD 已被取代，是假信号。

用法：
  .venv/bin/python scripts/guard_chanlun_lesson61_5seg.py [--limit N]
退出码：0 = 全部合规；1 = 有违规；2 = 无数据

性能：单标的约 6~8 秒（含 process_klines）。--limit 25 在 4 核机上会超过
280s 前台超时，日常守门用 --limit 12（实测 274 个信号、0 违规、约 40s），
需要全量时走 scripts/run_bg.sh 后台跑。

已用已知坏版本回归验证（AGENTS.md §7）：
  · 基线 mmd.py（git HEAD，V840 之前）→ exit 1，报出
    「c_回试笔不紧邻离开段」「d_引用被取代的旧中枢」两类违规
  · V840 mmd.py → exit 0
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


def _next_first_bi_idx_map(zss) -> dict[int, int]:
    """每个中枢 → 其后第一个中枢的首笔索引。"""
    out: dict[int, int] = {}
    for j, z in enumerate(zss):
        if not z.lines:
            continue
        for z2 in zss[j + 1 :]:
            if z2.lines:
                out[z.index] = z2.lines[0].index
                break
    return out


def check_one(code: str, res) -> tuple[Counter, list[str]]:
    """返回 (违规分类计数, 违规详情)。"""
    bad: Counter = Counter()
    details: list[str] = []

    zss = res.zss
    nxt = _next_first_bi_idx_map(zss)
    bis = res.bis
    bi_by_idx = {b.index: b for b in bis}

    for m in res.mmds:
        if m.mmd_type not in (MMDType.BUY_3, MMDType.SELL_3) or not m.bi or not m.zs:
            continue
        zs = m.zs
        if not zs.lines:
            continue

        # (a) 中枢 >= 3 笔
        if zs.line_count < 3:
            bad["a_中枢不足3笔"] += 1
            details.append(f"{code} {m.mmd_type.value} 中枢仅 {zs.line_count} 笔")

        # (b) 存在离开
        last_bi = zs.lines[-1]
        last_break = (
            (last_bi.direction.value == "up" and last_bi.high > zs.zg)
            or (last_bi.direction.value == "down" and last_bi.low < zs.zd)
        )
        leave_idx = last_bi.index
        if not last_break:
            found = None
            for idx in sorted(bi_by_idx):
                if idx <= last_bi.index:
                    continue
                b = bi_by_idx[idx]
                if b.low > zs.zg or b.high < zs.zd:
                    found = idx
                    break
            if found is None:
                bad["b_无离开段"] += 1
                details.append(
                    f"{code} {m.mmd_type.value} 中枢末笔未突破沿且其后无完全脱离[ZD,ZG]的笔"
                )
                continue
            leave_idx = found

        # (c) 回试笔紧邻离开段且不破沿
        if m.bi.index != leave_idx + 1:
            bad["c_回试笔不紧邻离开段"] += 1
            details.append(
                f"{code} {m.mmd_type.value} 回试笔#{m.bi.index} 离开段#{leave_idx} 不相邻"
            )
        if m.mmd_type == MMDType.BUY_3 and m.bi.low <= zs.zg:
            bad["c_3买回试跌破ZG"] += 1
            details.append(
                f"{code} 3买 回试低点{m.bi.low:.2f} <= zg={zs.zg:.2f}（跌回中枢内）"
            )
        if m.mmd_type == MMDType.SELL_3 and m.bi.high >= zs.zd:
            bad["c_3卖回试升破ZD"] += 1
            details.append(
                f"{code} 3卖 回试高点{m.bi.high:.2f} >= zd={zs.zd:.2f}（升回中枢内）"
            )

        # 独立不变量：回试笔不得越过下一个中枢首笔
        sup = nxt.get(zs.index)
        if sup is not None and m.bi.index > sup:
            bad["d_引用被取代的旧中枢"] += 1
            details.append(
                f"{code} {m.mmd_type.value} 回试笔#{m.bi.index} 越过下一中枢首笔#{sup}"
            )

    return bad, details


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    data = load_all(limit=args.limit)
    if not data:
        print(f"❌ {DATA_DIR} 无数据")
        return 2

    total: Counter = Counter()
    n_sig = 0
    all_details: list[str] = []

    for code, df in data:
        res = ChanlunAnalyser(
            code=code, frequency="daily", config=ChanlunConfig()
        ).process_klines(df)
        n_sig += sum(
            1 for m in res.mmds if m.mmd_type in (MMDType.BUY_3, MMDType.SELL_3)
        )
        bad, details = check_one(code, res)
        total.update(bad)
        all_details.extend(details)

    print(f"第61课结构职责守门 —— {len(data)} 只标的（真实日线）")
    print(f"3买/3卖 信号数: {n_sig}")
    if not total:
        print("\n✅ 全部合规（结构职责口径 (a)(b)(c) + 旧中枢守卫）")
        return 0

    print(f"\n❌ 违规 {sum(total.values())} 处:")
    for k, v in total.most_common():
        print(f"   {k}: {v}")
    print(f"\n详情（最多 20 条 / 共 {len(all_details)}）:")
    for d in all_details[:20]:
        print("   " + d)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
