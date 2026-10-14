#!/usr/bin/env python3
"""多级别策略 PIT 的**牙齿**：先证明本检测真能抓到"未来函数"，再谈结论。

## 为什么要有这个脚本
``verify_ml_pit.py`` 只做了"截断后逐位一致"这**半**件事——它默认
"如果代码有未来函数，截断后的结果一定会变"。这个默认**没被验证过**。

踩过的坑（2026-10-10）：
我写过一版 PIT 检查，同时截断日线和次级别数据，但**信号仍用全量预计算注入**
（``set_precomputed`` 传的是全量 main/sub 序列）。结果 30/30 全"一致"——
因为**信号根本没随数据一起截断**，本来就不该变。那是个**恒真的假检测**：
不管策略有没有未来函数，它都会报 ✅。

## 判据（三条，缺一不可）
1. **一致性**：截断到 N 根日线（次级别同步截断）后，截断范围内完成的
   配对必须与全量跑**逐位一致** —— 不通过 ⇒ 有未来函数。
2. **非空**：截断范围内必须**真的有配对**可比较。若 `f_in` 恒为空，
   比较 `[] == []` 必然"一致"，检测形同虚设。
3. **注入可检出**（真牙齿）：人为注入一个**已知的未来函数**
   （把次级别信号按**未来**时刻提前消费），本检测必须报 ❌。
   报 ✅ ⇒ 检测是恒真的，结论不可信。

用法：  .venv/bin/python scripts/verify_ml_pit_teeth.py --limit 12
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from easy_tdx.backtest.engine import BacktestEngine  # noqa: E402
from easy_tdx.backtest.strategies.chanlun_ml import ChanlunMLStrategy  # noqa: E402
from _ml_precompute import CACHE, load_pair  # noqa: E402

SLIP = 0.002
PLAN = {"entry_types": "1buy,2buy,3buy", "exit_types": "1sell",
        "fallback_exit_types": "", "max_hold_bars": 120}


def _signals(code: str, d: pd.DataFrame, s: pd.DataFrame, truncate: int | None = None):
    """取 (main, sub) 信号；truncate 时**同步截断信号**（这才是正确的 PIT 姿势）。"""
    p = next((x for x in CACHE.glob(f"{code}_*.json")), None)
    if p is None:
        return None
    c = json.loads(p.read_text())
    main = [(x["bar"], x["t"], x["c"]) for x in c["main"]]
    sub = [(pd.Timestamp(x["dt"]), x["t"], x["c"]) for x in c["sub"]]
    if truncate is not None:
        t_end = d["datetime"].iloc[truncate - 1]
        main = [x for x in main if x[0] < truncate]
        sub = [x for x in sub if x[0] <= t_end]
    return main, sub


def _run(d: pd.DataFrame, s: pd.DataFrame, main, sub, inject_future: bool = False) -> list[dict]:
    st = ChanlunMLStrategy(**PLAN)
    st.set_data(d, s)
    if inject_future:
        # 已知未来函数：把次级别信号**提前 5 根日线**消费 ——
        # 等价于"提前 5 天就知道后面的 30min 卖点"。
        sub2 = [(t - pd.Timedelta(days=5), ty, c) for (t, ty, c) in sub]
        sub2.sort(key=lambda x: x[0])
    else:
        sub2 = sub
    st.set_precomputed(main_signals=main, sub_signals=sub2)
    BacktestEngine(st, cash=100000.0, slippage=SLIP).run(d)
    return list(st.pair_log)


def _key(p: dict) -> tuple:
    return (p["entry_type"], p["exit_type"], p["entry_bar"], p["exit_bar"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--truncate", type=int, default=200)
    a = ap.parse_args()

    codes = sorted({f.name.split("_")[0] for f in CACHE.glob("*_*.json")})[: a.limit]
    print(f"多级别 PIT 牙齿：{len(codes)} 只，截断到前 {a.truncate} 根日线\n")

    n_same = n_bad = n_empty = 0
    n_inj_caught = n_inj_total = 0

    for code in codes:
        d, s = load_pair(code)
        if len(d) < a.truncate + 20:
            print(f"  {code}: 数据不足（{len(d)} 根），跳过")
            continue

        full = _run(d, s, *_signals(code, d, s))
        d2 = d.iloc[: a.truncate].reset_index(drop=True)
        s2 = s[s["datetime"] <= d2["datetime"].iloc[-1]].reset_index(drop=True)
        trunc = _run(d2, s2, *_signals(code, d, s, truncate=a.truncate))
        f_in = [p for p in full if p["exit_bar"] < a.truncate]

        if not f_in:
            n_empty += 1
            print(f"  {code}: ⚠️ 截断内 0 笔，无法判定（空比较恒真，不计入通过）")
            continue

        ok = len(f_in) == len(trunc) and all(_key(x) == _key(y) for x, y in zip(f_in, trunc))
        n_bad += 0 if ok else 1
        n_same += 1 if ok else 0

        # ── 注入测试：同一个策略，喂进"提前 5 天"的次级别信号 ──
        inj = _run(d, s, *_signals(code, d, s), inject_future=True)
        n_inj_total += 1
        inj_changed = [_key(p) for p in inj] != [_key(p) for p in full]
        n_inj_caught += 1 if inj_changed else 0

        print(f"  {code}: 全量{len(full)}笔 截断内{len(f_in)}笔 vs 截断跑{len(trunc)}笔 "
              f"{'✅一致' if ok else '❌不一致'}   "
              f"注入未来函数{'✅被检出' if inj_changed else '❌没检出'}")

    print()
    print(f"判定 1 一致性：{n_same}/{n_same + n_bad} 通过"
          f"（{n_empty} 只因截断内 0 笔被排除，不计入）")
    print(f"判定 2 非空性：{n_same + n_bad} 只做了实质比较"
          f"{'✅' if n_same + n_bad > 0 else '❌ 没有任何实质比较'}")
    print(f"判定 3 注入可检出：{n_inj_caught}/{n_inj_total} 被检出")

    ok_all = (n_bad == 0 and n_same > 0
              and n_inj_caught > 0
              and n_inj_caught == n_inj_total)
    print()
    if ok_all:
        print("✅ 牙齿通过：截断一致 + 有实质比较 + 注入的未来函数全部被检出")
        print("   ⇒ 说明本检测不是恒真的，『一致』这个结论可信")
        return 0
    print("❌ 牙齿失败：")
    if n_bad:
        print(f"   - {n_bad} 只截断不一致 ⇒ 存在未来函数")
    if n_same == 0:
        print("   - 没有任何实质比较（全是空比较）⇒ 检测恒真")
    if n_inj_caught < n_inj_total:
        print(f"   - 注入的未来函数有 {n_inj_total - n_inj_caught} 只没被检出 ⇒ 检测是恒真的假检测")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
