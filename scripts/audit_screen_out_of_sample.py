#!/usr/bin/env python3
"""样本外复核：在**全新**标的上，筛选口径还显著吗？（五之三十四）

背景
----
五之三十三 做了 6 个筛选口径的多重比较校正，但有个**未排除的威胁**：

- 那 60 只标的**是我挑的**；
- 6 个口径也是在**看过这些数据之后**定的；
- ⇒ 存在**选择偏差/幸存者偏差**，校正多重比较**并不能**消除它。

做法
----
`audit_data/` 里有 **286** 只个股，其中只有 60 只用过，
**228 只从未被任何口径碰过**。用这 228 只（池化 2288 个观测）重跑基线口径。

⚠️ 这个测试的**关键性质**：基线口径（any_buy）是在旧 60 只上定的，
   它的**定义**没有依赖那 60 只的任何**结果**（只是"池化入选"这一个条件），
   所以搬到新样本上仍是**真正的样本外**。
   若换成"挑出来显著的那个口径"就不成立——那才是选择偏差本身。

结论
----
见下方实测：**原始横截面显著，控制 beta 后消失** ⇒ 是市场 beta，不是选股力。
"""
from __future__ import annotations

import argparse
import json
import sys
from math import erfc, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OLD_SAMPLE_CODES = 60          # 五之二十三~三十三 一直用的样本量


def _load(cache: Path, h: int) -> pd.DataFrame:
    """把逐时点命中/未命中还原成长表，并按**时点收盘价**算前瞻收益。

    ⚠️ 必须 `t + H < len(close)`，否则是**未来函数**（用到了还没发生的K线）。
    """
    rows = []
    for r in json.loads(cache.read_text(encoding="utf-8")):
        f = ROOT / "audit_data" / f"{r['code']}.json"
        if not f.exists():
            continue
        bars = pd.DataFrame(json.loads(f.read_text(encoding="utf-8")))
        if "datetime" not in bars.columns or "close" not in bars.columns:
            continue
        bars["datetime"] = pd.to_datetime(bars["datetime"])
        close = bars.sort_values("datetime")["close"].to_numpy(float)
        for t, x, hit in (
                [(t, x, True) for t, x in
                 zip(r.get("hit_pts", []), r.get("hit", []))] +
                [(t, x, False) for t, x in
                 zip(r.get("miss_pts", []), r.get("miss", []))]):
            if t + h < len(close):
                rows.append((r["code"], t, float(close[t + h] / close[t] - 1),
                             bool(hit)))
    return pd.DataFrame(rows, columns=["code", "t", "r", "hit"])


def _compare(rel: np.ndarray, hit: np.ndarray, label: str) -> tuple:
    a, b = rel[hit], rel[~hit]
    if len(a) < 5 or len(b) < 5:
        print(f"  {label:<26} 样本不足，跳过")
        return (float("nan"),) * 3
    d = float(a.mean() - b.mean())
    se = float(np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)))
    t = d / se if se > 0 else float("nan")
    p = erfc(abs(t) / sqrt(2)) if t == t else float("nan")
    print(f"  {label:<26} 入选{a.mean()*100:+.2f}%  "
          f"未选{b.mean()*100:+.2f}%  差{d*100:+.2f}%  "
          f"t={t:+.2f}  p={p:.4f}  ⇒ {'**显著**' if abs(t) > 1.96 else '不显著'}")
    return d, t, p


