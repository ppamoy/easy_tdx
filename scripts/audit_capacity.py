#!/usr/bin/env python3
"""V733：冲击成本 / 容量建模 —— 回答「这个超额收益真金白银能吃到多少？」。

为什么必须做
------------
前面所有择时结论（1buy 6/6 窗为正、60 根 +3.01%）都是**按收盘价计价**的，
等于假设「能以信号触发那根 bar 的收盘价、无限量成交」。真实交易做不到：
- 挂单要吃对手价（至少半个价差）；
- 自己的买单会把价格往上推（冲击成本，随成交额占比上升）；
- 单只股票日成交额有限，仓位大到一定程度就装不下。

本脚本把三者分开建模，量化：**在多大的资金规模下，超额收益被吃光。**

成本模型（三块，各自可开关，便于看清楚是谁吃掉了收益）
--------------------------------------------------
1. **佣金 + 印花税**（`--fee`）：佣金双边各 0.025%（万 2.5），印花税卖出
   单边 0.05%（A 股现行）。合计约 0.10% 往返。
2. **价差（spread）**：用当日 high/low 振幅的比例近似（A 股无逐笔买卖价，
   只能用振幅的一定比例代替；默认取振幅的 10% 作为有效价差）。
3. **冲击成本（impact）**：平方根模型 —— `impact = k * sqrt(Q / ADV)`，
   Q 是本次成交额，ADV 是过去 20 日的日均成交额。k 默认 0.1（常见量级）。
   这是市场微观结构的标准近似，也是本脚本的核心。

成交额怎么来：`vol` 字段是**股数**，成交额 = vol × 当日均价（用 close 近似）。

容量约束：单笔成交额不得超过当日成交额的 `--max-part`（默认 10%）。

输出：对每个信号类型 × 每个资金规模，给出
  净超额 = 毛超额 − 总成本，以及「净超额仍为正」的最大规模。

用法：
    .venv/bin/python scripts/audit_capacity.py
    .venv/bin/python scripts/audit_capacity.py --sizes 1e5,1e6,1e7
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[1] / "audit_data"
HORIZON = 20
PIVOT = 5
BOOT = 300
N_WINDOWS = 6          # 与 audit_rolling_oos.py 保持一致
SEED = 20240917
DEFAULT_SIZES = "1e5,5e5,1e6,5e6,1e7,5e7"

# ── 成本参数 ──
COMMISSION = 0.00025      # 单边佣金 万2.5
STAMP_DUTY = 0.0005       # 卖出单边印花税
SPREAD_FRAC = 0.10        # 有效价差 = 当日振幅 × 该比例
IMPACT_K = 1.0            # 冲击系数：impact = k · σ · sqrt(Q/ADV)（**含波动率缩放**）
# ⚠️ 第一版写成无波动率缩放的 k=0.1·√(Q/ADV)，实测在 A 股典型标的上高估约 5 倍：
#    100 万单（占 ADV 0.13%）算出 36‱ 冲击，而常识量级是 5~15‱。
#    平方根模型的标准形式是「波动率 × √(参与率)」—— 流动性好的低波动股
#    冲击本来就小，不缩放会一刀切地把所有标的都判成"装不下"。
#    这里用 **该股自身 20 日 realized vol** 缩放（每只标的的 σ 不同）。
ADV_WINDOW = 20
VOL_WINDOW = 20


def _is_buy(st: str) -> bool:
    """信号方向。

    ⚠️ 必须用 `'buy' in st`，**不能**用 `st.endswith('buy')`：
    类二买 `2buy_s` 以 `_s` 结尾，endswith 判不出来，会被当成卖点、
    收益取反（V733 实测该 bug 让 2buy_s 稳定显示 −8%，实为 +8%）。
    """
    return "buy" in st


def pivot_indices(c: np.ndarray, k: int, low: bool, lo: int, hi: int) -> np.ndarray:
    """局部极值基准：窗口 [lo,hi) 内 k 根局部低点（或高点）的下标。"""
    out: list[int] = []
    for i in range(max(lo, k), min(hi, len(c) - k)):
        seg = c[i - k: i + k + 1]
        if low and c[i] == seg.min():
            out.append(i)
        elif (not low) and c[i] == seg.max():
            out.append(i)
    return np.array(out, dtype=int)


def trade_cost_vec(close: np.ndarray, high: np.ndarray, low: np.ndarray,
                   adv: np.ndarray, q: np.ndarray,
                   sigma: np.ndarray) -> np.ndarray:
    """一次交易（单边）的总成本，返回**相对价格的比例**（向量化）。

    含三部分：佣金、价差、冲击。印花税只在卖出时收，由调用方另加。
    """
    adv = np.where(np.isfinite(adv) & (adv > 0), adv, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        amp = np.where(close > 0, (high - low) / close, 0.0)
        spread = 0.5 * SPREAD_FRAC * amp
        ratio = np.where((adv > 0) & (q > 0), q / np.where(adv > 0, adv, 1.0), 0.0)
        sig = np.where(np.isfinite(sigma) & (sigma > 0), sigma, 0.02)
        impact = IMPACT_K * sig * np.sqrt(np.clip(ratio, 0.0, None))
    out = COMMISSION + spread + impact
    return np.where(np.isfinite(out), out, 0.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default=DEFAULT_SIZES,
                    help="单笔资金规模（元）列表，逗号分隔")
    ap.add_argument("--max-part", type=float, default=0.10,
                    help="单笔成交额不得超过当日成交额的比例（容量上限）")
    ap.add_argument("--horizon", type=int, default=HORIZON)
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 只标的（调试用）")
    a = ap.parse_args()

    sizes = [float(x) for x in a.sizes.split(",")]
    files = [p for p in sorted(DATA_DIR.glob("*.json"))
             if p.stem.split("_")[0] not in ("sh000300", "sh000001")]
    if not files:
        print(f"❌ {DATA_DIR} 无数据")
        return 2

    if a.limit:
        files = files[: a.limit]
    rng = np.random.default_rng(SEED)
    # type -> list of (gross_excess, adv, close, high, low, amount)
    recs: dict[str, list[tuple]] = {}
    n_sig = 0

    for fi, p in enumerate(files):
        if fi % 25 == 0:
            print(f"  ...处理 {fi}/{len(files)}", flush=True)
        code = p.stem.split("_")[0]
        df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
        df["datetime"] = pd.to_datetime(df["datetime"])
        c = df["close"].to_numpy(dtype=float)
        hi = df["high"].to_numpy(dtype=float)
        lo = df["low"].to_numpy(dtype=float)
        vol = df["vol"].to_numpy(dtype=float)
        n = len(c)
        # 成交额 ≈ 股数 × 收盘价
        amount = vol * c
        # 20 日 ADV（rolling，PIT：只用该 bar 之前的数据）
        adv = pd.Series(amount).rolling(ADV_WINDOW, min_periods=5).mean().to_numpy()
        # 20 日 realized vol（日收益标准差），用于缩放冲击成本
        ret = pd.Series(c).pct_change()
        sig = (ret.rolling(VOL_WINDOW, min_periods=5).std()
               .shift(1).fillna(0.02).to_numpy())

        res = ChanlunAnalyser(code=code, frequency="daily",
                              config=ChanlunConfig()).process_klines(df)
        usable = n - a.horizon
        # ⚠️ 必须与 audit_rolling_oos.py 的 N_WINDOWS 一致（那里是 6），
        # 否则基准窗宽度不同、超额不可比（第一版写成 7，导致 1buy 毛超额
        # 0.62% 与滚动 OOS 的 +0.96% 对不上）。
        edges = np.linspace(0, usable, N_WINDOWS + 1).astype(int)

        for m in res.mmds:
            if not m.bi:
                continue
            st = m.mmd_type.value.lower()
            i = m.bi.end.bar_index
            if i + a.horizon >= n or i < ADV_WINDOW:
                continue
            is_buy = _is_buy(st)
            r = c[i + a.horizon] / c[i] - 1.0
            if not is_buy:
                r = -r
            w = int(np.searchsorted(edges[1:], i, side="right"))
            if w >= N_WINDOWS:
                continue
            cand = pivot_indices(c, PIVOT, low=is_buy, lo=int(edges[w]), hi=int(edges[w + 1]))
            cand = cand[(cand + a.horizon) < n]
            if len(cand) < 5:
                continue
            idx = rng.choice(cand, size=(BOOT, 1), replace=True)
            rr = c[idx + a.horizon] / c[idx] - 1.0
            if not is_buy:
                rr = -rr
            gross = float(r - float(np.mean(rr)))
            recs.setdefault(st, []).append(
                (gross, float(adv[i]) if np.isfinite(adv[i]) else 0.0,
                 float(c[i]), float(hi[i]), float(lo[i]), float(amount[i]),
                 float(sig[i]) if np.isfinite(sig[i]) else 0.02))
            n_sig += 1

    print(f"\n信号总数 {n_sig}（{len(files)} 只标的，前瞻 {a.horizon} 根）")
    print(f"成本模型：佣金 {COMMISSION*1e4:.1f}‱ 双边；印花税 {STAMP_DUTY*1e4:.1f}‱ 卖出单边；"
          f"价差=振幅×{SPREAD_FRAC}；冲击={IMPACT_K}·σ·√(Q/ADV)【含波动率缩放】")
    print(f"容量约束：单笔成交额 ≤ 当日成交额的 {a.max_part:.0%}\n")

    hdr = f"{'类型':<9}{'n':>5}{'毛超额':>9}"
    for s in sizes:
        hdr += f"{s/1e4:>9.0f}万"
    print(hdr)
    print("-" * (23 + 9 * len(sizes)))

    summary: dict[str, float] = {}
    for st in sorted(recs, key=lambda k: -len(recs[k])):
        arr = recs[st]
        if len(arr) < 30:
            continue
        gross = np.array([x[0] for x in arr])
        advs = np.array([x[1] for x in arr])
        closes = np.array([x[2] for x in arr])
        highs = np.array([x[3] for x in arr])
        lows = np.array([x[4] for x in arr])
        amounts = np.array([x[5] for x in arr])
        sigmas = np.array([x[6] for x in arr])
        is_buy = _is_buy(st)

        line = f"{st:<9}{len(arr):>5}{np.mean(gross)*100:>8.2f}%"
        net_by_size = []
        for size in sizes:
            # 单笔成交额受容量约束
            q = np.minimum(size, amounts * a.max_part)
            # 买卖各一次：买入成本 + 卖出成本 + 印花税
            total = 2.0 * trade_cost_vec(closes, highs, lows, advs, q, sigmas) + STAMP_DUTY
            net = gross - total
            net_by_size.append(float(np.mean(net)))
            line += f"{np.mean(net)*100:>8.2f}%"
        print(line)
        # 净超额仍为正的最大规模
        best = 0.0
        for size, net in zip(sizes, net_by_size):
            if net > 0:
                best = size
        summary[st] = best

    print("\n各类型【净超额仍为正】的最大单笔资金规模：")
    print("-" * 50)
    for st, v in sorted(summary.items(), key=lambda kv: -kv[1]):
        if v > 0:
            print(f"  {st:<9} ≤ {v/1e4:>8.0f} 万元/笔")
        else:
            print(f"  {st:<9}   任何规模下都被成本吃光")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
