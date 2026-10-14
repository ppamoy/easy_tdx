#!/usr/bin/env python3
"""**真·区间套（次级别 30min）**验证：日线买点被 30min 确认，是否提升收益？

## 与已有 `audit_qujiantao_power.py` 的区别
已有脚本做的是「日线信号 + **周线**结构」的跨周期确认（真实聚合）。
本脚本做的是「日线信号 + **真实 30 分钟**结构」—— 这才是缠论原文说的
**次级别**（日线的次级别是 30min/60min，不是周线；周线是**高级别**）。

两者互补，不重复。此前两者**都没测过**（仓库没有分钟线数据）。

## 关键区分（项目文档已明确）
- **真区间套** = 高级别信号 + **另一份真实行情**的低周期结构 → 本脚本走这条
- **伪区间套** = 同序列递归级别，实测确认率仅 **3%**，不是真区间套
- **合成数据** = level_synth 近似值，也不是真区间套

## ⚠️ 确认率的口径修正（2026-10-10 实测）
早期冒烟（8 只）报确认率 **26.1%**，本脚本现在报 **~72%**。差异不是模型变了，
是**口径修正**：早期版本拿**全长日线**（1500 根，2020 起）的信号去配
**只有 2024-09 起**的 30min 数据 —— 其中 21/40 个信号的笔结束时间**早于**
30min 数据起点，根本没有低级别结构可查，必然判"未确认"，把确认率压下去。

实测（sh600000）：
  旧（全日线 1500 根）：40 信号 / 确认 12 = 30.0%，21 个早于 30min 起点
  新（截断到 30min 覆盖区间 494 根）：13 信号 / 确认 9 = 69.2%，0 个越界

现在所有脚本统一截断到 30min 覆盖区间（``_ml_precompute.load_pair``），
**26.1% 那个数字是口径 bug 的产物，不要再引用**。

## 要回答
缠论原文：区间套确认的买卖点可靠度显著更高。
实测：按 nested=True/False 分组比较前瞻收益与胜率。
      若确认组没有优势 ⇒ 区间套对选股无增量信息。

用法：  .venv/bin/python scripts/audit_qujiantao_30min.py --limit 20
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
from _ml_precompute import CACHE, load_pair  # noqa: E402
from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402
from easy_tdx.chanlun.qujiantao import compute_qujiantao_cross_period  # noqa: E402

D = ROOT / "audit_data"
DM = ROOT / "audit_data_min"
EXCLUDE = {"sh000300", "sh000001"}
MIN_N = 10


def has_cache(code: str) -> bool:
    return any(CACHE.glob(f"{code}_*.json")) if CACHE.exists() else False


def _job_from_cache(code: str) -> list[dict]:
    """从预计算缓存读（快）。缓存里已含 main_nested，但前瞻收益需重算。"""
    p = next(CACHE.glob(f"{code}_*.json"))
    c = json.loads(p.read_text())
    d, _s = load_pair(code)
    close = d["close"].to_numpy()
    out = []
    for i, x in enumerate(c["main"]):
        bar = x["bar"]
        row: dict = {"type": x["t"],
                     "nested": bool(c["main_nested"].get(str(i), False)),
                     "score": 0.0}
        for h in (5, 10, 20):
            row[f"r{h}"] = float(close[bar + h] / close[bar] - 1) if bar + h < len(close) else np.nan
        out.append(row)
    return out


def _job(code: str) -> list[dict]:
    if has_cache(code):
        return _job_from_cache(code)
    p = DM / f"{code}_30min.json"
    if not p.exists():
        return []
    d = pd.DataFrame(json.loads((D / f"{code}_daily.json").read_text()))
    d["datetime"] = pd.to_datetime(d["datetime"])
    s = pd.DataFrame(json.loads(p.read_text()))
    s["datetime"] = pd.to_datetime(s["datetime"])
    if len(d) < 100 or len(s) < 100:
        return []

    cfg = ChanlunConfig()
    rh = ChanlunAnalyser(code=code, frequency="daily", config=cfg).process_klines(d)
    rs = ChanlunAnalyser(code=code, frequency="30min", config=cfg).process_klines(s)

    qt = compute_qujiantao_cross_period(
        rh.mmds, bis_low=rs.bis, zss_low=rs.zss, mmds_low=rs.mmds,
    )

    close = d["close"].to_numpy()
    out = []
    for m, q in zip(rh.mmds, qt):
        t = str(m.mmd_type.value)
        bar = int(m.bi.end.bar_index) if m.bi else -1
        if bar < 0:
            continue
        row: dict = {"type": t, "nested": bool(q.get("nested")) if q else False,
                     "score": float(q.get("score", 0.0)) if q else 0.0}
        for h in (5, 10, 20):
            row[f"r{h}"] = float(close[bar + h] / close[bar] - 1) if bar + h < len(close) else np.nan
        out.append(row)
    return out


def _erfinv(y: float) -> float:
    """逆误差函数（Newton 迭代，够用即可；避免引入 scipy 依赖）。"""
    from math import erf, sqrt, pi, exp
    if not -1 < y < 1:
        raise ValueError(y)
    x = 0.0
    for _ in range(80):
        err = erf(x) - y
        if abs(err) < 1e-14:
            break
        x -= err / (2 / sqrt(pi) * exp(-x * x))
    return x


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--workers", type=int, default=None)
    a = ap.parse_args()
    workers = resolve_workers(a.workers)

    if CACHE.exists():
        codes = sorted({f.name.split("_")[0] for f in CACHE.glob("*_*.json")})
        src = "预计算缓存"
    else:
        codes = [p.name.split("_")[0] for p in sorted(DM.glob("*_30min.json"))]
        codes = [c for c in codes if c not in EXCLUDE]
        src = "实时计算（无缓存，会很慢）"
    codes = codes[:: a.step]
    if a.limit:
        codes = codes[: a.limit]
    print(f"样本 {len(codes)} 只（日线 + 真实 30min 次级别）来源={src}  并行度 {workers}\n")

    from concurrent.futures import ProcessPoolExecutor
    rows: list[dict] = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, r in enumerate(ex.map(_job, codes, chunksize=1)):
            rows.extend(r)
            if (i + 1) % 20 == 0:
                print(f"  进度 {i+1}/{len(codes)}  累计信号 {len(rows)}", flush=True)

    df = pd.DataFrame(rows)
    if df.empty:
        print("❌ 无信号")
        return 1
    print(f"\n信号总数 {len(df)}   区间套确认率 {df['nested'].mean()*100:.1f}%\n")

    # ── 多重比较校正 ──────────────────────────────────────────────────
    # 7 个买卖点类型 × 3 个前瞻期 = 21 组检验。若每组都用 |z|>1.96，
    # 在「区间套其实完全无效」的原假设下，21 组里也会**期望出现约 1 组**
    # 假阳性（21×5% ≈ 1.05）。实测确实出现了几组 z≈2.0 —— 那正是
    # 多重比较的产物，不能直接当成"区间套有效"。
    # ⇒ 先收集全部检验，再用 Bonferroni 校正后的阈值判定，并报 FDR。
    checks: list[tuple[str, int, float, float, float]] = []
    for h in (5, 10, 20):
        col = f"r{h}"
        for t in sorted(df["type"].unique()):
            sub = df[df["type"] == t].dropna(subset=[col])
            a1 = sub[sub.nested][col].dropna()
            a0 = sub[~sub.nested][col].dropna()
            if len(a1) >= MIN_N and len(a0) >= MIN_N:
                diff = (a1.mean() - a0.mean()) * 100
                se = np.sqrt(np.var(a1, ddof=1) / len(a1) + np.var(a0, ddof=1) / len(a0))
                z = (a1.mean() - a0.mean()) / se if se > 0 else 0.0
                checks.append((f"{t}@{h}", len(a1) + len(a0), diff, z, se))

    n_test = len(checks)
    # Bonferroni：阈值 z 对应双尾 alpha/n_test
    alpha = 0.05
    z_crit = float(abs(np.sqrt(2) * _erfinv(1 - alpha / n_test))) if n_test else 1.96
    # 未校正下期望的假阳性数
    exp_fp = n_test * alpha
    print(f"多重比较：共 {n_test} 组检验  ⇒ Bonferroni 校正后阈值 |z|>{z_crit:.2f}")
    print(f"          未校正（|z|>1.96）在原假设下期望假阳性 {exp_fp:.2f} 组\n")

    for h in (5, 10, 20):
        col = f"r{h}"
        print(f"── 前瞻 {h} 根 ──")
        print("%-14s %8s %11s %8s" % ("分组", "n", "平均收益", "胜率"))
        for t in sorted(df["type"].unique()):
            sub = df[df["type"] == t].dropna(subset=[col])
            for lab, g in (("✅确认", sub[sub.nested]), ("❌未确认", sub[~sub.nested])):
                if len(g) < MIN_N:
                    continue
                print("%-14s %8d %+10.2f%% %7.1f%%" % (
                    f"{t}/{lab}", len(g), g[col].mean() * 100, (g[col] > 0).mean() * 100))
            a1 = sub[sub.nested][col].dropna()
            a0 = sub[~sub.nested][col].dropna()
            if len(a1) >= MIN_N and len(a0) >= MIN_N:
                diff = (a1.mean() - a0.mean()) * 100
                se = np.sqrt(np.var(a1, ddof=1) / len(a1) + np.var(a0, ddof=1) / len(a0))
                z = (a1.mean() - a0.mean()) / se if se > 0 else 0.0
                if abs(z) > z_crit:
                    sig = "✅确认更高(校正后显著)" if diff > 0 else "❌确认更低(校正后显著)"
                elif abs(z) > 1.96:
                    sig = "⚠️未校正显著/校正后不显著" if diff > 0 else "⚠️未校正显著(反向)"
                else:
                    sig = "—无显著差异"
                print(f"{'':14} {'→差':>8} {diff:+9.2f}%  z={z:+.2f}  {sig}")
        print()

    n_sig = sum(1 for _, _, _, z, _ in checks if abs(z) > z_crit)
    n_raw = sum(1 for _, _, _, z, _ in checks if abs(z) > 1.96)
    print("── 汇总 ──")
    print(f"未校正显著（|z|>1.96）: {n_raw}/{n_test} 组")
    print(f"Bonferroni 校正后显著（|z|>{z_crit:.2f}）: {n_sig}/{n_test} 组")
    if n_sig == 0:
        print("⇒ 没有任何一组在多重比较校正后显著 ⇒ **区间套作为过滤器没有可证的增量**")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
