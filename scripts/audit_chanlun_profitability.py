#!/usr/bin/env python3
"""「持续盈利」审计 —— 用户真正关心的口径：**绝对收益**，不是超额。

与既有 audit_chanlun_* 的区别（动机）：
  既有脚本一律用「超额 vs 买入持有」判成败。但用户的实际诉求是
  「系统能不能持续赚钱」，牛市跑输大盘**可以接受**，只要绝对收益为正。
  本脚本改判：**绝对收益 > 0**；并报告 分段（牛/熊/震荡）各段是否为正。

三项硬约束（用户指定，缺一不可）：
  1. **标的选择**：市值 ≥ 100 亿（audit_mcap.json，通达信实时报价）
  2. **操作级别**：日线 **或** 30 分钟，分别出结论
  3. **市场状态分段**：沪深300 的 60 日均线 + 250 日涨幅客观划分，不手工贴标签

判据：
  主判据：**绝对收益 > 0**
  辅判据：**三段里几段为正**（持续盈利 = 不能只靠一段）+ 最大回撤

⚠️ 数据边界（诚实声明）：
  日线 2020-07 → 2026-09（1500 根，含一轮牛熊 + 震荡）
  30min 2024-09 → 2026-10（3976 根，**只有一段**，无法做牛熊分段）
  ⇒ 30min 只报「全段绝对收益 + 最大回撤」，**不报**牛熊分段结论。

用法：
    .venv/bin/python scripts/audit_chanlun_profitability.py --limit 20
    .venv/bin/python scripts/audit_chanlun_profitability.py             # 全量
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import pandas as pd  # noqa: E402

from easy_tdx.backtest.engine import BacktestEngine  # noqa: E402
from easy_tdx.backtest.strategies.chanlun_ml import ChanlunMLStrategy  # noqa: E402
from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402

DATA = ROOT / "audit_data"
DATA_MIN = ROOT / "audit_data_min"
MCAP = ROOT / "audit_mcap.json"
MIN_MCAP = 1e10  # 100 亿
EXCLUDE = {"sh000300", "sh000001"}
_BUY = {"1buy", "2buy", "3buy", "2buy_s"}
_SELL = {"1sell", "2sell", "3sell", "2sell_s"}


# ── 数据 ──────────────────────────────────────────────────────────────────────

def load_mcap() -> dict:
    return json.loads(MCAP.read_text()) if MCAP.exists() else {}


def big_caps(mcap: dict, limit: int = 0) -> list[str]:
    out = [k for k, v in mcap.items()
           if v.get("mcap", 0) >= MIN_MCAP and k not in EXCLUDE]
    out.sort(key=lambda k: -mcap[k]["mcap"])
    return out[:limit] if limit else out


def load_daily(code: str, start=None, end=None) -> pd.DataFrame:
    p = DATA / f"{code}_daily.json"
    if not p.exists():
        return pd.DataFrame()
    df = pd.DataFrame(json.loads(p.read_text()))
    df["datetime"] = pd.to_datetime(df["datetime"])
    if start:
        df = df[df["datetime"] >= pd.Timestamp(start)]
    if end:
        df = df[df["datetime"] <= pd.Timestamp(end)]
    return df.reset_index(drop=True)


def load_min(code: str) -> pd.DataFrame:
    p = DATA_MIN / f"{code}_30min.json"
    if not p.exists():
        return pd.DataFrame()
    df = pd.DataFrame(json.loads(p.read_text()))
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df.reset_index(drop=True)


# ── 信号构造（与 _ml_precompute / ChanlunMLStrategy.init() 同构）────────────────

def build_signals(df: pd.DataFrame, freq: str):
    """返回 (main_tuples, sub_tuples)。main 为 (bar,type,conf,idx)，sub 为 (dt,type,conf)。"""
    res = ChanlunAnalyser(code="X", frequency=freq, config=ChanlunConfig()).process_klines(df)
    main = []
    for i, m in enumerate(res.mmds):
        t = str(m.mmd_type.value)
        bar = int(m.bi.end.bar_index) if m.bi else -1
        if bar >= 0:
            main.append((bar, t, float(getattr(m, "confidence", 0.0))))
    main.sort(key=lambda x: x[0])
    dts = df["datetime"].reset_index(drop=True)
    sub = []
    for m in res.mmds:
        t = str(m.mmd_type.value)
        if t not in _SELL:
            continue
        bar = int(m.bi.end.bar_index) if m.bi else -1
        if 0 <= bar < len(dts):
            sub.append((pd.Timestamp(dts.iloc[bar]), t, float(getattr(m, "confidence", 0.0))))
    sub.sort(key=lambda x: x[0])
    return main, sub


# ── 市场状态分段（客观） ───────────────────────────────────────────────────────

def regimes(min_days: int = 60) -> list[tuple[str, str, str]]:
    """沪深300：收盘 > MA60 且 250日涨幅>+10% ⇒ 牛；<MA60 且 <-10% ⇒ 熊；其余震荡。

    ⚠️ 必须做**持续性过滤**：逐日打标会在均线附近反复抖动（实测一天就翻一次，
    打出来 40+ 段，没法用）。规则：新标签需连续 min_days 个交易日成立才切换。
    """
    df = load_daily("sh000300")
    if df.empty:
        return []
    c, d = df["close"].tolist(), df["datetime"].tolist()
    n = len(c)
    ma = [None] * n
    for i in range(59, n):
        ma[i] = sum(c[i - 59:i + 1]) / 60
    labs = [None] * n
    for i in range(60, n):
        if ma[i] is None:
            continue
        if i >= 250:
            ret = c[i] / c[i - 250] - 1
            labs[i] = "牛" if (c[i] > ma[i] and ret > 0.10) else \
                      ("熊" if (c[i] < ma[i] and ret < -0.10) else "震荡")
        else:
            labs[i] = "牛" if c[i] > ma[i] else "熊"

    # 持续性过滤：连续 min_days 天同一标签 ⇒ 确认切换
    out, cur, run, run_start = [], None, 0, None
    cand = None
    for i in range(60, n):
        if labs[i] is None:
            continue
        if labs[i] == cand:
            run += 1
        else:
            cand, run, run_start = labs[i], 1, i
        if run >= min_days and cand != cur:
            if cur is not None:
                out[-1] = (out[-1][0], out[-1][1], d[run_start - 1])
            out.append([cand, d[run_start], d[i]])
            cur = cand
        elif cur is not None:
            out[-1][2] = d[i]
    return [(l, str(s)[:10], str(e)[:10]) for l, s, e in out]


# ── 回测 ──────────────────────────────────────────────────────────────────────

def run_one(code: str, df: pd.DataFrame, sub_df=None, freq="daily",
            entry="1buy,2buy,3buy", exit_t="1sell", max_hold=60):
    if df is None or len(df) < 100:
        return None
    main, _ = build_signals(df, freq)
    if not main:
        return None
    sub = None
    if sub_df is not None and len(sub_df) > 100:
        # ⚠️ build_signals 返回 (main, sub) —— 顺序写反会把**整型的 main bar**
        #    当成次级别 datetime 传进去，运行时报
        #    `'>' not supported between instances of 'int' and 'Timestamp'`。
        _, sub = build_signals(sub_df, "30min")
        sub = sub or None
    try:
        st = ChanlunMLStrategy(entry_types=entry, exit_types=exit_t, max_hold_bars=max_hold)
        st.set_data(df, sub_df if sub_df is not None and len(sub_df) else None)
        # ⚠️ 格式必须是 **3 元组** (bar,type,conf)：策略 next() 里写的是
        #    `bar, t, conf = self._main_signals[...]`，传 4 元组会 unpack 失败。
        #    （_ml_precompute 内部存 4 元组是为了带 mmd 索引，喂策略时要去掉）
        st.set_precomputed(main, sub, None, None)
        r = BacktestEngine(st, cash=1_000_000, slippage=0.002).run(df)
    except Exception:
        import traceback
        if __import__("os").environ.get("PROF_DEBUG"):
            traceback.print_exc()
        return None
    perf = r.performance or {}
    tr = r.trades
    n = len(tr) if tr is not None else 0
    if n == 0:
        return {"ret": None, "n": 0, "win": None, "mdd": None}
    ret = perf.get("total_return")
    ret = ret * 100 if ret is not None and abs(ret) <= 10 else ret
    win = perf.get("win_rate")
    mdd = perf.get("max_drawdown")
    mdd = mdd * 100 if mdd is not None and abs(mdd) <= 10 else mdd
    wins = None
    if tr is not None and "pnl_pct" in getattr(tr, "columns", []):
        s = tr["pnl_pct"].dropna()
        wins = (s > 0).sum() / len(s) if len(s) else None
    return {"ret": ret, "n": n, "win": (win * 100) if (win is not None and win <= 1) else win,
            "mdd": mdd, "wins_calc": wins}


def buyhold(df: pd.DataFrame) -> float:
    if df is None or len(df) < 2:
        return 0.0
    return (df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--level", choices=["daily", "30min", "both"], default="both")
    a = ap.parse_args()

    mcap = load_mcap()
    if not mcap:
        print("❌ 无 audit_mcap.json，请先生成市值数据")
        return 2
    codes = big_caps(mcap, a.limit)
    print(f"市值 ≥100亿：{len(codes)} 只（总 {len(mcap)} 只）")

    regs = regimes()
    print("\n── 市场状态分段（沪深300：MA60 + 250日涨幅）──")
    for lab, s, e in regs:
        print(f"  {lab:4s} {s} → {e}")
    segs = [r for r in regs if (pd.Timestamp(r[2]) - pd.Timestamp(r[1])).days >= 120]
    print(f"  （保留 ≥120 天：{len(segs)} 段）")

    for level in (["daily", "30min"] if a.level == "both" else [a.level]):
        print(f"\n{'=' * 76}\n操作级别 = {level}\n{'=' * 76}")
        if level == "daily":
            rows = []
            for code in codes:
                full = load_daily(code)
                if len(full) < 300:
                    continue
                rec = {"code": code, "name": mcap[code]["name"],
                       "bh": buyhold(full), "全段": run_one(code, full, load_min(code))}
                for lab, s, e in segs:
                    seg = load_daily(code, s, e)
                    if len(seg) >= 120:
                        rec[lab] = run_one(code, seg, None)  # 段内次级别数据不足 ⇒ 同级别
                rows.append(rec)
                print(f"  ..{len(rows)}", end="\r", flush=True)
            _report(rows, segs, level)
        else:
            rows = []
            for code in codes:
                mdf = load_min(code)
                if len(mdf) < 500:
                    continue
                r = run_one(code, mdf, None, freq="30min")
                if r:
                    rows.append({"code": code, "name": mcap[code]["name"],
                                 "bh": buyhold(mdf), "全段": r})
                print(f"  ..{len(rows)}", end="\r", flush=True)
            _report(rows, [], level, note="30min 仅 2024-09 起一段，无法做牛熊分段")
    return 0


def _report(rows, segs, level, note=""):
    rows = [r for r in rows if r.get("全段")]
    if not rows:
        print("  无有效结果")
        return
    print(f"\n有效标的 {len(rows)} 只{'  ⚠️ ' + note if note else ''}")
    keys = ["全段"] + [l for l, _, _ in segs]
    print(f"\n{'标的':<11}{'名称':<9}{'买入持有':>10}" + "".join(f"{k:>20}" for k in keys))
    print("-" * (30 + 20 * len(keys)))
    for r in rows[:20]:
        line = f"{r['code']:<11}{r.get('name','')[:7]:<9}{r.get('bh',0):>+9.1f}%"
        for k in keys:
            v = r.get(k)
            line += f"{_fmt(v):>20}" if v else f"{'—':>20}"
        print(line)

    print(f"\n── 汇总（{level}，绝对收益口径）──")
    bh = [r.get("bh", 0) for r in rows]
    print(f"  买入持有均值：{sum(bh)/len(bh):+.2f}%（参照，不是判据）")
    for k in keys:
        vals = [r[k] for r in rows if r.get(k)]
        rets = [v["ret"] for v in vals if v.get("ret") is not None]
        if not rets:
            print(f"  {k}: 无数据")
            continue
        npos = sum(1 for x in rets if x > 0)
        mean = sum(rets) / len(rets)
        ns = [v["n"] for v in vals if v.get("n")]
        wins = [v["win"] for v in vals if v.get("win") is not None]
        mdds = [v["mdd"] for v in vals if v.get("mdd") is not None]
        print(f"  {k:<5} n={len(rets):<4} 均值{mean:+8.2f}%  为正 {npos}/{len(rets)}"
              f" ({npos/len(rets)*100:3.0f}%)  笔均{sum(ns)/len(ns) if ns else 0:4.1f}  "
              f"胜率{sum(wins)/len(wins) if wins else 0:5.1f}%  回撤{sum(mdds)/len(mdds) if mdds else 0:5.1f}%")
        print(f"        {'✅ 绝对收益为正' if mean > 0 else '❌ 绝对收益为负'}")


def _fmt(v) -> str:
    if not v or v.get("ret") is None:
        return "—"
    return f"{v['ret']:+.1f}%({v['n']})"


if __name__ == "__main__":
    sys.exit(main())
