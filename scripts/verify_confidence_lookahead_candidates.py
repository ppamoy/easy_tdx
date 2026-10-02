#!/usr/bin/env python3
"""定位：到底是哪些打分函数让历史买卖点的评分依赖未来数据？

``verify_confidence_pit_stability.py`` 证明了现象（8/8 个深历史信号置信度随
新数据变化）。本脚本定位**元凶**：逐个调用那些「形参含 mmd」的候选函数，
分别在「截断序列」和「加长序列」上调用，比较返回值差异。只对 latter 敏感
（即引用了信号之后的数据）的函数会被点名。

用法：.venv/bin/python scripts/verify_confidence_lookahead_candidates.py
"""

from __future__ import annotations

import inspect
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd  # noqa: E402

from easy_tdx.chanlun import ChanlunAnalyser, mmd_conditions as MC  # noqa: E402

SHORT, LONG = 400, 500
SIGNAL_IDX_CAP = 250


def _bars(n: int) -> pd.DataFrame:
    base = pd.Timestamp("2024-01-01")
    rows = []
    for i in range(n):
        px = 10.0 + 2.0 * math.sin(i / 11.0) + 0.6 * math.sin(i / 3.0)
        o, c = px, px + 0.05 * math.sin(i / 5.0)
        rows.append({
            "datetime": (base + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
            "open": round(o, 4), "close": round(c, 4),
            "high": round(max(o, c) + 0.05, 4), "low": round(min(o, c) - 0.05, 4),
            "vol": 1000 + (i % 7) * 50, "amount": 10000.0,
        })
    return pd.DataFrame(rows)


def _run(n: int):
    return ChanlunAnalyser(code="000001", frequency="daily").process_klines(_bars(n))


def _signature(obj) -> str:
    """把返回值压成可比较的字符串（float 保留 4 位，容忍浮点噪声）。"""
    if isinstance(obj, dict):
        return "{" + ", ".join(
            f"{k}:{_signature(v)}" for k, v in sorted(obj.items(), key=lambda x: str(x[0]))
        ) + "}"
    if isinstance(obj, (list, tuple)):
        return "[" + ", ".join(_signature(v) for v in obj) + "]"
    if isinstance(obj, float):
        return f"{obj:.4f}"
    return repr(obj)


def _arrays(n: int, r):
    df = _bars(n)
    return {
        "closes": df["close"].tolist(),
        "highs": df["high"].tolist(),
        "lows": df["low"].tolist(),
        "volumes": df["vol"].tolist(),
        "zss": r.zss,
    }


def main() -> int:
    rs, rl = _run(SHORT), _run(LONG)
    short_m = {(m.mmd_type.value, m.bi.end.k.k_index): m for m in rs.mmds
               if m.bi.end.k.k_index < SIGNAL_IDX_CAP}
    long_m = {(m.mmd_type.value, m.bi.end.k.k_index): m for m in rl.mmds
              if m.bi.end.k.k_index < SIGNAL_IDX_CAP}
    common = sorted(set(short_m) & set(long_m))
    if not common:
        print("无可比信号")
        return 2
    key = common[0]
    ms, ml = short_m[key], long_m[key]
    print(f"探针信号: {key[0]} idx={key[1]}（两侧都存在且位置 < {SIGNAL_IDX_CAP}）\n")

    As, Al = _arrays(SHORT, rs), _arrays(LONG, rl)

    suspects = []
    for name, fn in inspect.getmembers(MC, inspect.isfunction):
        if not name.startswith("_calc") and not name.startswith("_check"):
            continue
        params = list(inspect.signature(fn).parameters)
        if not params or params[0] != "mmd":
            continue
        named = set(params)
        def _call(mmd, A):
            kw = {}
            for want, val in (("closes", A["closes"]), ("highs", A["highs"]),
                              ("lows", A["lows"]), ("volumes", A["volumes"]),
                              ("zss", A["zss"])):
                if want in named:
                    kw[want] = val
            return fn(mmd, **kw)
        try:
            a = _call(ms, As)
            b = _call(ml, Al)
        except Exception:
            continue  # 需要其它必需参数的函数跳过（不猜，宁可不报）
        if _signature(a) != _signature(b):
            suspects.append((name, _signature(a)[:70], _signature(b)[:70]))

    print(f"候选函数里，**在 {'截断'} vs {'加长'} 上返回值不同**的（= 引用了信号之后的数据）：")
    if not suspects:
        print("  （无）")
        return 0
    for n, a, b in suspects:
        print(f"  ❌ {n}")
        print(f"       截断={a}")
        print(f"       加长={b}")
    print(f"\n共 {len(suspects)} 个。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
