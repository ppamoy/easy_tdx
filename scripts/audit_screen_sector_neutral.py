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


# ── 多重比较 ────────────────────────────────────────────
# ⚠️ 已实测的各筛选口径（市场控制后），来源 audit_chanlun_screen_usefulness.py。
#    每加一个新维度都要往这里登记，否则校正时数漏了口径会**低估** N。
MEASURED_BASES: list[tuple[str, float, float, float]] = [
    # ⚠️⚠️ **同一个 120 只样本**上测的 10 个口径（2025-10 补测）。
    #    此前 6 个结构口径用的是 60 只、4 个 signal_type 用的是 120 只，
    #    两者混在一起做多重比较是**不严格**的（样本不同⇒方差不同，
    #    校正门槛就不该用同一个 p 分布）。现已全部统一到 120 只。
    #    统一后的口径: 120 只A股 / 8 时点 / PIT / H=20 / 市场控制后
    # (口径, 超额%, t, p)
    ("any_buy 基线",       +0.12, +0.22, 0.8278),
    ("zs_position=above",  -1.39, -1.56, 0.1189),
    ("trend=up",           -0.27, -0.39, 0.6933),
    ("trend=down",         +0.56, +0.84, 0.3999),
    # ⚠️⚠️ 几乎**没测到东西**：端点 has_beichi 只有一个 bool，
    #    `bool(None)==False` ⇒ "any"/"false" **完全等价**（三选一是假的）。
    #    而"背驰"是**历史累计**的，t=130 时已有 2 个、之后单调增长
    #    ⇒ has_beichi=true 只在**极早期**（背驰仍为 0）才过滤得掉东西。
    #    实测：120 只里只有 **13/467（2.8%）** 入选被过滤掉，
    #    12/120 只股票受影响 ⇒ 与基线（+0.12% p=0.8278）**统计上无法区分**。
    #    ⇒ 下面这个 −0.20% **不能**当作"背驰无用"的证据；
    #      只能说"这个过滤器在实测样本上形同虚设"。
    ("has_beichi=true",    -0.20, -0.36, 0.7214),
    ("zs_position=below",  +0.68, +1.03, 0.3010),
    ("signal_type=1buy",   -0.81, -1.09, 0.2752),
    ("signal_type=2buy",   -1.04, -0.51, 0.6120),
    ("signal_type=3buy",   +0.77, +1.10, 0.2709),
    ("signal_type=1sell",  -0.46, -0.58, 0.5648),
    # ⚠️ 本轮新增的 3 个口径（端点一直支持，审计脚本此前**没有开关**）
    # ⚠️ inside 用**全量 286 只**重跑（120 只只有 134 条入选，样本太轻）。
    #    三个基准：原始 t=+2.87 p=0.0041；减同期均值 t=+2.07 p=0.0388；
    #    减沪深300 t=+2.72 p=0.0065 ⇒ **不是 beta**（与上面
    #    zs_position=above 的模式**相反**——那个是 beta 假象）。
    #
    # ⚠️⚠️ 但它**仍然扛不住校正**（N=13 时 Bonferroni α'=0.0038，
    #    而 p=0.0223），所以**不能**用它推翻"选股不可用"。
    #
    # ⚠️ 效应随"排除低入选次数的股票"**单调衰减**（全量 286 只）：
    #      全部观测      t=+2.28  p=0.0223   （入选 292 / 未选 1996）
    #      入选次数>=2   t=+2.05  p=0.0404
    #      入选次数>=3   t=+0.70  p=0.4844   ⚠️ 基本消失
    #    ⇒ 显著性**部分依赖**"只被选中一两次"的股票。
    #    入选次数分布：1次113只 / 2次50只 / 3次21只 / 4次4只。
    #    ⚠️ 池化诊断加权③的"3~15"上界在本数据里**形同虚设**（最大仅4次），
    #       它实际只做了"排除入选1~2次"，**不是**名字暗示的"保留中等"。
    # ⚠️⚠️ 已做**样本外**复测（前半段 t<=750，286 只）：
    #      zs_position=inside  +0.02%  t=+0.05  p=0.9607  ⇒ **完全消失**
    #      any_buy 基线        +0.05%  t=+0.13  p=0.8934  ⇒ 对照组也平
    #    ⇒ 下面的 +1.34% 是**样本内**的，换窗口就归零 ⇒ **已证伪**
    #      "缠论能按中枢位置选股"。这**加强**了"选股不可用"的结论。
    ("zs_position=inside", +1.34, +2.28, 0.0223),
    ("min_quality>=80",    +0.24, +0.41, 0.6801),
    ("min_zs_count>=5",    +0.88, +1.54, 0.1240),
]

