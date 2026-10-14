#!/usr/bin/env python3
"""process_klines_cross_timeframe 索引口径错位 —— 复现与量化脚本（V850）。

## 缺陷

`analyser.py: process_klines_cross_timeframe` 的做法是：

    1. lower.process_klines(lower_tf_df) → lower_xds     # 30min 线段
    2. cross_zss = find_zss(lower_xds)                    # 用 30min 线段构中枢
    3. result = self.process_klines(daily_df)             # 日线笔 bis
    4. find_mmds_v44(bis, cross_zss, ...)                 # ← 日线笔 + 30min中枢

`find_zss(lower_xds)` 产出的 `ZS.lines` 是**30min 线段对象**，其 `.index` 是
**30min 线段序列内的序号**（0,1,2,…）。

而 `mmd.py` 的 3买/3卖逻辑把这些 index 当**日线笔序号**用：

    mmd.py:2874   next_first_bi_idx_map[z.index] = z2.lines[0].index
    mmd.py:2928   last_idx = zs.lines[-1].index
    mmd.py:3124   bis[last_idx + 1]            # ← 拿 30min 线段序号当日线笔下标
    mmd.py:3125   retest_bi = bis[last_idx + 1]
    mmd.py:3148   ...
    mmd.py:3356/3477/3686  同类

⇒ 30min 线段序号（通常远小于日线笔序号）被当作日线笔下标，
   `bis[last_idx+1]` 取到的是**错误的笔**，回试段完全错位。

## 预期（已由前一轮 7 只标的扫描确认）

    默认          28 中枢 / 19 信号
    次级别路径     20 中枢 /  4 信号  (-79%)

## 本脚本职责

把「错位」从推断变成**逐条可复现的证据**：
1. 打印 30min 线段序号 vs 日线笔序号的实际分布（证明两者不同尺度）；
2. 逐个中枢打印 `zs.lines[-1].index` 与 `bis` 的长度、以及
   `bis[zs.lines[-1].index + 1]` 实际取到哪一笔；
3. 证明取到的笔与 30min 线段在**时间上不相关**（日期差）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402

DAILY_DIR = ROOT / "audit_data"
LOWER_DIR = ROOT / "audit_data" / "kline_30min"


def load_pair(code: str):
    dp = DAILY_DIR / f"{code}_daily.json"
    lp = LOWER_DIR / f"{code}_30min.json"
    if not dp.exists() or not lp.exists():
        return None
    d = pd.DataFrame(json.loads(dp.read_text(encoding="utf-8")))
    l = pd.DataFrame(json.loads(lp.read_text(encoding="utf-8")))
    d["datetime"] = pd.to_datetime(d["datetime"])
    l["datetime"] = pd.to_datetime(l["datetime"])
    return d, l


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=3)
    args = ap.parse_args()

    codes = sorted(p.stem.split("_")[0] for p in LOWER_DIR.glob("*_30min.json"))
    codes = [c for c in codes if load_pair(c) is not None][: args.limit]

    print("process_klines_cross_timeframe 索引口径错位复现（V850）", flush=True)
    print(f"标的: {codes}\n", flush=True)

    for code in codes:
        d, l = load_pair(code)
        cfg = ChanlunConfig()

        # ── 默认路径（日线笔构中枢）──────────────────────────────
        a1 = ChanlunAnalyser(code=code, frequency="daily", config=cfg)
        r1 = a1.process_klines(d)
        n_zs1 = len(r1.zss)
        n_sig1 = len(r1.mmds)

        # ── 次级别路径 ────────────────────────────────────────────
        a2 = ChanlunAnalyser(code=code, frequency="daily", config=cfg)
        r2 = a2.process_klines_cross_timeframe(d, l)
        n_zs2 = len(r2.zss)
        n_sig2 = len(r2.mmds)

        bis = r2.bis
        cross_zss = r2.zss

        print(f"【{code}】日线笔={len(bis)} 条, 30min线段={len(r2.xds_l1)} 条", flush=True)
        print(
            f"  默认: {n_zs1} 中枢 / {n_sig1} 信号   "
            f"次级别: {n_zs2} 中枢 / {n_sig2} 信号",
            flush=True,
        )

        # 证明 cross_zss.lines 是 30min 线段，其 index 与 bis 下标不同尺度
        if cross_zss and bis:
            for zs in cross_zss[:3]:
                if not zs.lines:
                    continue
                li = zs.lines[-1].index
                print(
                    f"    中枢#{zs.index}: lines={len(zs.lines)} "
                    f"末段(30min线段)#{li}  "
                    f"→ bis[{li}+1] = 日线笔#{min(li + 1, len(bis) - 1)}",
                    flush=True,
                )
                # 时间相关性证明
                seg_date = zs.lines[-1].end.k.date
                idx = li + 1
                if 0 <= idx < len(bis):
                    bi = bis[idx]
                    delta = abs((bi.end.k.date - seg_date).days)
                    print(
                        f"      30min线段末段结束 {seg_date.date()}  vs  "
                        f"日线笔#{idx} 结束 {bi.end.k.date.date()}  "
                        f"(相差 {delta} 天)",
                        flush=True,
                    )
        print(flush=True)

    print(
        "结论：若上表「相差 N 天」普遍为数十天且量级接近整段行情，"
        "则证明 bis[last_idx+1] 取错笔。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
