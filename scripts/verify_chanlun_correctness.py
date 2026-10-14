#!/usr/bin/env python3
"""缠论模型**正确性**验证（不是收益验证）。

用户真正想要的：「确认你的缠论模型是否正确」。
收益好不好是另一回事（受行情影响），**正确** = 信号方向本身有信息量：
  - 买点之后**真的更容易涨**，卖点之后**真的更容易跌**
  - 且**胜过随机**（否则那只是行情本身在涨/跌，缠论没贡献）

三个层次，逐层加严：
  L1 **方向对不对**：买点后 N 根平均涨跌幅 > 0？卖点后 < 0？
  L2 **胜过随机吗**：与同数量随机入场对照，超额 > 0？
  L3 **统计显著吗**：配对 t 检验（每只票一个样本），并做
      **多重比较校正**（Bonferroni：测了 m 个信号类型，阈值按 m 收紧）
      —— 不校正的话测 8 个类型就必然有 ~1 个"显著"是运气

与 audit_chanlun_profitability.py 的分工：
  那个答「能不能赚钱」（绝对收益、牛熊分段）
  这个答「模型对不对」（方向、超额、显著性）
  **两者不可互相替代**：行情好时模型错也能赚钱；模型对时也可能赚不到钱。

用法：
    .venv/bin/python scripts/verify_chanlun_correctness.py --limit 50
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import pandas as pd  # noqa: E402

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402

DATA = ROOT / "audit_data"
DATA_MIN = ROOT / "audit_data_min"
MCAP = ROOT / "audit_mcap.json"
MIN_MCAP = 1e10
EXCLUDE = {"sh000300", "sh000001"}
HORIZONS = (5, 10, 20)
MIN_STOCKS = 5   # 少于 5 只票有该类信号 ⇒ 样本不足，不出结论


def load_daily(code: str) -> pd.DataFrame:
    p = DATA / f"{code}_daily.json"
    if not p.exists():
        return pd.DataFrame()
    df = pd.DataFrame(json.loads(p.read_text()))
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df.reset_index(drop=True)


def load_min(code: str) -> pd.DataFrame:
    p = DATA_MIN / f"{code}_30min.json"
    if not p.exists():
        return pd.DataFrame()
    df = pd.DataFrame(json.loads(p.read_text()))
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df.reset_index(drop=True)


def mmds_of(df: pd.DataFrame, freq: str) -> list[tuple[int, str]]:
    res = ChanlunAnalyser(code="X", frequency=freq, config=ChanlunConfig()).process_klines(df)
    out = []
    for m in res.mmds:
        bar = int(m.bi.end.bar_index) if m.bi else -1
        if bar >= 0:
            out.append((bar, str(m.mmd_type.value)))
    out.sort(key=lambda x: x[0])
    return out


# ── 统计口径**一律**复用 src/easy_tdx/backtest/signal_stats.py ──
# 前端 /signal-check 与本脚本共用同一份实现，避免两处漂移出两个不同的数。
from easy_tdx.backtest.signal_stats import (  # noqa: E402
    bonferroni_crit,
    directional,
    evaluate_type,
    forward,
    is_buy_type,
    mean,
    paired_t,
    random_baseline,
    z_crit,
)


def fwd_returns(closes: list[float], idxs: list[int], h: int) -> list[float]:
    """前瞻收益（越界丢弃）。"""
    out = []
    for i in idxs:
        r = forward(closes, i, h)
        if r is not None:
            out.append(r)
    return out



def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50, help="标的数量（按市值取前 N）")
    ap.add_argument("--level", choices=["daily", "30min", "both"], default="both")
    a = ap.parse_args()

    mcap = json.loads(MCAP.read_text()) if MCAP.exists() else {}
    codes = [k for k, v in mcap.items() if v.get("mcap", 0) >= MIN_MCAP and k not in EXCLUDE]
    codes.sort(key=lambda k: -mcap[k]["mcap"])
    codes = codes[: a.limit] if a.limit else codes
    print(f"标的：{len(codes)} 只（市值 ≥100亿，按市值取前 {a.limit}）\n")

    for level in (["daily", "30min"] if a.level == "both" else [a.level]):
        print("=" * 78)
        print(f"操作级别 = {level}")
        print("=" * 78)

        # per_type[类型][h] = 每只票的 (信号均值, 随机均值) —— 配对样本
        per_type: dict[str, dict[int, list[tuple[float, float]]]] = {}
        n_stocks = 0

        for code in codes:
            df = load_daily(code) if level == "daily" else load_min(code)
            if len(df) < 300:
                continue
            closes = [float(x) for x in df["close"]]
            sigs = mmds_of(df, "daily" if level == "daily" else "30min")
            if not sigs:
                continue
            n_stocks += 1

            by_type: dict[str, list[int]] = {}
            for bar, t in sigs:
                by_type.setdefault(t, []).append(bar)

            for t, idxs in by_type.items():
                is_buy = is_buy_type(t)
                for h in HORIZONS:
                    f = fwd_returns(closes, idxs, h)
                    if len(f) < 1:
                        continue
                    # 随机基准：同数量，种子由 (类型, h, 股票) 决定 ⇒ 可复现
                    seed = (hash(t) & 0xFFFF) ^ (h * 7919) ^ (len(code) * 31)
                    rb = random_baseline(closes, len(f), h, seed)
                    if not rb:
                        continue
                    # 方向化：买点看涨为正，卖点看跌为正（统一成"对了就为正"）
                    sv = mean([directional(is_buy, x) for x in f])
                    rv = mean([directional(is_buy, x) for x in rb])
                    per_type.setdefault(t, {}).setdefault(h, []).append((sv, rv))
            print(f"  ..{n_stocks}", end="\r", flush=True)

        print(f"\n有效标的 {n_stocks} 只\n")

        # ── 汇总 + 显著性 ──
        # 多重比较：类型数 × horizon 数 ⇒ Bonferroni 收紧阈值
        n_tests = len(per_type) * len(HORIZONS)
        z_crit = bonferroni_crit(n_tests)
        print(f"类型 {len(per_type)} 个 × 前瞻 {len(HORIZONS)} 档 = {n_tests} 次检验；"
              f"Bonferroni 校正后 |t| 阈值 = {z_crit:.2f}\n")

        print(f"{'信号':<9}{'前瞻':>5}{'样本':>6}{'信号方向均值':>13}"
              f"{'随机基准':>11}{'超额':>10}{'t值':>8}  结论")
        print("-" * 74)

        verdicts = {"✅ 方向对且显著": 0, "⚠️ 方向对但不显著": 0,
                    "❌ 方向错/不显著": 0, "样本不足": 0}

        for t in sorted(per_type):
            for h in HORIZONS:
                pairs = per_type[t].get(h, [])
                if len(pairs) < MIN_STOCKS:
                    continue
                res = evaluate_type(pairs, z_crit)
                tv, diff = res["t"], res["excess"]
                ms, mr = res["avg"], res["rnd"]
                v = res["verdict"]
                verdicts[v] = verdicts.get(v, 0) + 1
                print(f"{t:<9}{h:>5}{len(pairs):>6}{ms*100:>12.2f}%"
                      f"{mr*100:>10.2f}%{diff*100:>9.2f}%{tv:>8.2f}  {v}")

        print(f"\n── 汇总（{level}）──")
        for k, v in verdicts.items():
            print(f"  {k}: {v}")
        ok = verdicts["✅ 方向对且显著"] + verdicts["⚠️ 方向对但不显著"]
        tot = sum(verdicts.values())
        print(f"\n  {'✅' if ok > tot / 2 else '❌'} 方向正确的组合：{ok}/{tot}")
        if verdicts["✅ 方向对且显著"] == 0:
            print("  ⚠️ **没有任何组合通过显著性检验** ⇒ 不能声称模型正确")

    return 0


if __name__ == "__main__":
    sys.exit(main())
