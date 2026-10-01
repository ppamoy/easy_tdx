#!/usr/bin/env python3
"""Point-in-time（PIT）泄漏检测器 —— 可复用的「生命线」守卫。

为什么需要它
------------
需求文档把 point-in-time 纪律称为 P1 可信度的**生命线**：历史时点分析只能
用「当时已可得」的数据（披露日 ≤ T），禁止未来数据回填。此前只有零散单测
（test_fundamental_pit_type_safety / test_chanlun_train_no_future_leak），
没有一条**端到端**的守卫：给定真实财报数据和一批历史时点，自动确认取到的
每一期都是当时已披露的。

本脚本按 AGENTS.md §7「把一次性验证变成可复用机制」沉淀，覆盖三个判据：

  判据1（无未来函数）：pick_report 返回的每行 disclosure_date ≤ target；
        披露日缺失时用 report_date 近似，且相差 ≤100 天。
  判据2（双实现一致）：pick_report（逐股）与 pick_reports_bulk（向量化）
        结果必须一致 —— 后者自称「规则与 pick_report 完全一致」，两套实现
        最容易悄悄漂移，漂移即意味着某条路径漏了 PIT 截断。
  判据3（自检/反向锁定）：故意注入一行「未来披露」的记录，检测器必须报警；
        若注入后仍然"通过"，说明检测逻辑本身失效（假阴性）。

用法：  .venv/bin/python scripts/verify_pit_no_leak.py
数据：  用 ~/.easy_tdx/gpcw_cache/ 下的真实财报 zip（无网络也能跑）。
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

import pandas as pd  # noqa: E402

from easy_tdx.fundamental.indicators import (  # noqa: E402
    load_all_periods_frame,
    pick_report,
    pick_reports_bulk,
)

CACHE_DIR = Path.home() / ".easy_tdx" / "gpcw_cache"
# 覆盖不同年份的历史时点：财报密集披露期前后各取，能抓到跨期回填
TARGETS = [
    date(2025, 3, 15),
    date(2025, 5, 10),
    date(2025, 9, 1),
    date(2026, 1, 20),
    date(2026, 4, 30),
    date(2026, 8, 15),
]
MAX_CODES = 400  # 抽样规模（全市场 5000+ 太慢，抽样仍有统计意义）


def _zips() -> list[str]:
    zs = sorted(CACHE_DIR.glob("gpcw*.zip"))
    return [z.name for z in zs]


def _future_violations(row: pd.Series, target: date) -> str | None:
    """返回违规原因，None 表示合规。"""
    dd = row.get("disclosure_date")
    rd = row.get("report_date")
    ts = pd.Timestamp(target)
    d = pd.to_datetime(dd, errors="coerce")
    if pd.notna(d):
        if d > ts:
            return f"披露日 {d.date()} > 时点 {target}（未来数据）"
        return None
    r = pd.to_datetime(rd, errors="coerce")
    if pd.notna(r):
        if r > ts:
            return f"报告期 {r.date()} > 时点 {target}（未来数据）"
        if (ts - r) > pd.Timedelta(days=100):
            return f"披露日缺失且报告期距今 {int((ts - r).days)} 天 > 100 天（越界近似）"
        return None
    return "披露日与报告期都缺失（无法判定可得性）"


def main() -> int:
    zips = _zips()
    if not zips:
        print(f"❌ 未找到 gpcw 财报 zip（{CACHE_DIR}）")
        return 2
    print(f"财报文件: {', '.join(zips)}")

    frame = load_all_periods_frame(zips, None)
    if frame.empty:
        print("❌ 指标帧为空")
        return 2
    print(f"指标帧: {len(frame)} 行 / {frame['code'].nunique()} 只股票\n")

    codes = sorted(frame["code"].unique())[:MAX_CODES]
    sample = frame[frame["code"].isin(codes)].copy()

    ok = True

    # ── 判据1 + 判据2 ───────────────────────────────────────────────
    for target in TARGETS:
        bulk = pick_reports_bulk(sample, target)
        bulk_map = {}
        if not bulk.empty:
            for _, r in bulk.iterrows():
                bulk_map[r["code"]] = r

        n = 0
        v1 = 0
        drift = 0
        for code in codes:
            row = pick_report(sample, code, target)
            if row is None:
                continue
            n += 1
            why = _future_violations(row, target)
            if why:
                v1 += 1
                if v1 <= 3:
                    print(f"  ❌ [{target}] {code}: {why}")
            # 判据2：与向量化实现比对
            b = bulk_map.get(code)
            if b is None:
                drift += 1
                if drift <= 3:
                    print(f"  ❌ [{target}] {code}: bulk 未返回（逐股有、批量无）")
                continue
            rd_a = pd.to_datetime(row.get("report_date"), errors="coerce")
            rd_b = pd.to_datetime(b.get("report_date"), errors="coerce")
            if str(rd_a) != str(rd_b):
                drift += 1
                if drift <= 3:
                    print(
                        f"  ❌ [{target}] {code}: 两实现漂移 "
                        f"逐股={rd_a} 批量={rd_b}"
                    )

        flag = "✅" if (v1 == 0 and drift == 0) else "❌"
        print(
            f"{flag} 时点 {target}: 命中 {n} 只 | 未来数据 {v1} | 实现漂移 {drift}"
        )
        if v1 or drift:
            ok = False

    # ── 判据3：自检 —— 注入未来数据，检测器必须报警 ──────────────────
    print("\n自检：注入一行「未来披露」记录，检测器必须报警")
    poisoned = sample.copy()
    fake = poisoned.iloc[[0]].copy()
    fake["report_date"] = pd.Timestamp("2030-12-31")
    fake["disclosure_date"] = pd.Timestamp("2030-12-31")
    fake["code"] = "__PIT_POISON__"
    poisoned = pd.concat([poisoned, fake], ignore_index=True)

    target = date(2026, 1, 20)
    # 判据：逐股实现要么**不返回**该行（已拦截），要么返回但被判据1识别为
    # 未来数据。两种都算"检测有效"；只有「返回了且判据1没认出来」才是假阴性。
    # （V731 自查：第一版把"返回 None"误当成检测器失效，逻辑写反了 ——
    #  拦截恰恰是正确行为。已修。）
    row = pick_report(poisoned, "__PIT_POISON__", target)
    if row is None:
        print("  逐股实现：已拦截（未返回该行）✅")
        detected = True
    else:
        why = _future_violations(row, target)
        print(f"  逐股实现：返回了该行 → 判据1识别: {why!r}")
        detected = why is not None

    bulk_p = pick_reports_bulk(poisoned, target)
    leaked = bulk_p[bulk_p["code"] == "__PIT_POISON__"] if not bulk_p.empty else bulk_p
    bulk_ok = leaked.empty
    print(f"  批量实现：{'已拦截 ✅' if bulk_ok else '❌ 泄漏了未来数据'}")

    if not (detected and bulk_ok):
        print("❌ 自检失败：检测器本身失效（假阴性）")
        ok = False
    else:
        print("✅ 自检通过：注入未来数据后两个实现都被拦下")

    print("\n结论:", "✅ PIT 无泄漏，两实现一致" if ok else "❌ 存在泄漏/漂移")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
