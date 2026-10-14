#!/usr/bin/env python3
"""缠论**完整理论**方案矩阵：区间套 / 多级别配合 / 买卖点组合 —— 全量端到端。

## 此前测漏了什么（本脚本补的）
之前所有回测都是**同级别配对**（本级别买点进 → 本级别卖点出）。缠论真正被推崇
的操作法是**级别配合 + 区间套**：

1. **多级别配合**：本级别（日线）定方向找买点，次级别（30min）找精确卖点。
2. **区间套（qujiantao）**：大级别买点在小级别也被背驰确认（真·跨周期，用真实
   30min 数据，不是同序列递归）。
3. **买卖点组合**：1/2/3买 × 1/2/3卖 的搭配。

## 双基准（必须，否则无法判断"是缠论的功劳"）
- **基准 A：同级别配对**（A0）—— 与多级别方案的唯一差别是"出场用哪级别"。
- **基准 B：买入持有**（BH）。
- **基准 C：局部低点随机配时**（RND）—— 同义反复对照：缠论买点本质上落在
  局部极值附近，若"多级别"的收益只是"低买高卖"的同义反复，RND 会同样赚钱。
  RND 口径 = 用**同样数量的**随机局部低点入场 + 随机局部高点出场，跑同样次数。

## 方法学硬性要求
- **统一时间窗**：30min 数据只从 2024-09 起，故所有方案（含对照）一律截断到
  同一区间，否则"多级别更好"可能只是区间不同造成的假象。
- **成本**：佣金 0.03% + 印花税 0.1% + 滑点 0.2%（引擎参数）。
- **配对 t 检验**：逐标的 (方案收益 − 同标的买入持有)，配对而非两样本。
- **样本外**：由 ``audit_chanlun_ml_oos.py`` 单独做，本脚本只出全样本。

## 性能
30min 分析 20s/只且 O(n²)，方案矩阵 10 个方案 ⇒ 直接跑要 16 小时。
改用 ``_ml_precompute``：每只只算一次，落盘缓存，方案间共享。
已验证注入结果与自算**逐位一致**（见 --check-cache）。

用法：
  .venv/bin/python scripts/audit_chanlun_full_theory60.py --limit 8      # 冒烟
  .venv/bin/python scripts/audit_chanlun_full_theory60.py --workers 2    # 全量
  .venv/bin/python scripts/audit_chanlun_full_theory60.py --check-cache  # 牙齿
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from _concurrency import resolve_workers  # noqa: E402
# ⚠️ CACHE 必须取自 _ml_precompute60（audit_cache60），不能在这里硬编码成
#    audit_cache —— 否则次级别数据虽然换成了 60min，**信号仍读 30min 的缓存**，
#    结果会和 30min 版逐位相同（我踩过：两边数字一模一样才发现）。
from _ml_precompute60 import CACHE, load_pair  # noqa: E402
from easy_tdx.backtest.engine import BacktestEngine  # noqa: E402
from easy_tdx.backtest.strategies.chanlun_ml import ChanlunMLStrategy  # noqa: E402
from easy_tdx.backtest.strategies.chanlun_pair import ChanlunPairStrategy  # noqa: E402

D = ROOT / "audit_data"
SLIP = 0.002
RND_TRIALS = 20           # 随机基准每只跑几遍（降低单次抽样的偶然性）
RND_SEED = 20241010
# 单笔往返成本：佣金双边 0.03%×2 + 印花税 0.1% + 滑点双边 0.2%×2
ROUND_COST = 0.0003 * 2 + 0.001 + 0.002 * 2


def _stable_seed(code: str) -> int:
    """稳定种子（不能用 hash()：Python 的 str hash 带随机盐，跨进程不可复现）。"""
    return int(hashlib.md5(code.encode()).hexdigest()[:8], 16)

# ── 方案矩阵 ────────────────────────────────────────────────────────────
# (名, ChanlunML 参数)。A0 是同级别对照（走 ChanlunPairStrategy）。
ML_PLANS: list[tuple[str, dict]] = [
    # 多级别：本级别买 → 次级别卖
    ("B1 本3买→次1卖", {"entry_types": "3buy", "exit_types": "1sell",
                        "fallback_exit_types": "", "max_hold_bars": 120}),
    ("B2 本全买→次1卖", {"entry_types": "1buy,2buy,3buy", "exit_types": "1sell",
                         "fallback_exit_types": "", "max_hold_bars": 120}),
    ("B3 本3买→次全卖", {"entry_types": "3buy", "exit_types": "1sell,2sell,3sell",
                         "fallback_exit_types": "", "max_hold_bars": 120}),
    ("B4 本全买→次全卖", {"entry_types": "1buy,2buy,3buy",
                          "exit_types": "1sell,2sell,3sell",
                          "fallback_exit_types": "", "max_hold_bars": 120}),
    # 本级别兜底（防次级别不出信号）
    ("C1 本3买→次1卖+本1卖兜底", {"entry_types": "3buy", "exit_types": "1sell",
                                  "fallback_exit_types": "1sell", "max_hold_bars": 120}),
    # ── 区间套：入场要求被 30min 背驰确认（真·跨周期）──
    ("D1 区间套确认后本全买→次1卖", {"entry_types": "1buy,2buy,3buy", "exit_types": "1sell",
                                     "fallback_exit_types": "", "max_hold_bars": 120,
                                     "sub_entry_scope": "nested"}),
    ("D2 区间套确认后本全买→次全卖", {"entry_types": "1buy,2buy,3buy",
                                      "exit_types": "1sell,2sell,3sell",
                                      "fallback_exit_types": "", "max_hold_bars": 120,
                                      "sub_entry_scope": "nested"}),
    # ── 反向对照：次级别买 → 本级别卖（检验方向性）──
    ("E1 本1买→次1卖(仅1买)", {"entry_types": "1buy", "exit_types": "1sell",
                                "fallback_exit_types": "", "max_hold_bars": 120}),
    ("E2 本2买→次1卖(仅2买)", {"entry_types": "2buy", "exit_types": "1sell",
                                "fallback_exit_types": "", "max_hold_bars": 120}),
]

PLAN_NAMES = ["A0 同级别:全买点→全卖点", "A1 同级别同口径(无守卫)"] + [n for n, _ in ML_PLANS]


def _local_extrema(c: np.ndarray, w: int, low: bool) -> np.ndarray:
    """局部极值下标（买入→局部低点，卖出→局部高点）。"""
    n = len(c)
    out = []
    for i in range(w, n - w):
        seg = c[i - w: i + w + 1]
        if low and c[i] == seg.min():
            out.append(i)
        elif not low and c[i] == seg.max():
            out.append(i)
    return np.asarray(out, dtype=int)


def _rnd_return(c: np.ndarray, n_trades: int, rng: np.random.Generator,
                w: int = 5) -> float:
    """基准 C：随机挑 n_trades 组**时序不重叠**的「局部低点买 → 局部高点卖」。

    口径对齐（否则对照不公平）：
      - **同样笔数**（取该标的方案的实际笔数）
      - **时序不重叠**：一笔卖掉后才开下一笔（缠论方案也是单仓位串行，
        若允许重叠就等于让随机基准同时持有多笔，"同样笔数"就名不副实）
      - **同样成本**：每笔往返扣 ROUND_COST（与回测引擎同口径）
    若缠论方案的收益不显著优于它 ⇒ 收益来自"局部极值低买高卖"的同义反复。
    """
    if n_trades <= 0:
        return 0.0
    lows = _local_extrema(c, w, True)
    highs = _local_extrema(c, w, False)
    if len(lows) < 2 or len(highs) < 2:
        return 0.0
    eq = 1.0
    cur = 0
    for _ in range(n_trades):
        cand_i = lows[lows > cur]
        if cand_i.size == 0:
            break
        i = int(rng.choice(cand_i))
        cand_j = highs[highs > i]
        if cand_j.size == 0:
            break
        j = int(rng.choice(cand_j))
        eq *= (c[j] / c[i]) * (1.0 - ROUND_COST)
        cur = j
    return float(eq - 1.0)


def _job(code: str) -> dict[str, list]:
    """单只标的：跑全部方案 + 三个基准。"""
    d, s = load_pair(code)
    if len(d) < 80:
        return {}
    p = CACHE / next((f.name for f in CACHE.glob(f"{code}_*.json")), "")
    if not p or not p.exists():
        return {}
    c = json.loads(p.read_text())

    close = d["close"].to_numpy(dtype=float)
    bh = float(close[-1] / close[0] - 1)
    out: dict[str, list] = {"__bh__": [bh]}

    # ── 基准 A：同级别配对 ──
    # ⚠️ 两条口径都要跑，否则对照不公平（这是实测发现的坑）：
    #   ChanlunPairStrategy 默认开 lookahead_guard=True：信号要经 3 根确认期
    #   复核、延后到 b+3 才发出（再 next_open 成交 ⇒ 实际 b+4）。
    #   而 chanlun_ml **没有**这套守卫：本级别信号在 bar b 发出、次级别信号
    #   按 30min 时刻消费，都是"下一根日线开盘"成交。
    #   ⇒ 拿"带守卫的 A0"当对照，等于让对手晚 3 根进场，**多级别的优势会被高估**。
    #   实测（25 只）：A0 开守卫 +15.78% vs 关守卫 +41.33%，差 25.6 个点（t=5.39）。
    #   所以 A0（开守卫，保守）与 A1（关守卫，与多级别同口径）**都要报**。
    for tag, guard in (("A0 同级别:全买点→全卖点", True),
                      ("A1 同级别同口径(无守卫)", False)):
        try:
            st = ChanlunPairStrategy(lookahead_guard=guard)
            r = BacktestEngine(st, cash=100000.0, slippage=SLIP).run(d)
            pl = st.pair_log
            out[tag] = [
                float(r.performance["total_return"]), len(pl),
                float(np.mean([x["pnl_pct"] for x in pl])) if pl else np.nan,
                float(np.mean([1.0 if x["pnl_pct"] > 0 else 0.0 for x in pl])) if pl else np.nan,
            ]
        except Exception:  # noqa: BLE001
            pass

    # ── 多级别 / 区间套方案 ──
    for name, kw in ML_PLANS:
        try:
            m = ChanlunMLStrategy(**kw)
            m.set_data(d, s)
            m.set_precomputed(
                main_signals=[(x["bar"], x["t"], x["c"]) for x in c["main"]],
                sub_signals=[(pd.Timestamp(x["dt"]), x["t"], x["c"]) for x in c["sub"]],
                main_nested={int(k): v for k, v in c["main_nested"].items()},
            )
            r = BacktestEngine(m, cash=100000.0, slippage=SLIP).run(d)
            pl = m.pair_log
            out[name] = [
                float(r.performance["total_return"]), len(pl),
                float(np.mean([x["pnl_pct"] for x in pl])) if pl else np.nan,
                float(np.mean([1.0 if x["pnl_pct"] > 0 else 0.0 for x in pl])) if pl else np.nan,
            ]
        except Exception:  # noqa: BLE001
            pass

    # ── 基准 C：随机局部低点（同义反复对照）──
    # ⚠️ 必须**逐方案**按各自笔数生成：不同方案笔数差很多（如 B2 约 4 笔、
    #    B3 约 2 笔）。若统一用某一个方案的笔数，笔数多的方案会因为
    #    "交易更多次"而被高估/低估 —— 对照就不公平了。
    #    做法：对每个方案取其在该标的的实际笔数 n，用同一 n 生成随机基准。
    # ⚠️ 即使本方案在这只股票上**一笔都没做**（n_tr=0）也要记一条 0.0，
    #    这样 RND 序列与方案序列**下标一一对应**；否则后面
    #    len(vals)==len(bh) 的对齐检查会失败，导致该方案的 vsRND 列整列消失。
    for name in ["A0 同级别:全买点→全卖点", "A1 同级别同口径(无守卫)"] + [n for n, _ in ML_PLANS]:
        n_tr = int(out.get(name, [0, 0])[1]) if name in out else 0
        if n_tr <= 0:
            out[f"RND::{name}"] = [0.0, 0]      # 空仓 ⇒ 随机基准也是 0 笔
            continue
        # 同一标的 + 同一笔数用同一个种子流，保证复现（跨进程稳定）
        rng = np.random.default_rng(_stable_seed(code + "|" + name) + RND_SEED)
        rr = [_rnd_return(close, n_tr, rng) for _ in range(RND_TRIALS)]
        out[f"RND::{name}"] = [float(np.mean(rr)), n_tr]
    return out


def _t(d: np.ndarray) -> float:
    """配对 t 值（单样本，对差值序列）。"""
    if len(d) < 3:
        return float("nan")
    sd = np.std(d, ddof=1)
    return float(np.mean(d) / sd * np.sqrt(len(d))) if sd > 0 else float("nan")


def _safe_mean(seq: list) -> float:
    """忽略 NaN 的均值；全 NaN 时返回 nan（不触发 RuntimeWarning）。"""
    a = np.asarray([x for x in seq if x is not None], dtype=float)
    a = a[~np.isnan(a)]
    return float(np.mean(a)) if a.size else float("nan")


def _report(agg: dict[str, list], bh: np.ndarray) -> list:
    n = len(bh)
    print(f"\n总样本 {n} 只   买入持有（同区间）均值 {np.mean(bh)*100:+.2f}%")
    print()
    print("%-26s %5s %9s %7s %9s %9s %7s %7s" % (
        "方案", "n", "超额vsBH", "t", "超额vsA1", "超额vsRND", "笔均%", "胜率%"))
    print("-" * 84)
    a0 = np.array([x[0] for x in agg.get("A0 同级别:全买点→全卖点", [])])
    a1 = np.array([x[0] for x in agg.get("A1 同级别同口径(无守卫)", [])])
    if len(a0):
        print(f"  A0 同级别(带前视守卫) 均值 {np.mean(a0)*100:+.2f}%   "
              f"A1 同级别(无守卫,与多级别同口径) 均值 {np.mean(a1)*100:+.2f}%")
    # RND 基准（同义反复对照）：**逐方案**配对，键为 RND::<方案名>
    rnd: dict[str, np.ndarray] = {}
    for name in PLAN_NAMES:
        vals = [x[0] for x in agg.get(f"RND::{name}", [])]
        # ⚠️ 长度必须等于 len(bh)，否则后面 ret[:m] 与 rnd[:m] 会错位
        #    （RND 少了就整列消失，见上面 out[f"RND::{name}"] 的 0.0 兜底）
        if len(vals) == len(bh):
            rnd[name] = np.asarray(vals, dtype=float)
        elif vals:
            print(f"  ⚠️ RND::{name} 只有 {len(vals)}/{len(bh)} 条，该列跳过")
    # 打印用的 RND 汇总行：取 B2 的那一路（代表性展示）
    rnd_show = rnd.get("B2 本全买→次1卖")

    rows: list[tuple[str, float, float, float, float, float, float]] = []
    for name in PLAN_NAMES:
        v = agg.get(name, [])
        if not v:
            print(f"{name:<26} {'—':>5}")
            continue
        ret = np.array([x[0] for x in v])
        m = min(len(ret), len(bh))
        ex_bh = ret[:m] - bh[:m]
        t_bh = _t(ex_bh)
        # ⚠️ 判据 2 用 **A1（同级别同口径、无守卫）** 才是公平对照：
        #    A0 带 lookahead_guard，进场比多级别方案晚 3 根，拿它当对照会
        #    **高估**多级别。A1 关掉守卫，与多级别方案的信号时点同口径。
        if name.startswith("A"):
            ex_a0, t_a0 = float("nan"), float("nan")
        elif len(a1) == 0:
            ex_a0, t_a0 = float("nan"), float("nan")
        else:
            ma = min(len(ret), len(a1))
            da = ret[:ma] - a1[:ma]
            ex_a0, t_a0 = float(np.mean(da)), _t(da)
        # ── 同义反复对照：本方案 vs 同笔数的随机局部低点（逐标的配对）──
        rv = rnd.get(name)
        if rv is None or len(rv) < m:
            ex_rnd, t_rnd = float("nan"), float("nan")
        else:
            dr = ret[:m] - rv[:m]
            ex_rnd, t_rnd = float(np.mean(dr)), _t(dr)
        pnl = _safe_mean([x[2] for x in v if len(x) >= 3])
        win = _safe_mean([x[3] for x in v if len(x) >= 4])
        ta = f"{t_a0:+.2f}" if not np.isnan(t_a0) else "  —"
        ea = f"{ex_a0*100:+.2f}%" if not np.isnan(ex_a0) else "   —"
        er = f"{ex_rnd*100:+.2f}%" if not np.isnan(ex_rnd) else "   —"
        print("%-26s %5d %+8.2f%% %7.2f %9s %9s %7.2f %7.1f" % (
            name, m, np.mean(ex_bh) * 100, t_bh, ea, er, pnl, win * 100))
        rows.append((name, float(np.mean(ex_bh)) * 100, t_bh,
                     ex_a0 * 100 if not np.isnan(ex_a0) else float("nan"),
                     ex_rnd * 100 if not np.isnan(ex_rnd) else float("nan"),
                     t_rnd, pnl, win * 100))
        if rnd_show is not None and len(rnd_show) >= m and name == "B2 本全买→次1卖":
            print("%-26s %5d %+8.2f%% %7.2f %9s %9s" % (
                "RND随机低点(B2同笔数)", m,
                np.mean(rnd_show[:m] - bh[:m]) * 100, _t(rnd_show[:m] - bh[:m]),
                f"{np.mean(rnd_show[:m]-a0[:min(len(a0),m)])*100:+.2f}%", "基准"))

    print()
    print("判据（三条都要过才算『真能帮用户赚钱』）：")
    print("  1. 超额vsBH 的 |t|>1.96")
    print("  2. 超额vsA1 为正 ⇒ 比同口径的同级别配对强")
    print("     （A1 = 无前视守卫，与多级别方案信号时点一致；")
    print("      用带守卫的 A0 当对照会让对手晚 3 根进场，高估多级别）")
    print("  3. 超额vsRND：为正**且** |t|>1.96 ⇒ 不是『局部低点低买高卖』的同义反复")
    print()
    print("── 逐条判定 ──")
    print("%-26s %10s %10s %11s   %s" % ("方案", "1.vsBH", "2.vsA1", "3.vsRND", "结论"))
    for row in rows:
        name, ebh, tbh, ea0, ernd, t_rnd, _p, _w = row
        c1 = abs(tbh) > 1.96 and ebh > 0
        c2 = (not np.isnan(ea0)) and ea0 > 0
        c3 = (not np.isnan(ernd)) and ernd > 0 and abs(t_rnd) > 1.96
        soft3 = (not np.isnan(ernd)) and ernd > 0
        verdict = ("✅ 三条全过" if (c1 and c2 and c3) else
                   "⚠️ 方向对但v3不显著" if (c1 and c2 and soft3) else
                   "⚠️ 部分通过" if (c1 and (c2 or soft3)) else "❌ 不成立")
        print("%-26s %10s %10s %11s   %s" % (
            name, f"{'✅' if c1 else '❌'}{ebh:+.2f}%",
            f"{'✅' if c2 else '❌'}{ea0:+.2f}%" if not np.isnan(ea0) else "—",
            (f"{'✅' if c3 else ('⚠️' if soft3 else '❌')}{ernd:+.2f}%"
             if not np.isnan(ernd) else "—"),
            verdict))
    return rows


def _check_cache() -> int:
    """牙齿：预计算注入 vs init() 自算，必须逐位一致。"""
    from _ml_precompute60 import compute

    print("牙齿：预计算注入 与 init() 自算 逐位一致性\n")
    bad = 0
    for code in ["sh600000", "sh600036"]:
        d, s = load_pair(code)
        kw = {"entry_types": "1buy,2buy,3buy", "exit_types": "1sell",
              "fallback_exit_types": "", "max_hold_bars": 120}
        a = ChanlunMLStrategy(**kw); a.set_data(d, s)
        BacktestEngine(a, cash=100000.0, slippage=SLIP).run(d)
        c = compute(code)
        b = ChanlunMLStrategy(**kw); b.set_data(d, s)
        b.set_precomputed(
            main_signals=[(x["bar"], x["t"], x["c"]) for x in c["main"]],
            sub_signals=[(pd.Timestamp(x["dt"]), x["t"], x["c"]) for x in c["sub"]],
            main_nested={int(k): v for k, v in c["main_nested"].items()},
        )
        BacktestEngine(b, cash=100000.0, slippage=SLIP).run(d)
        ok = list(a.pair_log) == list(b.pair_log)
        print(f"  {code}: 自算 {len(a.pair_log)} 笔 / 注入 {len(b.pair_log)} 笔  "
              f"{'✅一致' if ok else '❌不一致'}")
        if not ok:
            bad += 1
            print("    自算:", list(a.pair_log)[:3])
            print("    注入:", list(b.pair_log)[:3])
    print()
    if bad:
        print("❌ 预计算与自算不一致 ⇒ 缓存有静默错配风险，禁止用于全量")
        return 1
    print("✅ 一致 ⇒ 缓存可安全复用")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--check-cache", action="store_true", help="只跑一致性牙齿")
    ap.add_argument("--precompute-only", action="store_true")
    a = ap.parse_args()

    if a.check_cache:
        return _check_cache()

    workers = resolve_workers(a.workers)
    codes = sorted({f.name.split("_")[0] for f in CACHE.glob("*_*.json")})
    codes = codes[:: a.step]
    if a.limit:
        codes = codes[: a.limit]
    if not codes:
        print("❌ 没有预计算缓存。先跑：")
        print("   .venv/bin/python scripts/_ml_precompute.py --workers 2")
        return 1

    if a.precompute_only:
        return 0

    # ── 守门：缓存目录必须与本次的次级别周期匹配 ──────────────────────
    # 踩过的坑：CACHE 被硬编码成 audit_cache，导致次级别数据换了但信号没换，
    # 结果与 30min 版**逐位相同**却毫无察觉。这里显式断言一次。
    _d, _s = load_pair(codes[0])
    _n_sub = len(_s)
    _c = json.loads(next(CACHE.glob(f"{codes[0]}_*.json")).read_text())
    _n_sub_sig = len(_c["sub"])
    if str(CACHE).endswith("audit_cache60") and _n_sub > 3000:
        print(f"❌ 缓存与次级别周期不匹配：CACHE={CACHE} 但次级别有 {_n_sub} 根（60min 应约 2000）")
        return 1
    print(f"守门：CACHE={CACHE.name}  次级别 {_n_sub} 根 / 次级别信号 {_n_sub_sig} 条 ✓")

    print(f"样本 {len(codes)} 只   并行度 {workers}")
    print("⚠️ 所有方案统一截断到 60min 覆盖区间（2024-09 起），保证可比")
    print("⚠️ 成本：佣金0.03% + 印花税0.1% + 滑点0.2%\n")

    from concurrent.futures import ProcessPoolExecutor
    agg: dict[str, list] = defaultdict(list)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, out in enumerate(ex.map(_job, codes, chunksize=1)):
            for k, v in out.items():
                agg[k].append(v)
            if (i + 1) % 25 == 0:
                print(f"  进度 {i+1}/{len(codes)}", flush=True)

    bh = np.array([x[0] for x in agg.get("__bh__", [])])
    _report(agg, bh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
