#!/usr/bin/env python3
"""V733：跨周期稳健性 —— 这个择时边际在**非日线**上还在吗？

为什么要做
----------
前面所有结论都来自**日线**（scale=240）。如果 1buy/1sell 的正超额只在日线上
存在、在 60 分钟或周线上就消失甚至反号，那么：
  - 它是"日线特有的数据伪像"（比如日线收盘价的微观结构），而不是
    真正的缠论结构规律；
  - 用户拿它做**日内择时**会被误导。

所以本脚本对同一批标的，抓取 5/15/30/60 分钟 + 日/周/月 共 7 个周期，
用**完全相同**的口径（同窗局部极值基准、前瞻 N 根）重跑，横向对比。

周期与新浪 scale 的对应（实测确认，见 fetch 注释）：
    5→5  15→15  30→30  60→60  日→240  周→1200  月→7200
⚠️ scale=120（2小时）实测返回 null，不可用，故不做。

前瞻窗口：各周期统一用 **20 根**，但注意 20 根在不同周期代表的时间跨度
完全不同（5 分钟=100 分钟；月线=20 个月）。所以结论只能横向对比
「同样的 20 根」下的表现，**不能**跨周期直接比较收益幅度。

用法：
    .venv/bin/python scripts/audit_multi_period.py
    .venv/bin/python scripts/audit_multi_period.py --codes 600519,000001 --scales 60,240
    .venv/bin/python scripts/audit_multi_period.py --limit 40
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

API = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
       "CN_MarketData.getKLineData")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
CACHE = Path(__file__).resolve().parents[1] / "audit_data_multi"

# 周期名 -> (新浪 scale, 说明)
SCALES = {
    "5min": (5, "5 分钟"),
    "15min": (15, "15 分钟"),
    "30min": (30, "30 分钟"),
    "60min": (60, "60 分钟"),
    "day": (240, "日线"),
    "week": (1200, "周线"),
    "month": (7200, "月线"),
}

HORIZON = 20
PIVOT = 5
BOOT = 200
SEED = 20240917


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


def fetch(code: str, scale: int, bars: int, retries: int = 3) -> list[dict]:
    """抓一根标的某周期的 K 线（带本地缓存，避免重复打接口）。"""
    CACHE.mkdir(exist_ok=True)
    cf = CACHE / f"{code[2:] if code[:2] in ('sh','sz','bj') else code}_{scale}.json"
    if cf.exists():
        try:
            return json.loads(cf.read_text(encoding="utf-8"))
        except Exception:
            pass
    # ⚠️ audit_data 里的文件名带交易所前缀（sh600000），而新浪要的是
    # sh+6位数字。第一版直接拿 'sh600000' 再拼前缀 → 'shsh600000' → 全部
    # 返回空、6/6 只标的都判为无效（脚本静默输出"无数据"，差点当成
    # "该周期没信号"的结论）。必须先剥掉前缀再按首位数字重新判定。
    bare = code[2:] if code[:2] in ("sh", "sz", "bj") else code
    prefix = "sh" if bare[0] in ("6", "5", "9") else "sz"
    url = f"{API}?symbol={prefix}{bare}&scale={scale}&ma=no&datalen={bars}"
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as resp:
                txt = resp.read().decode("utf-8", "ignore")
            data = json.loads(txt)
            if isinstance(data, list) and data:
                rows = [{"datetime": d["day"],
                         "open": float(d["open"]), "close": float(d["close"]),
                         "high": float(d["high"]), "low": float(d["low"]),
                         "vol": float(d["volume"])} for d in data]
                cf.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
                return rows
            return []
        except Exception:
            if a == retries - 1:
                return []
            time.sleep(1.5 * (a + 1))
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", default="", help="逗号分隔；为空则用日线样本的前 N 只")
    ap.add_argument("--limit", type=int, default=60, help="标的数量上限")
    ap.add_argument("--scales", default="5min,15min,30min,60min,day,week,month")
    ap.add_argument("--bars", type=int, default=1500)
    ap.add_argument("--horizon", type=int, default=HORIZON)
    a = ap.parse_args()

    scales = [s for s in a.scales.split(",") if s in SCALES]
    if not scales:
        print("❌ 无有效周期")
        return 2

    if a.codes:
        codes = [c.strip() for c in a.codes.split(",") if c.strip()]
    else:
        d = Path(__file__).resolve().parents[1] / "audit_data"
        codes = [p.stem.split("_")[0] for p in sorted(d.glob("*.json"))
                 if p.stem.split("_")[0] not in ("sh000300", "sh000001")]
        codes = codes[: a.limit]

    print(f"\n跨周期稳健性：{len(codes)} 只标的 × {len(scales)} 个周期，"
          f"前瞻 {a.horizon} 根，同窗局部极值基准")
    print("=" * 104)

    rng = np.random.default_rng(SEED)
    # period -> type -> list[(gross,)]
    agg: dict[str, dict[str, list[float]]] = {}

    for pname in scales:
        scale_val, label = SCALES[pname]
        n_ok = 0
        for ci, code in enumerate(codes):
            rows = fetch(code, scale_val, a.bars)
            if len(rows) < a.horizon * 4:
                continue
            df = pd.DataFrame(rows)
            df["datetime"] = pd.to_datetime(df["datetime"])
            c = df["close"].to_numpy(dtype=float)
            n = len(c)
            try:
                res = ChanlunAnalyser(code=code, frequency="daily",
                                      config=ChanlunConfig()).process_klines(df)
            except Exception:
                continue
            n_ok += 1
            usable = n - a.horizon
            if usable <= a.horizon:
                continue
            edges = np.linspace(0, usable, 7).astype(int)

            for m in res.mmds:
                if not m.bi:
                    continue
                st = m.mmd_type.value.lower()
                i = m.bi.end.bar_index
                if i + a.horizon >= n:
                    continue
                is_buy = _is_buy(st)
                w = int(np.searchsorted(edges[1:], i, side="right"))
                if w >= 6:
                    continue
                r = c[i + a.horizon] / c[i] - 1.0
                if not is_buy:
                    r = -r
                cand = pivot_indices(c, PIVOT, low=is_buy,
                                     lo=int(edges[w]), hi=int(edges[w + 1]))
                cand = cand[(cand + a.horizon) < n]
                if len(cand) < 5:
                    continue
                idx = rng.choice(cand, size=(BOOT, 1), replace=True)
                rr = c[idx + a.horizon] / c[idx] - 1.0
                if not is_buy:
                    rr = -rr
                agg.setdefault(pname, {}).setdefault(st, []).append(
                    float(r - float(np.mean(rr))))
        flag = "" if n_ok >= max(1, len(codes) // 2) else "  ⚠️ 有效标的过少，结果不可信"
        print(f"  {label:<8} 有效标的 {n_ok}/{len(codes)}{flag}")

    print("\n【各周期 × 信号类型】对比**同窗极值基准**的毛超额（%）")
    print("⚠️ 前瞻都是 20 根，但 20 根在各周期代表的时间跨度不同，"
          "只能横向看「同周期内的相对强弱」，不能跨周期比幅度。")
    print("=" * 104)

    types = ["1buy", "1sell", "2buy", "2sell", "2buy_s", "2sell_s", "3buy", "3sell"]
    hdr = f"{'周期':<8}{'n':>6}" + "".join(f"{t:>9}" for t in types)
    print(hdr)
    print("-" * (14 + 9 * len(types)))

    for pname in scales:
        label = SCALES[pname][1]
        d = agg.get(pname, {})
        if not d:
            print(f"{label:<8}{'—':>6}  无数据")
            continue
        tot = sum(len(v) for v in d.values())
        line = f"{label:<8}{tot:>6}"
        for t in types:
            v = d.get(t)
            if v and len(v) >= 25:
                line += f"{np.mean(v)*100:>9.2f}"
            else:
                line += f"{'—':>9}"
        print(line)

    print("\n【关键判断】1buy / 1sell 在各周期是否仍为正：")
    print("-" * 60)
    for t in ("1buy", "1sell"):
        marks = []
        for pname in scales:
            v = agg.get(pname, {}).get(t)
            if v and len(v) >= 25:
                marks.append(f"{SCALES[pname][1]}={np.mean(v)*100:+.2f}%")
            else:
                marks.append(f"{SCALES[pname][1]}=样本不足")
        print(f"  {t}: " + "  ".join(marks))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
