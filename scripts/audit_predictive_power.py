#!/usr/bin/env python3
"""缠论买卖点「前瞻收益」实测 —— 回答「能否指导选股与择时」。

这是本次审计的结论层。前两层（结构不变式 / 未来函数）只证明「实现没写错」，
这一层才回答「有没有用」。

⚠️ 重要前提：本脚本允许**只在全量数据上算一次信号**，再回看每个信号的前瞻
收益。这在一般情况下是**未来函数**，但此处成立，因为
`scripts/audit_future_leak_real.py` 已实测证明：**截断序列与全量序列的早期
信号完全一致**（32 只 × 7 个检查点 = 224 组，0 违反）。既然历史信号不随
后续数据改变，全量算一次 == 逐 bar 推进的结果，于是可以用 O(n) 代替 O(n²)。
这个前提一旦被破坏（未来免疫回归），本脚本的结论立即作废 —— 故两者必须
一起跑，本脚本开头会提示。

三个必须回答的问题
------------------
Q1 择时力：某类买卖点出现后，未来 N 根 K 线的方向性收益，是否显著优于
   「同标的、同窗口的随机入场」？用配对重抽样得到经验 p 值。
Q2 选股力：能否用「缠论信号统计」横截面排序挑出未来表现更好的股票？
   —— 与未来收益做 Spearman 相关。
Q3 稳健性：结论在前后半段是否一致（符号是否翻转）。

方法论（避免自欺）
------------------
* 方向对齐：买点用 +r，卖点用 -r，统一成「押对方向的收益」。
* 配对随机基准：同标的、同窗口随机抽**同样数量**的入场点，重复 500 次，
  得到基准分布 → 真实均值的经验 p 值。避免"信号集中在上涨段"的假显著。
* 多重比较：6 类 × 4 窗口 = 24 次，Bonferroni 校正，同时报未校正 p。
* 样本量门槛：单类单窗口 < 30 不参与结论。
* 收益口径含**超额**：同时给相对沪深300 的同期收益，剔除大盘 beta。

用法：  .venv/bin/python scripts/audit_predictive_power.py
"""

from __future__ import annotations

import json
import sys
from math import erfc, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402

DATA_DIR = ROOT / "audit_data"

HORIZONS = (5, 10, 20, 60)
MIN_N = 30
BOOT = 500
BUY = {"1buy", "2buy", "2buy_s", "3buy"}  # V733：补入类二买（此前被漏掉）
SELL = {"1sell", "2sell", "2sell_s", "3sell"}  # V733：补入类二卖
SEED = 20241002
PIVOT = 5  # 对照组：局部极值窗口（±5 根）



def _pivot_indices(c: np.ndarray, w: int, low: bool) -> np.ndarray:
    """局部极值下标：买→局部低点，卖→局部高点（对照缠论笔端点的同义反复）。"""
    n = len(c)
    out = []
    for i in range(w, n - w):
        seg = c[i - w : i + w + 1]
        if low and c[i] == seg.min():
            out.append(i)
        elif not low and c[i] == seg.max():
            out.append(i)
    return np.array(out, dtype=int)


def norm_p(z: float) -> float:
    return float(erfc(abs(z) / sqrt(2)))


