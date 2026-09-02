#!/usr/bin/env python3
"""easy_tdx 缠论模型完整性验证与测试脚本。

运行方式：
    cd /home/skp/workspace/easy_tdx
    source .venv/bin/activate
    python tests/scripts/test_chanlun_pipeline.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta

import pandas as pd

# 确保源码在 path 中
sys.path.insert(0, "src")

from easy_tdx.chanlun.types import Kline


def _make_kline(
    idx: int,
    date: str,
    o: float,
    c: float,
    h: float,
    lo: float,
) -> Kline:
    return Kline(
        index=idx,
        date=datetime.strptime(date, "%Y-%m-%d"),
        open=o,
        close=c,
        high=h,
        low=lo,
        amount=1000.0,
    )


def test_full_pipeline():
    """测试完整缠论管道。"""
    from easy_tdx.chanlun import ChanlunAnalyser

    # 构造一个有明确趋势的行情：上涨→盘整→下跌→反弹
    klines = [
        _make_kline(0, "2024-01-02", 10.0, 10.5, 11.0, 9.8),
        _make_kline(1, "2024-01-03", 10.5, 11.2, 11.5, 10.3),
        _make_kline(2, "2024-01-04", 11.2, 11.8, 12.0, 11.0),
        _make_kline(3, "2024-01-05", 11.8, 11.5, 12.0, 11.2),
        _make_kline(4, "2024-01-08", 11.5, 12.0, 12.5, 11.3),
        _make_kline(5, "2024-01-09", 12.0, 11.8, 12.2, 11.5),
        _make_kline(6, "2024-01-10", 11.8, 11.5, 11.8, 11.2),
        _make_kline(7, "2024-01-11", 11.5, 11.0, 11.5, 10.8),
        _make_kline(8, "2024-01-12", 11.0, 10.5, 11.0, 10.2),
        _make_kline(9, "2024-01-15", 10.5, 10.0, 10.5, 9.8),
        _make_kline(10, "2024-01-16", 10.0, 9.5, 10.2, 9.3),
        _make_kline(11, "2024-01-17", 9.5, 10.0, 10.2, 9.3),
        _make_kline(12, "2024-01-18", 10.0, 10.5, 10.8, 9.8),
        _make_kline(13, "2024-01-19", 10.5, 10.2, 10.5, 10.0),
        _make_kline(14, "2024-01-22", 10.2, 9.8, 10.3, 9.5),
        _make_kline(15, "2024-01-23", 9.8, 9.5, 10.0, 9.3),
        _make_kline(16, "2024-01-24", 9.5, 10.0, 10.2, 9.3),
        _make_kline(17, "2024-01-25", 10.0, 10.5, 10.8, 9.8),
        _make_kline(18, "2024-01-26", 10.5, 10.2, 10.5, 10.0),
        _make_kline(19, "2024-01-29", 10.2, 9.8, 10.3, 9.5),
    ]

    analyser = ChanlunAnalyser(code="TEST", frequency="DAILY")
    result = analyser.process_klines(
        pd.DataFrame(
            [
                {
                    "datetime": k.date,
                    "open": k.open,
                    "close": k.close,
                    "high": k.high,
                    "low": k.low,
                    "vol": k.amount,
                }
                for k in klines
            ]
        )
    )

    print(f"K线数量: {len(result.klines)}")
    print(f"缠论K线数量: {len(result.cklines)}")
    print(f"分型数量: {len(result.fractals)}")
    print(f"笔数量: {len(result.bis)}")
    print(f"中枢数量: {len(result.zss)}")
    print(f"线段数量: {len(result.xds)}")
    print(f"买卖点数量: {len(result.mmds)}")
    print(f"背驰数量: {len(result.bcs)}")

    # 验证基本结构
    assert len(result.klines) == 20, f"期望20根K线，实际{len(result.klines)}"
    assert len(result.cklines) > 0, "应有缠论K线"
    assert len(result.macd["dif"]) == 20, "MACD序列长度应与K线一致"

    # 验证笔的方向交替
    for i in range(1, len(result.bis)):
        assert result.bis[i].direction != result.bis[i - 1].direction, f"笔{i}和笔{i - 1}方向相同"

    # 验证中枢属性
    for zs in result.zss:
        assert zs.zg > zs.zd, f"中枢{zs.index}: zg({zs.zg}) 应 > zd({zs.zd})"
        assert zs.gg >= zs.zg, f"中枢{zs.index}: gg({zs.gg}) 应 >= zg({zs.zg})"
        assert zs.dd <= zs.zd, f"中枢{zs.index}: dd({zs.dd}) 应 <= zd({zs.zd})"

    # 验证序列化
    d = result.to_dict()
    assert "bis" in d
    assert "zss" in d
    assert "mmds" in d
    assert "macd" in d
    assert "dif" in d["macd"]
    assert "dea" in d["macd"]
    assert "hist" in d["macd"]

    print("✓ 完整管道测试通过")
    return True


def test_fractal_detection():
    """测试分型识别。"""
    from easy_tdx.chanlun.fractal import find_fractals
    from easy_tdx.chanlun.kline_merge import merge_klines
    from easy_tdx.chanlun.types import Kline

    klines = [
        Kline(index=0, date=datetime(2024, 1, 2), open=10, close=12, high=12, low=10, amount=100),
        Kline(index=1, date=datetime(2024, 1, 3), open=12, close=15, high=16, low=12, amount=100),
        Kline(index=2, date=datetime(2024, 1, 4), open=15, close=13, high=15, low=12, amount=100),
        Kline(index=3, date=datetime(2024, 1, 5), open=13, close=10, high=13, low=9, amount=100),
        Kline(index=4, date=datetime(2024, 1, 8), open=10, close=7, high=10, low=7, amount=100),
        Kline(index=5, date=datetime(2024, 1, 9), open=7, close=12, high=13, low=8, amount=100),
    ]

    cklines = merge_klines(klines)
    fxs = find_fractals(cklines)

    print(f"分型数量: {len(fxs)}")
    for fx in fxs:
        print(f"  {fx.fx_type.value}: val={fx.val:.2f}, bar_index={fx.bar_index}")

    # 至少应有1个顶分型和1个底分型
    ding_count = sum(1 for fx in fxs if fx.fx_type.value == "ding")
    di_count = sum(1 for fx in fxs if fx.fx_type.value == "di")
    print(f"  顶分型: {ding_count}, 底分型: {di_count}")

    assert ding_count >= 1, "应至少有1个顶分型"
    assert di_count >= 1, "应至少有1个底分型"
    print("✓ 分型识别测试通过")
    return True


def test_bi_direction_alternation():
    """测试笔方向严格交替。"""
    from easy_tdx.chanlun import ChanlunAnalyser
    from easy_tdx.chanlun.types import Kline

    # 构造明确的锯齿形走势
    klines = []
    base = 100.0
    for i in range(30):
        if i % 2 == 0:
            o, c, h, lo = base, base + 3, base + 4, base - 1
        else:
            o, c, h, lo = base, base - 3, base + 1, base - 4
        klines.append(
            Kline(
                index=i,
                date=datetime(2024, 1, 2) + timedelta(days=i),
                open=o,
                close=c,
                high=h,
                low=lo,
                amount=1000,
            )
        )
        base += 1

    df = pd.DataFrame(
        [
            {
                "datetime": k.date,
                "open": k.open,
                "close": k.close,
                "high": k.high,
                "low": k.low,
                "vol": k.amount,
            }
            for k in klines
        ]
    )

    analyser = ChanlunAnalyser(code="TEST", frequency="DAILY")
    result = analyser.process_klines(df)

    print(f"笔数量: {len(result.bis)}")
    directions = [b.direction.value for b in result.bis]
    print(f"笔方向序列: {directions}")

    for i in range(1, len(result.bis)):
        assert result.bis[i].direction != result.bis[i - 1].direction, (
            f"笔{i}({result.bis[i].direction.value})与笔{i - 1}"
            f"({result.bis[i - 1].direction.value})方向相同"
        )

    print("✓ 笔方向交替测试通过")
    return True


def test_zs_overlap_logic():
    """测试中枢重叠逻辑。"""
    from easy_tdx.chanlun.zs import _is_valid_zs_range, _overlap_ratio

    # 测试重叠率计算
    assert _overlap_ratio(10, 5, 3, 1) == 0.0  # 无重叠
    ratio = _overlap_ratio(10, 5, 7, 3)
    assert 0 < ratio < 1.0, f"部分重叠应为(0,1)，实际{ratio}"
    assert _overlap_ratio(10, 5, 9, 6) == 1.0  # 完全包含

    # 测试中枢区间有效性
    assert _is_valid_zs_range(20, 18, 22, 16) is True
    assert _is_valid_zs_range(18, 20, 22, 16) is False  # zg <= zd
    assert _is_valid_zs_range(100.001, 100.0, 100.002, 99.999) is False  # 过窄

    print("✓ 中枢重叠逻辑测试通过")
    return True


def test_confidence_bounds():
    """测试买卖点置信度范围。"""
    from easy_tdx.chanlun import ChanlunAnalyser
    from easy_tdx.chanlun.types import Kline

    # 构造足够数据
    klines = []
    base = 50.0
    for i in range(100):
        trend = (i % 20) * 0.5
        o = base + trend
        c = base + trend + 1
        h = c + 0.5
        lo = o - 0.5
        klines.append(
            Kline(
                index=i,
                date=datetime(2024, 1, 2) + timedelta(days=i),
                open=o,
                close=c,
                high=h,
                low=lo,
                amount=1000,
            )
        )
        base += 0.3

    df = pd.DataFrame(
        [
            {
                "datetime": k.date,
                "open": k.open,
                "close": k.close,
                "high": k.high,
                "low": k.low,
                "vol": k.amount,
            }
            for k in klines
        ]
    )

    analyser = ChanlunAnalyser(code="TEST", frequency="DAILY")
    result = analyser.process_klines(df)

    print(f"买卖点数量: {len(result.mmds)}")
    for mmd in result.mmds[:5]:
        print(f"  {mmd.mmd_type.value}: conf={mmd.confidence:.2f}, msg={mmd.msg[:50]}")

    # 置信度应在 [0, 1] 范围内
    for mmd in result.mmds:
        assert 0.0 <= mmd.confidence <= 1.0, f"置信度{mmd.confidence}超出[0,1]范围"

    print("✓ 置信度边界测试通过")
    return True


def test_signal_accuracy_computation():
    """测试信号准确度计算。"""
    import numpy as np

    from easy_tdx.backtest.signal_accuracy import compute_signal_accuracy_by_type

    n = 200
    np.random.seed(42)
    base = np.linspace(10, 25, n) + np.random.randn(n) * 0.5
    closes = base.tolist()

    signals = [
        {"type": "1buy", "bar_index": 50},
        {"type": "1buy", "bar_index": 120},
        {"type": "2buy", "bar_index": 70},
        {"type": "2buy", "bar_index": 140},
        {"type": "3buy", "bar_index": 90},
        {"type": "1sell", "bar_index": 60},
        {"type": "1sell", "bar_index": 130},
    ]

    result = compute_signal_accuracy_by_type(closes, signals, horizons=(5,))
    assert "by_type" in result
    assert "ranking" in result
    assert "summary" in result
    assert len(result["ranking"]) > 0

    print(f"信号准确度验证通过，类型数: {len(result['by_type'])}")
    print(f"  排名: {[(r['type'], r['hit_rate']) for r in result['ranking']]}")
    return True


def test_backtest_strategy_registry():
    """测试回测策略注册表。"""
    from easy_tdx.backtest.strategies.registry import get_registry

    registry = get_registry()
    names = registry.names()
    print(f"已注册策略: {names}")

    assert "ma_cross" in names
    assert "chanlun" in names
    assert "changying_chanlun" in names

    # 测试策略实例化
    ma_cross = registry.get("ma_cross")
    assert ma_cross.label == "双均线交叉"

    chanlun = registry.get("chanlun")
    assert chanlun.label == "缠论买卖点"

    print("✓ 策略注册表测试通过")
    return True


def main():
    """运行所有测试。"""
    tests = [
        ("分型识别", test_fractal_detection),
        ("笔方向交替", test_bi_direction_alternation),
        ("中枢重叠逻辑", test_zs_overlap_logic),
        ("完整管道", test_full_pipeline),
        ("置信度边界", test_confidence_bounds),
        ("信号准确度", test_signal_accuracy_computation),
        ("策略注册表", test_backtest_strategy_registry),
    ]

    passed = 0
    failed = 0
    errors = []

    for name, test_fn in tests:
        try:
            result = test_fn()
            if result:
                passed += 1
                print(f"  ✓ {name} 通过\n")
            else:
                failed += 1
                errors.append(f"{name}: 返回False")
                print(f"  ✗ {name} 失败\n")
        except Exception as e:
            failed += 1
            errors.append(f"{name}: {e}")
            print(f"  ✗ {name} 异常: {e}\n")

    print(f"\n{'=' * 50}")
    print(f"测试结果: {passed} 通过, {failed} 失败")
    if errors:
        print("失败详情:")
        for err in errors:
            print(f"  - {err}")
    print(f"{'=' * 50}")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
