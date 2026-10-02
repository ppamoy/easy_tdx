#!/usr/bin/env python3
"""P1 历史时点选股端到端校验（用真实 gpcw 数据，无需网络）。

为什么需要它
------------
单元测试用的是构造数据。本脚本走**真实的整条 P1 管线**（`run_screen`）：
真实 gpcw 财报 → point-in-time 选期 → 树粮菜打分 → 春节夏秋冬 → 清单。
用来守住 F8 的三条硬要求：

  判据1  选出的每只票，其财报**披露日 ≤ T**（无未来数据）。这是 P1 可信度
         的生命线。
  判据2  同一 target 重复运行结果**完全一致**（可复现）。F3 训练数据也依赖这点。
  判据3  早时点不能看到晚财报：给两个相邻时点 T1 < T2，若某只票在 T2 才首次
         披露新一期，则它在 T1 的选期必须仍是**更旧**的那一期。

用法：  .venv/bin/python scripts/verify_p1_screen_e2e.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from easy_tdx.fundamental.indicators import load_all_periods_frame, pick_report  # noqa: E402
from easy_tdx.fundamental.pipeline import run_screen  # noqa: E402

CACHE_DIR = Path.home() / ".easy_tdx" / "gpcw_cache"
TARGET = date(2026, 4, 30)
# 早/晚时点必须**两边都有数据**，否则判定3 会空跑（我第一版取 T1=2026-01-20，
# 那时缓存里几乎没有财报，检查了 0 只却报"通过" —— 典型的假通过）。
# 实测披露日集中在 2026-04(9874) 与 2026-08(5328)，故选这两个月份之后。
T1, T2 = date(2026, 4, 30), date(2026, 8, 31)
MAX_POOL = 300


def _zips() -> list[str]:
    return sorted(z.name for z in CACHE_DIR.glob("gpcw*.zip"))


def main() -> int:
    zips = _zips()
    if not zips:
        print(f"❌ 未找到 gpcw zip（{CACHE_DIR}）")
        return 2
    frame = load_all_periods_frame(zips, None)
    if frame.empty:
        print("❌ 指标帧为空")
        return 2
    # 股票池必须用**表里真实的 (code, market)** 配对。此前我按 code 排序后半 SZ /
    # 半 SH 硬分，绝大多数搭配是错的，导致 pick_report 因 market 过滤而返回 None
    # （判据3 因此检查了 0 只 —— 空跑还报了通过）。
    pairs = (
        frame[["code", "market"]].drop_duplicates()
        .sort_values("code").head(MAX_POOL)
    )
    pool = [
        {"code": row.code, "market": row.market} for row in pairs.itertuples()
    ]

    ok = True
    print(f"股票池 {len(pool)} 只，财报zip {len(zips)} 份\n")

    # ── 判据1 + 判据2：跑一次完整选股 ──────────────────────────────
    r = run_screen(TARGET, pool, zips=zips, with_performance=False)
    rows = r.get("results", []) or []
    print(f"判据1/2：target={TARGET} 选出 {len(rows)} 只")
    if not rows:
        print("  ⚠ 没选出任何标的（判据无法充分验证，但不算失败）")
    else:
        bad = 0
        for row in rows:
            code = row.get("code")
            dd = row.get("disclosure_date")
            rd = row.get("report_date")
            ts = pd.Timestamp(TARGET)
            d = pd.to_datetime(dd, errors="coerce")
            r_d = pd.to_datetime(rd, errors="coerce")
            if pd.notna(d) and d > ts:
                bad += 1
                if bad <= 3:
                    print(f"  ❌ {code}: 披露日 {d.date()} > {TARGET}（未来数据）")
            elif pd.isna(d) and pd.notna(r_d) and r_d > ts:
                bad += 1
                if bad <= 3:
                    print(f"  ❌ {code}: 报告期 {r_d.date()} > {TARGET}（未来数据）")
        print(f"  {'✅' if bad == 0 else '❌'} 未来数据 {bad} 只")
        if bad:
            ok = False

        # 判据2：可复现（同一时点两次运行结果一致）
        r2 = run_screen(TARGET, pool, zips=zips, with_performance=False)
        rows2 = r2.get("results", []) or []
        same = len(rows) == len(rows2) and all(
            a.get("code") == b.get("code") and a.get("report_date") == b.get("report_date")
            for a, b in zip(rows, rows2)
        )
        print(f"  {'✅' if same else '❌'} 重复运行一致: {same}")
        if not same:
            ok = False

    # ── 判据3：早时点不得看到晚财报（写成"未来免疫"形式）────────────
    #
    # ⚠️ 旧写法有漏检（实测发现，务必保留这条注释）：
    # 旧版比较 T1 与 T2 的选期，只在 `r1 > r2` 时报警。但 T1 与 T2 **本来就可能
    # 选到同一期**（中间没有新披露），所以"T1 偷看了 T2 的期"会表现为 r1 == r2，
    # 永远不报警。实测注入「30% 的股票在 T1 返回 T2 的选期」，旧版竟报 ✅ 退出码 0。
    #
    # 正确写法：未来免疫 —— 用**全量财报**在 T1 选出的结果，必须等于用
    # 「披露日 <= T1 的财报子集」选出的结果。这样任何偷看未来的行为都无处遁形。
    print(f"\n判据3（未来免疫）：T1={T1} 选期不受 T1 之后披露的财报影响")
    frame_t1 = frame[
        pd.to_datetime(frame["disclosure_date"], errors="coerce")
        <= pd.Timestamp(T1)
    ]
    leaked = 0
    checked = 0
    for p in pool[:200]:
        c = p["code"]
        mkt = p.get("market")
        full = pick_report(frame, c, T1, market=mkt)
        only_t1 = pick_report(frame_t1, c, T1, market=mkt)
        if full is None and only_t1 is None:
            continue
        checked += 1
        a = None if full is None else str(full.get("report_date"))
        b = None if only_t1 is None else str(only_t1.get("report_date"))
        if a != b:
            leaked += 1
            if leaked <= 3:
                print(f"  ❌ {c}: 全量={a} 但截至T1应为={b}")
    flag = "✅" if leaked == 0 else "❌"
    print(f"  {flag} 检查 {checked} 只，异常 {leaked} 只")
    if leaked:
        ok = False
    # 覆盖范围自检：样本太少时判定毫无意义，必须报错而非"通过"
    if checked < 20:
        print(
            f"  ❌ 可比样本仅 {checked} 只（<20），判定3 无效 —— "
            "请选两个**都有数据**的时点"
        )
        ok = False

    print("\n结论:", "✅ P1 端到端 PIT 纪律成立" if ok else "❌ P1 存在问题")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
