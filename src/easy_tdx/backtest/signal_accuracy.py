"""信号前瞻命中率与模型准确度验证。

目标：让用户通过历史回测验证「模型信号是否真的择时准确」，而不是只看账户盈亏。
对每次实际成交的 BUY/SELL 信号，统计未来 N 根 K 线的前瞻收益与命中率，并与
「随机入场基准」和「同期买入持有基准」对比，回答两个问题：

1. 模型的买卖点是否显著好于随机入场？（超额命中率 = 模型命中率 - 随机命中率）
2. 模型相对涨了就不动的买入持有是否有超额收益？（alpha）

术语：
- 命中（hit）：对 BUY 信号，未来 N 根收益 > 0；对 SELL 信号，未来 N 根收益 < 0
  （卖出是为了避开下跌，因此下跌视为命中）。
- 随机基准：以相同信号数量在全部可入场 bar 上随机采样（可复现 seed），
  统计同一批前瞻窗口的平均命中率与收益，作为「抛硬币择时」的下限参照。
- 前瞻收益：close[idx + h] / close[idx] - 1，h 为持有根数（不含交易成本）。

所有输出为 JSON 兼容的纯 Python 类型（float/int/str/list/dict）。
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pandas as pd

# 默认前瞻窗口（根数）：1/3/5/10/20 根 K 线后
DEFAULT_HORIZONS: tuple[int, ...] = (1, 3, 5, 10, 20)
# 随机基准采样次数（每窗口）
RANDOM_SAMPLES = 512


def _datetime_to_int(arr: np.ndarray) -> np.ndarray:
    """把 datetime 列规整为 YYYYMMDD 整数（与 backtest.strategy 同一口径）。

    Args:
        arr: np.datetime64 / pd.Timestamp / 对象数组

    Returns:
        int64 数组（YYYYMMDD）
    """
    if len(arr) == 0:
        return np.asarray([], dtype=np.int64)
    first = arr[0]
    if isinstance(first, np.datetime64 | pd.Timestamp | pd.Timedelta):
        # 真日期类型 → YYYYMMDD
        return np.asarray(pd.to_datetime(arr).strftime("%Y%m%d").astype(np.int64))
    # 已是数值（int/float，含 YYYYMMDD）原样取整，避免被 pd.to_datetime 误当纳秒
    return np.asarray(arr, dtype=np.float64).astype(np.int64)


def _random_split(n: int, seed: int) -> np.ndarray:
    """可复现的随机索引采样。

    样本数 = min(RANDOM_SAMPLES, n)；可用 bar 不足采样数时直接用全部
    （小样本下全量 = 真实平均基准，避免放回抽样带来的偏差）。
    """
    if n <= 0:
        return np.asarray([], dtype=np.int64)
    if n <= RANDOM_SAMPLES:
        return np.arange(n)
    rng = np.random.default_rng(seed)
    return rng.choice(n, size=RANDOM_SAMPLES, replace=False)


def _horizon_stats(
    fwd: np.ndarray,
) -> dict[str, float]:
    """压缩一个前瞻收益数组为统计字段。"""
    if len(fwd) == 0:
        return {"count": 0, "hit_rate": 0.0, "avg_return": 0.0, "median_return": 0.0}
    return {
        "count": int(len(fwd)),
        "hit_rate": float(np.mean(fwd > 0)),
        "avg_return": float(np.mean(fwd)),
        "median_return": float(np.median(fwd)),
    }


def compute_signal_accuracy(
    df: pd.DataFrame,
    trades: pd.DataFrame,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    strategy_total_return: float | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    """计算一次回测的信号前瞻命中率与准确度验证报告。

    Args:
        df: 回测用 OHLCV DataFrame（须含 datetime/close 列）
        trades: 成交记录 DataFrame（须含 datetime/direction/rejected 列，
            引擎 _trades_to_df 输出即满足）
        horizons: 前瞻窗口（根数）元组
        strategy_total_return: 策略自身总收益率（用于 alpha 对比，可为 None）
        seed: 随机基准采样种子

    Returns:
        dict：{"buy": {...}, "sell": {...}, "benchmark": {...}, "verdict": ...}
        无任何可验证信号时返回 {"buy": None, "sell": None, "benchmark": {...}, "verdict": ...}
    """
    if df is None or len(df) == 0 or trades is None or len(trades) == 0:
        return _empty_report(strategy_total_return)

    if "close" not in df.columns:
        return _empty_report(strategy_total_return, note="数据缺少 close 列")

    closes = df["close"].to_numpy(dtype=float)
    n_bars = len(closes)
    if n_bars < 2:
        return _empty_report(strategy_total_return, note="数据不足 2 根，无法验证前瞻命中率")

    # datetime → bar 索引映射（YYYYMMDD int）
    if "datetime" in df.columns:
        dt_ints = _datetime_to_int(df["datetime"].to_numpy())
    elif "date" in df.columns:
        dt_ints = _datetime_to_int(df["date"].to_numpy())
    else:
        return _empty_report(strategy_total_return, note="数据缺少 datetime/date 列")

    idx_by_dt: dict[int, int] = {}
    for i, dt in enumerate(dt_ints):
        idx_by_dt.setdefault(int(dt), i)

    # 分离 BUY / SELL 已成交信号
    buy_trades = trades[(trades["direction"] == "BUY") & (~trades["rejected"])]
    sell_trades = trades[(trades["direction"] == "SELL") & (~trades["rejected"])]

    # 随机基准：对每个窗口在全部可入场 bar 上采样一次（各窗口独立）
    random_baseline: dict[int, dict[str, float]] = {}
    for h in horizons:
        if n_bars <= h:
            random_baseline[h] = {"count": 0, "hit_rate": 0.0, "avg_return": 0.0}
            continue
        eligible = n_bars - h
        sample_idx = _random_split(eligible, seed)
        fwd = closes[sample_idx + h] / closes[sample_idx] - 1.0
        random_baseline[h] = {
            "count": int(len(sample_idx)),
            "hit_rate": float(np.mean(fwd > 0)),
            "avg_return": float(np.mean(fwd)),
        }

    def _signal_stats(
        dir_trades: pd.DataFrame,
        direction: Literal["BUY", "SELL"],
    ) -> dict[str, Any] | None:
        """单方向信号的前瞻统计。"""
        if len(dir_trades) == 0:
            return None
        result: dict[str, Any] = {"signals": int(len(dir_trades)), "horizons": {}}
        # 成交记录的 datetime 在不同路径下可能是 int(YYYYMMDD) 或 Timestamp，
        # 统一规整为 int 便于查索引映射。
        signal_dts = _datetime_to_int(dir_trades["datetime"].to_numpy())
        for h in horizons:
            fwd_list: list[float] = []
            for dt in signal_dts.tolist():
                idx = idx_by_dt.get(int(dt))
                if idx is None or idx + h >= n_bars:
                    continue
                # BUY 持有 N 根；SELL 为空仓避跌，命中 = 期间价格下跌
                raw = closes[idx + h] / closes[idx] - 1.0
                fwd_list.append(raw)
            fwd = np.asarray(fwd_list, dtype=float)
            base = random_baseline[h]
            stats = _horizon_stats(fwd)
            if direction == "SELL" and len(fwd) > 0:
                # 卖出方向：下跌为命中
                stats["hit_rate"] = float(np.mean(fwd < 0))
                stats["avg_return"] = float(np.mean(-fwd))
                stats["median_return"] = float(np.median(-fwd))
            stats["baseline_hit_rate"] = base["hit_rate"]
            stats["baseline_avg_return"] = base["avg_return"]
            stats["excess_hit_rate"] = (
                float(stats["hit_rate"] - base["hit_rate"]) if stats["count"] else 0.0
            )
            stats["excess_avg_return"] = (
                float(stats["avg_return"] - base["avg_return"]) if stats["count"] else 0.0
            )
            result["horizons"][str(h)] = stats
        return result

    buy_report: dict[str, Any] | None = _signal_stats(buy_trades, "BUY")
    sell_report: dict[str, Any] | None = _signal_stats(sell_trades, "SELL")

    # 基准：同期买入持有总收益
    buy_hold_return = float(closes[-1] / closes[0] - 1.0) if closes[0] != 0 else 0.0
    benchmark: dict[str, float] = {"buy_hold_return": buy_hold_return}
    if strategy_total_return is not None:
        benchmark["strategy_return"] = strategy_total_return
        benchmark["alpha"] = float(strategy_total_return - buy_hold_return)

    verdict = _build_verdict(buy_report, buy_hold_return)

    return {
        "buy": buy_report,
        "sell": sell_report,
        "benchmark": benchmark,
        "verdict": verdict,
    }


def _build_verdict(
    buy_report: dict[str, Any] | None,
    buy_hold_return: float,
) -> str:
    """根据 5 根窗口（若存在）生成一句可读结论。"""
    if buy_report is None:
        return "无买入成交记录，无法验证择时准确度"
    horizons = buy_report.get("horizons", {})
    h5 = horizons.get("5") or horizons.get("3") or horizons.get("10")
    if not h5 or h5.get("count", 0) == 0:
        return "买入信号不足，无法形成可靠结论（样本过少）"
    excess = float(h5.get("excess_hit_rate", 0.0))
    avg = float(h5.get("avg_return", 0.0))
    n = int(h5.get("count", 0))
    parts = [f"买入信号 {n} 个"]
    if excess > 0.05:
        grade = "信号命中率显著高于随机入场基准"
    elif excess > 0:
        grade = "信号命中率略高于随机入场基准"
    elif excess > -0.05:
        grade = "命中率与随机入场基本相当（择时贡献有限）"
    else:
        grade = "信号命中率低于随机入场（可能有反向择时风险）"
    parts.append(grade)
    if buy_hold_return != 0:
        parts.append(f"同期买入持有 {buy_hold_return:+.2%}")
    parts.append(f"5根前瞻均值 {avg:+.2%}")
    return "；".join(parts) + "。"


def _empty_report(
    strategy_total_return: float | None,
    note: str = "",
) -> dict[str, Any]:
    """无可验证数据时的空报告。"""
    benchmark: dict[str, float] = {}
    if strategy_total_return is not None:
        benchmark["strategy_return"] = strategy_total_return
        benchmark["buy_hold_return"] = 0.0
        benchmark["alpha"] = strategy_total_return
    report: dict[str, Any] = {"buy": None, "sell": None, "benchmark": benchmark}
    if note:
        report["note"] = note
    report["verdict"] = note or "无成交记录，无法验证择时准确度"
    return report
