#!/usr/bin/env python3
"""长历史（2020-07 起，1500 根日线）的未来函数（PIT）验证。

动机：
  ``verify_ml_pit_teeth.py`` 只在 **2024-09 起** 的窗口验过 PIT（因为次级别
  30min 数据只有那一段）。而 ``audit_chanlun_profitability.py`` 用的是
  **2020-07 起的长历史** —— 那段**没有做过未来函数排查**。
  在补齐之前，长历史跑出的 +139.8% 之类数字**有可能是水分**，
  不能作为结论。本脚本就是来封这个口子的。

难点与处理：
  30min 数据只覆盖 2024-09 之后 ⇒ 长历史**用不了**次级别 ⇒ 本脚本验证
  **同级别**（本级别买 → 本级别卖，即 audit_chanlun_profitability.py 里
  **分段回测**所用的口径）。这覆盖了长历史结论的主要部分；
  全段带次级别的口径仍受限于 30min 数据长度，**本脚本无法验证**，如实声明。

三条判据（与 verify_ml_pit_teeth.py 同构，缺一不可）：
  1. **一致性**：截断到 N 根后，截断范围内已完成的交易必须逐位一致
  2. **非空**：截断范围内必须真的有配对可比（否则"一致"是空比较，恒真）
  3. **牙齿**：注入已知未来函数（卖点信号提前消费）必须被检出

用法：
    .venv/bin/python scripts/verify_pit_long_history.py --limit 10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import pandas as pd  # noqa: E402

from easy_tdx.backtest.engine import BacktestEngine  # noqa: E402
from easy_tdx.backtest.signal_stats import is_buy_type  # noqa: E402
from easy_tdx.backtest.strategies.chanlun_ml import ChanlunMLStrategy  # noqa: E402
from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402

DATA = ROOT / "audit_data"
MCAP = ROOT / "audit_mcap.json"
PLAN = {"entry_types": "1buy,2buy,3buy", "exit_types": "1sell", "max_hold_bars": 60}
SHIFT_DAYS = 5  # 注入的未来函数：信号提前这么多天


def load_daily(code: str) -> pd.DataFrame:
    p = DATA / f"{code}_daily.json"
    if not p.exists():
        return pd.DataFrame()
    df = pd.DataFrame(json.loads(p.read_text()))
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df.reset_index(drop=True)


def signals(df: pd.DataFrame, upto: int | None = None):
    """构造同级别信号 (main=入场/出场, sub=None)。upto 时同步截断。"""
    res = ChanlunAnalyser(code="X", frequency="daily", config=ChanlunConfig()).process_klines(df)
    main = []
    for m in res.mmds:
        bar = int(m.bi.end.bar_index) if m.bi else -1
        if bar >= 0:
            main.append((bar, str(m.mmd_type.value), float(getattr(m, "confidence", 0.0))))
    main.sort(key=lambda x: x[0])
    if upto is not None:
        main = [x for x in main if x[0] < upto]
    return main


def run(code: str, d: pd.DataFrame, upto: int | None = None, inject: bool = False):
    m = signals(d, upto)
    if inject:
        # 已知未来函数：把卖点信号**提前 SHIFT_DAYS 天**消费
        m2 = []
        dts = d["datetime"].reset_index(drop=True)
        for bar, t, c in m:
            # ⚠️ 不能用 t.endswith("sell")：`2sell_s` 以 `_s` 结尾会漏判，
            #   导致注入的未来函数覆盖面不够（削弱牙齿）。用唯一口径取反。
            if not is_buy_type(t) and bar < len(dts):
                shifted = pd.Timestamp(dts.iloc[bar]) - pd.Timedelta(days=SHIFT_DAYS)
                m2.append((_bar_of(dts, shifted), t, c))
            else:
                m2.append((bar, t, c))
        m2.sort(key=lambda x: x[0])
        m = m2
    st = ChanlunMLStrategy(**PLAN)
    st.set_data(d, None)
    st.set_precomputed(main_signals=m)
    BacktestEngine(st, cash=1_000_000, slippage=0.002).run(d)
    return st.pair_log


def _bar_of(dts, ts) -> int:
    """找 <= ts 的最后一个 bar 下标。"""
    n = len(dts)
    lo, hi = 0, n - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if pd.Timestamp(dts.iloc[mid]) <= ts:
            lo = mid
        else:
            hi = mid - 1
    return lo


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--frac", type=float, default=0.7, help="截断到全长的比例")
    a = ap.parse_args()

    mcap = json.loads(MCAP.read_text()) if MCAP.exists() else {}
    codes = [k for k, v in sorted(mcap.items(), key=lambda x: -x[1].get("mcap", 0))]
    if not codes:
        codes = [p.name.split("_")[0] for p in sorted(DATA.glob("*_daily.json"))]
    codes = codes[: a.limit] if a.limit else codes

    print(f"长历史 PIT 验证：{len(codes)} 只，截断到 {a.frac:.0%}")
    print("口径：同级别（本级别买 → 本级别卖）—— 次级别 30min 只有 2024-09 起，长历史用不了")
    print()

    ok_consist, ok_nonempty, ok_inject, skipped = 0, 0, 0, 0
    for code in codes:
        d = load_daily(code)
        if len(d) < 500:
            continue
        cut = int(len(d) * a.frac)

        full = run(code, d)
        trunc = run(code, d, upto=cut)

        # 截断范围内（exit_bar < cut）已完成的交易
        f_in = [p for p in full if p["exit_bar"] < cut]
        t_in = [p for p in trunc if p["exit_bar"] < cut]

        if not f_in and not t_in:
            print(f"  {code}: ⚠️ 截断内 0 笔，无法判定（空比较恒真，不计入通过）")
            skipped += 1
            continue

        consist = list(f_in) == list(t_in)
        nonempty = bool(f_in)

        # 牙齿：注入未来函数必须产生差异
        inj = run(code, d, inject=True)
        caught = list(inj) != list(full)

        print(f"  {code}: 一致={'✅' if consist else '❌'} "
              f"({len(f_in)}/{len(t_in)} 笔)  非空={'✅' if nonempty else '❌'}  "
              f"注入检出={'✅' if caught else '❌'}")

        ok_consist += consist
        ok_nonempty += nonempty
        ok_inject += caught

    n = ok_consist + ok_nonempty and max(ok_consist, ok_nonempty)
    total = len(codes) - skipped
    print(f"\n判定 1 一致性：{ok_consist}/{total}")
    print(f"判定 2 非空性：{ok_nonempty}/{total}")
    print(f"判定 3 注入可检出：{ok_inject}/{total}")

    good = ok_consist == total and ok_nonempty == total and ok_inject == total and total > 0
    if good:
        print("\n✅ 长历史 PIT 通过：截断一致 + 有实质比较 + 注入的未来函数全部被检出")
        print("   ⇒ 长历史口径的回测结果可以采信（至少就未来函数而言）")
        return 0
    print("\n❌ 未通过：上述三项必须全过，否则『一致』这个结论本身不可信")
    return 1


if __name__ == "__main__":
    sys.exit(main())
