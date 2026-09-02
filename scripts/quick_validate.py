#!/usr/bin/env python3
"""快速验证脚本：测试缠论核心功能是否正常工作。

用法：
    python scripts/quick_validate.py
"""

from __future__ import annotations

import sys
import math
from datetime import datetime, timedelta

sys.path.insert(0, "src")

import pandas as pd
from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig


def make_test_data(n: int = 200, base: float = 50.0) -> pd.DataFrame:
    """生成测试用的K线数据。"""
    rows = []
    dt = datetime(2023, 1, 4)
    for i in range(n):
        close = base + i * 0.05 + math.sin(i / 15.0) * 2.0
        open_ = close + math.sin(i / 10.0) * 0.5
        high = max(open_, close) + abs(math.sin(i / 8.0)) * 1.0
        low = min(open_, close) - abs(math.sin(i / 8.0)) * 1.0
        rows.append({
            "date": dt,
            "open": round(open_, 2),
            "close": round(close, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "vol": int(1000000 + i * 5000),
        })
        dt += timedelta(days=1)
    return pd.DataFrame(rows)


def main():
    print("=" * 50)
    print("easy_tdx 缠论功能快速验证")
    print("=" * 50)

    df = make_test_data(200, base=50.0)
    print(f"\n测试数据: {len(df)} 根K线, 价格范围 [{df['low'].min():.2f}, {df['high'].max():.2f}]")

    # 测试1: 基础缠论分析
    print("\n[1] 基础缠论分析...")
    analyser = ChanlunAnalyser(code="TEST", frequency="daily")
    result = analyser.process_klines(df)
    print(f"  K线: {len(result.klines)}, 缠论K线: {len(result.cklines)}")
    print(f"  分型: {len(result.fractals)}, 笔: {len(result.bis)}, 中枢: {len(result.zss)}")
    print(f"  线段: {len(result.xds)}, 买卖点: {len(result.mmds)}, 背驰: {len(result.bcs)}")

    # 验证笔方向交替
    alt_ok = all(
        result.bis[i].direction != result.bis[i + 1].direction
        for i in range(len(result.bis) - 1)
    ) if len(result.bis) > 1 else True
    print(f"  笔方向交替: {'✓' if alt_ok else '❌'}")

    # 验证中枢有效性
    zs_ok = all(zs.zg > zs.zd for zs in result.zss)
    print(f"  中枢区间有效: {'✓' if zs_ok else '❌'}")

    # 验证置信度范围
    conf_ok = all(0.0 <= m.confidence <= 1.0 for m in result.mmds)
    print(f"  置信度范围: {'✓' if conf_ok else '❌'}")

    # 测试2: 弱笔跳过
    print("\n[2] 弱笔跳过配置...")
    df_flat = make_test_data(100, base=10.0)
    # 制造极小振幅数据
    df_flat["close"] = df_flat["close"] * 1.0001
    df_flat["open"] = df_flat["close"]
    df_flat["high"] = df_flat["close"] + 0.001
    df_flat["low"] = df_flat["close"] - 0.001

    config_skip = ChanlunConfig(bi_weak_skip=True)
    config_no_skip = ChanlunConfig(bi_weak_skip=False)

    a_skip = ChanlunAnalyser(code="SKIP", frequency="daily", config=config_skip)
    a_no_skip = ChanlunAnalyser(code="NOSKIP", frequency="daily", config=config_no_skip)

    r_skip = a_skip.process_klines(df_flat)
    r_no_skip = a_no_skip.process_klines(df_flat)

    print(f"  不跳弱笔: {len(r_no_skip.bis)} 笔")
    print(f"  跳弱笔: {len(r_skip.bis)} 笔")
    skip_ok = len(r_skip.bis) <= len(r_no_skip.bis)
    print(f"  跳过效果: {'✓' if skip_ok else '❌'}")

    # 测试3: 序列化
    print("\n[3] 序列化测试...")
    d = result.to_dict()
    required = ["bis", "zss", "xds", "mmds", "fractal_count", "bi_count", "zs_count"]
    missing = [k for k in required if k not in d]
    print(f"  缺少字段: {missing if missing else '无'}")
    print(f"  序列化: {'✓' if not missing else '❌'}")

    # 总结
    print("\n" + "=" * 50)
    all_ok = alt_ok and zs_ok and conf_ok and skip_ok and not missing
    print(f"验证结果: {'全部通过 ✓' if all_ok else '存在失败项 ❌'}")
    print("=" * 50)

    if result.mmds:
        print(f"\n最近5个买卖点:")
        for m in result.mmds[-5:]:
            bi_date = result._fmt_dt(m.bi.end.k.date) if m.bi else "?"
            print(f"  {m.mmd_type.value:8s} | 置信度 {(m.confidence*100):5.1f}% | {bi_date}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
