#!/usr/bin/env python3
"""PIT 稳定性探针：历史买卖点的置信度，会不会因为"后来又来新数据"而变化？

背景
----
上一轮发现 `_check_post_signal_price_follow_through`（V47 后确认）用
`closes[-1]`（序列最后一根）给**历史**信号算调整量 —— 同一个信号随数据推进
会从 "通过(+0.04)" 变成 "失败(-0.05)"，即**前视**。

进一步扫描发现：`mmd_conditions.py` 里有 **101 个**「形参含 mmd 且函数体内
引用最新 bar（closes[-1] / len(closes)-1）」的函数。它们是否也是同一类缺陷，
不能靠读代码猜 —— 有些可能只用于实时语境（给"当前最新信号"打分，此时
closes[-1] 就是"现在"，合法）。

本探针用**实测**区分：把同一段行情分别截断到 N 根和 N+Δ 根，比较两侧都能识别
出的、**位置足够深**（结构稳定）的买卖点的置信度。若同一位置的置信度变了，
说明该打分依赖了它之后的数据 —— 即前视。

用法：.venv/bin/python scripts/verify_confidence_pit_stability.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd  # noqa: E402

from easy_tdx.chanlun import ChanlunAnalyser  # noqa: E402

TOTAL = 500
SHORT = 400  # 截断长度
DEEP_LIMIT = 250  # 只比较位置 < 250 的信号（结构已稳定区）


def _bars(n: int) -> pd.DataFrame:
    """确定性波动（无随机，保证两次运行结果可比）。"""
    base = pd.Timestamp("2024-01-01")
    rows = []
    for i in range(n):
        px = 10.0 + 2.0 * math.sin(i / 11.0) + 0.6 * math.sin(i / 3.0)
        o = px
        c = px + 0.05 * math.sin(i / 5.0)
        rows.append(
            {
                "datetime": (base + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
                "open": round(o, 4),
                "close": round(c, 4),
                "high": round(max(o, c) + 0.05, 4),
                "low": round(min(o, c) - 0.05, 4),
                "vol": 1000 + (i % 7) * 50,
                "amount": 10000.0,
            }
        )
    return pd.DataFrame(rows)


def _mmd_map(n: int) -> dict[tuple, float]:
    r = ChanlunAnalyser(code="000001", frequency="daily").process_klines(_bars(n))
    out = {}
    for m in r.mmds:
        idx = m.bi.end.k.k_index
        if idx < DEEP_LIMIT:
            out[(m.mmd_type.value, idx)] = m.confidence
    return out


def main() -> int:
    short_map = _mmd_map(SHORT)
    long_map = _mmd_map(TOTAL)

    common = sorted(set(short_map) & set(long_map))
    if not common:
        print("两侧没有共同的深历史信号，无法比较（数据/参数需调整）")
        return 2

    print(f"截断{SHORT}根: 深历史信号 {len(short_map)} 个（位置<{DEEP_LIMIT}）")
    print(f"全长{TOTAL}根: 深历史信号 {len(long_map)} 个")
    print(f"可比信号: {len(common)} 个\n")

    diff = []
    for key in common:
        a, b = short_map[key], long_map[key]
        if abs(a - b) > 1e-9:
            diff.append((key, a, b))

    if not diff:
        print(f"✅ 全部 {len(common)} 个深历史信号置信度一致 —— 无前视")
        return 0

    print(f"❌ {len(diff)}/{len(common)} 个深历史信号的置信度随新数据变化：\n")
    for (t, idx), a, b in diff[:15]:
        print(f"  {t:8s} idx={idx:4d}  {a:.4f} -> {b:.4f}  (Δ{b - a:+.4f})")
    if len(diff) > 15:
        print(f"  ... 另有 {len(diff) - 15} 个")
    print(
        "\n同一位置的买卖点，仅仅因为后面多来了一批数据就改了评分 —— "
        "说明打分函数引用了信号之后的数据（前视）。"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
