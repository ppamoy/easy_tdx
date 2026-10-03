#!/usr/bin/env python3
"""V733：缠论策略**端到端**能否跑赢买入持有？（默认参数，未调优）

为什么单独做这个
----------------
前面所有择时结论都是**信号层**的：单信号前瞻 N 根的超额 vs 同窗极值基准。
但用户真正关心的是"这套东西当**策略**用到底行不行"。本脚本补这一层。

⚠️ 这份脚本记录的**两次自我推翻**，比它的数字本身更重要：
  1. 我看到默认 `use_3buy/3sell=True`，而信号层测出 3买/3卖有害，
     直觉"该改成默认关"；实测关掉**反而更差** ⇒ 直觉错。
  2. 但"关掉更好"也不是真相：策略 vs 买入持有的超额 **t≈0.7 < 2**，
     不显著；"开着更好"多半只是暴露/beta 更大。⇒ **两个说法都不成立**。

所以本脚本的结论是：**没有证据支持改动默认值**，而不是"默认更好"。

用法：
    .venv/bin/python scripts/audit_strategy_vs_buyhold.py
    .venv/bin/python scripts/audit_strategy_vs_buyhold.py --limit 30

退出码：0 = 跑完（结论可能是"不显著"）；2 = 环境不可用。
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
from easy_tdx.backtest.strategies.chanlun import ChanlunStrategy  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "audit_data"
EXCLUDE = {"sh000300", "sh000001"}  # 指数不做个股择时


def files(limit: int) -> list[Path]:
    fs = [p for p in sorted(DATA.glob("*.json"))
          if p.stem.split("_")[0] not in EXCLUDE]
    return fs[:limit] if limit else fs


def run(fs: list[Path], **kw) -> tuple[np.ndarray, np.ndarray, int]:
    """返回 (策略总收益, 买入持有总收益, 平仓单数)。"""
    a: list[float] = []
    b: list[float] = []
    n_sell = 0
    for p in fs:
        try:
            df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
            df["datetime"] = pd.to_datetime(df["datetime"])
            r = BacktestEngine(ChanlunStrategy(**kw), cash=100000.0).run(df)
            a.append(float(r.performance["total_return"]))
            b.append(float(df["close"].iloc[-1] / df["close"].iloc[0] - 1))
            tr = r.trades
            if isinstance(tr, pd.DataFrame) and not tr.empty:
                n_sell += int((tr["direction"] == "SELL").sum())
        except Exception:
            continue
    return np.array(a), np.array(b), n_sell


def t_stat(d: np.ndarray) -> float:
    """超额的单样本 t 统计（d 均值 / 标准差 / sqrt(n)）。"""
    if len(d) < 3 or d.std() == 0:
        return float("nan")
    return float(d.mean() / d.std() * np.sqrt(len(d)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20)
    a = ap.parse_args()
    fs = files(a.limit)
    if not fs:
        print("❌ 无 audit_data，先跑 audit_fetch_real_data.py")
        return 2

    print("缠论策略（默认参数，未调优）vs 买入持有")
    print("=" * 78)
    res: dict[str, tuple] = {}
    for label, kw in (("默认(3buy/3sell 开)", {}),
                      ("关掉 3buy/3sell", {"use_3buy": False, "use_3sell": False})):
        a_, b_, ns = run(fs, **kw)
        if len(a_) < 3:
            print(f"❌ {label} 样本不足")
            return 2
        res[label] = (a_, b_, ns)
        d = a_ - b_
        print(f"\n【{label}】  n={len(a_)}")
        print(f"  策略平均     {a_.mean()*100:+7.2f}%")
        print(f"  买入持有平均 {b_.mean()*100:+7.2f}%")
        print(f"  超额        {d.mean()*100:+7.2f}%   "
              f"t={t_stat(d):+.2f}   跑赢比例 {(a_ > b_).mean()*100:.0f}%")
        print(f"  平仓单数     {ns}")

    print("\n" + "=" * 78)
    d1 = res["默认(3buy/3sell 开)"][0] - res["默认(3buy/3sell 开)"][1]
    t1 = t_stat(d1)
    print("结论：")
    print(f"  1) 策略 vs 买入持有：超额 t={t1:+.2f}"
          f" {'（|t|<2，不显著 —— 无法与噪声区分）' if abs(t1) < 2 else '（|t|>=2，显著）'}")
    print("  2) 「关掉 3buy/3sell」与「默认」哪个好，取决于样本期 beta，")
    print("     本脚本样本 n 较小且未做 beta 中性化，不足以支持改默认值。")
    print("\n⚠️ 局限：")
    print("   - 仅日线、单市场（A股 2020-2026）、未 beta/市值中性化；")
    print("   - 回测交易日志只有 BUY/SELL，无信号类型字段 ⇒ 无法把单笔盈亏")
    print("     归因到 3buy/1buy；")
    print("   - 参数为默认值（未调优），故结果不含过拟合 —— 这是有意的。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
