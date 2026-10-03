#!/usr/bin/env python3
"""V733：缠论 vs **经典技术指标策略**（用户真正会拿来对比的东西）

为什么做这个
------------
前面测的基准都是"随机"或"买入持有"，而用户真正会拿来对比的是
**双均线 / MACD / RSI / 布林带**这些教科书策略。缠论要是连它们都打不过，
"能否作为选股择时的帮手"就有了直接答案。

⚠️ 这次特意控制**暴露/beta**（上一轮的 t=0.71 就是被暴露混淆的）：
- 所有策略跑**同一批股票、同一段 K 线、同一套成本**（BacktestEngine 自带
  佣金/印花税/slippage/next_open）；
- 报**收益、夏普、跑赢买入持有比例、t 统计**，单看平均收益会被少数暴赚票带偏；
- 排名同时给**夏普**和**跑赢比例**，两者不一致就说明是运气成分。

⚠️ 局限（写清楚，不夸大）：
- 缠论参数取**默认值（未调优）**；经典策略同样取**默认参数**；
  这对缠论略有利（没调参就赢了才是真赢），但也可能因为缠论默认值不佳而不利；
- 单市场、���线、n 有限，不做 beta/市值中性化；
- 不做样本外切分（本轮只做横截面对比，不宣称是样本外结论）。

用法：
    .venv/bin/python scripts/audit_chanlun_vs_classic.py
    .venv/bin/python scripts/audit_chanlun_vs_classic.py --limit 30

退出码：0 = 跑完；2 = 环境不可用。
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from easy_tdx.backtest.engine import BacktestEngine  # noqa: E402
from easy_tdx.backtest.strategies.builtin import (  # noqa: E402
    AdxTrendStrategy, AtrBreakoutStrategy, BbiStrategy, BiasReversalStrategy,
    BollBreakoutStrategy, CciStrategy, DmiStrategy, DonchianStrategy,
    DpoStrategy, EmaCrossStrategy, EmvStrategy, FslStrategy,
    KdjCrossStrategy, KeltnerStrategy, MaCrossStrategy, MacdStrategy,
    ObvBreakoutStrategy, RsiDivergenceStrategy, RsiReversalStrategy,
    SuperTrendStrategy, TripleMaStrategy, TrixStrategy,
    VolumeBreakoutStrategy, WrReversalStrategy,
)
from easy_tdx.backtest.strategies.chanlun import ChanlunStrategy  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "audit_data"
EXCLUDE = {"sh000300", "sh000001"}

# 经典策略全集（全部取默认参数）
CLASSIC = [
    ("双均线", MaCrossStrategy), ("MACD", MacdStrategy),
    ("EMA双线", EmaCrossStrategy), ("三均线", TripleMaStrategy),
    ("布林突破", BollBreakoutStrategy), ("RSI反转", RsiReversalStrategy),
    ("RSI背离", RsiDivergenceStrategy), ("KDJ", KdjCrossStrategy),
    ("ADX趋势", AdxTrendStrategy), ("ATR突破", AtrBreakoutStrategy),
    ("BBI", BbiStrategy), ("乖离反转", BiasReversalStrategy),
    ("CCI", CciStrategy), ("DMI", DmiStrategy), ("唐奇安", DonchianStrategy),
    ("DPO", DpoStrategy), ("EMV", EmvStrategy), ("FSL", FslStrategy),
    ("肯特纳", KeltnerStrategy), ("OBV突破", ObvBreakoutStrategy),
    ("超级趋势", SuperTrendStrategy), ("TRIX", TrixStrategy),
    ("量能突破", VolumeBreakoutStrategy), ("威廉反转", WrReversalStrategy),
]


def load(fs: list[Path]) -> list[pd.DataFrame]:
    out = []
    for p in fs:
        try:
            df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
            df["datetime"] = pd.to_datetime(df["datetime"])
            if len(df) > 200:
                out.append(df)
        except Exception:
            continue
    return out


def backtest(cls, dfs: list[pd.DataFrame]) -> tuple | None:
    """**一次**回测同时取收益与夏普。

    ⚠️ 早期版本只返回"成功跑出"的那部分收益，却拿去和**全样本**买入持有
    逐元素相减 → 30 只里只有 3 只成功时报
    `ValueError: operands could not be broadcast (3,) (30,)`。
    现在按**同一个 index 子集**取买入持有，保证一一对应。
    """
    rows: list[tuple[int, float, float]] = []
    for i, df in enumerate(dfs):
        try:
            r = BacktestEngine(cls(), cash=100000.0).run(df)
            rows.append((i, float(r.performance["total_return"]),
                         float(r.performance["sharpe"])))
        except Exception:
            continue
    if len(rows) < 3:
        return None
    idx = np.array([r[0] for r in rows])
    return (np.array([r[1] for r in rows]), idx,
            float(np.mean([r[2] for r in rows])))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20)
    a = ap.parse_args()
    fs = [p for p in sorted(DATA.glob("*.json"))
          if p.stem.split("_")[0] not in EXCLUDE]
    if a.limit:
        fs = fs[: a.limit]
    if not fs:
        print("❌ 无 audit_data，先跑 audit_fetch_real_data.py")
        return 2
    dfs = load(fs)
    print(f"缠论 vs 经典策略 —— {len(dfs)} 只 A 股日线，全部默认参数，"
          f"同成本模型（BacktestEngine 含佣金/印花税/slippage/next_open）")
    print("=" * 96)

    bh = np.array([float(d["close"].iloc[-1] / d["close"].iloc[0] - 1)
                   for d in dfs])
    rows: list[tuple] = []
    for label, cls in [("【缠论】", ChanlunStrategy)] + CLASSIC:
        res = backtest(cls, dfs)
        if res is None:
            rows.append((label, None))
            continue
        r, idx, sh = res
        d = r - bh[idx]          # ← 关键：只和同一子集的买持比
        t = (float(d.mean() / d.std() * np.sqrt(len(d)))
             if d.std() > 0 else float("nan"))
        rows.append((label, (r.mean(), sh,
                             (r > bh[idx]).mean() * 100, t, len(r))))

    rows_sorted = sorted(
        [x for x in rows if x[1] is not None],
        key=lambda x: x[1][0], reverse=True)
    rank = {lab: i + 1 for i, (lab, _) in enumerate(rows_sorted)}

    print(f"{'排名':<5}{'策略':<12}{'平均收益':>10}{'夏普':>8}"
          f"{'跑赢买持':>10}{'t(超额)':>10}")
    print("-" * 60)
    for lab, v in rows_sorted:
        m, sh, win, t, n = v
        print(f"{rank[lab]:<5}{lab:<12}{m*100:>9.2f}%{sh:>8.2f}"
              f"{win:>9.0f}%{t:>10.2f}")
    miss = [lab for lab, v in rows if v is None]
    if miss:
        print(f"\n（未跑出结果: {' '.join(miss)}）")
    print(f"\n买入持有平均 {bh.mean()*100:+.2f}%  n={len(bh)}")

    ch = rank.get("【缠论】")
    print("\n" + "=" * 96)
    if ch is None:
        print("❌ 缠论未跑出结果")
        return 0
    print(f"缠论在 {len(rows_sorted)} 个策略中排第 {ch}"
          f"（1=最好，共 {len(rows_sorted)} 个）")
    top = rows_sorted[:3]
    print("前三名：" + "、".join(f"{l}({v[0]*100:+.1f}%)" for l, v in top))
    chv = dict((l, v) for l, v in rows_sorted)["【缠论】"]
    print(f"\n缠论：平均 {chv[0]*100:+.2f}%、夏普 {chv[1]:+.2f}、"
          f"跑赢买持 {chv[2]:.0f}%、超额 t={chv[3]:+.2f}")
    if abs(chv[3]) < 2:
        print("⇒ 缠论相对买入持有的超额**统计上不显著**。")
    print("\n⚠️ 局限：单市场日线、n 有限、未 beta/市值中性化；")
    print("   全部取默认参数（缠论未调优是优势，但也可能是其默认值不佳）；")
    print("   本轮为横截面对比，**不是**样本外结论。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
