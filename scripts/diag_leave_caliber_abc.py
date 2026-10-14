#!/usr/bin/env python3
"""三种「离开笔」口径的召回/合规对比，用于确定 V840 的正确边界。

口径 A（旧/V731）：离开笔可从 zs.lines[-1] 起（一笔两用，段数最多 4）
口径 B（V840 严）：离开笔只能是 bis[末笔+1]，不突破就整轮不产信号
口径 C（V840 宽松）：离开笔 = bis[末笔+1]；若它没突破，允许在**其后
   第一个反向笔之前**继续找同向突破笔（即「离开段可以自己带内部小往复」，
   但仍以第一个突破的同向笔为准，且回试笔必须是它的紧邻下一笔）

对每个口径输出：信号总数、段数分布、<5 段违规数、>30 段占比。

用法：.venv/bin/python scripts/diag_leave_caliber_abc.py [--limit N]
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
from easy_tdx.chanlun.types import BI, MMD, MMDType, ZS  # noqa: E402

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
    bis: list[BI],
    zss: list[ZS],
    first_type_mmds: list[MMD],
    caliber: str,
) -> list[MMD]:
    mmds: list[MMD] = []
    existing: set[int] = {m.bi.end.k.k_index for m in first_type_mmds if m.bi}

    for zs in zss:
        if zs.line_count < 3 or not zs.lines:
            continue
        last = zs.lines[-1].index
        if last + 1 >= len(bis):
            continue
        leave_bi = bis[last + 1]
        produced: set[str] = set()

        # ── 3买 ──
        cur = None
        if caliber == "A":
            start = last
        else:
            start = last + 1
            if leave_bi.direction.value == "up" and leave_bi.high > zs.zg:
                cur = leave_bi
        for bi in bis[start:]:
            if bi.direction.value == "up" and bi.high > zs.zg:
                if cur is None and (caliber == "A" or bi.index == start):
                    cur = bi
                continue
            if cur is None or bi.direction.value != "down":
                if caliber == "C" and cur is not None and bi.index > cur.index + 1:
                    break  # 离开笔之后只能紧邻一个回试笔
                continue
            if bi.low <= zs.zg:
                cur = None
                continue
            if bi.end.k.k_index in existing:
                cur = None
                continue
            mmds.append(MMD(mmd_type=MMDType.BUY_3, zs=zs, bi=bi, msg=""))
            existing.add(bi.end.k.k_index)
            produced.add("buy")
            break

        # ── 3卖 ──
        if "buy" in produced:
            continue
        cur = None
        if caliber != "A" and leave_bi.direction.value == "down" and leave_bi.low < zs.zd:
            cur = leave_bi
        for bi in bis[start:]:
            if bi.direction.value == "down" and bi.low < zs.zd:
                if cur is None and (caliber == "A" or bi.index == start):
                    cur = bi
                continue
            if cur is None or bi.direction.value != "up":
                continue
            if bi.high >= zs.zd:
                cur = None
                continue
            if bi.end.k.k_index in existing:
                cur = None
                continue
            mmds.append(MMD(mmd_type=MMDType.SELL_3, zs=zs, bi=bi, msg=""))
            existing.add(bi.end.k.k_index)
            break

    return mmds


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    data = load_all(limit=args.limit)
    if not data:
        print(f"❌ {DATA_DIR} 无数据")
        return 2

    for caliber in ("A", "B", "C"):
        tot = 0
        dist: Counter[int] = Counter()
        for code, df in data:
            res = ChanlunAnalyser(
                code=code, frequency="daily", config=ChanlunConfig()
            ).process_klines(df)
            ft = [
                m
                for m in res.mmds
                if m.mmd_type in (MMDType.BUY_1, MMDType.SELL_1)
            ]
            for m in scan(res.bis, res.zss, ft, caliber):
                tot += 1
                dist[m.bi.index - m.zs.lines[0].index + 1] += 1
        bad = sum(v for k, v in dist.items() if k < 5)
        far = sum(v for k, v in dist.items() if k > 30)
        print(f"\n=== 口径 {caliber} ===")
        print(f"信号总数: {tot}")
        print(f"第61课 <5 段违规: {bad}/{tot} ({bad/max(tot,1)*100:.1f}%)")
        print(f"回试笔距中枢 >30 段: {far} ({far/max(tot,1)*100:.1f}%)")
        print("段数分布(前12): " + " ".join(f"{k}:{v}" for k, v in sorted(dist.items())[:12]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
