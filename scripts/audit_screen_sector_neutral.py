#!/usr/bin/env python3
"""审计「缠论选股」的**行业中性化**效果（五之二十九）。

背景
----
五之二十七/二十八 测出四个筛选维度都"与零无显著差异"，
但当时只用**沪深300**做基准，并明确留了个缺口：

    ⚠️ 未做行业中性化——若入选组集中在某行业，残留行业 beta 可能性未排除

本脚本补这个缺口。

做什么
------
1 从通达信 API 取**申万行业**分类（SecurityInfo.industry_sw）
2 检验入选组是否**集中在少数行业**（卡方均匀性）
3 把每只股票的收益减去**同行业均值**，重算"入选 vs 未入选"的超额
   —— 这一步才是真正的"行业中性"

⚠️ 口径提醒：这是**横截面选股**检验，与"择时"是两回事。
"""
from __future__ import annotations

import argparse
import json
import sys
from math import erfc, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

PRE2MKT = {"sh": 1, "sz": 0, "bj": 2}   # 通达信 Market 枚举


def load_industries(codes: set[str], cache: Path | None) -> dict[str, dict]:
    """取申万行业分类。cache 存在则直接复用，避免反复连服务器。"""
    if cache and cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from easy_tdx.client import TdxClient

    want = {f"{PRE2MKT[c[:2]]}{c[2:]}": c for c in codes}
    client = TdxClient()
    try:
        df = client.get_security_list_all()
    finally:
        client.disconnect()
    if df is None or not len(df):
        print("❌ 取不到证券列表，无法做行业中性化")
        raise SystemExit(2)

    out: dict[str, dict] = {}
    for _, r in df.iterrows():
        key = f"{int(r['market'])}{r['code']}"
        if key in want:
            out[want[key]] = {"name": str(r["name"]),
                              "tdx": str(r["industry_tdx"]),
                              "sw": str(r["industry_sw"])}
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="/tmp/screen_audit_cache.json",
                    help="audit_chanlun_screen_usefulness.py 产生的缓存")
    ap.add_argument("--industry-cache", default="/tmp/easy_tdx_industry.json")
    ap.add_argument("--limit", type=int, default=60)
    args = ap.parse_args()

    paths = sorted(Path("audit_data").glob("*.json"))[: args.limit]
    if not paths:
        print("❌ audit_data/ 无数据，无法审计（不要拿空目录凑结论）")
        return 2

    cache = Path(args.cache)
    if not cache.exists():
        print(f"❌ 找不到 {cache}；先跑 audit_chanlun_screen_usefulness.py")
        return 2
    res = json.loads(cache.read_text(encoding="utf-8"))
    if not res:
        print("❌ 缓存为空，无法审计")
        return 2

    codes = {r["code"].split("_")[0] for r in res}
    ind = load_industries(codes, Path(args.industry_cache))
    print(f"缓存 {len(res)} 只，其中有申万行业标签 {len(ind)} 只")

    rec = []
    for r in res:
        code = r["code"].split("_")[0]
        if code not in ind:
            continue
        sw = ind[code]["sw"]
        for t, x in zip(r.get("hit_pts", []), r.get("hit", [])):
            rec.append((code, t, x, True, sw))
        for t, x in zip(r.get("miss_pts", []), r.get("miss", [])):
            rec.append((code, t, x, False, sw))
    if not rec:
        print("❌ 没有可用的（收益, 时点, 行业）配对")
        return 2

    df = pd.DataFrame(rec, columns=["code", "t", "r", "hit", "ind"])

    # ── 1) 入选组是否集中在少数行业 ────────────────────────
    hit = df[df["hit"]]
    conc = hit["ind"].value_counts()
    print(f"\n入选观测 {len(hit)} 条，分布在 {conc.nunique()} 个行业")
    print("最集中的 5 个:", {str(k): int(v) for k, v in conc.head(5).items()})
    concentrated = "无法判定"
    if conc.nunique() > 1 and len(conc) >= 2:
        try:
            from scipy.stats import chisquare
            chi, pv = chisquare(conc.values)
            print(f"卡方均匀性: chi2={chi:.1f}  p={pv:.4f}"
                  f"  ⇒ {'**集中**' if pv < 0.05 else '不集中'}")
            concentrated = "集中" if pv < 0.05 else "不集中"
        except ImportError:
            print("⚠️ 无 scipy，跳过卡方（不影响中性化结论）")

    # ── 2) 行业中性化后的超额 ────────────────────────────
    # ⚠️ 关键是减去**同行业**均值：这样"某行业整体上涨"就不会
    #    被算成"选股选得好"。
    g = df.groupby("ind")["r"].transform("mean")
    rel = (df["r"] - g).to_numpy()
    is_hit = df["hit"].to_numpy()
    a, b = rel[is_hit], rel[~is_hit]
    if len(a) < 5 or len(b) < 5:
        print("⚠️ 样本不足，无法判定")
        return 2

    d = float(a.mean() - b.mean())
    se = float(np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)))
    t = d / se if se > 0 else float("nan")
    p = erfc(abs(t) / sqrt(2)) if t == t else float("nan")
    print(f"\n── 行业中性化后（减去**同行业**均值）──")
    print(f"  入选   n={len(a):<5} {a.mean()*100:+.2f}%")
    print(f"  未入选 n={len(b):<5} {b.mean()*100:+.2f}%")
    print(f"  差 = {d*100:+.2f}%  t={t:+.2f}  p={p:.4f}")

    if t != t:
        verdict = "⚠️ 样本不足，无法判定"
    elif abs(t) > 2:
        verdict = (f"{'✅ 显著为正' if d > 0 else '❌ 显著为负'}"
                   f"（t={t:+.2f}, p={p:.4f}）")
    else:
        verdict = (f"❌ **与零无显著差异**（t={t:+.2f}, p={p:.4f}）"
                   f" ⇒ 行业中性化后仍选不出超额")
    print(f"\n== 判定: {verdict} ==")
    print(f"   （行业集中度: {concentrated}）")
    print("⚠️ 口径提醒：这是**横截面选股**检验；即便为正也不代表"
          "能跑赢买入持有（五之十八未证明）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
