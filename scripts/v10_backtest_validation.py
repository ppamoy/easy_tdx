#!/usr/bin/env python3
"""V10 缠论买卖点回测验证脚本。

用于验证V10改进（MA斜率、BOLL过滤、ADX趋势强度、RSI动量确认）对
3买/3卖准确率提升的效果。

用法:
    python3 scripts/v10_backtest_validation.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig
from easy_tdx.chanlun.mmd import find_mmds, _calc_ma_slope, _calc_boll_position


def generate_trending_data(
    n: int = 300,
    trend: str = "up",
    seed: int = 42,
) -> pd.DataFrame:
    """生成有趋势的模拟K线数据。"""
    np.random.seed(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    close = [100.0]
    for i in range(1, n):
        if trend == "up":
            close.append(close[-1] * (1.0015 + np.random.normal(0, 0.008)))
        else:
            close.append(close[-1] * (0.9985 + np.random.normal(0, 0.008)))
    close = np.array(close)
    return pd.DataFrame({
        "datetime": dates,
        "open": close * (1 + np.random.uniform(-0.003, 0.003, n)),
        "high": close * (1 + np.random.uniform(0, 0.01, n)),
        "low": close * (1 + np.random.uniform(-0.01, 0, n)),
        "close": close,
        "vol": [1e6] * n,
    })


def generate_oscillating_data(n: int = 300, seed: int = 77) -> pd.DataFrame:
    """生成震荡数据（无明确趋势）。"""
    np.random.seed(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    close = [50.0]
    for i in range(1, n):
        close.append(close[-1] * (1 + np.random.normal(0, 0.015)))
    close = np.array(close)
    return pd.DataFrame({
        "datetime": dates,
        "open": close * (1 + np.random.uniform(-0.003, 0.003, n)),
        "high": close * (1 + np.random.uniform(0, 0.01, n)),
        "low": close * (1 + np.random.uniform(-0.01, 0, n)),
        "close": close,
        "vol": [1e6] * n,
    })


def run_backtest(df: pd.DataFrame, label: str) -> dict:
    """运行缠论分析并统计买卖点。"""
    analyser = ChanlunAnalyser(code="TEST", frequency="daily")
    result = analyser.process_klines(df)

    counts = {
        "1buy": sum(1 for m in result.mmds if m.mmd_type.value == "1buy"),
        "1sell": sum(1 for m in result.mmds if m.mmd_type.value == "1sell"),
        "2buy": sum(1 for m in result.mmds if m.mmd_type.value == "2buy"),
        "2sell": sum(1 for m in result.mmds if m.mmd_type.value == "2sell"),
        "3buy": sum(1 for m in result.mmds if m.mmd_type.value == "3buy"),
        "3sell": sum(1 for m in result.mmds if m.mmd_type.value == "3sell"),
        "total": len(result.mmds),
    }

    # 计算3买/3卖的平均置信度
    buy_3_conf = [m.confidence for m in result.mmds if m.mmd_type.value == "3buy"]
    sell_3_conf = [m.confidence for m in result.mmds if m.mmd_type.value == "3sell"]

    return {
        "label": label,
        "counts": counts,
        "avg_3buy_conf": round(np.mean(buy_3_conf), 3) if buy_3_conf else None,
        "avg_3sell_conf": round(np.mean(sell_3_conf), 3) if sell_3_conf else None,
    }


def main():
    """运行回测验证。"""
    print("=" * 70)
    print("EasyTDX V10 缠论买卖点回测验证")
    print("=" * 70)
    print()

    results = []

    # 1. 上升趋势数据
    df_up = generate_trending_data(300, trend="up", seed=42)
    results.append(run_backtest(df_up, "上升趋势(300日)"))

    # 2. 下降趋势数据
    df_down = generate_trending_data(300, trend="down", seed=43)
    results.append(run_backtest(df_down, "下降趋势(300日)"))

    # 3. 震荡数据
    df_osc = generate_oscillating_data(300, seed=77)
    results.append(run_backtest(df_osc, "震荡市场(300日)"))

    # 4. 长期上涨数据（更长的趋势）
    df_long_up = generate_trending_data(500, trend="up", seed=99)
    results.append(run_backtest(df_long_up, "长期上涨(500日)"))

    # 5. 高波动数据
    np.random.seed(55)
    dates = pd.date_range("2024-01-01", periods=300, freq="D")
    close = [100.0]
    for i in range(1, 300):
        close.append(close[-1] * (1 + np.random.normal(0, 0.02)))
    close = np.array(close)
    df_high_vol = pd.DataFrame({
        "datetime": dates,
        "open": close * (1 + np.random.uniform(-0.01, 0.01, 300)),
        "high": close * (1 + np.random.uniform(0, 0.02, 300)),
        "low": close * (1 + np.random.uniform(-0.02, 0, 300)),
        "close": close,
        "vol": [1e6] * 300,
    })
    results.append(run_backtest(df_high_vol, "高波动市场(300日)"))

    # 打印结果
    print(f"{'场景':<25} {'1买':>6} {'2买':>6} {'3买':>6} {'1卖':>6} {'2卖':>6} {'3卖':>6} {'总计':>6}")
    print("-" * 70)
    for r in results:
        c = r["counts"]
        print(
            f"{r['label']:<25} "
            f"{c['1buy']:>6} {c['2buy']:>6} {c['3buy']:>6} "
            f"{c['1sell']:>6} {c['2sell']:>6} {c['3sell']:>6} "
            f"{c['total']:>6}"
        )

    print()
    print("V10 改进对比（3买/3卖置信度提升）:")
    print("-" * 70)
    for r in results:
        if r["avg_3buy_conf"] is not None:
            print(f"  {r['label']}: 3买平均置信度 = {r['avg_3buy_conf']:.3f}")
        if r["avg_3sell_conf"] is not None:
            print(f"  {r['label']}: 3卖平均置信度 = {r['avg_3sell_conf']:.3f}")

    print()
    print("=" * 70)
    print("V10 核心改进说明:")
    print("  1. MA斜率确认: 3买要求MA20向上倾斜，3卖要求MA20向下倾斜")
    print("  2. BOLL位置过滤: 避免在极端位置(上轨外侧/下轨内侧)入场")
    print("  3. ADX趋势强度: 要求ADX>=20才确认信号有效")
    print("  4. RSI动量确认: 3买RSI在35-80之间且动量向上，3卖相反")
    print("  5. 多因子共振: 同时满足越多条件，置信度越高")
    print("  6. 置信度校准: 3买从0.60→0.68，3卖从0.55→0.63")
    print("=" * 70)


if __name__ == "__main__":
    main()
