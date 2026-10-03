#!/usr/bin/env python3
"""V733：非 A 股样本 —— 这个择时边际是 A 股特有的吗？

为什么要做
----------
前面所有结论都基于**A 股**。而 A 股有几个非常特殊的制度：
  - T+1（当日买入不能卖）
  - 涨跌停限制（±10%/±20%）
  - 以散户交易为主导
如果 1buy/1sell 的正超额只在 A 股存在，那它是**制度/微观结构的产物**，
而不是缠论结构本身的规律 —— 那就不该声称"缠论有效"。

所以本脚本在**美股 / 港股**上用完全相同的口径重跑：
  - 同一套 ChanlunAnalyser / ChanlunConfig（不调参）
  - 同一个同窗局部极值基准
  - 同样的前瞻 20 根

数据源：Yahoo Finance（`query1.finance.yahoo.com/v8/finance/chart`）。
⚠️ 实测新浪的 CN_MarketData 接口**只覆盖 A 股**：`hk00700` / `gb_aapl`
均返回 null，所以必须换源。

用法：
    .venv/bin/python scripts/audit_non_a_share.py
    .venv/bin/python scripts/audit_non_a_share.py --limit 40

退出码：0 = 跑完（无论结果如何）；2 = 取数失败/无数据。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
CACHE = Path(__file__).resolve().parents[1] / "audit_data_nona"

# 美股蓝筹 + 港股主要标的（分散行业，避免全选科技股）
US = ["AAPL", "MSFT", "KO", "JNJ", "XOM", "JPM", "PG", "WMT", "MCD", "BA",
      "CAT", "MMM", "CVX", "PFE", "T", "VZ", "IBM", "GE", "HD", "DIS"]
HK = ["0700.HK", "1299.HK", "0005.HK", "0939.HK", "1398.HK", "0388.HK",
      "2318.HK", "0941.HK", "0001.HK", "0011.HK"]

HORIZON = 20
PIVOT = 5
BOOT = 300
SEED = 20240917
N_WINDOWS = 6


def _is_buy(st: str) -> bool:
    """必须用 'buy' in st（类二买 2buy_s 用 endswith 会漏判并被取反）。"""
    return "buy" in st


def pivot_indices(c: np.ndarray, k: int, low: bool, lo: int, hi: int) -> np.ndarray:
    out: list[int] = []
    for i in range(max(lo, k), min(hi, len(c) - k)):
        seg = c[i - k: i + k + 1]
        if low and c[i] == seg.min():
            out.append(i)
        elif (not low) and c[i] == seg.max():
            out.append(i)
    return np.array(out, dtype=int)


def fetch(symbol: str, years: int = 5, retries: int = 3) -> list[dict]:
    """取 Yahoo 日线（带本地缓存）。"""
    CACHE.mkdir(exist_ok=True)
    cf = CACHE / f"{symbol.replace('.', '_')}.json"
    if cf.exists():
        try:
            return json.loads(cf.read_text(encoding="utf-8"))
        except Exception:
            pass
    rng = "10y" if years >= 10 else ("5y" if years >= 5 else "2y")
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?range={rng}&interval=1d")
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                d = json.loads(r.read().decode("utf-8", "ignore"))
            res = d.get("chart", {}).get("result")
            if not res:
                return []
            r0 = res[0]
            ts = r0.get("timestamp") or []
            q = (r0.get("indicators", {}).get("quote") or [{}])[0]
            rows = []
            for i, t in enumerate(ts):
                c = (q.get("close") or [None] * len(ts))[i]
                h = (q.get("high") or [None] * len(ts))[i]
                lo = (q.get("low") or [None] * len(ts))[i]
                o = (q.get("open") or [None] * len(ts))[i]
                v = (q.get("volume") or [0] * len(ts))[i]
                if None in (c, h, lo, o):
                    continue  # 停牌/缺失
                rows.append({"datetime": pd.to_datetime(t, unit="s").strftime("%Y-%m-%dT%H:%M:%S"),
                             "open": float(o), "high": float(h), "low": float(lo),
                             "close": float(c), "vol": float(v or 0)})
            if rows:
                cf.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            return rows
        except Exception:
            if a == retries - 1:
                return []
            time.sleep(1.5 * (a + 1))
    return []


def run(symbols: list[str], label: str, horizon: int) -> dict[str, list[float]]:
    rng = np.random.default_rng(SEED)
    per_type: dict[str, list[float]] = {}
    n_ok = 0
    for sym in symbols:
        rows = fetch(sym)
        if len(rows) < horizon * 5:
            print(f"   ⚠️ {sym} 数据不足（{len(rows)} 根），跳过")
            continue
        df = pd.DataFrame(rows)
        df["datetime"] = pd.to_datetime(df["datetime"])
        c = df["close"].to_numpy(dtype=float)
        n = len(c)
        try:
            res = ChanlunAnalyser(code=sym, frequency="daily",
                                  config=ChanlunConfig()).process_klines(df)
        except Exception:
            print(f"   ⚠️ {sym} 分析失败，跳过")
            continue
        n_ok += 1
        usable = n - horizon
        edges = np.linspace(0, usable, N_WINDOWS + 1).astype(int)
        for m in res.mmds:
            if not m.bi:
                continue
            st = m.mmd_type.value.lower()
            i = m.bi.end.bar_index
            if i + horizon >= n:
                continue
            is_buy = _is_buy(st)
            w = int(np.searchsorted(edges[1:], i, side="right"))
            if w >= N_WINDOWS:
                continue
            r = c[i + horizon] / c[i] - 1.0
            if not is_buy:
                r = -r
            cand = pivot_indices(c, PIVOT, low=is_buy,
                                 lo=int(edges[w]), hi=int(edges[w + 1]))
            cand = cand[(cand + horizon) < n]
            if len(cand) < 5:
                continue
            idx = rng.choice(cand, size=(BOOT, 1), replace=True)
            rr = c[idx + horizon] / c[idx] - 1.0
            if not is_buy:
                rr = -rr
            per_type.setdefault(st, []).append(float(r - float(np.mean(rr))))
    print(f"   {label}: 有效 {n_ok}/{len(symbols)} 只")
    return per_type


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="每市场标的数量上限（0=全部）")
    ap.add_argument("--horizon", type=int, default=HORIZON)
    a = ap.parse_args()

    us = US[: a.limit] if a.limit else US
    hk = HK[: a.limit] if a.limit else HK

    print(f"\n非 A 股样本审计：美股 {len(us)} 只 + 港股 {len(hk)} 只，"
          f"前瞻 {a.horizon} 根，同窗局部极值基准")
    print("口径与 A 股完全一致（同一 ChanlunAnalyser/ChanlunConfig，未调参）")
    print("=" * 96)

    print("\n取数中…")
    res_us = run(us, "美股", a.horizon)
    res_hk = run(hk, "港股", a.horizon)

    # ⚠️ 牙齿：防"取到错数据还不自知"。若 AAPL 不是美股价格区间、
    # 或缓存目录少于 20 只，说明取数环节有问题，结果不可信。
    _aapl = CACHE / "AAPL.json"
    if _aapl.exists():
        rows = json.loads(_aapl.read_text(encoding="utf-8"))
        last = float(rows[-1]["close"])
        if not (50.0 < last < 2000.0):
            print(f"\n⚠️ 可疑：AAPL 末价 {last:.2f} 不在合理区间(50~2000)，"
                  f"取到的可能不是美股数据 —— 结果不可信")
        else:
            print(f"\n✅ 数据源抽检：AAPL 末价 {last:.2f}、{len(rows)} 根，符合美股")
    else:
        print("\n⚠️ 未缓存 AAPL，跳过数据源抽检")
    n_files = len(list(CACHE.glob("*.json")))
    if n_files < 20:
        print(f"⚠️ 缓存仅 {n_files} 只，样本过少，结果不可信")

    types = ["1buy", "1sell", "2buy", "2sell", "2buy_s", "2sell_s", "3buy", "3sell"]
    print("\n【毛超额（对比同窗极值基准）】")
    print(f"{'市场':<8}{'n':>6}" + "".join(f"{t:>9}" for t in types))
    print("-" * (14 + 9 * len(types)))
    for label, d in (("美股", res_us), ("港股", res_hk)):
        if not d:
            print(f"{label:<8}{'—':>6}   无数据")
            continue
        tot = sum(len(v) for v in d.values())
        line = f"{label:<8}{tot:>6}"
        for t in types:
            v = d.get(t)
            line += f"{np.mean(v)*100:>9.2f}" if (v and len(v) >= 25) else f"{'—':>9}"
        print(line)

    print("\n【核心对比：1buy / 1sell 是否仍为正】")
    print("-" * 60)
    for t in ("1buy", "1sell", "3buy", "3sell"):
        out = []
        for label, d in (("美股", res_us), ("港股", res_hk)):
            v = d.get(t)
            if v and len(v) >= 25:
                out.append(f"{label} {np.mean(v)*100:+.2f}%（n={len(v)}）")
            else:
                out.append(f"{label} 样本不足")
        print(f"  {t:<6} " + "   ".join(out))

    print("\n⚠️ 局限：")
    print("   - 未建模美股/港股的交易成本与税费（与 A 股口径不同，不可直接比）；")
    print("   - 港股/美股无涨跌停、T+0，制度差异本身就可能改变结论；")
    print("   - 样本量远小于 A 股（286 只），单市场结论置信度较低。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
