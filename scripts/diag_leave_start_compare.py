#!/usr/bin/env python3
"""对比两种「离开笔起点」口径，量化第61课 5 段合规率与召回率。

口径 A（现状，V731）：leave_start_idx = zs.lines[-1].index
    —— 把中枢末笔（与 [ZD,ZG] 有重叠的**延伸段**）当作候选离开笔
口径 B（原文）：leave_start_idx = zs.lines[-1].index + 1
    —— 第20课中枢中心定理一：「若有 Zn，使得 dn>ZG 或 gn<ZD，则必然产生
       高级别的走势中枢」⇒ 与 [ZD,ZG] 有重叠的笔是延伸，不是离开。
       zs.py 关闭中枢的那一笔（完全无重叠）本身不在 zs.lines 内，
       它就是 bis[末笔.index + 1]，即新中枢候选的第一笔。

对每个口径输出：3买/3卖 总数、段数分布、<5 段违规数、假离开笔占比。

用法：.venv/bin/python scripts/diag_leave_start_compare.py [--limit N]
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
from easy_tdx.chanlun.mmd import _find_third_type_mmds_original  # noqa: E402
from easy_tdx.chanlun.types import MMD, MMDType, ZS  # noqa: E402

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


def scan(
    bis: list,
    zss: list[ZS],
    first_type_mmds: list[MMD],
    cfg,
    plus_one: bool,
) -> tuple[list[MMD], Counter, Counter]:
    """复刻 _find_third_type_mmds_original，只改 leave_start_idx 口径。"""
    mmds: list[MMD] = []
    existing: set[int] = {m.bi.end.k.k_index for m in first_type_mmds if m.bi}
    max_bars = int(getattr(cfg, "mmd_3rd_retest_max_bars", 0) or 0) if cfg else 0

    next_zs_bi_idx_map: dict[int, int | None] = {}
    for i, zs in enumerate(zss):
        nxt = None
        for j in range(i + 1, len(zss)):
            if zss[j].lines:
                nxt = zss[j].lines[0].index
                break
        next_zs_bi_idx_map[zs.index] = nxt

    dist: Counter[int] = Counter()
    fake_leave: Counter[str] = Counter()

    for zs in zss:
        if zs.line_count < 3 or not zs.lines:
            continue
        base = zs.lines[-1].index
        leave_start_idx = base + 1 if plus_one else base
        cur_break = None
        next_zs_bi = next_zs_bi_idx_map.get(zs.index)

        for bi in bis[leave_start_idx:]:
            if next_zs_bi is not None and bi.index > next_zs_bi:
                break
            if bi.direction.value == "up" and bi.high > zs.zg:
                if cur_break is None:
                    # 记录该离开笔是否与 [ZD,ZG] 有重叠（原文 ⇒ 属延伸）
                    if min(zs.zg, bi.high) > max(zs.zd, bi.low):
                        fake_leave["buy_overlap"] += 1
                    else:
                        fake_leave["buy_clean"] += 1
                    cur_break = bi
                continue
            if cur_break is None or bi.direction.value != "down":
                continue
            if bi.low <= zs.zg:
                cur_break = None
                continue
            if max_bars and bi.end.k.k_index - cur_break.end.k.k_index > max_bars:
                cur_break = None
                continue
            if bi.end.k.k_index in existing:
                cur_break = None
                continue
            mmds.append(
                MMD(
                    mmd_type=MMDType.BUY_3,
                    zs=zs,
                    bi=bi,
                    msg=f"3buy seg={bi.index - zs.lines[0].index + 1}",
                )
            )
            existing.add(bi.end.k.k_index)
            dist[bi.index - zs.lines[0].index + 1] += 1
            break

        cur_break = None
        for bi in bis[leave_start_idx:]:
            if next_zs_bi is not None and bi.index > next_zs_bi:
                break
            if bi.direction.value == "down" and bi.low < zs.zd:
                if cur_break is None:
                    if min(zs.zg, bi.high) > max(zs.zd, bi.low):
                        fake_leave["sell_overlap"] += 1
                    else:
                        fake_leave["sell_clean"] += 1
                    cur_break = bi
                continue
            if cur_break is None or bi.direction.value != "up":
                continue
            if bi.high >= zs.zd:
                cur_break = None
                continue
            if max_bars and bi.end.k.k_index - cur_break.end.k.k_index > max_bars:
                cur_break = None
                continue
            if bi.end.k.k_index in existing:
                cur_break = None
                continue
            mmds.append(
                MMD(
                    mmd_type=MMDType.SELL_3,
                    zs=zs,
                    bi=bi,
                    msg=f"3sell seg={bi.index - zs.lines[0].index + 1}",
                )
            )
            existing.add(bi.end.k.k_index)
            dist[bi.index - zs.lines[0].index + 1] += 1
            break

    return mmds, dist, fake_leave


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    data = load_all(limit=args.limit)
    if not data:
        print(f"❌ {DATA_DIR} 无数据")
        return 2

    for label, plus_one in (("口径A 现状 leave=末笔.index", False),
                            ("口径B 原文 leave=末笔.index+1", True)):
        tot = 0
        dist: Counter[int] = Counter()
        fake: Counter[str] = Counter()
        for code, df in data:
            res = ChanlunAnalyser(
                code=code, frequency="daily", config=ChanlunConfig()
            ).process_klines(df)
            mmds, d, f = scan(
                res.bis, res.zss, res.mmds, ChanlunConfig(), plus_one
            )
            tot += len(mmds)
            dist.update(d)
            fake.update(f)
        bad = sum(v for k, v in dist.items() if k < 5)
        print(f"\n=== {label} ===")
        print(f"3买/3卖 总数: {tot}")
        print(
            "段数分布: "
            + " ".join(f"{k}段:{v}" for k, v in sorted(dist.items()))
        )
        print(
            f"第61课 <5 段违规: {bad}/{tot} "
            f"({bad / max(tot, 1) * 100:.1f}%)"
        )
        ov = fake["buy_overlap"] + fake["sell_overlap"]
        cl = fake["buy_clean"] + fake["sell_clean"]
        print(
            f"候选离开笔构成: 与[ZD,ZG]有重叠(原文属延伸)={ov}  "
            f"完全在外(原文真离开)={cl}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
