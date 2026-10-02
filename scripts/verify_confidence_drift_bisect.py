#!/usr/bin/env python3
"""定位置信度前视残留的**元凶**：逐个冻结助手函数，看谁能消掉偏差。

思路（不靠读代码猜，也不靠猜函数签名）
------------------------------------
先把跑分所用的每个助手函数调用一次（在"短序列"语境下）拿到它的返回值，
然后把这个助手**冻结**成"永远返回那个值"。此时若再比较"短序列 vs 长序列"
的置信度，偏差应该变小或归零 —— 被冻结的那个助手就是（或参与了）前视来源。

这是标准的因果二分：不需要知道每个函数的参数怎么传，只需要能观察到结果。

用法：.venv/bin/python scripts/verify_confidence_drift_bisect.py
"""

from __future__ import annotations

import ast
import copy
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from easy_tdx.chanlun import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun import mmd_conditions as MC  # noqa: E402
from easy_tdx.chanlun.mmd_conditions import _calc_confidence_v47  # noqa: E402

SHORT, LONG = 400, 500
CAP = 250
AGGREGATORS = {"_calc_confidence", "_calc_confidence_v47", "_calc_mmd_quality"}


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


def _maker(n: int):
    """返回 (result, arrays)，arrays 供 _calc_confidence_v47 使用。"""
    r = ChanlunAnalyser(code="000001", frequency="daily").process_klines(_bars(n))
    df = _bars(n)
    arrays = {
        "closes": df["close"].tolist(),
        "highs": df["high"].tolist(),
        "lows": df["low"].tolist(),
        "volumes": df["vol"].tolist(),
        "zss": r.zss,
    }
    return r, arrays


def _conf(mmd, arrays) -> float:
    return _calc_confidence_v47(
        mmd, 0.5, arrays["volumes"], arrays["closes"], None, 0.02,
        arrays["zss"], arrays["highs"], arrays["lows"],
    )


def _helpers() -> list[str]:
    """从三个汇总函数的源码里提取它们调用的助手名（即真正接线的那些）。"""
    src = (ROOT / "src" / "easy_tdx" / "chanlun" / "mmd_conditions.py").read_text()
    tree = ast.parse(src)
    names: set[str] = set()
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.name in AGGREGATORS:
            body = ast.get_source_segment(src, fn) or ""
            names.update(re.findall(r"(_(?:calc|check)_\w+)\s*\(", body))
    return sorted(names - AGGREGATORS)


def main() -> int:
    rs, As = _maker(SHORT)
    rl, Al = _maker(LONG)

    def pick(r):
        return {(m.mmd_type.value, m.bi.end.k.k_index): m
                for m in r.mmds if m.bi.end.k.k_index < CAP}

    short_m, long_m = pick(rs), pick(rl)
    common = sorted(set(short_m) & set(long_m))
    if not common:
        print("无可比信号")
        return 2

    def total_drift() -> float:
        """所有可比信号的偏差绝对值之和。"""
        return sum(
            abs(_conf(short_m[k], As) - _conf(short_m[k], Al)) for k in common
        )

    base = total_drift()
    print(f"可比信号 {len(common)} 个，基线总偏差 = {base:.4f}\n")
    print("逐个冻结助手后的总偏差（越小=消掉的越多）：\n")

    results = []
    for name in _helpers():
        original = getattr(MC, name, None)
        if original is None:
            continue

        # 记录该助手在"短序列 + 各信号"下的返回值，用作冻结值
        seen: list = []
        real = original

        def _spy(mmd, *a, __real=real, **kw):
            v = __real(mmd, *a, **kw)
            try:
                seen.append(copy.deepcopy(v))
            except Exception:
                seen.append(v)
            return v

        setattr(MC, name, _spy)
        try:
            for k in common:
                _conf(short_m[k], As)
        except Exception:
            setattr(MC, name, original)
            continue

        frozen = seen[-1] if seen else None

        def _frozen(*a, __v=frozen, **kw):
            try:
                return copy.deepcopy(__v)
            except Exception:
                return __v

        setattr(MC, name, _frozen)
        try:
            d = total_drift()
        except Exception:
            d = float("nan")
        finally:
            setattr(MC, name, original)  # 必须还原，避免污染后续
        results.append((name, d))

    results.sort(key=lambda x: (x[1] if x[1] == x[1] else 9e9))
    for name, d in results:
        if d != d:
            print(f"  (冻结后报错)  {name}")
            continue
        cut = base - d
        mark = "  ← 消掉大部分" if cut > base * 0.5 and base > 0 else ""
        print(f"  {d:.4f}  (消掉 {cut:+.4f})  {name}{mark}")

    print(f"\n基线 {base:.4f}。消掉最多者为前视主要来源。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
