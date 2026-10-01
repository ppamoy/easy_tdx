"""由高级别 K 线合成低级别 K 线，供区间套（跨周期确认）使用。

缠论区间套的原文含义：大级别的背驰段，在小级别上也被确认为背驰。
回测时策略只被喂进一个周期的 DataFrame（例如日线），拿不到真实的 30 分钟线。
本模块用"周期放大"的办法合成近似低级别数据：

    ratio = 低级别根数 / 每根高级别 bar
    例如日线 -> 30 分钟：A 股每天 4 小时 = 8 根 30 分钟，ratio = 8

合成方法：把每根高级别 bar 的 (open, high, low, close) 展开成 ratio 根子 bar，
在高级别 OHLC 范围内构造一条经过所有关键点的路径。这样：
  - 低级别的最高/最低价不会超出高级别 bar 的范围（保证不凭空造价格）
  - 低级别收盘点位与高级别一致（保证跨周期时间对齐后的结论可比）

重要：这只是**近似**，不是真实 Tick。因此区间套确认结果应视为"结构性参考"，
不能当成精确的小级别买卖点。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# 每根高级别 bar 对应的低级别根数（A 股交易时段 4 小时 = 240 分钟）
_UNITS_PER_BAR = {
    ("DAY", "MIN_60"): 4,
    ("DAY", "MIN_30"): 8,
    ("DAY", "MIN_15"): 16,
    ("DAY", "MIN_5"): 48,
    ("WEEK", "DAY"): 5,
    ("MONTH", "DAY"): 21,
}


def units_per_bar(high_level: str, low_level: str) -> int:
    """高级别一根 bar 内含多少根低级别 bar。未知组合返回 0。"""
    return _UNITS_PER_BAR.get((high_level.upper(), low_level.upper()), 0)


def _expand_ohlc(
    o: float, h: float, low: float, c: float, n: int, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """把一根 bar 展开成 n 根子 bar，返回 (opens, highs, lows, closes)。

    路径必须经过 o / h / low / c 四个关键点，且子 bar 不越界。
    """
    if n <= 0:
        return np.array([]), np.array([]), np.array([]), np.array([])
    lo = min(o, c, low)
    hi = max(o, c, h)
    if n == 1:
        return (
            np.array([o]),
            np.array([hi]),
            np.array([lo]),
            np.array([c]),
        )

    # 构造一条 o -> ... -> h/low -> ... -> c 的价格路径：
    # 先走到极值之一，再走到另一极值，最后收在 c
    mid = n // 2
    # 第一段：o → h（或 low），第二段：→ low（或 h），第三段：→ c
    first_ext = h if rng.random() < 0.5 else low
    second_ext = low if first_ext == h else h

    path = np.empty(n)
    path[0] = o
    path[n - 1] = c
    if n >= 3:
        path[mid] = first_ext
        if n >= 4:
            path[min(mid + 1, n - 2)] = second_ext

    # 其余点位在 [lo, hi] 内随机游走，并做单调插值保证连续
    known = {0: o, n - 1: c}
    if n >= 3:
        known[mid] = first_ext
    if n >= 4:
        known[min(mid + 1, n - 2)] = second_ext
    ks = sorted(known)
    for a, b in zip(ks, ks[1:]):
        va, vb = known[a], known[b]
        span = b - a
        if span <= 1:
            continue
        noise = rng.normal(0, max(abs(vb - va) * 0.15, 1e-9), span - 1)
        walk = np.linspace(va, vb, span + 1)[1:-1] + noise
        path[a + 1 : b] = np.clip(walk, lo, hi)
    path = np.clip(path, lo, hi)
    path[0] = o
    path[n - 1] = c

    # 由路径反推每根子 bar 的 OHLC
    opens = np.empty(n)
    closes = path
    opens[0] = o
    opens[1:] = path[:-1]
    highs = np.maximum(opens, closes)
    lows = np.minimum(opens, closes)
    # 让相邻子 bar 之间有一点波动，避免 high==low 的退化 bar
    jitter_h = np.abs(rng.normal(0, (hi - lo) * 0.02 + 1e-9, n))
    highs = np.minimum(highs + jitter_h, hi)
    jitter_l = np.abs(rng.normal(0, (hi - lo) * 0.02 + 1e-9, n))
    lows = np.maximum(lows - jitter_l, lo)
    # 保证整段覆盖高级别的高低点
    highs[np.argmax(highs)] = hi
    lows[np.argmin(lows)] = lo
    return (
        opens,
        np.minimum(np.maximum(highs, np.maximum(opens, closes)), hi),
        np.maximum(np.minimum(lows, np.minimum(opens, closes)), lo),
        closes,
    )


def synthesize_lower_level(
    df: pd.DataFrame,
    high_level: str = "DAY",
    low_level: str = "MIN_30",
    seed: int = 20240101,
) -> pd.DataFrame | None:
    """把高级别 DataFrame 合成为近似低级别 DataFrame。

    Args:
        df: 高级别 K 线，需含 open/high/low/close 与 datetime
        high_level: 高级别周期名
        low_level: 目标低级别周期名
        seed: 随机种子（保证可复现——回测必须可复现）

    Returns:
        合成的低级别 DataFrame；无法合成时返回 None。
    """
    n_per = units_per_bar(high_level, low_level)
    if n_per <= 0 or df is None or len(df) == 0:
        return None
    need = {"open", "high", "low", "close"}
    if not need.issubset(df.columns):
        return None

    rng = np.random.default_rng(seed)
    o_cols, h_cols, l_cols, c_cols = [], [], [], []
    for _, row in df.iterrows():
        o, h, lo, c = (
            float(row["open"]),
            float(row["high"]),
            float(row["low"]),
            float(row["close"]),
        )
        oo, hh, ll, cc = _expand_ohlc(o, h, lo, c, n_per, rng)
        o_cols.append(oo)
        h_cols.append(hh)
        l_cols.append(ll)
        c_cols.append(cc)

    opens = np.concatenate(o_cols)
    highs = np.concatenate(h_cols)
    lows = np.concatenate(l_cols)
    closes = np.concatenate(c_cols)

    # 时间轴：把每根高级别 bar 的区间均分给子 bar，保证跨周期时间重叠对齐可用
    if "datetime" in df.columns:
        base = pd.to_datetime(df["datetime"])
        span = base.diff().shift(-1)
        # 最后一根用前一跨度的中位数兜底
        if span.isna().all():
            step = pd.Timedelta(days=1)
            starts = base + step * 0.0
        else:
            med = span.median()
            span = span.fillna(med if pd.notna(med) else pd.Timedelta(days=1))
            starts = base
        sub_step = (span / n_per).fillna(pd.Timedelta(days=1) / n_per)
        times = np.concatenate(
            [
                pd.date_range(starts.iloc[i], periods=n_per, freq=sub_step.iloc[i])
                for i in range(len(df))
            ]
        )
    else:
        times = pd.RangeIndex(len(closes))

    vol = df["vol"] / n_per if "vol" in df.columns else np.ones(len(closes))
    vol_arr = np.concatenate([np.full(n_per, float(v)) for v in vol])

    out = pd.DataFrame(
        {
            "datetime": times,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "vol": vol_arr,
        }
    )
    if "amount" in df.columns:
        amt = df["amount"] / n_per
        out["amount"] = np.concatenate([np.full(n_per, float(v)) for v in amt])
    return out