def main() -> int:
    files = sorted(DATA_DIR.glob("*.json"))
    if not files:
        print(f"❌ {DATA_DIR} 无数据，先跑 scripts/audit_fetch_real_data.py")
        return 2

    bench_file = DATA_DIR / "sh000300_daily.json"
    bench_df = None
    if bench_file.exists():
        bench_df = pd.DataFrame(json.loads(bench_file.read_text(encoding="utf-8")))
        bench_df["datetime"] = pd.to_datetime(bench_df["datetime"])

    files = [p for p in files if p.stem.split("_")[0] not in ("sh000300", "sh000001")]

    print("前提：本脚本依赖「历史信号不随后续数据改变」（未来免疫）。")
    print("      请先确认 scripts/audit_future_leak_real.py 为 0 违反。\n")

    # 收集：每只股票一次全量计算
    records: list[dict] = []
    closes_by_sym: dict[str, np.ndarray] = {}
    dates_by_sym: dict[str, pd.Series] = {}
    for p in files:
        code = p.stem.split("_")[0]
        df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
        df["datetime"] = pd.to_datetime(df["datetime"])
        closes = df["close"].to_numpy(dtype=float)
        closes_by_sym[code] = closes
        dates_by_sym[code] = df["datetime"]

        res = ChanlunAnalyser(code=code, frequency="daily", config=ChanlunConfig()).process_klines(df)
        n = len(closes)
        cnt: dict[str, int] = {}
        for m in res.mmds:
            if not m.bi:
                continue
            st = m.mmd_type.value.lower()
            if st not in BUY and st not in SELL:
                continue
            cnt[st] = cnt.get(st, 0) + 1
            idx = m.bi.end.bar_index
            if idx >= n - 1:
                continue
            is_buy = st in BUY
            rec: dict = {"symbol": code, "type": st, "idx": idx}
            for h in HORIZONS:
                if idx + h >= n:
                    continue
                r = closes[idx + h] / closes[idx] - 1.0
                rec[f"r{h}"] = float(r) if is_buy else float(-r)
            records.append(rec)
        print(f"  {p.stem:<18} 信号 {len(cnt):>3}  {cnt}")

    obs = pd.DataFrame(records)
    print(f"\n总信号 {len(obs)}")
    if obs.empty:
        print("无信号，无法评估")
        return 1

    rng = np.random.default_rng(SEED)
    print("\n" + "=" * 100)
    print("Q1 择时力：各类买卖点 押对方向收益 vs 配对随机基准（同标的同窗口，500 次重抽样）")
    print("=" * 100)
    print(f"{'类型':<7}{'窗口':>5}{'n':>5}{'信号均值':>10}{'随机基准':>10}{'随机p':>8}"
          f"{'极值基准':>10}{'极值p':>8}{'抗极值':>8}  判定")
    print("-" * 100)

    rows: list[dict] = []
    for st in sorted(BUY | SELL):
        sub = obs[obs["type"] == st]
        if len(sub) < MIN_N:
            print(f"{st:<7}{'—':>5}{len(sub):>5}  样本不足（<{MIN_N}），不参与结论")
            continue
        is_buy = st in BUY
        for h in HORIZONS:
            col = f"r{h}"
            vals = sub[col].dropna().to_numpy(dtype=float)
            if len(vals) < MIN_N:
                continue
            # 配对基准：按标的分组，每组随机抽同数量入场点，再按**样本量加权
            # 平均**合成一个总体基准均值。
            #
            # ⚠️ 自误报修正（V732）：第一版写成 `base += np.mean(rr, axis=1)`
            # 即对各标的的均值**求和**。30 只标的叠加后，基准分布的 sd 被放大
            # 约 sqrt(30)≈5.5 倍，于是 z=(obs-base)/sd 被系统性缩小 ——
            # 所有 p 值虚高到 0.63~0.96，"0/24 显著"是**我的脚本 bug 造成的
            # 假阴性**，不是真实结论。这里改为按样本量加权平均：
            # 总体均值 == 各组均值的加权平均，与信号均值的口径一致。
            base = np.zeros(BOOT)
            wsum = 0.0
            for sym, g in sub.groupby("symbol"):
                c = closes_by_sym[sym]
                k = len(g)
                lo, hi = 0, len(c) - h - 1
                if hi <= lo:
                    continue
                idxs = rng.integers(lo, hi, size=(BOOT, k))
                rr = c[idxs + h] / c[idxs] - 1.0
                if not is_buy:
                    rr = -rr
                base += np.mean(rr, axis=1) * k
                wsum += k
            if wsum == 0:
                continue
            base /= wsum

            # ── 更强的对照组：局部极值匹配基准 ──
            # 买点在**定义上**就靠近局部低点（笔的端点 = 分型极值），
            # 那么"买点后反弹"很可能只是"从局部低点买入当然会反弹"的同义反复，
            # 而非缠论的价值。故加一组对照：随机抽**同样是局部极值**的 bar
            # （买→局部低点，卖→局部高点，窗口 ±PIVOT），看缠论是否还能胜出。
            pbase = np.zeros(BOOT)
            pwsum = 0.0
            for sym, g in sub.groupby("symbol"):
                c = closes_by_sym[sym]
                k = len(g)
                cand = _pivot_indices(c, PIVOT, low=is_buy)
                cand = cand[(cand >= 0) & (cand + h < len(c))]
                if len(cand) < 5:
                    continue
                idxs = rng.choice(cand, size=(BOOT, k), replace=True)
                rr = c[idxs + h] / c[idxs] - 1.0
                if not is_buy:
                    rr = -rr
                pbase += np.mean(rr, axis=1) * k
                pwsum += k
            if pwsum:
                pbase /= pwsum
            obs_mean = float(np.mean(vals))
            b_mean = float(np.mean(base))
            sd = float(np.std(base)) or 1e-9
            z = (obs_mean - b_mean) / sd

            # 自校验：基准 sd 必须与「单样本 sd / sqrt(n_eff)」同量级。
            # 若基准 sd 反而**大于**单样本离散度，说明加权口径写错了
            # （第一版就是求和导致 sd 膨胀 5.5 倍），直接判定脚本有 bug，
            # 不允许带着错误数字出结论。
            pooled = sub[col].notna().to_numpy()
            _all = np.concatenate(
                [
                    (closes_by_sym[s][h:] / closes_by_sym[s][:-h] - 1.0)
                    for s in sub["symbol"].unique()
                ]
            )
            sd_expected = float(np.std(_all)) / sqrt(max(len(pooled), 1))
            if sd > 3 * sd_expected:
                raise AssertionError(
                    f"基准 sd={sd:.5f} 远大于理论值 {sd_expected:.5f} —— "
                    "配对基准口径写错了（疑似把各组均值求和而非加权平均）"
                )
            rows.append(
                {
                    "type": st,
                    "h": h,
                    "n": len(vals),
                    "mean": obs_mean,
                    "base": b_mean,
                    "excess": obs_mean - b_mean,
                    "p": norm_p(z),
                    "pbase": float(np.mean(pbase)) if pwsum else float("nan"),
                    "pexcess": obs_mean - float(np.mean(pbase)) if pwsum else float("nan"),
                    "pp": norm_p((obs_mean - float(np.mean(pbase))) / (float(np.std(pbase)) or 1e-9)) if pwsum else float("nan"),
                }
            )

    n_tests = len(rows)
    alpha_b = 0.05 / max(n_tests, 1)
    n_sig = 0
    n_vs = 0
    for r in rows:
        if r["p"] < alpha_b and r["excess"] > 0:
            mark, n_sig = "✅显著为正", n_sig + 1
        elif r["p"] < alpha_b and r["excess"] < 0:
            mark = "❌显著为负"
        elif r["p"] < 0.05:
            mark = "~未过Bonf"
        else:
            mark = "—不显著"
        pe = r["pexcess"]
        pp = r["pp"]
        if np.isfinite(pp) and pp < alpha_b and pe > 0:
            vs = "✅胜出"
        elif np.isfinite(pp) and pp < 0.05:
            vs = "~弱"
        else:
            vs = "❌消失"
        print(
            f"{r['type']:<7}{r['h']:>5}{r['n']:>5}{r['mean']:>10.3%}{r['base']:>10.3%}"
            f"{r['p']:>8.4f}{r['pbase']:>10.3%}{pp:>8.4f}{pe:>8.2%}  {mark} / 抗极值{vs}"
        )
        if np.isfinite(pp):
            n_vs += 1 if (pp < alpha_b and pe > 0) else 0
    print(f"\nBonferroni α = {alpha_b:.4f}（{n_tests} 次比较）；显著为正 {n_sig}/{n_tests}")
    print(f"抗极值对照：仍显著胜出 {n_vs}/{n_tests}")
    print("\n  ⚠️ 关键解读：「随机p」只证明信号优于随机入场；但买点在定义上就靠近")
    print("     局部低点，所以还要看「极值p」——信号是否优于**同样是局部低点**的")
    print("     随机入场。只有极值p也显著，才能说超额来自缠论结构而非同义反复。")

    # ── Q2 选股力 ──
    print("\n" + "=" * 100)
    print("Q2 选股力：横截面 —— 用全段信号统计预测「最后 60 根」收益（Spearman）")
    print("=" * 100)
    xs: list[dict] = []
    for p in files:
        code = p.stem.split("_")[0]
        c = closes_by_sym[code]
        if len(c) < 200:
            continue
        t = len(c) - 61
        sub = obs[(obs["symbol"] == code) & (obs["idx"] <= t)]
        n_buy = int((sub["type"].isin(BUY)).sum())
        n_sell = int((sub["type"].isin(SELL)).sum())
        fwd = float(c[-1] / c[t] - 1.0)
        # 相对沪深300 的超额
        exc = float("nan")
        if bench_df is not None:
            bc = bench_df["close"].to_numpy(dtype=float)
            bd = bench_df["datetime"]
            d0 = dates_by_sym[code].iloc[t]
            j = int((bd <= d0).sum()) - 1
            if 0 <= j and j + 60 < len(bc):
                exc = fwd - float(bc[j + 60] / bc[j] - 1.0)
        xs.append({"symbol": code, "n_buy": n_buy, "n_sell": n_sell, "net": n_buy - n_sell,
                   "fwd": fwd, "exc": exc})
    X = pd.DataFrame(xs)
    print(f"横截面样本 {len(X)} 只\n")
    for col, label in (("n_buy", "买点数"), ("n_sell", "卖点数"), ("net", "净买点")):
        for tgt, tl in (("fwd", "绝对收益"), ("exc", "超额收益")):
            v = X[[col, tgt]].dropna()
            if len(v) < 8:
                continue
            rx = v[col].rank().to_numpy()
            ry = v[tgt].rank().to_numpy()
            if np.std(rx) == 0 or np.std(ry) == 0:
                print(f"  {col:<7} vs {tl}  ρ=n/a（无变化）")
                continue
            rho = float(np.corrcoef(rx, ry)[0, 1])
            nn = len(v)
            tstat = rho * sqrt((nn - 2) / (1 - rho**2)) if abs(rho) < 1 else float("inf")
            pv = norm_p(tstat) if np.isfinite(tstat) else 0.0
            mark = "✅" if (pv < 0.05 and abs(rho) > 0.3) else "—"
            print(f"  {mark} {label:<6} vs 未来60根{tl}  ρ={rho:+.3f}  p={pv:.4f}  (n={nn})")

    print("\n  明细（按未来60根收益降序）：")
    for _, r in X.sort_values("fwd", ascending=False).iterrows():
        e = f"{r['exc']:+.2%}" if np.isfinite(r["exc"]) else "n/a"
        print(
            f"    {r['symbol']:<10} 买{int(r['n_buy']):>3} 卖{int(r['n_sell']):>3} "
            f"净{int(r['net']):>+4}  未来60根 {r['fwd']:+.2%}  超额 {e}"
        )

    # ── Q3 稳健性 ──
    print("\n" + "=" * 100)
    print("Q3 稳健性：各类型 20 根收益在前后半段是否同号")
    print("=" * 100)
    mid = obs["idx"].median()
    for st in sorted(BUY | SELL):
        sub = obs[(obs["type"] == st) & obs["r20"].notna()]
        if len(sub) < MIN_N * 2:
            print(f"  {st:<7} 样本不足（{len(sub)}）")
            continue
        e = sub[sub["idx"] <= mid]["r20"]
        l = sub[sub["idx"] > mid]["r20"]
        if len(e) < 15 or len(l) < 15:
            print(f"  {st:<7} 前后段各不足 15（{len(e)}/{len(l)}）")
            continue
        me, ml = float(e.mean()), float(l.mean())
        same = (me > 0) == (ml > 0)
        print(f"  {'同号✅' if same else '异号❌'} {st:<7} 前半 {me:+.3%}(n={len(e)})  后半 {ml:+.3%}(n={len(l)})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
