#!/usr/bin/env python3
"""缠论配对**按大盘状态分组**的表现：只在能赚钱的状态下出手，能不能提高收益？

## 动机（来自已测事实，不是猜测）
1. 全样本：熊市段超额 **+8.19% t=+8.60**，牛市段 **−9.77% t=−6.06**（2025 全年 −15.31%）。
   见 `scripts/audit_chanlun_excess_by_regime.py`。
2. 但那个脚本是**按整年收益正负事后划分**的 —— 那是未来函数，**不能用来指导操作**。
   本脚本改成用**开仓当时就能算出来**的状态量分组，可直接执行。

## 状态定义（全部只用开仓日及之前的数据）
- `above_ma250`: 沪深300 收盘价 在 250 日均线之上（牛/熊粗判）
- `ma250_up`   : 沪深300 的 250 日均线 自身在上升（趋势方向）
- 组合成 4 态：多头加速 / 多头转弱 / 空头反弹 / 空头探底

## 判据
跑**同级别配对**回测一次，把每笔**按开仓时的大盘状态**归类，分组统计胜率/盈亏比。
若某状态组显著优于其他 ⇒ 该状态才值得出手（可实时判断，无未来函数）。

用法：  .venv/bin/python scripts/audit_chanlun_by_market_state.py --limit 40
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from _concurrency import resolve_workers  # noqa: E402
from easy_tdx.backtest.engine import BacktestEngine  # noqa: E402
from _chanlun_lib import make_original_strategy, pairs_from_trades  # noqa: E402

DATA_DIR = ROOT / "audit_data"
INDEX = "sh000300"
SLIP = 0.002
MA_N = 250
EXCLUDE = {"sh000300", "sh000001"}


def _load_index() -> pd.DataFrame:
    d = pd.DataFrame(json.loads((DATA_DIR / f"{INDEX}_daily.json").read_text()))
    d["datetime"] = pd.to_datetime(d["datetime"])
    d = d.sort_values("datetime").reset_index(drop=True)
    d["ma"] = d["close"].rolling(MA_N).mean()
    d["ma_prev"] = d["ma"].shift(20)          # 20 日前均线值 → 判断均线自身方向
    d["above"] = d["close"] > d["ma"]
    d["up"] = d["ma"] > d["ma_prev"]
    return d[["datetime", "above", "up"]]


def _state_at(idx: pd.DataFrame, dt: pd.Timestamp) -> str | None:
    """开仓日**当时**能观测到的状态（只用 dt 当天及之前的指数数据）。"""
    sub = idx[idx["datetime"] <= dt]
    if sub.empty:
        return None
    r = sub.iloc[-1]
    if pd.isna(r["above"]) or pd.isna(r["up"]):
        return None
    if r["above"] and r["up"]:
        return "①多头加速(价>MA250且MA250上行)"
    if r["above"] and not r["up"]:
        return "②多头转弱(价>MA250但MA250下行)"
    if not r["above"] and r["up"]:
        return "③空头反弹(价<MA250但MA250上行)"
    return "④空头探底(价<MA250且MA250下行)"


def _job(args: tuple[str, list]) -> list[dict]:
    code, idx_rows = args
    p = DATA_DIR / f"{code}_daily.json"
    if not p.exists():
        return []
    df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
    df["datetime"] = pd.to_datetime(df["datetime"])
    if len(df) < MA_N + 60:
        return []
    try:
        st = make_original_strategy()
        r = BacktestEngine(st, cash=100000.0, slippage=SLIP).run(df)
        pairs = pairs_from_trades(r)
    except Exception:  # noqa: BLE001
        return []
    if not pairs:
        return []

    idx = pd.DataFrame(idx_rows)
    idx["datetime"] = pd.to_datetime(idx["datetime"])
    out = []
    for pr in pairs:
        eb = int(pr["entry_bar"])
        if eb >= len(df):
            continue
        stt = _state_at(idx, df["datetime"].iloc[eb])
        if stt is None:
            continue
        out.append({"state": stt, "pnl": float(pr["pnl_pct"]),
                    "entry_type": pr["entry_type"], "exit_type": pr["exit_type"]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--workers", type=int, default=None)
    a = ap.parse_args()
    workers = resolve_workers(a.workers)

    idx = _load_index()
    idx_rows = idx.to_dict("records")
    codes = [p.name.split("_")[0] for p in sorted(DATA_DIR.glob("*_daily.json"))]
    codes = [c for c in codes if c not in EXCLUDE][:: a.step]
    if a.limit:
        codes = codes[: a.limit]
    print(f"样本 {len(codes)} 只   并行度 {workers}   状态量=沪深300 MA250（开仓当时可观测）\n")

    from concurrent.futures import ProcessPoolExecutor
    rows: list[dict] = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, r in enumerate(ex.map(_job, [(c, idx_rows) for c in codes], chunksize=1)):
            rows.extend(r)
            if (i + 1) % 50 == 0:
                print(f"  进度 {i+1}/{len(codes)}  累计配对 {len(rows)}", flush=True)

    df = pd.DataFrame(rows)
    if df.empty:
        print("❌ 无配对")
        return 1
    print(f"\n配对总数 {len(df)}\n")
    print("%-32s %7s %9s %8s %9s %9s" % ("大盘状态（开仓时）", "n", "胜率", "笔均收益", "平均盈利", "平均亏损"))
    print("-" * 80)
    for s in sorted(df["state"].unique()):
        g = df[df["state"] == s]
        w = g[g["pnl"] > 0]["pnl"]
        l = g[g["pnl"] <= 0]["pnl"]
        wl = (w.mean() / abs(l.mean())) if len(l) and l.mean() != 0 else float("nan")
        print("%-32s %7d %8.1f%% %+8.2f%% %+8.2f%% %+8.2f%%  盈亏比 %.2f" % (
            s, len(g), (g["pnl"] > 0).mean() * 100, g["pnl"].mean() * 100,
            w.mean() * 100 if len(w) else float("nan"),
            l.mean() * 100 if len(l) else float("nan"), wl))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
