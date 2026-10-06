#!/usr/bin/env python3
"""V733：审计 **"缠论选股" 功能本身有没有用**（五之二十五）。

背景
----
UI 有一个 `StockPickView.vue` →「缠论选股」标签页 → 后端
`POST /screening/chanlun-scan`（`web/routers/screening.py:618`），
按缠论结构条件（信号类型/走势/中枢位置/背驰）筛股票，宣称"缠论原著选股"。

而本项目此前的横截面审计结论是：**选股维度显著为负**
（买点数 ρ=−0.239 p<0.0001、信号密度 ρ=−0.256，n=286）⇒ **选股不可用**。

⚠️ 那次测的是"信号数量"这一个维度。**这次直接测这个功能本身**：
   复刻端点里 `_chanlun_screen()` 的**完全相同**判定，
   看"被它选出来的股票"事后是否跑赢"没被选出来的"。

口径
----
- PIT：只用 t 时刻及之前的数据判定，与端点一致（`process_klines(df[:t+1])`）；
- 基准：同市场同期**未被选中**的股票（等权）；
- 持有期 H=20 个交易日；
- 对比口径：入选组均值超额 vs 未入选组，并做 t 检验。

⚠️ 纪律：先跑数据拿结果，再写结论；**不允许**"预期为负就先说它不行"。
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor
from math import erfc, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

H = 20
MIN_BARS = 120
# ⚠️ 每个再平衡点都要重跑完整缠论（PIT 要求），成本 = 时点数 × 单次分析。
#    实测 800 根 → 约 15 个时点。限 8 个点把单只成本降一半，
#    仍足以估计超额（池化样本量 = 标的数 × 8）。
MAX_POINTS = 8


def _fwd(c: np.ndarray, i: int) -> float | None:
    """i 之后 H 日收益（买入口径）。"""
    j = i + H
    if j >= len(c) or c[i] <= 0:
        return None
    return c[j] / c[i] - 1.0


def one_symbol(path_str: str, sig: str = "any_buy",
               trend: str = "any", zs_pos: str = "any",
               has_bc: str = "any") -> dict | None:
    """对一只股票，在每个再平衡时点判定"是否被缠论选股选中"。"""
    from easy_tdx.web.routers.screening import _chanlun_screen
    from easy_tdx.chanlun import ChanlunAnalyser

    p = Path(path_str)
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
        df = pd.DataFrame(rows)
        if "datetime" not in df.columns:
            return None
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values("datetime").reset_index(drop=True)
        c = df["close"].to_numpy(float)
        n = len(c)
        if n < MIN_BARS + H + 10:
            return None

        # 再平衡时点：从 MIN_BARS 起，每 H 步一次
        # ⚠️ 每个时点都要**重跑一遍完整缠论**（PIT 要求不能用未来数据），
        #    800 根K线约 15 个时点 ⇒ 单只很贵。所以限上限并支持分批。
        points = list(range(MIN_BARS, n - H, H))
        if len(points) > MAX_POINTS:  # 均匀抽样，保留时序分布
            step = len(points) / MAX_POINTS
            points = [points[int(k * step)] for k in range(MAX_POINTS)]
        if not points:
            return None

        hit = []   # 命中买入且事后有收益
        miss = []  # 未命中且事后有收益
        hit_pts: list[int] = []   # 与 hit 一一对应的时点
        miss_pts: list[int] = []
        for t in points:
            # 端点用 fetch_qfq_klines(...,0,500) → 约500根；这里用 t 之前的数据保证 PIT
            sub = df.iloc[: t + 1]
            if len(sub) < MIN_BARS:
                continue
            try:
                r = ChanlunAnalyser(code=p.stem, frequency="daily").process_klines(sub)
            except Exception:  # noqa: BLE001
                continue
            close = float(c[t])
            try:
                # ⚠️ must 用**端点自己的判定**，逐项透传 criteria
                ok, _ = _chanlun_screen(
                    r,
                    {"signal_type": sig, "trend": trend,
                     "zs_position": zs_pos,
                     "has_beichi": (None if has_bc == "any"
                                    else has_bc == "true")},
                    close,
                )
            except Exception:  # noqa: BLE001
                continue
            r20 = _fwd(c, t)
            if r20 is None:
                continue
            (hit_pts if ok else miss_pts).append(t)
            (hit if ok else miss).append(r20)
        if not hit and not miss:
            return None
        return {"code": p.stem, "hit": hit, "miss": miss,
                "n_pts": len(points), "sig": sig,
                # ⚠️ 必须记下**时点**，才能算"同期全市场均值"做基准。
                #    没有它就退化成'和大盘比'，而大盘涨跌会**全部算进信号头上**。
                "hit_pts": hit_pts, "miss_pts": miss_pts}
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="audit_data")
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default="")
    ap.add_argument("--cache", default="/tmp/screen_audit_cache.json")
    ap.add_argument("--signal-type", default="any_buy",
                    help="复刻端点的 signal_type 判定（默认 any_buy）")
    ap.add_argument("--trend", default="any", choices=("any", "up", "down"))
    ap.add_argument("--zs-position", default="any",
                    choices=("any", "above", "below", "inside"))
    ap.add_argument("--has-beichi", default="any",
                    choices=("any", "true", "false"))
    a = ap.parse_args()

    files = sorted(Path(a.data).glob("*.json"))[: a.limit]
    # ⚠️⚠️ 这里原来写成 `if cache_path.name.startswith("screen_audit_cache")`
    #    才加 tag —— 于是我传 `--cache /tmp/sc3.json` 时**根本没加 tag**，
    #    各种口径共用一个缓存。更糟的是那次运行是**在加 --zs-position 参数
    #    之前**发出去的，脚本按老逻辑跑，等于测了 zs_position=any。
    #    ⇒ 两条 bug 叠加，输出了"0 命中"这种一眼就假的结果。
    #    教训：**缓存键必须无条件由内容决定**，不能靠文件名约定。
    cache_path = Path(a.cache)
    tag = f"{a.signal_type}_{a.trend}_{a.zs_position}_{a.has_beichi}"
    if not cache_path.stem.endswith(tag):
        cache_path = cache_path.with_name(
            f"{cache_path.stem}_{tag}{cache_path.suffix}")
    if not files:
        print(f"❌ {a.data}/ 无数据，无法审计（不要拿空目录凑结论）")
        return 2
    print(f"审计「缠论选股」功能：{len(files)} 只，持有期 {H} 日")
    print(f"  判定口径 = 端点 _chanlun_screen 原样复刻："
          f"signal_type={a.signal_type} trend={a.trend} "
          f"zs_position={a.zs_position} has_beichi={a.has_beichi}")
    print(f"  缓存 = {cache_path}")

    cache = cache_path
    res: list[dict] = []
    if cache.exists():
        res = json.loads(cache.read_text(encoding="utf-8"))
        print(f"复用缓存 {len(res)} 只（口径 {a.signal_type}）")
    done = {r["code"] for r in res}
    todo = [str(f) for f in files if f.stem not in done]
    if todo:
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            for r in ex.map(one_symbol, todo,
                            [(a.signal_type, a.trend, a.zs_position,
                              a.has_beichi)] * len(todo)):
                if not r:
                    continue
                res.append(r)
                # ⚠️ 每只完成就落盘：否则一次超时就**全部白跑**（本次就这么丢过一次）
                cache.write_text(json.dumps(res, ensure_ascii=False),
                                 encoding="utf-8")

    if not res:
        print("❌ 无有效样本")
        return 2

    # ① 汇总口径：所有时点池化
    hit = np.array([x for r in res for x in r["hit"]], dtype=float)
    miss = np.array([x for r in res for x in r["miss"]], dtype=float)
    n_sym_hit = sum(1 for r in res if r["hit"])

    print(f"\n有效样本 {len(res)} 只（其中 {n_sym_hit} 只曾被选中），"
          f"池化入选 {len(hit)} / 未入选 {len(miss)} 个时点")

    def stat(v: np.ndarray, name: str) -> tuple[float, float]:
        if len(v) < 5:
            print(f"  {name:<10} n={len(v):<6} 样本不足")
            return float("nan"), float("nan")
        m, se = v.mean(), v.std(ddof=1) / sqrt(len(v))
        t = m / se if se > 0 else float("nan")
        print(f"  {name:<10} n={len(v):<6} 均值 {m*100:+.2f}%  "
              f"中位 {np.median(v)*100:+.2f}%  胜率 {(v>0).mean()*100:.1f}%  "
              f"t={t:+.2f}")
        return m, t

    # ── 市场控制（beta 调整）──────────────────────────────────
    # ⚠️⚠️ 本轮**实测踩到的坑**：zs_position=above 原始差 +3.71%(t=3.16,p=0.002)
    #    看着像重大发现——但那 2024-2025 A股整体上行，"站上中枢"的股票
    #    天然涨得多。**换成"相对同期全市场均值"后只剩 +1.61%, p=0.15 ⇒ 不显著**。
    #    不做这一步，就会把**大盘 beta 记在信号账上**（虚高的发现）。
    by_t: dict[int, list[float]] = {}
    for r in res:
        for t, x in zip(r.get("hit_pts", []), r.get("hit", [])):
            by_t.setdefault(t, []).append(x)
        for t, x in zip(r.get("miss_pts", []), r.get("miss", [])):
            by_t.setdefault(t, []).append(x)
    mkt = {t: float(np.mean(v)) for t, v in by_t.items() if len(v) >= 5}

    def _rel(xs: list[float], pts: list[int]) -> np.ndarray:
        """把收益减去**同一时点**的全市场均值。"""
        out = []
        for x, t in zip(xs, pts):
            if t in mkt:
                out.append(x - mkt[t])
        return np.array(out, dtype=float)

    rel_h = np.concatenate([_rel(r.get("hit", []), r.get("hit_pts", []))
                            for r in res]) if res else np.array([])
    rel_m = np.concatenate([_rel(r.get("miss", []), r.get("miss_pts", []))
                            for r in res]) if res else np.array([])

    if len(rel_h) > 5 and len(rel_m) > 5:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            d2 = float(rel_h.mean() - rel_m.mean())
            se2 = float(np.sqrt(rel_h.var(ddof=1) / len(rel_h)
                                + rel_m.var(ddof=1) / len(rel_m)))
        t2 = d2 / se2 if se2 == se2 and se2 > 0 else float("nan")
        p2 = erfc(abs(t2) / sqrt(2)) if t2 == t2 else float("nan")
        print("\n  ── 市场控制后（减去**同期全市场均值**）──")
        print(f"  被选中相对超额 {rel_h.mean()*100:+.2f}%   "
              f"未选中相对超额 {rel_m.mean()*100:+.2f}%")
        print(f"  差 = {d2*100:+.2f}%  t={t2:+.2f}  p={p2:.4f}")
    else:
        d2 = t2 = p2 = float("nan")
        print("\n  ⚠️ 同期市场基准样本不足，无法做 beta 调整"
              "（结论只能按**原始**口径读）")

    mh, th = stat(hit, "被选中")
    mm, tm = stat(miss, "未选中")
    # ⚠️ 样本不足时 numpy 会刷一串 RuntimeWarning(自由度≤0/除零)，
    #    那是**预期**路径，不该污染输出（且日志会被刷屏）。
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        d = mh - mm
        se = (np.sqrt(hit.var(ddof=1) / len(hit)
                      + miss.var(ddof=1) / len(miss))
              if len(hit) > 1 and len(miss) > 1 else float("nan"))
    t = d / se if se == se and se > 0 else float("nan")
    p = erfc(abs(t) / sqrt(2)) if t == t else float("nan")
    print(f"\n  超额（选中−未选中）= {d*100:+.2f}%  t={t:+.2f}  p={p:.4f}")

    # ② 逐只口径：每只股票入选时点均值 − 未入选时点均值
    per = np.array([np.mean(r["hit"]) - np.mean(r["miss"])
                    for r in res if r["hit"] and r["miss"]], dtype=float)
    if len(per) >= 5:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            m = per.mean()
            se_p = per.std(ddof=1) / sqrt(len(per))
        t_p = m / se_p if se_p > 0 else float("nan")
        print(f"  逐只超额（配对，n={len(per)}）= {m*100:+.2f}%  "
              f"t={t_p:+.2f}  p={erfc(abs(t_p)/sqrt(2)):.4f}  "
              f"为正的占比 {(per>0).mean()*100:.1f}%")

    # ⚠️ 之前我写 "❌ 无用/为负" 把两件事混为一谈。
    #    "显著为负" 与 "与零无显著差异" 是**不同结论**，必须分开说。
    use_t = t2 if (t2 == t2 and d2 == d2) else t
    use_d = d2 if (t2 == t2 and d2 == d2) else d
    if t2 == t2:
        print("  ⇒ 判定以**市场控制后**为准（未控制会把大盘涨幅算到信号头上）")
    if use_t != use_t:
        verdict = "⚠️ 样本不足，无法判定"
    elif use_t < -2:
        verdict = f"❌ 显著为负（t={use_t:+.2f}, p={p2:.4f}）"
    elif use_t > 2:
        verdict = f"✅ 显著为正（t={use_t:+.2f}, p={p2:.4f}）"
    else:
        verdict = (f"❌ **与零无显著差异**（t={use_t:+.2f}, p={p2:.4f}）"
                   f" ⇒ 选不出超额，等同不可用")
    print(f"\n== 判定: {verdict} ==")
    print("⚠️ 口径提醒：这是**横截面选股**检验，与'择时'(五之五)是两回事；"
          "\n   即便为正也不代表能跑赢买入持有（五之十八未证明）。")

    if a.out:
        Path(a.out).write_text(json.dumps({
            "n_symbols": len(res), "H": H,
            "hit_mean": float(mh), "miss_mean": float(mm),
            "excess": float(d), "t": float(t), "p": float(p),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
