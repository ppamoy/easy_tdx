#!/usr/bin/env python3
"""V733：1买 的正超额到底来自哪里？—— 归因检验。

问题
----
滚动验证显示 **1buy 是唯一 6/6 窗为正的类型**（60根 +3.01%，扣 0.2% 成本后
仍有 +2.81%）。但"1买"在缠论定义上就是**下跌背驰后的转折点**，也就是说它
天然出现在**一段下跌之后**。那么：

  Q-A1 它的超额，是不是只是**均值回复**（跌多了就反弹）？
       → 对照：在同一滚动窗内，找「过去 N 根跌幅 ≥ 该信号前跌幅」的普通
         bar 作基准。若 1buy 不再显著，说明它只是"跌多了"的代理变量。

  Q-A2 还是说它在**同等跌幅**的入场点里仍能选出更好的？
       → 若显著，则缠论结构确实提供了"跌多少"之外的增量信息。

这是决定「1buy 能否指导择时」的最后一关：如果只是均值回复，用户直接用
"跌 X% 就买"即可，不需要缠论。

做法（跌幅匹配基准，drawdown-matched）
--------------------------------------
对每个 1buy 信号 i（在窗 [lo,hi) 内）：
  1. 计算其"前跌" d_i = 1 - close[i] / max(close[i-L : i])  （L=20）
  2. 在窗内找所有满足 前跌 ≥ d_i 的 bar（且前瞻窗口不越界）
  3. 这些 bar 的前瞻收益均值 = 该信号的匹配基准
  4. 超额 = 信号收益 − 匹配基准

用法：  .venv/bin/python scripts/audit_1buy_attribution.py
"""

from __future__ import annotations

import json
import sys
from math import erfc, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402

DATA_DIR = ROOT / "audit_data"
HORIZONS = (5, 10, 20, 60)
N_WINDOWS = 6
DD_LOOKBACK = 20      # 计算"前跌"的回看窗口
MIN_N = 30
MIN_MATCH = 5         # 匹配基准至少要几个候选 bar


def norm_p(z: float) -> float:
    return float(erfc(abs(z) / sqrt(2)))


def drawdown_at(c: np.ndarray, i: int, lookback: int) -> float:
    """bar i 处相对前 lookback 根最高价的回撤（0~1）—— 买点的匹配量。"""
    lo = max(0, i - lookback)
    peak = c[lo : i + 1].max()
    return float(1.0 - c[i] / peak) if peak > 0 else 0.0


def runup_at(c: np.ndarray, i: int, lookback: int) -> float:
    """bar i 处相对前 lookback 根最低价的涨幅（0~1）—— 卖点的镜像匹配量。"""
    lo = max(0, i - lookback)
    trough = c[lo : i + 1].min()
    return float(c[i] / trough - 1.0) if trough > 0 else 0.0


