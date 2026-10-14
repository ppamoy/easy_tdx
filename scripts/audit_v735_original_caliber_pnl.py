#!/usr/bin/env python3
"""V735：三个「缠论原文口径」开关的收益对照 —— 只为评估**影响面**，
**不是**决定是否改默认值的依据。判据是原文；收益只回答「切过去会怎样」。

对照的四套配置（10~25 只日线，带成本，纯买卖点配对）：
  A 现状        ：三个开关全 False（工程口径，当前默认）
  B 原文全开    ：zs_zd_original_ac / mmd_2nd_original / mmd_1st_original 全 True
  C 只 ZG/ZD    ：仅 zs_zd_original_ac=True（影响 3买/3卖 阈值）
  D 只 2买/1买  ：仅 mmd_2nd_original + mmd_1st_original=True（影响 1、2 类）

⚠️ 纪律：
  1. 传 config 必须用 **config= 关键字**（位置传参会落进 `code`，
     开关永远无效 → 误测「差异 0」。已栽过一次）。
  2. 不用 BacktestEngine.run() 跑 A/B —— 引擎内部用已安装模块。
     这里直接调 ChanlunAnalyser 取 mmds，自己配对，避免 patch 问题。
  3. 样本外：--oos 可把后半段切出来单独统计。

用法：
  .venv/bin/python scripts/audit_v735_original_caliber_pnl.py --limit 25
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402

DATA_DIR = Path(__file__).parent.parent / "audit_data"
COMMISSION = 0.0003
STAMP = 0.001
SLIPPAGE = 0.002
ROUND_TRIP = COMMISSION * 2 + STAMP + SLIPPAGE * 2  # ~0.56%
EXCLUDE = {"sh000001"}  # 指数不可交易


def _cfg(ac: bool, second: bool, first: bool) -> ChanlunConfig:
    c = ChanlunConfig()
    c.zs_zd_original_ac = ac
    c.mmd_2nd_original = second
    c.mmd_1st_original = first
    return c


def _mmds_for(code: str, cfg: ChanlunConfig, oos: bool):
    p = DATA_DIR / f"{code}_daily.json"
    rows = json.loads(p.read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    if oos:
        df = df.iloc[len(df) // 2 :].reset_index(drop=True)
    r = ChanlunAnalyser(config=cfg).process_klines(df)  # ⚠️ 必须关键字
    out = []
    for m in getattr(r, "mmds", []) or []:
        v = m.mmd_type.value
        if m.bi is None or m.bi.end is None or m.bi.end.k is None:
            continue
        out.append((int(m.bi.end.k.k_index), v, float(m.bi.end.val)))
    return out, df


def _pairs(mmds, df):
    """按时间顺序配对：买点 → 其后第一个卖点。"""
    mmds = sorted(mmds, key=lambda x: x[0])
    n = len(df)
    close = df["close"].to_numpy(dtype=float)
    pairs = []
    open_i = None
    for idx, v, _price in mmds:
        if open_i is None and "buy" in v:
            open_i = idx
        elif open_i is not None and "sell" in v:
            if idx <= open_i or open_i >= n or idx >= n:
                continue
            pnl = (close[idx] - close[open_i]) / close[open_i] * 100
            pairs.append({"pnl_pct": pnl, "holding_bars": idx - open_i})
            open_i = None
    return pairs


def _summarize(pairs, label):
    if not pairs:
        return {"口径": label, "笔数": 0}
    d = pd.DataFrame(pairs)
    w = d[d["pnl_pct"] > 0]["pnl_pct"]
    l = d[d["pnl_pct"] <= 0]["pnl_pct"]
    net = d["pnl_pct"] - ROUND_TRIP * 100
    return {
        "口径": label,
        "笔数": len(d),
        "胜率%": round(float((d["pnl_pct"] > 0).mean() * 100), 2),
        "毛均收益%": round(float(d["pnl_pct"].mean()), 3),
        "扣成本均%": round(float(net.mean()), 3),
        "扣成本总%": round(float(net.sum()), 2),
        "盈亏比": round(float(w.mean() / abs(l.mean())), 2)
        if len(l) and l.mean() != 0
        else np.nan,
        "持有中位": int(d["holding_bars"].median()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--oos", action="store_true", help="只用后半段（样本外）")
    args = ap.parse_args()

    codes = sorted(
        p.name[: -len("_daily.json")]
        for p in DATA_DIR.glob("*_daily.json")
        if p.name[: -len("_daily.json")] not in EXCLUDE
    )[: args.limit]

    variants = [
        ("A 现状(全False)", _cfg(False, False, False)),
        ("B 原文(全True)", _cfg(True, True, True)),
        ("C 只ZG/ZD(AC)", _cfg(True, False, False)),
        ("D 只1、2类", _cfg(False, True, True)),
    ]

    print(f"样本 {len(codes)} 只日线 | 成本往返 {ROUND_TRIP*100:.2f}%"
          + (" | **样本外(后半段)**" if args.oos else ""))

    results = []
    for label, cfg in variants:
        all_pairs = []
        for code in codes:
            try:
                mmds, df = _mmds_for(code, cfg, args.oos)
                all_pairs.extend(_pairs(mmds, df))
            except Exception as e:  # noqa: BLE001
                print(f"  ! {code} 失败: {e}")
                continue
        results.append(_summarize(all_pairs, label))

    out = pd.DataFrame(results)
    pd.set_option("display.width", 200)
    print(out.to_string(index=False))
    print()
    print("⚠️ 收益只是**影响面**参考。判据是缠论原文（108课），"
          "收益好坏不得用来否决原文要求。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