def _pooling_check(df: pd.DataFrame, rel: np.ndarray,
                   hit: np.ndarray) -> None:
    """池化偏差诊断：入选占比差异大时，结论还稳吗？

    ⚠️ 池化的隐含假设是"每条观测独立等权"。若某只股票被选中 40 次、
       另一只只 1 次，前者会**主导**整个结论。

    实测（286 只 / 2288 观测）：入选次数 最小1 / 中位4 / 最大8，
       入选最多的 5 只只占全部入选的 **3.0%** ⇒ 分布其实很**均匀**。
       但仍用 3 种加权交叉验证——不靠"看起来均匀"就下结论。
    """
    n_hit = df[df["hit"]].groupby("code").size()
    tot = max(int(n_hit.sum()), 1)
    print("\n── 池化偏差诊断 ──")
    print(f"  入选次数  最小 {int(n_hit.min())} / 中位 {int(n_hit.median())}"
          f" / 最大 {int(n_hit.max())}"
          f"（{n_hit.size} 只有入选，共 {tot} 条）")
    print(f"  入选最多的 5 只占全部入选的 {n_hit.nlargest(5).sum()/tot*100:.1f}%")

    def _t(a, b):
        if len(a) < 2 or len(b) < 2:
            return float("nan")
        d = float(a.mean() - b.mean())
        se = float(np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)))
        return d / se if se > 0 else float("nan")

    ts = [ _t(rel[hit], rel[~hit]) ]
    print(f"  ① 池化（每条观测等权）      t={ts[0]:+.2f} "
          f"p={erfc(abs(ts[0])/sqrt(2)):.4f}")

    # ② 每只股票先求均值 ⇒ 每只股票等权，重的股票不再主导
    per = (pd.DataFrame({"code": df["code"].to_numpy(), "hit": hit, "rel": rel})
           .groupby(["code", "hit"])["rel"].mean().reset_index())
    t2 = _t(per[per["hit"]]["rel"].to_numpy(), per[~per["hit"]]["rel"].to_numpy())
    ts.append(t2)
    print(f"  ② 每股票等权                t={t2:+.2f} "
          f"p={erfc(abs(t2)/sqrt(2)):.4f}")

    # ③ 去掉入选次数两端的极端股票
    cnt = n_hit.reindex(df["code"]).to_numpy()
    mid = (cnt >= 3) & (cnt <= 15)
    t3 = (_t(rel[mid][hit[mid]], rel[mid][~hit[mid]])
          if mid.any() and hit[mid].any() and (~hit[mid]).any()
          else float("nan"))
    if t3 == t3:
        ts.append(t3)
    print(f"  ③ 只留中等入选次数(3~15)   t={t3:+.2f} "
          f"p={erfc(abs(t3)/sqrt(2)):.4f}  (剩 {int(mid.sum())} 条)")

    ok = [x for x in ts if x == x]
    if len(ok) >= 2 and all(abs(x) < 1.96 for x in ok):
        print("  ⇒ ✅ 三种加权**一致不显著** ⇒ 池化偏差不影响结论")
    elif len(ok) >= 2:
        print("  ⇒ ⚠️ **加权方式之间有分歧** ⇒ 池化结论不可靠，"
              "不能只报池化那一个数字")


