#!/usr/bin/env python3
"""多级别/区间套方案的**样本外**验证 —— 防"挑出来的超额"。

## 为什么必须做
方案矩阵跑完会挑出"最优方案"，那个超额很可能是**多重比较挑出来的**。
必须在**没参与挑选**的时间段上再验一次才可信。

## 设计（用同一份预计算缓存，按时间切段）
30min 数据覆盖 2024-09 ~ 2026-10（约 2 年），按时间切：
  - **样本内** = 前半段（用来挑方案）
  - **样本外** = 后半段（**未参与挑选**，只验样本内选出的方案）

关键：**切段在"信号消费"层做，不在"信号计算"层做** —— 复用同一份缓存结构，
只把落在窗口外的信号丢掉。这与"截断数据重算"不等价（重算会改笔的确认状态），
但消费层截窗是**更保守**的：保留全量算出的结构、只不消费窗口外信号，
等价于"回测只跑到那个时间点就停"。

⚠️ 诚实前提：2 年数据做样本外很勉强（理想应跨完整牛熊）。
本脚本结论**只作为参考**，不能替代更长时间的验证。

用法：  .venv/bin/python scripts/audit_chanlun_ml_oos.py --limit 40
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from _concurrency import resolve_workers  # noqa: E402
from _ml_precompute import load_pair  # noqa: E402
from easy_tdx.backtest.engine import BacktestEngine  # noqa: E402
from easy_tdx.backtest.strategies.chanlun_ml import ChanlunMLStrategy  # noqa: E402
from easy_tdx.backtest.strategies.chanlun_pair import ChanlunPairStrategy  # noqa: E402

CACHE = ROOT / "audit_cache"
SLIP = 0.002

PLANS: list[tuple[str, dict]] = [
    ("B1 本3买→次1卖", {"entry_types": "3buy", "exit_types": "1sell",
                        "fallback_exit_types": "", "max_hold_bars": 120}),
    ("B2 本全买→次1卖", {"entry_types": "1buy,2buy,3buy", "exit_types": "1sell",
                         "fallback_exit_types": "", "max_hold_bars": 120}),
    ("B3 本3买→次全卖", {"entry_types": "3buy", "exit_types": "1sell,2sell,3sell",
                         "fallback_exit_types": "", "max_hold_bars": 120}),
    ("B4 本全买→次全卖", {"entry_types": "1buy,2buy,3buy",
                          "exit_types": "1sell,2sell,3sell",
                          "fallback_exit_types": "", "max_hold_bars": 120}),
    ("C1 本3买→次1卖+本1卖兜底", {"entry_types": "3buy", "exit_types": "1sell",
                                  "fallback_exit_types": "1sell", "max_hold_bars": 120}),
    ("D1 区间套+本全买→次1卖", {"entry_types": "1buy,2buy,3buy", "exit_types": "1sell",
                                "fallback_exit_types": "", "max_hold_bars": 120,
                                "sub_entry_scope": "nested"}),
    ("D2 区间套+本全买→次全卖", {"entry_types": "1buy,2buy,3buy",
                                 "exit_types": "1sell,2sell,3sell",
                                 "fallback_exit_types": "", "max_hold_bars": 120,
                                 "sub_entry_scope": "nested"}),
    ("E1 本1买→次1卖", {"entry_types": "1buy", "exit_types": "1sell",
                        "fallback_exit_types": "", "max_hold_bars": 120}),
    ("E2 本2买→次1卖", {"entry_types": "2buy", "exit_types": "1sell",
                        "fallback_exit_types": "", "max_hold_bars": 120}),
]


def _job(args: tuple[str, float, float]) -> dict[str, float]:
    """在 [start_frac, end_frac] 时间窗上跑所有方案（信号消费层截窗）。"""
    code, f0, f1 = args
    d, s = load_pair(code)
    if len(d) < 60:
        return {}
    p = CACHE / next((x.name for x in CACHE.glob(f"{code}_*.json")), "")
    if not p or not p.exists():
        return {}
    c = json.loads(p.read_text())

    n = len(d)
    i0, i1 = int(n * f0), int(n * f1)
    sub_d = d.iloc[i0:i1].reset_index(drop=True)
    if len(sub_d) < 40:
        return {}
    t0, t1 = sub_d["datetime"].iloc[0], sub_d["datetime"].iloc[-1]

    # 信号消费层截窗：只保留落在 [t0, t1] 的信号，bar 序号重映射到子窗口
    main = [(x["bar"] - i0, x["t"], x["c"], int(k))
            for k, x in enumerate(c["main"]) if i0 <= x["bar"] < i1]
    main_nested = {i: bool(c["main_nested"].get(str(mi), False))
                   for i, (_, _, _, mi) in enumerate(main)}
    sub = [(pd.Timestamp(x["dt"]), x["t"], x["c"])
           for x in c["sub"] if t0 <= pd.Timestamp(x["dt"]) <= t1]

    bh = float(sub_d["close"].iloc[-1] / sub_d["close"].iloc[0] - 1)
    out: dict[str, float] = {"__bh__": bh}

    # ⚠️ 同级别对照要跑两条口径（与 audit_chanlun_full_theory.py 一致）：
    #   A0 = 带前视守卫（默认，保守，进场晚 3 根）
    #   A1 = 无守卫（与多级别方案的信号时点同口径，公平对照）
    #   只拿 A0 当对照会**高估**多级别；只拿 A1 当对照则 A1 有轻微前视
    #   （PIT 扫描 100 组里 7 组不一致）。所以**两条都报**，看结论 Robust 与否。
    for tag, guard in (("A0 同级别对照", True), ("A1 同级别同口径(无守卫)", False)):
        st = ChanlunPairStrategy(lookahead_guard=guard)
        out[tag] = float(
            BacktestEngine(st, cash=100000.0, slippage=SLIP).run(sub_d).performance["total_return"])

    for name, kw in PLANS:
        try:
            m = ChanlunMLStrategy(**kw)
            m.set_data(sub_d, s)
            m.set_precomputed(
                main_signals=[(b, t, cf) for b, t, cf, _ in main],
                sub_signals=sub,
                main_nested=main_nested,
            )
            out[name] = float(
                BacktestEngine(m, cash=100000.0, slippage=SLIP).run(sub_d).performance["total_return"])
        except Exception:  # noqa: BLE001
            pass
    return out


def _report(tag: str, agg: dict[str, list]) -> dict[str, tuple[float, float]]:
    bh = np.array(agg.get("__bh__", []))
    print(f"\n── {tag}  n={len(bh)}  买入持有 {np.mean(bh)*100:+.2f}% ──")
    print("%-26s %9s %7s" % ("方案", "超额", "t"))
    res: dict[str, tuple[float, float]] = {}
    for name, _ in [("A0 同级别对照", {}), ("A1 同级别同口径(无守卫)", {})] + PLANS:
        v = np.array(agg.get(name, []))
        if len(v) == 0:
            continue
        m = min(len(v), len(bh))
        ex = v[:m] - bh[:m]
        t = (float(np.mean(ex) / np.std(ex, ddof=1) * np.sqrt(m))
             if m > 2 and np.std(ex, ddof=1) > 0 else float("nan"))
        res[name] = (float(np.mean(ex)), t)
        print("%-26s %+8.2f%% %7.2f" % (name, np.mean(ex) * 100, t))
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--workers", type=int, default=None)
    a = ap.parse_args()
    workers = resolve_workers(a.workers)
    codes = sorted({f.name.split("_")[0] for f in CACHE.glob("*_*.json")})
    codes = codes[:: a.step]
    if a.limit:
        codes = codes[: a.limit]
    print(f"样本 {len(codes)} 只   并行度 {workers}")
    print("切窗：样本内=前 50%，样本外=后 50%（信号消费层截窗）")

    from concurrent.futures import ProcessPoolExecutor
    ins: dict[str, list] = defaultdict(list)
    oos: dict[str, list] = defaultdict(list)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for o in ex.map(_job, [(c, 0.0, 0.5) for c in codes], chunksize=1):
            for k, v in o.items():
                ins[k].append(v)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for o in ex.map(_job, [(c, 0.5, 1.0) for c in codes], chunksize=1):
            for k, v in o.items():
                oos[k].append(v)

    r_in = _report("样本内（前50%，挑方案用）", ins)
    r_out = _report("样本外（后50%，未参与挑选）", oos)

    print("\n── 稳定性对照：样本内选出的方案，样本外还行吗 ──")
    print("%-26s %11s %11s %14s" % ("方案", "样本内超额", "样本外超额", "判定"))
    best = max(r_in.items(), key=lambda kv: kv[1][0]) if r_in else None
    for name in r_in:
        ein, _ = r_in[name]
        eout, tout = r_out.get(name, (float("nan"), float("nan")))
        if np.isnan(eout):
            print(f"{name:<26} {ein*100:+10.2f}% {'—':>11} {'—':>14}")
            continue
        if ein > 0 and eout > 0:
            ok = "✅同号且显著" if abs(tout) > 1.96 else "⚠️同号不显著"
        elif ein <= 0 and eout > 0:
            # 样本内为负、样本外为正 ⇒ 不是"策略稳定"，而是**两段市场不同**
            # （本例：样本内买入持有 +41.97% 大涨、样本外 −6.70% 回落，
            #   策略空仓/轻仓 ⇒ 样本内跑输、样本外跑赢）。
            # 这是**市场状态效应**，不是可迁移的选股能力，不能算通过。
            ok = "❌变号(市场状态效应)"
        elif ein > 0 and eout <= 0:
            ok = "❌样本外转负"
        else:
            ok = "❌两段皆为负"
        print(f"{name:<26} {ein*100:+10.2f}% {eout*100:+10.2f}% {ok:>14}")

    if best:
        print(f"\n样本内最优：{best[0]}（超额 {best[1][0]*100:+.2f}%，t={best[1][1]:+.2f}）")
        bo, bto = r_out.get(best[0], (float("nan"), float("nan")))
        passed = bo > 0 and abs(bto) > 1.96 and best[1][0] > 0
        print(f"  该方案样本外：{bo*100:+.2f}%（t={bto:+.2f}）"
              f"  {'✅ 通过样本外' if passed else '❌ 未通过样本外'}")
        if best[1][0] <= 0:
            print(f"  ⚠️ 样本内超额本身为负（{best[1][0]*100:+.2f}%）——"
                  f" '样本内最优'只是矮子里拔将军，谈样本外通过没有意义。")
            print("     本轮两段的买入持有差异极大（见上方两节标题），")
            print("     超额符号翻转主要反映**仓位/市场状态**，不是选股能力。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
