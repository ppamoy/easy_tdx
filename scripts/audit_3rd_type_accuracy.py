#!/usr/bin/env python3
"""3买/3卖 定位准确性验证（V731 审计）。

判据：缠论原文对第三类买卖点的定义是**结构位置唯一确定**的——

  3买 = 中枢形成后向上突破 ZG，其后**紧随的次级别回抽**不跌回 ZG，
        该回抽低点即 3买。
  3卖 = 中枢形成后向下跌破 ZD，其后**紧随的次级别反抽**不升破 ZD，
        该反抽高点即 3卖。

因此：一个「教科书式」3买样本，其 ground truth 回抽低点就是**突破笔之后
紧接着的那一个向下笔**的低点（前提是该笔不破 ZG）。模型若在**更晚**的某个
向下笔上标 3买（例如把后续另一段上涨后的回调当成回抽），即为定位错误——
会指向一个结构语义完全不同的点。

本脚本合成大量此类样本，统计：
  - 召回率：教科书 3买/3卖 是否被识别出来
  - 定位准确率：识别出的 3买/3卖 是否落在 ground-truth 回抽笔上

运行：  .venv/bin/python scripts/audit_3rd_type_accuracy.py
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta

import pandas as pd

sys.path.insert(0, "src")

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402


def _mk(bars) -> pd.DataFrame:
    rows = []
    dt = datetime(2024, 1, 2)
    for o, c, h, l in bars:
        rows.append({"datetime": dt, "open": o, "close": c, "high": h, "low": l, "vol": 1e6})
        dt += timedelta(days=1)
    return pd.DataFrame(rows)


def _seg(n, o, c, jitter=0.05):
    out = []
    for i in range(n):
        t0 = o + (c - o) * (i / n)
        t1 = o + (c - o) * ((i + 1) / n)
        lo, hi = min(t0, t1), max(t0, t1)
        out.append((t0, t1, hi + jitter, lo - jitter))
    return out


def build_3buy_case(rng: random.Random):
    """教科书 3买：前跌 → 箱体中枢 → 突破 ZG → 回抽不破 ZG → 续涨。

    返回 (bars, gt_pullback_low)。gt_pullback_low = 回抽笔的目标低点。
    """
    top = rng.uniform(16.0, 17.5)      # 箱体上沿附近
    bot = top - rng.uniform(1.2, 2.2)  # 箱体下沿
    bars: list = []
    bars += _seg(rng.randint(8, 14), top + 4, bot)          # 前期下跌
    # 中枢：3~4 段箱体震荡
    n_seg = rng.randint(3, 4)
    cur = bot
    for i in range(n_seg):
        tgt = top if i % 2 == 0 else bot + rng.uniform(0, 0.3)
        bars += _seg(rng.randint(5, 8), cur, tgt)
        cur = tgt
    # 突破笔：向上离开中枢，明显超过 top
    break_top = top + rng.uniform(1.5, 3.0)
    bars += _seg(rng.randint(8, 14), cur, break_top)
    # 回抽笔：不破 top（ZG≈top），ground truth 3买 低点
    gt_low = top + rng.uniform(0.3, 0.8)
    pull_n = rng.randint(5, 9)
    bars += _seg(pull_n, break_top, gt_low)
    # 后续续涨 + 收尾（模拟真实后续走势）
    bars += _seg(rng.randint(8, 14), gt_low, break_top + rng.uniform(1.5, 3.0))
    bars += _seg(rng.randint(5, 9), break_top + 1.5, break_top + rng.uniform(0.3, 1.0))
    return bars, gt_low


def build_3sell_case(rng: random.Random):
    """教科书 3卖：前涨 → 箱体中枢 → 跌破 ZD → 反抽不升破 ZD → 续跌。"""
    bot = rng.uniform(15.0, 16.5)
    top = bot + rng.uniform(1.2, 2.2)
    bars: list = []
    bars += _seg(rng.randint(8, 14), bot - 4, top)          # 前期上涨
    n_seg = rng.randint(3, 4)
    cur = top
    for i in range(n_seg):
        tgt = bot if i % 2 == 0 else top - rng.uniform(0, 0.3)
        bars += _seg(rng.randint(5, 8), cur, tgt)
        cur = tgt
    # 跌破笔
    break_bot = bot - rng.uniform(1.5, 3.0)
    bars += _seg(rng.randint(8, 14), cur, break_bot)
    # 反抽笔：不升破 bot（ZD≈bot），ground truth 3卖 高点
    gt_high = bot - rng.uniform(0.3, 0.8)
    bars += _seg(rng.randint(5, 9), break_bot, gt_high)
    bars += _seg(rng.randint(8, 14), gt_high, break_bot - rng.uniform(1.5, 3.0))
    bars += _seg(rng.randint(5, 9), break_bot - 1.5, break_bot - rng.uniform(0.3, 1.0))
    return bars, gt_high


def analyze(bars):
    res = ChanlunAnalyser(code="T", frequency="daily", config=ChanlunConfig()).process_klines(
        _mk(bars)
    )
    return res


def main() -> None:
    rng = random.Random(20261001)
    n = 40
    tol = 0.35  # 价格容差：回抽低点可能因分型取极值而略有出入

    for label, builder, want, key in (
        ("3买", build_3buy_case, "3buy", "low"),
        ("3卖", build_3sell_case, "3sell", "high"),
    ):
        found = 0
        correct = 0
        missed_detail = []
        for _ in range(n):
            bars, gt = builder(rng)
            res = analyze(bars)
            hits = [m for m in res.mmds if m.mmd_type.value == want]
            if not hits:
                missed_detail.append(("未识别", round(gt, 2)))
                continue
            found += 1
            # 取最接近 gt 的那个命中，判断定位是否准确
            vals = [round(m.bi.end.val, 2) for m in hits]
            best = min(vals, key=lambda v: abs(v - gt))
            if abs(best - gt) <= tol:
                correct += 1
            else:
                missed_detail.append((f"定位偏: {vals}", round(gt, 2)))

        print(f"\n{'=' * 66}")
        print(f"【{label}】样本 {n} 个")
        print(f"  召回率(识别出{label})     : {found}/{n} = {found / n:.0%}")
        print(f"  定位准确率(落在真回抽点) : {correct}/{n} = {correct / n:.0%}")
        if missed_detail:
            print(f"  失败样本（前 6 个）:")
            for d, g in missed_detail[:6]:
                print(f"    - gt={g}  {d}")

    print(f"\n{'=' * 66}")
    print("判据：原文 3买/3卖 是唯一确定的结构位置。")
    print("召回率<100% = 漏掉真实信号；定位准确率<100% = 标在了错误的结构点上。")


if __name__ == "__main__":
    main()