def main() -> int:
    files = [p for p in sorted(DATA_DIR.glob("*.json"))
             if p.stem.split("_")[0] not in ("sh000300", "sh000001")]
    if not files:
        print(f"❌ {DATA_DIR} 无数据")
        return 2

    rows: list[dict] = []
    for p in files:
        code = p.stem.split("_")[0]
        df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
        df["datetime"] = pd.to_datetime(df["datetime"])
        c = df["close"].to_numpy(dtype=float)
        n = len(c)
        if n < 500:
            continue
        res = ChanlunAnalyser(code=code, frequency="daily", config=ChanlunConfig()).process_klines(df)
        usable = n - max(HORIZONS)
        edges = np.linspace(0, usable, N_WINDOWS + 1).astype(int)

        for m in res.mmds:
            if not m.bi:
                continue
            st = m.mmd_type.value.lower()
            if st not in ("1buy", "1sell", "3buy", "3sell"):
                continue
            i = m.bi.end.bar_index
            is_buy = "buy" in st
            w = int(np.searchsorted(edges[1:], i, side="right"))
            if w >= N_WINDOWS:
                continue
            lo, hi = int(edges[w]), int(edges[w + 1])
            # ⚠️ 自误报修正：第一版对买卖都用「回撤」匹配。对卖点而言，
            # 正确的镜像量是**涨幅**（run-up），不是回撤 —— 用回撤匹配卖点
            # 会选出「同样在跌」的 bar，对"做空/卖出"是**反向**筛选，
            # 于是基准变成 −3.01%、超额虚高到 +8.40%。改为按方向取镜像量。
            if is_buy:
                dd = drawdown_at(c, i, DD_LOOKBACK)
            else:
                dd = runup_at(c, i, DD_LOOKBACK)

            rec: dict = {"type": st, "dd": dd}
            for h in HORIZONS:
                if i + h >= n:
                    continue
                r = c[i + h] / c[i] - 1.0
                if not is_buy:
                    r = -r
                # 跌幅匹配基准：窗内"前跌 >= 该信号前跌"的 bar
                cand = []
                for j in range(max(DD_LOOKBACK, lo), min(hi, n - h)):
                    m_j = drawdown_at(c, j, DD_LOOKBACK) if is_buy else runup_at(c, j, DD_LOOKBACK)
                    if m_j >= dd:
                        cand.append(j)
                if len(cand) < MIN_MATCH:
                    continue
                cand_arr = np.array(cand, dtype=int)
                rr = c[cand_arr + h] / c[cand_arr] - 1.0
                if not is_buy:
                    rr = -rr
                rec[f"r{h}"] = float(r)
                rec[f"m{h}"] = float(np.mean(rr))
                rec[f"nm{h}"] = int(len(cand_arr))
            rows.append(rec)
        print(f"  {p.stem}")

    X = pd.DataFrame(rows)
    print(f"\n纳入信号 {len(X)}（基准 = 同窗内「前跌 ≥ 信号前跌」的 bar 均值）")

    print("\n" + "=" * 100)
    print("Q-A 跌幅匹配后的超额 —— 1买 是否只是「跌多了就反弹」？")
    print("=" * 100)
    print(f"{'类型':<7}{'窗口':>5}{'n':>6}{'信号':>10}{'跌幅匹配基准':>14}{'超额':>10}{'p':>9}  判定")
    print("-" * 100)

    for st in ("1buy", "1sell", "3buy", "3sell"):
        sub = X[X["type"] == st]
        if len(sub) < MIN_N:
            print(f"{st} 样本不足（{len(sub)}）")
            continue
        for h in HORIZONS:
            rc, mc = f"r{h}", f"m{h}"
            d = sub[[rc, mc]].dropna()
            if len(d) < MIN_N:
                continue
            diff = (d[rc] - d[mc]).to_numpy(dtype=float)
            excess = float(np.mean(diff))
            se = float(np.std(diff, ddof=1)) / sqrt(len(diff))
            p = norm_p(excess / se if se > 0 else 0.0)
            ok = p < 0.05 and excess > 0
            mark = "✅仍有增量" if ok else ("❌显著更差" if (p < 0.05 and excess < 0) else "—无差异（=均值回复）")
            print(f"{st:<7}{h:>5}{len(d):>6}{d[rc].mean():>10.3%}{d[mc].mean():>14.3%}"
                  f"{excess:>+10.2%}{p:>9.4f}  {mark}")

    # 参考：1买信号的"前跌"有多大（确认它确实发生在下跌后）
    print("\n" + "-" * 100)
    for st in ("1buy", "1sell", "3buy", "3sell"):
        sub = X[X["type"] == st]
        if len(sub):
            print(f"  {st} 触发时的前 {DD_LOOKBACK} 根回撤：中位 {sub['dd'].median():.2%}  "
                  f"均值 {sub['dd'].mean():.2%}")

    print("\n解读：若「超额」一栏不显著，说明 1买/1卖 的超额可被"
          "「同样跌幅就买」完全解释 —— 缠论结构没有提供增量信息。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
