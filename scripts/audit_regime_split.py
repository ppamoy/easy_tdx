#!/usr/bin/env python3
"""V733：中位数口径 + 分行情（牛/熊/震荡）下的策略横截面比较。

为什么单独做这个（补上一轮自己标记的缺口）
------------------------------------------------
五之十三用 t 检验（**均值**口径）得出"所有策略超额 t 均为负"。但我同时
核对了行情分布，发现：

    买入持有：均值 +34.9%，但**中位 −2.3%**；涨超 20% 的票占 40%

少数暴涨票主导了均值，于是 **t 检验会系统性压低所有主动策略的超额**——
这是样本分布造成的偏差，不是策略能力的结论。我上一轮明确写了
"公平检验应在熊市或中位数口径下做（本轮未做）"，本脚本补上。

做法（三件事，缺一不可）
------------------------
1. **中位数口径**：用 paired 中位超额 + **符号检验**（binomial）代替 t 检验，
   让几个暴涨票无法主导结论；
2. **分行情**：按每只票的自身走势把样本切成 上涨/震荡/下跌 三组，
   各自单独比较 —— 看缠论是不是"只在熊市有价值"；
3. **同窗对照**：每只票先算出自己的买持收益，再比较，
   避免跨股票的绝对涨幅差异掩盖超额。

⚠️ 局限（如实声明）
- 单市场（A股）、日线、n 有限，未做 beta/市值中性化；
- PIT 分组用"前 40% 走势"作标签，仍是**样本内**切分（不是滚动样本外）；
- 策略取默认参数（缠论未调优）；
- 行情分组用**样本内**事后走势划分 ⇒ 分组本身有 look-ahead，
  只能用于**诊断**"是否只在某类行情下有效"，**不能**当作样本外证据。

用法：
    .venv/bin/python scripts/audit_regime_split.py
    .venv/bin/python scripts/audit_regime_split.py --limit 40

退出码：0 = 跑完；2 = 环境不可用。
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from easy_tdx.backtest.engine import BacktestEngine  # noqa: E402
from easy_tdx.backtest.strategies.builtin import (  # noqa: E402
    BbiStrategy,
    BollBreakoutStrategy,
    DonchianStrategy,
    DpoStrategy,
    KdjCrossStrategy,
    MaCrossStrategy,
    MacdStrategy,
    RsiReversalStrategy,
    SuperTrendStrategy,
)
from easy_tdx.backtest.strategies.chanlun import ChanlunStrategy  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "audit_data"
EXCLUDE = {"sh000300", "sh000001"}

CONTROL = [
    ("双均线", MaCrossStrategy),
    ("MACD", MacdStrategy),
    ("RSI反转", RsiReversalStrategy),
    ("布林突破", BollBreakoutStrategy),
    ("KDJ", KdjCrossStrategy),
    ("唐奇安", DonchianStrategy),
    ("超级趋势", SuperTrendStrategy),
    ("BBI", BbiStrategy),
    ("DPO", DpoStrategy),
]
CHANLUN = ("【缠论】", ChanlunStrategy)

BULL_CUT = 0.20  # 买持 >= +20% 视为"上涨票"
BEAR_CUT = -0.10  # 买持 <= -10% 视为"下跌票"


def sign_test(pairs: np.ndarray) -> tuple[float, int, int]:
    """符号检验：返回 (比例为正, 正数个数, 总数)。

    比 t 检验更抗"少数极端值主导"——只问"赢的比例是否显著高于 50%"。
    """
    if len(pairs) == 0:
        return float("nan"), 0, 0
    pos = int((pairs > 0).sum())
    return pos / len(pairs), pos, len(pairs)


def run_all(items: list[tuple[str, pd.DataFrame]]) -> dict[str, dict[str, float]]:
    """跑所有策略，返回 {策略名: {标的符号: 总收益率}}。

    ⚠️ 为什么**必须按 symbol 建 dict 而不是位置 list**（实测抓到的真 bug）：
    原实现用 `vals.append(...)` + 失败时 `continue`，一旦某个策略在某只票上
    抛异常，该策略的列表就会比别人短一截；而 `main()` 里配对用的是
    `bh_all[:len(ch)]` **按位置截断** ⇒ 从第 k 只起，
    "策略收益"和"买持收益"来自**不同的股票**，配对超额完全是错的。

    实测证据（注入"缠论在第 3 只票失败"）：
        缠论[2]=+75.16% 来自 sh600016，买持[2]=+48.84% 来自 sh600011  ← 错配
    改成按 symbol 对齐后，缺失的标的会被**安全丢弃**（两侧都丢），
    宁可少样本也不能错配。
    """
    out: dict[str, dict[str, float]] = {}
    for label, cls in [CHANLUN] + CONTROL:
        vals: dict[str, float] = {}
        for sym, df in items:
            try:
                r = BacktestEngine(cls(), cash=100000.0).run(df)
                vals[sym] = float(r.performance["total_return"])
            except Exception:
                # 按 symbol 存 ⇒ 这里丢一个不会带偏其余元素的下标
                print(f"  ⚠️ {label} 在 {sym} 上失败，已跳过该标的", flush=True)
                continue
        out[label] = vals
    return out


def group_report(name: str, strat: np.ndarray, bh: np.ndarray) -> None:
    if len(strat) < 5:
        print(f"\n【{name}】 n={len(strat)} 样本不足，跳过")
        return
    d = strat - bh
    med = float(np.median(d))
    frac, pos, n = sign_test(d)
    t = float(d.mean() / d.std() * np.sqrt(len(d))) if d.std() > 0 else float("nan")
    flag = "中位超额为正" if med > 0 else "中位超额为负"
    sig = "" if abs(t) < 2 else "  ⚠️t显著"
    print(f"\n【{name}】 n={n}")
    print(f"  缠论均值 {strat.mean() * 100:+7.2f}%   买持均值 {bh.mean() * 100:+7.2f}%")
    print(f"  缠论中位 {np.median(strat) * 100:+7.2f}%   买持中位 {np.median(bh) * 100:+7.2f}%")
    print(
        f"  配对超额：中位 {med * 100:+7.2f}%（{flag}）  均值 {d.mean() * 100:+7.2f}%  t={t:+.2f}{sig}"
    )
    print(f"  符号检验：跑赢买持 {pos}/{n} = {frac * 100:.0f}%（>60% 才算有倾向）")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30)
    a = ap.parse_args()
    fs = [p for p in sorted(DATA.glob("*.json")) if p.stem.split("_")[0] not in EXCLUDE]
    if a.limit:
        fs = fs[: a.limit]
    if not fs:
        print("❌ 无 audit_data，先跑 audit_fetch_real_data.py")
        return 2

    items: list[tuple[str, pd.DataFrame]] = []
    for p in fs:
        try:
            df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
            df["datetime"] = pd.to_datetime(df["datetime"])
            if len(df) > 200:
                items.append((p.stem.split("_")[0], df))
        except Exception:
            continue
    if len(items) < 5:
        print("❌ 有效数据不足")
        return 2

    print(f"中位数口径 + 分行情的策略比较 —— {len(items)} 只 A 股日线，默认参数，同成本模型")
    print("=" * 78)

    res = run_all(items)
    bh_map = {sym: float(d["close"].iloc[-1] / d["close"].iloc[0] - 1) for sym, d in items}
    df_map = dict(items)

    # ✅ 按 **symbol 交集** 对齐：任何一侧缺失的标的整条丢弃，
    #    绝不用位置截断（那会把不同股票配对在一起，见 run_all 文档里的实测证据）
    def pair(label: str) -> tuple[np.ndarray, np.ndarray, list[str]]:
        sm = res[label]
        syms = [s for s in bh_map if s in sm and s in df_map]
        return np.array([sm[s] for s in syms]), np.array([bh_map[s] for s in syms]), syms

    ch, bh, csyms = pair(CHANLUN[0])
    group_report("全样本", ch, bh)

    # ── 分行情：用每只票自身的买持收益分三组 ──
    m = min(len(ch), len(bh))
    c, b = ch[:m], bh[:m]  # 已按 symbol 对齐，长度天然一致
    groups = {
        f"上涨票(买持>+{BULL_CUT:.0%})": c[b >= BULL_CUT],
        f"震荡票": c[(b < BULL_CUT) & (b > BEAR_CUT)],
        f"下跌票(买持<{BEAR_CUT:.0%})": c[b <= BEAR_CUT],
    }
    print("\n" + "=" * 78)
    print("按每只票自身买持收益分组（事后划分，仅诊断用，非样本外证据）：")
    for name, arr in groups.items():
        mask = (
            (b >= BULL_CUT)
            if "上涨" in name
            else ((b <= BEAR_CUT) if "下跌" in name else ((b < BULL_CUT) & (b > BEAR_CUT)))
        )
        group_report(name, arr, b[mask])

    # ── PIT 安全复核：只用前 40% 走势打 PIT 行情标签（无 look-ahead）──
    print("\n" + "=" * 78)
    print("PIT 安全复核（行情标签只用前 40% 走势，策略收益在标签之后）：")
    pit = []
    for sym, st in zip(csyms, c[: len(csyms)]):
        df = df_map[sym]
        px = df["close"].to_numpy(float)
        n = len(px)
        k = max(1, int(n * 0.4))
        pit.append((px[k] / px[0] - 1.0, float(st), float(px[-1] / px[0] - 1.0)))
    pa = np.array(pit)
    for name, mask in (("PIT上涨", pa[:, 0] >= 0.05), ("PIT下跌", pa[:, 0] <= -0.05)):
        if int(mask.sum()) < 5:
            print(f"\n【{name}】n={int(mask.sum())} 样本不足")
            continue
        d = pa[mask, 1] - pa[mask, 2]
        t = float(d.mean() / d.std() * np.sqrt(len(d))) if d.std() > 0 else float("nan")
        print(f"\n【{name}】n={int(mask.sum())}  前段走势均值 {pa[mask, 0].mean() * 100:+.1f}%")
        print(f"  缠论 {pa[mask, 1].mean() * 100:+.1f}%   买持 {pa[mask, 2].mean() * 100:+.1f}%")
        print(
            f"  超额 中位 {np.median(d) * 100:+.1f}%  均值 {d.mean() * 100:+.1f}%  "
            f"t={t:+.2f}  跑赢 {(d > 0).mean() * 100:.0f}%"
        )

    # ── 横向：缠论 vs 各经典策略的中位超额排序 ──
    print("\n" + "=" * 78)
    print("中位超额（策略 − 同票买持）横向排名：")
    rows = []
    for label, _ in [CHANLUN] + CONTROL:
        strat, base, _syms = pair(label)
        if len(strat) < 5:
            continue
        d = strat - base
        rows.append((label, float(np.median(d)), float(np.mean(d)), int((d > 0).sum()), len(d)))
    rows.sort(key=lambda r: r[1], reverse=True)
    print(f"{'策略':<12}{'中位超额':>10}{'均值超额':>10}{'跑赢数':>10}")
    for lab, med, mean, pos, k in rows:
        mark = "  ←缠论" if lab == CHANLUN[0] else ""
        print(f"{lab:<12}{med * 100:>9.2f}%{mean * 100:>9.2f}%{pos:>6}/{k}{mark}")
    rank = next(i for i, r in enumerate(rows) if r[0] == CHANLUN[0]) + 1
    print(f"\n缠论按中位超额排第 {rank}/{len(rows)}")

    # ── 回撤对比（全样本，最稳健的一条）──
    print("\n" + "=" * 78)
    print("最大回撤：缠论策略 vs 同票买入持有")
    dds = []
    for sym, df in items:
        if sym not in res[CHANLUN[0]]:
            continue  # 该标的策略没跑出来 ⇒ 不留半条数据
        try:
            r = BacktestEngine(CHANLUN[1](), cash=100000.0).run(df)
            px = df["close"].to_numpy(float)
            peak = np.maximum.accumulate(px)
            dds.append(
                (float(r.performance["max_drawdown"]), float((peak - px).max() / peak.max()))
            )
        except Exception:
            continue
    if dds:
        da = np.array(dds)
        print(
            f"  缠论策略 中位回撤 {np.median(da[:, 0]) * 100:.1f}%   "
            f"买入持有 中位回撤 {np.median(da[:, 1]) * 100:.1f}%"
        )
        print(f"  缠论回撤更小的比例 {(da[:, 0] < da[:, 1]).mean() * 100:.0f}%  (n={len(da)})")
        print("  ⇒ 若该比例接近 100%，说明缠论的价值在**风险控制**而非收益增强。")
    print("\n⚠️ 局限：单市场日线、n 有限、未 beta 中性化、默认参数；")
    print("   分组为样本内事后划分，仅用于诊断，不可当样本外证据。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
