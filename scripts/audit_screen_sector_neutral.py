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


def _compare(rel: np.ndarray, is_hit: np.ndarray, label: str) -> None:
    """统一的入选 vs 未入选比较输出。判定用 |t|>2。"""
    a, b = rel[is_hit], rel[~is_hit]
    if len(a) < 5 or len(b) < 5:
        print(f"\n── {label} ── 样本不足，跳过")
        return
    d = float(a.mean() - b.mean())
    se = float(np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)))
    t = d / se if se > 0 else float("nan")
    p = erfc(abs(t) / sqrt(2)) if t == t else float("nan")
    print(f"\n── {label} ──")
    print(f"  入选   n={len(a):<5} {a.mean()*100:+.2f}%")
    print(f"  未入选 n={len(b):<5} {b.mean()*100:+.2f}%")
    print(f"  差 = {d*100:+.2f}%  t={t:+.2f}  p={p:.4f}")
    print(f"  ⇒ {'显著' if t == t and abs(t) > 2 else '**不显著**'}")


def load_float_shares(codes: set[str], cache: Path | None) -> dict[str, float]:
    """取流通股本，用于算**流通市值**。

    ⚠️ 小盘效应是 A股已知最强的异象之一，若选股只是"挑中小盘股"，
    那它赚的是**小盘效应**而不是缠论的价值。
    """
    if cache and cache.exists():
        raw = json.loads(cache.read_text(encoding="utf-8"))
        out: dict[str, float] = {}
        for k, v in raw.items():
            # 容忍两种缓存格式：裸数字，或 {"liutong": ...} 这样的字典
            # （早期的一次性脚本存的是后者，正式脚本也该能读）
            if isinstance(v, dict):
                v = v.get("liutong") or v.get("float_shares")
            if v is None:
                continue
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                continue
        return out

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from easy_tdx.client import TdxClient
    from easy_tdx.models.enums import Market

    mkt_of = {"sh": Market.SH, "sz": Market.SZ, "bj": Market.BJ}
    client = TdxClient()
    out: dict[str, float] = {}
    try:
        for code in sorted(codes):
            mkt = mkt_of.get(code[:2])
            if mkt is None:
                continue
            try:
                df = client.get_finance_info(mkt, code[2:])
            except Exception:      # noqa: BLE001 - 单只失败不该中断全批
                continue
            if df is not None and len(df):
                out[code] = float(df.iloc[0]["liutong_guben"])
    finally:
        client.disconnect()
    if cache and out:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out, ensure_ascii=False),
                         encoding="utf-8")
    return out


def _with_market_cap(res: list[dict], shares: dict[str, float]) -> pd.DataFrame:
    """给每条观测补上**时点**流通市值（亿元）。

    ⚠️ 必须用**该时点的收盘价** × 流通股本。
    用最新价会把未来信息带进历史——那就是未来函数，测出来的不可信。
    """
    rows = []
    for r in res:
        code = r["code"].split("_")[0]
        if code not in shares:
            continue
        f = Path("audit_data") / f"{r['code']}.json"
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
            if t < len(close):
                rows.append((code, t, x, bool(hit),
                             float(close[t] * shares[code] / 1e8)))
    return pd.DataFrame(rows, columns=["code", "t", "r", "hit", "mcap"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="/tmp/screen_audit_cache.json",
                    help="audit_chanlun_screen_usefulness.py 产生的缓存")
    ap.add_argument("--industry-cache", default="/tmp/easy_tdx_industry.json")
    ap.add_argument("--cap-cache", default="/tmp/easy_tdx_float_shares.json")
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

    _compare(rel, is_hit, "行业中性化后（减去**同行业**均值）")
    d = float(a.mean() - b.mean())
    se = float(np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)))
    t = d / se if se > 0 else float("nan")
    p = erfc(abs(t) / sqrt(2)) if t == t else float("nan")

    # ── 3) 市值中性化 ────────────────────────────────────
    # ⚠️ 小盘效应是 A股已知最强的异象之一。若选股只是"挑中了小盘股"，
    #    它赚的钱其实是**小盘效应**，不是缠论的价值——必须排除。
    size_t = size_p = float("nan")
    mdf = _with_market_cap(res, load_float_shares(codes, Path(args.cap_cache)))
    if not mdf.empty:
        ca = mdf[mdf["hit"]]["mcap"].to_numpy()
        cb = mdf[~mdf["hit"]]["mcap"].to_numpy()
        print("\n── 入选组 vs 未入选组的流通市值（中位数，亿元）──")
        print(f"  入选 {np.median(ca):.1f}   未入选 {np.median(cb):.1f}"
              f"   差 {np.median(ca) - np.median(cb):+.1f}")
        try:
            from scipy.stats import mannwhitneyu
            _, pu = mannwhitneyu(ca, cb)
            print(f"  Mann-Whitney p={pu:.4f} ⇒ "
                  f"{'市值**显著**不同' if pu < 0.05 else '市值无显著差异'}")
        except ImportError:
            print("  ⚠️ 无 scipy，跳过秩检验（不影响中性化结论）")

        # ⚠️ 市值必须用**时点**收盘价 × 流通股本。用最新价会把未来信息
        #    带进历史，那就是未来函数，测出来的结论不可信。
        bins = pd.qcut(mdf["mcap"], 5, labels=False, duplicates="drop")
        mdf = mdf.assign(rel=mdf["r"] - mdf.groupby(bins)["r"].transform("mean"))
        rel_s = mdf["rel"].to_numpy()
        hit_s = mdf["hit"].to_numpy()
        _compare(rel_s, hit_s, "市值中性化后（减去**同市值五分位**均值）")
        a2, b2 = rel_s[hit_s], rel_s[~hit_s]
        if len(a2) > 1 and len(b2) > 1:
            d3 = float(a2.mean() - b2.mean())
            se3 = float(np.sqrt(a2.var(ddof=1) / len(a2)
                                + b2.var(ddof=1) / len(b2)))
            size_t = d3 / se3 if se3 > 0 else float("nan")
            size_p = (erfc(abs(size_t) / sqrt(2))
                      if size_t == size_t else float("nan"))

    # ⚠️ 两个口径都**不显著**才算真的没戏；任一显著都要报告出来。
    if t != t:
        verdict = "⚠️ 样本不足，无法判定"
    elif abs(t) > 2 or (size_t == size_t and abs(size_t) > 2):
        verdict = (f"{'✅ 显著为正' if d > 0 else '❌ 显著为负'}"
                   f"（行业中性 t={t:+.2f}, p={p:.4f}；"
                   f"市值中性 t={size_t:+.2f}, p={size_p:.4f}）")
    else:
        verdict = (f"❌ **与零无显著差异**（行业 t={t:+.2f}, p={p:.4f}；"
                   f"市值 t={size_t:+.2f}, p={size_p:.4f}）"
                   f" ⇒ 行业与市值中性化后仍选不出超额")
    print(f"\n== 判定: {verdict} ==")
    print(f"   （行业集中度: {concentrated}）")
    print("⚠️ 口径提醒：这是**横截面选股**检验；即便为正也不代表"
          "能跑赢买入持有（五之十八未证明）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
