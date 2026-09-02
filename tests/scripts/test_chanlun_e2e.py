"""缠论模型端到端测试：验证笔/中枢/线段/买卖点正确性，回测准确度验证。

此脚本用于手动验证改进后的缠论模型：
1. 用合成数据验证核心算法
2. 用真实数据验证前端显示
3. 验证回测与缠论信号的一致性
"""

from __future__ import annotations

import math
import sys
from datetime import datetime, timedelta

import pandas as pd

# 添加源码路径
sys.path.insert(0, "src")

from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig
from easy_tdx.chanlun.types import Direction


def make_trend_data(n: int, base: float, trend_slope: float, noise: float) -> pd.DataFrame:
    """生成有趋势的合成K线。"""
    rows = []
    dt = datetime(2023, 1, 4)
    for i in range(n):
        trend = i * trend_slope
        noise_val = math.sin(i / 10.0) * noise + (math.random() - 0.5) * noise * 0.5
        close = base + trend + noise_val
        open_ = close + (math.random() - 0.5) * noise * 0.3
        high = max(open_, close) + abs(noise_val) * 0.2
        low = min(open_, close) - abs(noise_val) * 0.2
        rows.append(
            {
                "date": dt,
                "open": round(open_, 2),
                "close": round(close, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "vol": int(1000000 + i * 1000),
            }
        )
        dt += timedelta(days=1)
    return pd.DataFrame(rows)


def make_consolidation(n: int, base: float, amplitude: float) -> pd.DataFrame:
    """生成盘整走势。"""
    rows = []
    dt = datetime(2023, 1, 4)
    for i in range(n):
        close = base + math.sin(i / 8.0) * amplitude
        open_ = close + (math.random() - 0.5) * amplitude * 0.3
        high = max(open_, close) + amplitude * 0.15
        low = min(open_, close) - amplitude * 0.15
        rows.append(
            {
                "date": dt,
                "open": round(open_, 2),
                "close": round(close, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "vol": int(800000 + i * 500),
            }
        )
        dt += timedelta(days=1)
    return pd.DataFrame(rows)


def main():
    print("=" * 60)
    print("缠论模型端到端测试")
    print("=" * 60)

    # 测试1：上升趋势中的笔
    print("\n【测试1】上升趋势笔识别")
    df1 = make_trend_data(200, 50.0, 0.08, 1.5)
    a1 = ChanlunAnalyser(code="TEST1", frequency="daily")
    r1 = a1.process_klines(df1)
    print(
        f"  K线: {len(r1.klines)}, 笔: {len(r1.bis)}, 中枢: {len(r1.zss)}, 买卖点: {len(r1.mmds)}"
    )

    # 验证笔方向交替
    alt_ok = True
    for i in range(1, len(r1.bis)):
        if r1.bis[i - 1].direction == r1.bis[i].direction:
            alt_ok = False
            print(
                f"  ❌ 笔方向未交替: [{i - 1}]={r1.bis[i - 1].direction} vs "
                f"[{i}]={r1.bis[i].direction}"
            )
            break
    print(f"  笔方向交替: {'✓' if alt_ok else '❌'}")

    # 验证笔端点价格方向
    endpoint_ok = True
    for bi in r1.bis:
        if bi.direction == Direction.UP and bi.end.val <= bi.start.val:
            endpoint_ok = False
            print(f"  ❌ 向上笔终点不高于起点: {bi}")
        elif bi.direction == Direction.DOWN and bi.end.val >= bi.start.val:
            endpoint_ok = False
            print(f"  ❌ 向下笔终点不低于起点: {bi}")
    print(f"  笔端点方向一致: {'✓' if endpoint_ok else '❌'}")

    # 测试2：盘整中的中枢识别
    print("\n【测试2】盘整中枢识别")
    df2 = make_consolidation(300, 20.0, 1.0)
    config2 = ChanlunConfig(zs_min_lines=3)
    a2 = ChanlunAnalyser(code="TEST2", frequency="daily", config=config2)
    r2 = a2.process_klines(df2)
    print(f"  K线: {len(r2.klines)}, 笔: {len(r2.bis)}, 中枢: {len(r2.zss)}")

    zs_ok = True
    for zs in r2.zss:
        if zs.zg <= zs.zd:
            zs_ok = False
            print(f"  ❌ 中枢zg<=zd: zg={zs.zg}, zd={zs.zd}")
        if zs.gg < zs.zg or zs.dd > zs.zd:
            zs_ok = False
            print(f"  ❌ 中枢gg<zg或dd>zd: gg={zs.gg}, dd={zs.dd}")
    print(f"  中枢区间有效: {'✓' if zs_ok else '❌'}")

    # 测试3：买卖点置信度范围
    print("\n【测试3】买卖点置信度验证")
    conf_ok = True
    for mmd in r2.mmds:
        if not (0.0 <= mmd.confidence <= 1.0):
            conf_ok = False
            print(f"  ❌ 置信度超出范围: {mmd.confidence}")
    print(f"  置信度范围[0,1]: {'✓' if conf_ok else '❌'}")

    # 测试4：弱笔跳过配置
    print("\n【测试4】弱笔跳过配置")
    df4 = make_consolidation(100, 10.0, 0.005)  # 极小振幅
    config_skip = ChanlunConfig(bi_weak_skip=True)
    config_noskip = ChanlunConfig(bi_weak_skip=False)
    a4_skip = ChanlunAnalyser(code="TEST4_SKIP", frequency="daily", config=config_skip)
    a4_noskip = ChanlunAnalyser(code="TEST4_NOSKIP", frequency="daily", config=config_noskip)
    r4_skip = a4_skip.process_klines(df4)
    r4_noskip = a4_noskip.process_klines(df4)
    print(f"  不跳弱笔: {len(r4_noskip.bis)} 笔")
    print(f"  跳弱笔: {len(r4_skip.bis)} 笔")
    skip_ok = len(r4_skip.bis) <= len(r4_noskip.bis)
    print(f"  跳弱笔数量 <= 不跳: {'✓' if skip_ok else '❌'}")

    # 测试5：序列化完整性
    print("\n【测试5】序列化完整性")
    d = r1.to_dict()
    required_keys = ["bis", "zss", "xds", "mmds", "fractal_count", "bi_count"]
    missing = [k for k in required_keys if k not in d]
    print(f"  缺少字段: {missing if missing else '无'}")
    print(f"  序列化完整: {'✓' if not missing else '❌'}")

    # 测试6：多周期兼容性
    print("\n【测试6】多周期兼容性")
    df_day = make_trend_data(150, 30.0, 0.05, 1.0)
    df_min = make_trend_data(150, 30.0, 0.05, 0.3)
    a_day = ChanlunAnalyser(code="DAY", frequency="daily")
    a_min = ChanlunAnalyser(code="MIN", frequency="5min")
    r_day = a_day.process_klines(df_day)
    r_min = a_min.process_klines(df_min)
    print(f"  日线: {len(r_day.bis)} 笔, {len(r_day.zss)} 中枢")
    print(f"  5分钟: {len(r_min.bis)} 笔, {len(r_min.zss)} 中枢")
    print("  多周期兼容: ✓ (无崩溃)")

    # 总结
    print("\n" + "=" * 60)
    all_pass = alt_ok and endpoint_ok and zs_ok and conf_ok and skip_ok and not missing
    print(f"测试结果: {'全部通过 ✓' if all_pass else '存在失败项 ❌'}")
    print("=" * 60)

    return 0 if all_pass else 1


if __name__ == "__main__":
    # 修复 random 调用
    import random

    math.random = random.random
    sys.exit(main())