# ⚠️ 60 只口径下的旧数值，**仅供对照**，**不参与**多重比较校正。
#    (口径, 超额%, t, p, 标的数)
LEGACY_60_BASES = [
    ("any_buy 基线",       -0.41, -0.51, 0.6132, 60),
    ("zs_position=above",  -1.40, -1.14, 0.2560, 60),
    ("trend=up",           -1.24, -1.24, 0.2137, 60),
    ("trend=down",         +0.88, +0.93, 0.3506, 60),
    ("has_beichi=true",    -0.99, -1.22, 0.2226, 60),
    ("zs_position=below",  +0.32, +0.39, 0.6944, 60),
]

# ⚠️⚠️ 两层口径**不同、不矛盾**，必须讲清楚，否则读者会以为自相矛盾：
#
#   择时层：持有该信号期间，收益 vs **同窗极值基准**
#           ⇒ 1buy 6/6 窗正（甚至优于随机极值入场）
#   选股层：某时点**最新信号**是该类型，持有 20 日 vs **同市场其他股票**
#           ⇒ 无差异（连 1buy/1sell 也没有）
#
#   翻译成人话：
#     择时层回答"信号发生时**该不该买**"；选股层回答"该买的时候**买哪只**"。
#     前者成立不代表后者成立——你可能该买，只是不知道买哪一只。
#
# ⚠️ 反过来也不成立：选股层有效不代表择时层有效。
#   两层必须**分别**报告，不能拿一层的结论替另一层背书。


def multiplicity_report() -> None:
    """多重比较校正 + p 值均匀性检验。

    ⚠️ 为什么必须做：我已经**假阳性**过一次——五之二十五测出
       `zs_position=above` 的 +3.71% t=+3.16 p=0.002，一度写进报告，
       后来发现那是**市场 beta**（减去同期沪深300 后 p=0.15）。

    ⚠️ 单个口径"不显著"是弱证据（可能只是没测出来）；
       **校正后仍无一显著**才是强证据。两者不能混为一谈。
    """
    import numpy as np

    rows = MEASURED_BASES
    n = len(rows)
    ps = np.array([r[3] for r in rows])
    pmin = float(ps.min())
    print(f"\n{'='*62}")
    print(f"── 多重比较校正（N = {n} 个已实测筛选口径）──")
    print(f"  最小 p = {pmin:.4f}（{rows[int(ps.argmin())][0]}）")
    print(f"  α=0.05 下显著的个数 = {int((ps < 0.05).sum())} / {n}")

    bon = 0.05 / n
    print(f"\n  ① Bonferroni: α' = 0.05/{n} = {bon:.4f}")
    print(f"     ⇒ {'**有**口径通过校正' if pmin < bon else '**无**口径通过校正'}"
          f"（最小 p={pmin:.4f} {'<' if pmin < bon else '≥'} α')")

    print("\n  ② Holm-Bonferroni（逐步放宽，FWER 仍受控）:")
    order = np.argsort(ps)
    for rank, i in enumerate(order):
        thr = 0.05 / (n - rank)
        print(f"     第{rank+1}顺位 {rows[i][0]:<18} p={ps[i]:.4f} "
              f"vs α'={thr:.4f} ⇒ {'通过' if ps[i] < thr else '不通过'}")

    print("\n  ③ Benjamini-Hochberg（FDR@5%）:")
    any_bh = False
    for rank, i in enumerate(order):
        thr = 0.05 * (rank + 1) / n
        found = ps[i] <= thr
        any_bh = any_bh or found
        print(f"     p={ps[i]:.4f} vs 阈值={thr:.4f} ⇒ "
              f"{'发现' if found else '不发现'}")
    print(f"     ⇒ 有发现: {any_bh}")

    try:
        from scipy.stats import kstest
        d, pu = kstest(ps, "uniform")
        print(f"\n  ④ p 值均匀性 KS 检验: D={d:.3f} p={pu:.4f} ⇒ "
              f"{'p 值分布**均匀**，与「全无效应」一致' if pu > 0.05 else '分布**不均匀**，可能存在真效应'}")
    except ImportError:
        print("\n  ④ 无 scipy，跳过均匀性检验")

    if pmin >= bon and not any_bh:
        print(f"\n  ⇒ {n} 个口径、最小 p={pmin:.4f}，"
              f"**校正后仍无一显著**。")
        print("     这比「每个口径各自不显著」强得多——"
              "不是「没测出来」，是**校正后依然没有**。")


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
    multiplicity_report()
    print(f"   （行业集中度: {concentrated}）")
    print("⚠️ 口径提醒：这是**横截面选股**检验；即便为正也不代表"
          "能跑赢买入持有（五之十八未证明）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
