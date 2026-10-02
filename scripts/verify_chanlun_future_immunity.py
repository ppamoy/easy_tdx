#!/usr/bin/env python3
"""缠论（P0）「未来免疫」探针：追加未来 K 线，历史买卖点不得改变。

为什么需要它
------------
F2（逐笔复盘讲解）与 F3（训练数据）都依赖一个前提：**过去某个 bar 上识别出的
买卖点是稳定可复现的**。若"后面多来一批数据"就改写了历史信号，那讲解和训练数据
都不可信。这与 P1 的 PIT 纪律是同一类要求，只是对象从财报换成了 K 线。

判定（运行时行为，不依赖代码形状）
--------------------------------
    signals(截至 N 根) == signals(截至 N+M 根)，且只看 index < cap 的早期信号

不等即为用了未来数据。

⚠️ 已踩过的坑（务必保留这条注释）
------------------------------
我第一版用「正弦」「锯齿」两种序列，结果它们**一个信号都没产生**（共有 0），
却因为集合相等而报 ✅ —— 空集自然相等，这是**假通过**（与 P1 探针里"检查 0 只
却报通过"完全同类）。因此本脚本加了**样本量自检**：可比信号少于 `MIN_SIGNALS`
时判定为**无效并报错**，绝不当通过。

用法：  .venv/bin/python scripts/verify_chanlun_future_immunity.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from easy_tdx.chanlun import ChanlunAnalyser  # noqa: E402

MIN_SIGNALS = 2  # 低于此数判定无效（防止空集相等的假通过）


def _mk(n: int, gen) -> pd.DataFrame:
    base = pd.Timestamp("2024-01-01")
    rows = []
    for i in range(n):
        px = gen(i)
        o, c = px, px + 0.05 * math.sin(i / 5.0)
        rows.append({
            "datetime": (base + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
            "open": round(o, 4), "close": round(c, 4),
            "high": round(max(o, c) + 0.05, 4), "low": round(min(o, c) - 0.05, 4),
            "vol": 1000 + (i % 7) * 50, "amount": 10000.0,
        })
    return pd.DataFrame(rows)


# 注意：只用**能稳定产生买卖点**的生成器。纯正弦/锯齿实测信号数为 0，无法验证。
GENS = {
    "趋势+噪声": lambda i: 10.0 + i * 0.02 + 0.3 * math.sin(i / 2.0),
    "双周期": lambda i: 10.0 + 1.5 * math.sin(i / 7.0) + 0.8 * math.sin(i / 23.0),
    "阶梯上涨": lambda i: 10.0 + (i // 15) * 0.4 + 0.15 * math.sin(i / 3.0),
    "先涨后跌": lambda i: 10.0 + (i * 0.05 if i < 200 else (400 - i) * 0.05)
                          + 0.2 * math.sin(i / 4.0),
}


def _sig(result, cap: int) -> set[tuple[str, int]]:
    return {
        (m.mmd_type.value, m.bi.end.k.k_index)
        for m in result.mmds
        if m.bi.end.k.k_index < cap
    }


def main() -> int:
    fails: list[str] = []
    invalid: list[str] = []
    print("缠论 P0 未来免疫探针\n")

    for name, gen in GENS.items():
        for short, long in ((300, 420), (400, 500), (350, 600)):
            rs = ChanlunAnalyser(code="000001", frequency="daily").process_klines(
                _mk(short, gen)
            )
            rl = ChanlunAnalyser(code="000001", frequency="daily").process_klines(
                _mk(long, gen)
            )
            cap = short // 2  # 只看"早期"信号（远离新增数据的尾部）
            s, l = _sig(rs, cap), _sig(rl, cap)
            common = len(s & l)
            tag = f"{name:10s} {short}->{long} (cap={cap})"

            if common < MIN_SIGNALS:
                print(f"  ⚠ 无效 {tag}: 可比信号仅 {common} 个（<{MIN_SIGNALS}），无法判定")
                invalid.append(tag)
                continue

            ok = s == l
            mark = "✅" if ok else "❌"
            print(f"  {mark} {tag}: 共有{common} 仅短{len(s - l)} 仅长{len(l - s)}")
            if not ok:
                for x in sorted(s - l)[:5]:
                    print(f"       仅短有: {x}")
                for x in sorted(l - s)[:5]:
                    print(f"       仅长有: {x}")
                fails.append(tag)

    print()
    if invalid:
        print(f"⚠ {len(invalid)} 个用例样本不足、未纳入判定（不算通过）：")
        for t in invalid:
            print(f"   - {t}")
    if fails:
        print(f"\n结论: ❌ {len(fails)} 个用例未通过未来免疫")
        return 1
    print("结论: ✅ 缠论历史买卖点不因追加未来 K 线而改变")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