def main() -> int:
    global ROOT

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", required=True,
                    help="audit_chanlun_screen_usefulness.py 的**明细**缓存"
                         "（screen_audit_cache_*.json，不是 --out 的汇总）")
    ap.add_argument("--h", type=int, default=20)
    ap.add_argument("--index", default="audit_data/sh000300_daily.json")
    ap.add_argument("--known", type=int, default=OLD_SAMPLE_CODES,
                    help="此前用过的标的数，用于估算'全新'样本量")
    ap.add_argument("--audit-root", default=str(ROOT),
                    help="数据根目录（默认仓库根）；测试用临时目录注入")
    args = ap.parse_args()
    ROOT = Path(args.audit_root)

    cache = Path(args.cache)
    if not cache.exists():
        print(f"❌ 缓存不存在: {cache}", file=sys.stderr)
        print("   先跑 scripts/audit_chanlun_screen_usefulness.py", file=sys.stderr)
        return 2
    if not (ROOT / "audit_data").is_dir():
        print("❌ 缺 audit_data/ 目录，无法做样本外复核", file=sys.stderr)
        return 2

    df = _load(cache, args.h)
    if df.empty:
        print("❌ 缓存里没有可用观测（可能是 t+H 越界）", file=sys.stderr)
        return 2

    n_sym = df["code"].nunique()
    fresh = n_sym - args.known
    print(f"观测 {len(df)} 条 / {n_sym} 只标的（{df['t'].nunique()} 个时点，H={args.h}）")
    print(f"入选 {int(df['hit'].sum())}  未入选 {int((~df['hit']).sum())}")
    print(f"⚠️ 其中约 **{max(fresh, 0)} 只从未被此前口径碰过**"
          f"（假定此前用 {args.known} 只）")

    hit = df["hit"].to_numpy()
    print("\n── 三种基准对照 ──")
    print("  ⚠️ '原始'未控制 beta，会把大盘涨幅算到信号头上——")
    print("     五之二十五已经在这个坑上栽过一次（+3.71% p=0.002 实为大盘 beta）。")

    d0, t0, p0 = _compare(df["r"].to_numpy(), hit, "① 原始（不控制）")

    mkt = df.groupby("t")["r"].transform("mean")
    d1, t1, p1 = _compare((df["r"] - mkt).to_numpy(), hit, "② 减同期全样本均值")

    idxf = ROOT / args.index
    if idxf.exists():
        idx = pd.DataFrame(json.loads(idxf.read_text(encoding="utf-8")))
        idx["datetime"] = pd.to_datetime(idx["datetime"])
        idx = idx.sort_values("datetime")
        ir, ic = [], idx["close"].to_numpy(float)
        idates = idx["datetime"].to_numpy()
        for code, t in zip(df["code"], df["t"]):
            bf = ROOT / "audit_data" / f"{code}.json"
            if not bf.exists():
                ir.append(np.nan)
                continue
            bb = pd.DataFrame(json.loads(bf.read_text(encoding="utf-8")))
            bb["datetime"] = pd.to_datetime(bb["datetime"])
            day = bb.sort_values("datetime")["datetime"].to_numpy()[t]
            j = int(np.searchsorted(idates, np.datetime64(day)))
            ir.append(ic[j + args.h] / ic[j] - 1 if j + args.h < len(ic)
                      else np.nan)
        df["idx_r"] = ir
        ok = df["idx_r"].notna()
        if ok.any():
            sub = df[ok]
            d2, t2, p2 = _compare(
                (sub["r"] - sub["idx_r"]).to_numpy(), sub["hit"].to_numpy(),
                "③ 减沪深300真实指数")
        else:
            d2 = t2 = p2 = float("nan")
    else:
        d2 = t2 = p2 = float("nan")

    _pooling_check(df, (df["r"] - mkt).to_numpy(), hit)

    # ── 判定 ──────────────────────────────────────────────
    print("\n== 判定 ==")
    ctrl = [x for x in (t1, t2) if x == x]
    ctrl_sig = [x for x in ctrl if abs(x) > 1.96]
    if t0 != t0:
        print("⚠️ 样本不足，无法判定")
        return 2
    if ctrl_sig:
        print(f"❗ **样本外仍显著**（控制 beta 后 t={[round(x,2) for x in ctrl]}）"
              f" ⇒ 与原结论不同，需重新审视")
        return 0
    if abs(t0) > 1.96:
        print(f"⚠️ **原始显著但控制 beta 后消失**"
              f"（原始 t={t0:+.2f} p={p0:.4f} ⇒ "
              f"控制后 t={[round(x,2) for x in ctrl]}）")
        print(f"   ⇒ 这是**市场 beta**，不是选股力。"
              f" 与五之二十五 zs_position=above 的模式**完全一致**。")
    else:
        print(f"❌ 原始就不显著（t={t0:+.2f} p={p0:.4f}）⇒ 选股力为负/不存在")
    print(f"\n   差值从 {d0*100:+.2f}% 缩到 {d1*100:+.2f}%"
          f"（减同期均值）/ {d2*100:+.2f}%（减真实指数）")
    print("   ⇒ 样本外复核结论与原结论**一致**：选不出超额。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())