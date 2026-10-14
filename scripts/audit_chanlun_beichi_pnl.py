#!/usr/bin/env python3
"""扣成本对照回测：1买/1卖 的「笔背驰」（当前）vs「趋势背驰」（原文口径）。

背景（docs/CHANLUN_FIDELITY_AUDIT_V734.md §4）：
  `_is_strong_beichi` 的**笔背驰分支先跑且不要求任何中枢**，命中即 return True
  ⇒ 零中枢/单中枢也能出 1买。而代码注释自己写着「一买/一卖 只认趋势背驰」。
  实测（8 只日线 / 446 次调用）：笔背驰命中 107、趋势背驰命中 **0**
  ⇒ 现在的 1买/1卖 **全部**来自笔背驰。

  但 1sell 的既有实测是 82.9% 胜率 / +18.59%（docs/CHANLUN_CAN_IT_MAKE_MONEY.md），
  那批正是"不合规"的笔背驰版本 ⇒ **"更合原文"与"更赚钱"可能冲突**。
  本脚本就是为了判这个冲突。

改法：把笔背驰分支整体短路（for 范围置空），只留趋势背驰分支。
⚠️ 用**行号**定位（`for j in range(bi_idx - 1, -1, -1):` 在文件里有 2 处，
另一处属于 `_get_beichi_strength`，误改会污染对照 —— 见 docs §6 教训 2）。

用法：  .venv/bin/python scripts/audit_chanlun_beichi_pnl.py --limit 30
"""

from __future__ import annotations

import argparse
import json
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from _concurrency import resolve_workers  # noqa: E402

DATA_DIR = ROOT / "audit_data"
EXCLUDE = {"sh000300", "sh000001"}
COMMISSION, STAMP, SLIPPAGE = 0.0003, 0.001, 0.002
ROUND_TRIP = COMMISSION * 2 + STAMP + SLIPPAGE * 2

# _is_strong_beichi 里笔背驰分支的 for 行（1-based，见 mmd_conditions.py）
BI_LOOP_LINE = 16514


def _build(strict_trend: bool) -> types.ModuleType:
    p = ROOT / "src/easy_tdx/chanlun/mmd_conditions.py"
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    i = BI_LOOP_LINE - 1
    if "for j in range(bi_idx - 1, -1, -1):" not in lines[i]:
        raise SystemExit(
            f"行号 {BI_LOOP_LINE} 已漂移（现为 {lines[i].strip()!r}），请重新定位"
        )
    if strict_trend:
        lines[i] = lines[i].replace("range(bi_idx - 1, -1, -1)", "range(0, 0)")
    name = f"mc_{'strict' if strict_trend else 'current'}"
    mod = types.ModuleType(name)
    mod.__file__ = "mmd_conditions.py"
    sys.modules[name] = mod
    exec(compile("".join(lines), "mmd_conditions.py", "exec"), mod.__dict__)
    return mod


def _pairs(code, strict_trend):
    from easy_tdx.backtest.engine import BacktestEngine
    from easy_tdx.backtest.strategies.chanlun_pair import ChanlunPairStrategy
    import easy_tdx.chanlun.mmd as M

    mod = _build(strict_trend)
    saved = M._is_strong_beichi
    M._is_strong_beichi = mod._is_strong_beichi
    try:
        df = pd.DataFrame(json.loads((DATA_DIR / f"{code}_daily.json").read_text(encoding="utf-8")))
        df["datetime"] = pd.to_datetime(df["datetime"])
        s = ChanlunPairStrategy()
        BacktestEngine(s, cash=100000.0, commission=COMMISSION,
                       stamp_tax=STAMP, slippage=SLIPPAGE).run(df)
        return list(s.pair_log)
    finally:
        M._is_strong_beichi = saved


def _star(t):
    return _pairs(*t)


def _report(pairs, label):
    d = pd.DataFrame(pairs)
    if d.empty:
        return {"口径": label, "笔数": 0}
    net = d["pnl_pct"] - ROUND_TRIP * 100
    out = {
        "口径": label,
        "总笔数": len(d),
        "总胜率%": round(float((d["pnl_pct"] > 0).mean() * 100), 2),
        "总扣成本均%": round(float(net.mean()), 3),
    }
    for t in ("1buy", "1sell"):
        g = d[d["entry_type"] == t]
        if len(g):
            gn = g["pnl_pct"] - ROUND_TRIP * 100
            out[f"{t}_n"] = len(g)
            out[f"{t}_胜率%"] = round(float((g["pnl_pct"] > 0).mean() * 100), 1)
            out[f"{t}_扣成本%"] = round(float(gn.mean()), 2)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args()
    workers = resolve_workers(args.workers)
    codes = sorted(
        p.name[: -len("_daily.json")]
        for p in DATA_DIR.glob("*_daily.json")
        if p.name[: -len("_daily.json")] not in EXCLUDE
    )[: args.limit]
    print(f"样本 {len(codes)} 只 | 往返成本约 {ROUND_TRIP*100:.2f}%")

    from concurrent.futures import ProcessPoolExecutor
    rows = []
    for strict, label in ((False, "当前_笔背驰"), (True, "原文_只趋势背驰")):
        allp = []
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for r in ex.map(_star, [(c, strict) for c in codes]):
                if r:
                    allp.extend(r)
        rows.append(_report(allp, label))
        print(f"  {label}: {len(allp)} 笔", flush=True)

    print("\n" + "=" * 76)
    print(pd.DataFrame(rows).to_string(index=False))
    print("=" * 76)
    print("\n⚠️ 若「原文_只趋势背驰」笔数骤降但扣成本均%没有明显更好，")
    print("   则不应改（会丢信号又没多赚）；只有明显更好才值得改。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
