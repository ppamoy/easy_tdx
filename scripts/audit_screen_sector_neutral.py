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


def _fama_macbeth(joint: pd.DataFrame, min_dof: int = 10) -> tuple[float, float, float, int, int]:
    """Fama-MacBeth 回归：控制行业 + 市值后，"被选中"还有没有解释力。

    ⚠️ 为什么必须做这个：前面都是**分组减均值**（非参数、分箱粒度是折中）。
       回归能**同时**纳入多个控制变量，是更严格的口径。

    ⚠️⚠️ 自己实现 OLS（不引 statsmodels）——CI 里不该为单个审计脚本加依赖。

    ⚠️⚠️ 行业固定效应**必须用粗分类**。第一版用完整申万行业：
       47 行业 = 46 个虚拟变量，加截距/hit/log市值 共 **49 参数**，
       而每个时点只有 **57 观测** ⇒ 自由度仅 8，模型**接近饱和**，
       R²=0.93 是**过拟合**，且 beta 被扭曲成 **+1.25%（符号都反了）**。
       改用申万**一级**（前 3 位）后 beta 回到 −1.40%，与分组口径一致。

    标准误：Fama-MacBeth 的做法是对**逐时点系数**取均值，
    其标准误 = 这些系数的样本标准差 / sqrt(时点数)——
    这天然按时点聚类（同一时点观测不独立）。
    """
    df = joint.copy()
    df["ind_fine"] = df["ind"]
    df["ind"] = df["ind"].astype(str).str[:3]      # 申万一级
    levels = sorted(df["ind"].unique())
    di = {k: i for i, k in enumerate(levels[1:])}  # 省略第一个作基准

    n_par = 3 + max(0, len(levels) - 1)            # 截距+hit+logmcap+行业虚拟
    rows = []
    for _, g in df.groupby("t"):
        if g["hit"].nunique() < 2 or len(g) - n_par < min_dof:
            continue
        D = np.zeros((len(g), len(levels) - 1))
        for i, v in enumerate(g["ind"].values):
            j = di.get(v)
            if j is not None:
                D[i, j] = 1.0
        X = np.column_stack([np.ones(len(g)),
                             g["hit"].astype(float).to_numpy(),
                             g["logmcap"].to_numpy(), D])
        y = g["r"].to_numpy(float)
        XtX = X.T @ X
        try:
            inv = np.linalg.pinv(XtX)
        except Exception:        # noqa: BLE001
            continue
        b = inv @ (X.T @ y)
        resid = y - X @ b
        n, k = X.shape
        if n <= k:
            continue
        s2 = float(resid @ resid) / (n - k)
        sse = float(resid @ resid)
        sst = float(((y - y.mean()) @ (y - y.mean())))
        r2 = 1.0 - sse / sst if sst > 0 else 0.0
        rows.append((float(b[1]), r2, int(n - k)))

    if len(rows) < 5:
        return float("nan"), float("nan"), float("nan"), 0, n_par
    arr = np.array(rows, dtype=float)
    mb = float(arr[:, 0].mean())
    se = (float(arr[:, 0].std(ddof=1)) / np.sqrt(len(arr))
          if len(arr) > 1 else float("nan"))
    return mb, se, float(arr[:, 1].mean()), len(rows), n_par


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
    joint_t = joint_p = float("nan")
    fm_t = fm_p = mb = float("nan")
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

        # ── 4) 行业 + 市值**联合**中性化 ────────────────────
        # ⚠️⚠️ 分开做**不够**：行业与市值强相关（实测 Spearman ρ=0.827，
        #    因为银行/石油天生大市值、白酒天生小市值）。单独减行业均值
        #    之后，组内仍残留市值差异；单独减市值均值之后，组内仍残留
        #    行业差异。必须**同时**按 (行业, 市值分位) 分组减均值。
        joint = mdf.merge(df[["code", "t", "ind"]], on=["code", "t"],
                          how="left")
        joint["mcap_bin"] = pd.qcut(joint["mcap"], 3, labels=False,
                                    duplicates="drop")
        joint["rel"] = (joint["r"]
                        - joint.groupby(["ind", "mcap_bin"],
                                        observed=True)["r"].transform("mean"))
        rel_j = joint["rel"].to_numpy()
        hit_j = joint["hit"].to_numpy()
        _compare(rel_j, hit_j,
                 "行业+市值**联合**中性化后（减去同(行业×市值分位)均值）")
        a3, b3 = rel_j[hit_j], rel_j[~hit_j]
        if len(a3) > 1 and len(b3) > 1:
            d4 = float(a3.mean() - b3.mean())
            se4 = float(np.sqrt(a3.var(ddof=1) / len(a3)
                                + b3.var(ddof=1) / len(b3)))
            joint_t = d4 / se4 if se4 > 0 else float("nan")
            joint_p = (erfc(abs(joint_t) / sqrt(2))
                       if joint_t == joint_t else float("nan"))

            # 量化"分开做到底漏了多少"——这是联合口径的价值所在
            print(f"  ⇒ 联合口径比行业单独口径的差异变化: "
                  f"{(d4 - d) * 100:+.2f}%")

            # ── 5) Fama-MacBeth 回归（最严格口径）────────────
            j2 = joint.copy()
            j2["logmcap"] = np.log(j2["mcap"].clip(lower=1e-6))
            mb, mb_se, mb_r2, n_tp, n_par = _fama_macbeth(j2)
            fm_t = mb / mb_se if mb_se == mb_se and mb_se > 0 else float("nan")
            fm_p = (erfc(abs(fm_t) / sqrt(2))
                    if fm_t == fm_t else float("nan"))
            print(f"\n── Fama-MacBeth 回归（行业一级固定效应 + log市值）──")
            print(f"  成功回归时点 {n_tp}，每时点约 {n_par} 参数"
                  f"（已用**粗行业**，避免自由度耗尽）")
            print(f"  「被选中」系数 = {mb*100:+.3f}% / 20日"
                  f"   标准误 {mb_se*100:.3f}%")
            print(f"  t = {fm_t:+.2f}   p = {fm_p:.4f}"
                  f"   平均 R² = {mb_r2:.4f}")
            print(f"  ⇒ {'✅ 显著（95%）' if fm_t == fm_t and abs(fm_t) > 1.96 else '**不显著**'}")

    # ⚠️ 所有口径都**不显著**才算真的没戏；任一显著都要报告出来。
    if t != t:
        verdict = "⚠️ 样本不足，无法判定"
    elif (abs(t) > 2 or (size_t == size_t and abs(size_t) > 2)
          or (joint_t == joint_t and abs(joint_t) > 2)
          or (fm_t == fm_t and abs(fm_t) > 1.96)):
        verdict = (f"{'✅ 显著为正' if d > 0 else '❌ 显著为负'}"
                   f"（行业 t={t:+.2f}, p={p:.4f}；"
                   f"市值 t={size_t:+.2f}, p={size_p:.4f}；"
                   f"联合 t={joint_t:+.2f}, p={joint_p:.4f}；"
                   f"FM t={fm_t:+.2f}, p={fm_p:.4f}）")
    else:
        verdict = (f"❌ **与零无显著差异**（行业 t={t:+.2f}, p={p:.4f}；"
                   f"市值 t={size_t:+.2f}, p={size_p:.4f}；"
                   f"联合 t={joint_t:+.2f}, p={joint_p:.4f}；"
                   f"FM t={fm_t:+.2f}, p={fm_p:.4f}）"
                   f" ⇒ 四种口径（指数/行业/市值/回归）均选不出超额")
    print(f"\n== 判定: {verdict} ==")
    print(f"   （行业集中度: {concentrated}）")
    print("⚠️ 口径提醒：这是**横截面选股**检验；即便为正也不代表"
          "能跑赢买入持有（五之十八未证明）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
