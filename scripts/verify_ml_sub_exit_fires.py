#!/usr/bin/env python3
"""牙齿：多级别策略的**次级别出场到底有没有真的触发**。

## 为什么必须有这个脚本（我自己踩过的坑）
`chanlun_ml.py` 曾有一处**时间对齐**问题：日线时间戳是 00:00，而 30min 是当日
10:00~15:00。用日线时间做 `sub_dt > now` 比较 ⇒ 当日收盘前出现的次级别卖点
要**等到下一根日线**才被消费 ⇒ 出场系统性延迟一根日线。

⚠️ **更正（2026-10-10 实测，推翻我原先的说法）**：
我曾在注释里写"次级别卖点**永远无法触发**、全部退化成 max_hold 兜底"。
30 只实测证明这是**错的**：坏版本出场分布 {1sell:104, max_hold:10} 与好版本
**完全相同**，104 笔差异全部是 exit_bar **恰好 +1 根**，零笔退化成 max_hold。
真实后果是**晚一天卖**（配对差 −2.37%，t=−2.15），不是"功能失效"。
所以本脚本的牙齿**不能**只断言"不是 max_hold"，还要断言：
  (a) 全局真实卖点占比 ≥50%
  (b) 抽走次级别信号后真实卖点归零（归因）
  (c) 有次级别时持仓更短（更早离场）
这三条一起才抓得住"次级别没真生效"这一类失效。

本脚本把这件事变成**可自动回归的断言**：
1. 次级别信号必须**真的消费到**（`exit_type` 里有真实的 1sell/2sell/3sell，
   而不是清一色 max_hold）
2. 次级别出场必须**比同级别出场更早**（否则"精确卖点"没有意义）
3. 对照：把次级别数据抽走（传 None），方案应退化成纯兜底 —— 证明差异
   **确实来自**次级别数据，而不是别的什么

用法：  .venv/bin/python scripts/verify_ml_sub_exit_fires.py --limit 8
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from _ml_precompute import CACHE, load_pair  # noqa: E402
from easy_tdx.backtest.engine import BacktestEngine  # noqa: E402
from easy_tdx.backtest.strategies.chanlun_ml import ChanlunMLStrategy  # noqa: E402

SLIP = 0.002
PLAN = {"entry_types": "1buy,2buy,3buy", "exit_types": "1sell",
        "fallback_exit_types": "", "max_hold_bars": 120}
REAL_SELLS = ("1sell", "2sell", "2sell_s", "3sell")


def run_ml(code: str, with_sub: bool, bad_align: bool = False):
    d, s = load_pair(code)
    p = next((x for x in CACHE.glob(f"{code}_*.json")), None)
    if p is None:
        return None
    c = json.loads(p.read_text())
    m = ChanlunMLStrategy(**PLAN)
    m.set_data(d, s)
    if bad_align:
        # 坏对齐：日线时间不加 23:59（复现已更正的那处问题）
        m._dt_arr = list(pd.to_datetime(pd.Series(d["datetime"]).reset_index(drop=True)))
    if with_sub:
        m.set_precomputed(
            main_signals=[(x["bar"], x["t"], x["c"]) for x in c["main"]],
            sub_signals=[(pd.Timestamp(x["dt"]), x["t"], x["c"]) for x in c["sub"]],
            main_nested={int(k): v for k, v in c["main_nested"].items()},
        )
    else:
        # 抽走次级别信号 ⇒ 只剩本级别入场 + max_hold 兜底
        m.set_precomputed(
            main_signals=[(x["bar"], x["t"], x["c"]) for x in c["main"]],
            sub_signals=[],
        )
    BacktestEngine(m, cash=100000.0, slippage=SLIP).run(d)
    return m.pair_log


def _inject_bad_alignment(codes: list[str]) -> tuple[int, float]:
    """注入坏对齐（日线时间不加 23:59），统计逐笔 exit_bar 差异。

    返回 (差异笔数, 平均延迟根数)。
    """
    shifts: list[int] = []
    for code in codes:
        good = run_ml(code, True, bad_align=False)
        badp = run_ml(code, True, bad_align=True)
        if not good or not badp:
            continue
        for g, b in zip(good, badp):
            if g["exit_bar"] != b["exit_bar"]:
                shifts.append(b["exit_bar"] - g["exit_bar"])
    return len(shifts), (float(np.mean(shifts)) if shifts else 0.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=8)
    a = ap.parse_args()

    codes = sorted({f.name.split("_")[0] for f in CACHE.glob("*_*.json")})[: a.limit]
    if not codes:
        print("❌ 无缓存，先跑 scripts/_ml_precompute.py")
        return 1

    print(f"牙齿：次级别出场是否真的触发（{len(codes)} 只）\n")
    tot = Counter()
    hold_with, hold_without = 0, 0
    n_with = n_without = 0
    bad = 0
    for code in codes:
        pl_with = run_ml(code, True)
        pl_without = run_ml(code, False)
        if pl_with is None:
            continue
        c_with = Counter(p["exit_type"] for p in pl_with)
        tot.update(c_with)
        real = sum(v for k, v in c_with.items() if k in REAL_SELLS)
        allx = sum(c_with.values())
        n_with += real
        hold_with += sum(p["holding_bars"] for p in pl_with)
        if pl_without:
            n_without += sum(1 for p in pl_without if p["exit_type"] in REAL_SELLS)
            hold_without += sum(p["holding_bars"] for p in pl_without)
        # ⚠️ 单笔标的不能按比率判：只有 1 笔且恰好走到 max_hold 是正常现象
        #    （该标的窗口内次级别没出现 1sell），不是"次级别没生效"。
        #    故：>=2 笔才按比率判，整体另设**全局**比率门槛。
        rate = real / allx if allx else 0.0
        if allx == 0:
            mark, skip = "—", True
        elif allx >= 2:
            mark, skip = ("✅" if rate >= 0.5 else "❌"), False
            if rate < 0.5:
                bad += 1
        else:
            mark, skip = "—", True
        print(f"  {code}: {allx} 笔，次级别真实卖点出场 {real} 笔 ({rate*100:.0f}%) {mark}"
              f"  分布={dict(c_with)}")

    print(f"\n全场出场类型分布（有次级别数据）: {dict(tot)}")
    real_all = sum(v for k, v in tot.items() if k in REAL_SELLS)
    all_all = sum(tot.values())
    print(f"真实次级别卖点占比: {real_all}/{all_all} = {real_all/max(all_all,1)*100:.1f}%")

    print("\n── 对照：抽走次级别信号后 ──")
    print(f"  有次级别数据：真实卖点出场 {n_with} 笔，累计持有 {hold_with} 根")
    print(f"  无次级别信号：真实卖点出场 {n_without} 笔，累计持有 {hold_without} 根")
    degraded = (n_with > 0 and n_without == 0)
    print(f"  {'✅' if degraded else '❌'} 抽走后真实卖点出场归零"
          f" ⇒ 差异确实来自次级别数据" if degraded else
          "  ❌ 抽走后仍有真实卖点出场 ⇒ 说明有别的路径在产生出场，口径有问题")

    g_rate = real_all / max(all_all, 1)
    g_ok = g_rate >= 0.5
    hold_ok = hold_with < hold_without   # 次级别出场应让持仓更短（更早离场）
    print(f"  {'✅' if g_ok else '❌'} 全局比率 {g_rate*100:.1f}% ≥ 50%")
    print(f"  {'✅' if hold_ok else '❌'} 有次级别时持仓更短（{hold_with} < {hold_without} 根）"
          f" ⇒ 次级别确实抓到了更早的卖点")

    # ── 牙齿 4（关键新增）：延迟检测 ──────────────────────────────────
    # 上面三条抓得住"次级别完全没生效"，但**抓不住"生效了但晚一根"**。
    # 而我实测发现：坏对齐的真实后果恰恰是 exit_bar 系统性 +1（30 只、
    # 104/104 笔全部 +1，零笔退化成 max_hold）—— 前三条会全部通过。
    # 所以必须有一条**延迟**断言：把日线时间改回 00:00（坏对齐），
    # 逐笔 exit_bar 必须出现 ≥1 的差异 ⇒ 证明当前口径确实在"当日收盘"消费。
    print("\n── 牙齿 4：坏对齐（日线时间不加 23:59）必须产生可观测差异 ──")
    inj = _inject_bad_alignment(codes)
    n_shift, mean_shift = inj
    delay_ok = n_shift > 0
    print(f"  坏对齐 vs 好对齐：{n_shift} 笔 exit_bar 不同"
          f"{f'，平均延迟 {mean_shift:.2f} 根' if n_shift else ''}")
    print(f"  {'✅' if delay_ok else '❌'} 坏对齐可被检出 ⇒ 牙齿对"
          f"『晚一根』这类失效有分辨力" if delay_ok else
          "  ❌ 坏对齐与好对齐逐笔一致 ⇒ 牙齿形同虚设，抓不到延迟类 bug")

    ok = (bad == 0) and degraded and real_all > 0 and g_ok and hold_ok and delay_ok
    print()
    if ok:
        print("✅ 牙齿通过：次级别出场真的触发了，差异可归因于次级别数据，")
        print("   且本牙齿对『完全失效』与『延迟一根』两类失效都有分辨力")
        return 0
    print(f"❌ 牙齿失败：多笔标的中 {bad} 只占比 <50%，或某条断言不成立")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
