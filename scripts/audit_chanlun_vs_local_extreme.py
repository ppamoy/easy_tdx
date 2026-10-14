#!/usr/bin/env python3
"""对照实验：缠论买点的超额，是「缠论的功劳」还是「局部低点」的同义反复？

## 为什么非做不可
`audit_can_chanlun_make_money.py` 的信号层给出 32/32 全部显著为正，
**完美得不正常**。真实市场里不存在这种事。最可疑的一条解释：

  缠论买点在定义上就落在**笔端点**（局部极值）附近。
  拿"局部低点之后的涨幅"去跟"任意随机点之后的涨幅"比，
  赢的是"低买"这件事，不是"缠论"这套理论。
  这是同义反复（tautology），不是预测力。

## 本脚本的三组对照
  A. 随机点基准     —— 与随机入场比（已有结论）
  B. 局部极值基准   —— 与「同样数量的局部低点/高点」比（同义反复检验）
  C. 全样本均值基准 —— 与该标的全期平均漂移比（beta 检验）

**判定逻辑**：若 A 显著为正、而 B 不显著（或大幅缩水），
则所谓"缠论有效"只是局部低点效应 → 不能指导买股票。

用法：  .venv/bin/python scripts/audit_chanlun_vs_local_extreme.py [--limit 0]
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
from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402

DATA_DIR = ROOT / "audit_data"
HORIZONS = (5, 10, 20, 60)
BUY = {"1buy", "2buy", "2buy_s", "3buy"}
SELL = {"1sell", "2sell", "2sell_s", "3sell"}
MIN_N = 30
BOOT = 500
SEED = 20241002
PIVOT = 5          # 局部极值半窗（±5 根）
EXCLUDE = {"sh000300", "sh000001"}


def _analyze_one(p: Path):
    """子进程：算一只标的的缠论信号 + 收盘价。"""
    code = p.stem.split("_")[0]
    df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
    df["datetime"] = pd.to_datetime(df["datetime"])
    c = df["close"].to_numpy(dtype=float)
    n = len(c)
    try:
        res = ChanlunAnalyser(
            code=code, frequency="daily", config=ChanlunConfig()
        ).process_klines(df)
    except Exception as e:  # noqa: BLE001
        return code, c, [{"__error__": f"{type(e).__name__}: {e}"}]
    rows = []
    for m in res.mmds:
        if not m.bi:
            continue
        st = m.mmd_type.value.lower()
        if st not in BUY and st not in SELL:
            continue
        idx = int(m.bi.end.bar_index)
        if idx >= n - 1:
            continue
        rows.append({"symbol": code, "type": st, "idx": idx})
    return code, c, rows


def collect(files: list[Path], workers: int):
    from concurrent.futures import ProcessPoolExecutor
    rows: list[dict] = []
    closes: dict[str, np.ndarray] = {}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(_analyze_one, files, chunksize=1))
    for code, c, rs in results:
        closes[code] = c
        for r in rs:
            if "__error__" in r:
                print(f"  ⚠️ {code}: {r['__error__']}")
                continue
            rows.append(r)
    return pd.DataFrame(rows), closes


def local_extrema(c: np.ndarray, w: int, low: bool) -> np.ndarray:
    """局部极值下标（买→局部低点，卖→局部高点）。"""
    n = len(c)
    out = []
    for i in range(w, n - w):
        seg = c[i - w: i + w + 1]
        if low and c[i] == seg.min():
            out.append(i)
        elif not low and c[i] == seg.max():
            out.append(i)
    return np.asarray(out, dtype=int)


def fwd(c: np.ndarray, starts: np.ndarray, h: int) -> np.ndarray:
    n = len(c)
    ok = starts <= n - 1 - h
    out = np.full(len(starts), np.nan)
    if ok.any():
        s = starts[ok]
        out[ok] = c[s + h] / c[s] - 1.0
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--pivot", type=int, default=PIVOT)
    a = ap.parse_args()
    workers = resolve_workers(a.workers)

    files = [p for p in sorted(DATA_DIR.glob("*.json"))
             if p.stem.split("_")[0] not in EXCLUDE]
    files = files[:a.limit] if a.limit else files
    if not files:
        print("❌ 无数据")
        return 2

    print(f"对照实验：缠论买卖点 vs「局部极值」基准   样本 {len(files)} 只")
    print(f"局部极值半窗 ±{a.pivot} 根   重抽样 {BOOT}")
    print("判定：若随机基准显著为正、而局部极值基准不显著")
    print("      ⇒ 所谓有效只是「低买高卖」的同义反复，不是缠论的预测力。\n")

    sig, closes = collect(files, workers)
    if sig.empty:
        print("❌ 无信号")
        return 2
    rng = np.random.default_rng(SEED)

    print("%-12s %6s | %8s %8s | %8s %8s %8s" % (
        "信号@窗口", "样本", "信号均值", "随机基准", "极值基准", "vs极值", "经验p"))
    print("-" * 78)

    summary = {"vs_random_sig": 0, "vs_extreme_sig": 0, "n": 0}

    for h in HORIZONS:
        for st in sorted(BUY | SELL):
            sub = sig[sig["type"] == st]
            if len(sub) < MIN_N:
                continue
            sign = 1.0 if st in BUY else -1.0
            low = st in BUY

            real_parts, rand_bounds = [], []
            for code in np.unique(sub["symbol"].to_numpy()):
                c = closes[code]
                sel = sub["idx"].to_numpy()[sub["symbol"].to_numpy() == code]
                real_parts.append(fwd(c, sel, h) * sign)
                hi = np.minimum(sel, len(c) - 1 - h)
                rand_bounds.append((code, hi))
            real = np.concatenate(real_parts)
            real = real[~np.isnan(real)]
            if len(real) < MIN_N:
                continue

            # 基准A：随机点
            boot_r = np.empty(BOOT)
            for b in range(BOOT):
                tot, cnt = 0.0, 0
                for code, hi in rand_bounds:
                    c = closes[code]
                    ok = hi > 0
                    if not ok.any():
                        continue
                    k = rng.integers(0, hi[ok] + 1)
                    tot += float(np.sum((c[k + h] / c[k] - 1.0) * sign))
                    cnt += int(ok.sum())
                boot_r[b] = tot / cnt if cnt else np.nan

            # 基准B：局部极值（同数量，从同标的的极值池里抽）
            extreme_pool: dict[str, np.ndarray] = {}
            for code in np.unique(sub["symbol"].to_numpy()):
                c = closes[code]
                idxs = local_extrema(c, a.pivot, low)
                idxs = idxs[idxs <= len(c) - 1 - h]
                extreme_pool[code] = idxs

            boot_e = np.empty(BOOT)
            for b in range(BOOT):
                tot, cnt = 0.0, 0
                for code, hi in rand_bounds:
                    pool = extreme_pool[code]
                    m = int((hi > 0).sum())
                    if len(pool) == 0 or m == 0:
                        continue
                    k = pool[rng.integers(0, len(pool), size=m)]
                    tot += float(np.sum((c_h(closes[code], k, h)) * sign))
                    cnt += m
                boot_e[b] = tot / cnt if cnt else np.nan

            boot_r = boot_r[~np.isnan(boot_r)]
            boot_e = boot_e[~np.isnan(boot_e)]
            mu = float(real.mean())
            mr, me = float(boot_r.mean()), float(boot_e.mean())

            p_r = float((boot_r >= mu).mean())
            p_e = float((boot_e >= mu).mean())
            sd_e = float(boot_e.std())
            z_e = (mu - me) / sd_e if sd_e > 0 else float("nan")

            sig_r = p_r < 0.05 and mu > mr
            sig_e = p_e < 0.05 and mu > me
            summary["n"] += 1
            summary["vs_random_sig"] += int(sig_r)
            summary["vs_extreme_sig"] += int(sig_e)

            print("%-12s %6d | %7.2f%% %7.2f%% | %7.2f%% %7.2f%% %8.3f  %s" % (
                f"{st}@{h}", len(real), mu * 100, mr * 100, me * 100,
                (mu - me) * 100, p_e,
                "✅仍显著" if sig_e else "❌不显著(同义反复)"))

    print("-" * 78)
    n = summary["n"]
    print(f"共 {n} 组：")
    print(f"  显著优于【随机点】  {summary['vs_random_sig']}/{n}")
    print(f"  显著优于【局部极值】{summary['vs_extreme_sig']}/{n}")
    r = summary["vs_extreme_sig"] / n if n else 0
    print("\n【判定】")
    if r >= 0.7:
        print("  绝大多数在排除「局部低点效应」后仍显著 ⇒ 缠论确有增量信息。")
    elif r >= 0.3:
        print("  部分仍显著 ⇒ 缠论有一定增量，但主脚本的超额被局部极值效应放大了。")
    else:
        print("  排除局部低点效应后基本不显著 ⇒ 主脚本的超额主要是")
        print("  「买了局部低点」的同义反复，不能归因于缠论理论本身。")
    return 0


def c_h(c: np.ndarray, k: np.ndarray, h: int) -> np.ndarray:
    return c[k + h] / c[k] - 1.0


if __name__ == "__main__":
    raise SystemExit(main())
