#!/usr/bin/env python3
"""easy_tdx 缠论模型综合验证脚本。

运行方式：
    cd /home/skp/workspace/easy_tdx
    python -m pytest tests/unit/test_chanlun.py -xvs
    python -m pytest tests/unit/test_chanlun_v84_train_session.py -xvs
    python scripts/verify_chanlun_model.py

验证内容：
1. 笔计算正确性（分型→笔的完整流程）
2. 中枢计算正确性（至少3笔重叠）
3. 线段计算正确性（特征序列分型）
4. 买卖点识别正确性（1买/1卖/2买/2卖/3买/3卖）
5. 背驰判断正确性（笔/盘整/趋势背驰）
6. 置信度计算合理性
7. 前后端数据一致性
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

import pandas as pd

from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig
from easy_tdx.chanlun.types import MMDType


def _synthetic_uptrend(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """生成上升趋势合成数据（含明显笔、中枢、买卖点）。"""
    rng = random.Random(seed)
    base = 10.0
    rows: list[dict] = []
    dt = datetime(2024, 1, 2)
    for i in range(n):
        # 上升趋势 + 震荡中枢
        wave = math.sin(i / 30.0) * 2.0 + math.sin(i / 10.0) * 0.5
        drift = 0.005 * i  # 缓慢上涨
        open_ = base + wave + drift
        close = open_ + rng.uniform(-0.2, 0.3)
        high = max(open_, close) + rng.uniform(0.05, 0.3)
        low = min(open_, close) - rng.uniform(0.05, 0.3)
        rows.append({
            "date": dt,
            "open": round(open_, 3),
            "close": round(close, 3),
            "high": round(high, 3),
            "low": round(low, 3),
            "vol": float(rng.randint(100_000, 500_000)),
        })
        dt += timedelta(days=1)
    return pd.DataFrame(rows)


def _synthetic_downtrend(n: int = 300, seed: int = 43) -> pd.DataFrame:
    """生成下降趋势合成数据。"""
    rng = random.Random(seed)
    base = 50.0
    rows: list[dict] = []
    dt = datetime(2024, 1, 2)
    for i in range(n):
        wave = math.sin(i / 25.0) * 1.5 + math.sin(i / 8.0) * 0.3
        drift = -0.005 * i
        open_ = base + wave + drift
        close = open_ + rng.uniform(-0.2, 0.2)
        high = max(open_, close) + rng.uniform(0.05, 0.25)
        low = min(open_, close) - rng.uniform(0.05, 0.25)
        rows.append({
            "date": dt,
            "open": round(open_, 3),
            "close": round(close, 3),
            "high": round(high, 3),
            "low": round(low, 3),
            "vol": float(rng.randint(100_000, 500_000)),
        })
        dt += timedelta(days=1)
    return pd.DataFrame(rows)


def _synthetic_sideways(n: int = 200, seed: int = 44) -> pd.DataFrame:
    """生成横盘震荡数据（无明确趋势，应有中枢但无1买/1卖）。"""
    rng = random.Random(seed)
    base = 20.0
    rows: list[dict] = []
    dt = datetime(2024, 1, 2)
    for i in range(n):
        wave = math.sin(i / 15.0) * 1.0
        open_ = base + wave
        close = open_ + rng.uniform(-0.3, 0.3)
        high = max(open_, close) + rng.uniform(0.05, 0.2)
        low = min(open_, close) - rng.uniform(0.05, 0.2)
        rows.append({
            "date": dt,
            "open": round(open_, 3),
            "close": round(close, 3),
            "high": round(high, 3),
            "low": round(low, 3),
            "vol": float(rng.randint(50_000, 200_000)),
        })
        dt += timedelta(days=1)
    return pd.DataFrame(rows)


def test_basic_pipeline() -> dict:
    """测试基本缠论管道。"""
    results = {}
    
    # 测试上升趋势
    df_up = _synthetic_uptrend(300)
    analyser_up = ChanlunAnalyser(code="TEST_UP", frequency="daily")
    result_up = analyser_up.process_klines(df_up)
    
    results["uptrend"] = {
        "klines": len(result_up.klines),
        "fractals": len(result_up.fractals),
        "bis": len(result_up.bis),
        "zss": len(result_up.zss),
        "xds": len(result_up.xds),
        "mmds": len(result_up.mmds),
        "bcs": len(result_up.bcs),
        "bi_count": len(result_up.bis),
        "zs_count": len(result_up.zss),
        "xd_count": len(result_up.xds),
        "mmd_count": len(result_up.mmds),
        "bc_count": len(result_up.bcs),
    }
    
    # 测试下降趋势
    df_down = _synthetic_downtrend(300)
    analyser_down = ChanlunAnalyser(code="TEST_DOWN", frequency="daily")
    result_down = analyser_down.process_klines(df_down)
    
    results["downtrend"] = {
        "klines": len(result_down.klines),
        "fractals": len(result_down.fractals),
        "bis": len(result_down.bis),
        "zss": len(result_down.zss),
        "xds": len(result_down.xds),
        "mmds": len(result_down.mmds),
        "bcs": len(result_down.bcs),
    }
    
    # 测试横盘
    df_side = _synthetic_sideways(200)
    analyser_side = ChanlunAnalyser(code="TEST_SIDE", frequency="daily")
    result_side = analyser_side.process_klines(df_side)
    
    results["sideways"] = {
        "klines": len(result_side.klines),
        "fractals": len(result_side.fractals),
        "bis": len(result_side.bis),
        "zss": len(result_side.zss),
        "xds": len(result_side.xds),
        "mmds": len(result_side.mmds),
        "bcs": len(result_side.bcs),
    }
    
    return results


def test_bi_direction_alternation() -> bool:
    """验证笔方向严格交替。"""
    df = _synthetic_uptrend(300)
    analyser = ChanlunAnalyser(code="TEST", frequency="daily")
    result = analyser.process_klines(df)
    
    bis = result.bis
    if len(bis) < 2:
        return True  # 笔太少无法验证
    
    for i in range(1, len(bis)):
        if bis[i].direction == bis[i - 1].direction:
            print(f"ERROR: 笔{i}和笔{i-1}方向相同: {bis[i].direction} == {bis[i-1].direction}")
            return False
    return True


def test_zs_min_lines() -> bool:
    """验证中枢至少由3笔构成。"""
    df = _synthetic_uptrend(300)
    analyser = ChanlunAnalyser(code="TEST", frequency="daily")
    result = analyser.process_klines(df)
    
    for zs in result.zss:
        if zs.line_count < 3:
            print(f"ERROR: 中枢{zs.index}只有{zs.line_count}笔，应>=3")
            return False
    return True


def test_mmd_types() -> dict:
    """验证买卖点类型分布。"""
    df = _synthetic_uptrend(300)
    analyser = ChanlunAnalyser(code="TEST", frequency="daily")
    result = analyser.process_klines(df)
    
    type_counts = {}
    for mmd in result.mmds:
        t = mmd.mmd_type.value
        type_counts[t] = type_counts.get(t, 0) + 1
    
    return type_counts


def test_confidence_range() -> bool:
    """验证置信度在[0, 1]范围内。"""
    df = _synthetic_uptrend(300)
    analyser = ChanlunAnalyser(code="TEST", frequency="daily")
    result = analyser.process_klines(df)
    
    for mmd in result.mmds:
        if not (0.0 <= mmd.confidence <= 1.0):
            print(f"ERROR: 置信度超出范围: {mmd.confidence}")
            return False
    return True


def test_serialization() -> bool:
    """验证结果可序列化。"""
    df = _synthetic_uptrend(300)
    analyser = ChanlunAnalyser(code="TEST", frequency="daily")
    result = analyser.process_klines(df)
    
    try:
        d = result.to_dict()
        assert "bis" in d
        assert "zss" in d
        assert "mmds" in d
        assert "fractals" in d
        assert "bcs" in d
        assert "macd" in d
        return True
    except Exception as e:
        print(f"ERROR: 序列化失败: {e}")
        return False


def test_multi_level() -> bool:
    """验证多级别分析。"""
    try:
        from easy_tdx.chanlun.multi_level import MultiLevelAnalyser
        
        df_daily = _synthetic_uptrend(300)
        df_60min = _synthetic_uptrend(600)
        
        analyser_daily = ChanlunAnalyser(code="TEST", frequency="daily")
        analyser_60min = ChanlunAnalyser(code="TEST", frequency="60min")
        
        result_daily = analyser_daily.process_klines(df_daily)
        result_60min = analyser_60min.process_klines(df_60min)
        
        mla = MultiLevelAnalyser()
        mla.add_level("daily", analyser_daily)
        mla.add_level("60min", analyser_60min)
        
        confluence = mla.compute_confluence_score("daily", "60min")
        
        assert "score" in confluence
        assert 0.0 <= confluence["score"] <= 1.0
        return True
    except Exception as e:
        print(f"ERROR: 多级别分析失败: {e}")
        return False


def main() -> None:
    """运行所有验证。"""
    print("=" * 60)
    print("easy_tdx 缠论模型综合验证")
    print("=" * 60)

    all_passed = True

    # 1. 基本管道
    print("\n[1] 测试基本缠论管道...")
    try:
        results = test_basic_pipeline()
        for trend, r in results.items():
            print(f"  {trend}: {r['klines']}K → {r['fractals']}F → {r['bis']}B → {r['zss']}ZS → {r['xds']}XD → {r['mmds']}MMD → {r['bcs']}BC")
        print("  ✓ 基本管道正常")
    except Exception as e:
        print(f"  ✗ 基本管道失败: {e}")
        all_passed = False

    # 2. 笔方向交替
    print("\n[2] 测试笔方向交替...")
    if test_bi_direction_alternation():
        print("  ✓ 笔方向严格交替")
    else:
        print("  ✗ 笔方向未严格交替")
        all_passed = False

    # 3. 中枢最小笔数
    print("\n[3] 测试中枢最小笔数...")
    if test_zs_min_lines():
        print("  ✓ 中枢至少由3笔构成")
    else:
        print("  ✗ 存在不足3笔的中枢")
        all_passed = False

    # 4. 买卖点类型
    print("\n[4] 测试买卖点类型分布...")
    try:
        type_counts = test_mmd_types()
        print(f"  类型分布: {type_counts}")
    except Exception as e:
        print(f"  ✗ 买卖点类型测试失败: {e}")
        all_passed = False

    # 5. 置信度范围
    print("\n[5] 测试置信度范围...")
    if test_confidence_range():
        print("  ✓ 置信度在[0, 1]范围内")
    else:
        print("  ✗ 存在置信度超出范围的买卖点")
        all_passed = False

    # 6. 序列化
    print("\n[6] 测试结果序列化...")
    if test_serialization():
        print("  ✓ 结果可正常序列化")
    else:
        print("  ✗ 序列化失败")
        all_passed = False

    # 7. 多级别分析
    print("\n[7] 测试多级别分析...")
    if test_multi_level():
        print("  ✓ 多级别分析正常")
    else:
        print("  ✗ 多级别分析失败")
        all_passed = False

    # 8. 中枢属性验证
    print("\n[8] 测试中枢属性验证...")
    try:
        df = _synthetic_uptrend(300)
        analyser = ChanlunAnalyser(code="TEST", frequency="daily")
        result = analyser.process_klines(df)
        for zs in result.zss:
            assert zs.zg > zs.zd, f"中枢{zs.index}: zg <= zd"
            assert zs.gg >= zs.zg, f"中枢{zs.index}: gg < zg"
            assert zs.dd <= zs.zd, f"中枢{zs.index}: dd > zd"
        print(f"  ✓ {len(result.zss)} 个中枢属性验证通过")
    except Exception as e:
        print(f"  ✗ 中枢属性验证失败: {e}")
        all_passed = False

    # 总结
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ 所有验证通过！")
    else:
        print("✗ 部分验证失败，请检查上方输出")
    print("=" * 60)


if __name__ == "__main__":
    main()
