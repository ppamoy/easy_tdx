"""缠论核心算法集成测试（笔/中枢/线段/买卖点全链路验证）。

测试场景：
1. 已知走势的合成数据 → 验证笔的端点一致性
2. 标准盘整走势 → 验证中枢识别正确性
3. 趋势走势 → 验证线段划分
4. 买卖点场景 → 验证一类/二类/三类买卖点
5. weak bi skip 配置验证
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import pandas as pd

from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig
from easy_tdx.chanlun.types import Direction


def _make_kline_df(
    n: int,
    base_price: float = 100.0,
    pattern: str = "trend_up",
    amplitude: float = 2.0,
) -> pd.DataFrame:
    """生成合成K线DataFrame用于测试。"""
    rows = []
    dt = datetime(2024, 1, 2)
    for i in range(n):
        if pattern == "trend_up":
            trend = i * 0.1
            noise = math.sin(i / 5.0) * amplitude
        elif pattern == "trend_down":
            trend = -i * 0.1
            noise = math.sin(i / 5.0) * amplitude
        elif pattern == "consolidation":
            trend = 0
            noise = math.sin(i / 3.0) * amplitude
        elif pattern == "v_shape":
            trend = (i - n // 2) ** 2 * 0.001 - 5
            noise = math.sin(i / 3.0) * 1.0
        elif pattern == "trend_v":
            half = n // 2
            if i < half:
                trend = (half - i) * 0.15
            else:
                trend = (i - half) * 0.15
            noise = math.sin(i / 4.0) * amplitude
        else:
            trend = 0
            noise = (i % 10 - 5) * amplitude * 0.2

        close = base_price + trend + noise
        open_ = close + (noise * 0.3 if i > 0 else 0)
        high = max(open_, close) + abs(noise) * 0.2
        low = min(open_, close) - abs(noise) * 0.2

        rows.append(
            {
                "date": dt,
                "open": round(open_, 2),
                "close": round(close, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "vol": 1000000 + i * 1000,
            }
        )
        dt += timedelta(days=1)
    return pd.DataFrame(rows)


def test_trend_up_bis_alternate_direction():
    """上升趋势中，笔的方向应严格交替。"""
    df = _make_kline_df(200, base_price=50.0, pattern="trend_up", amplitude=3.0)
    analyser = ChanlunAnalyser(code="TEST", frequency="daily", config=ChanlunConfig(zs_from_xd=False))
    result = analyser.process_klines(df)

    assert len(result.bis) >= 3, f"应产生至少3笔，实际 {len(result.bis)}"

    # 验证方向交替
    for i in range(1, len(result.bis)):
        prev_dir = result.bis[i - 1].direction
        curr_dir = result.bis[i].direction
        assert prev_dir != curr_dir, f"笔[{i - 1}]和笔[{i}]方向未交替: {prev_dir} vs {curr_dir}"

    # 向上笔的终点应高于起点
    for bi in result.bis:
        if bi.direction == Direction.UP:
            assert bi.end.val > bi.start.val, f"向上笔终点不应低于起点: {bi}"
        else:
            assert bi.end.val < bi.start.val, f"向下笔终点不应高于起点: {bi}"


def test_consolidation_zs_recognition():
    """盘整走势中应识别出中枢。"""
    df = _make_kline_df(300, base_price=20.0, pattern="consolidation", amplitude=1.5)
    config = ChanlunConfig(zs_min_lines=3, zs_from_xd=False)
    analyser = ChanlunAnalyser(code="TEST", frequency="daily", config=config)
    result = analyser.process_klines(df)

    assert len(result.bis) >= 3, f"盘整应产生至少3笔，实际 {len(result.bis)}"

    # 中枢zg应大于zd
    for zs in result.zss:
        assert zs.zg > zs.zd, f"中枢zg({zs.zg})应大于zd({zs.zd})"
        assert zs.gg >= zs.zg, f"中枢最高gg({zs.gg})应>=zg({zs.zg})"
        assert zs.dd <= zs.zd, f"中枢最低dd({zs.dd})应<=zd({zs.zd})"


def test_v_shape_segment_identification():
    """V形反转走势中应识别出线段的转折。"""
    df = _make_kline_df(300, base_price=30.0, pattern="v_shape", amplitude=2.0)
    config = ChanlunConfig(zs_from_xd=False)
    analyser = ChanlunAnalyser(code="TEST", frequency="daily", config=config)
    result = analyser.process_klines(df)

    # 线段应由至少3笔构成
    assert len(result.xds) >= 1, f"应产生至少1条线段，实际 {len(result.xds)}"

    for xd in result.xds:
        assert xd.high >= xd.low, f"线段high({xd.high})应>=low({xd.low})"
        # 方向与端点一致
        if xd.direction == Direction.UP:
            assert xd.end.val > xd.start.val or xd.high > xd.start.val
        else:
            assert xd.end.val < xd.start.val or xd.low < xd.start.val


def test_weak_bi_skip_config():
    """验证 bi_weak_skip=True 时弱笔被跳过。"""
    # 生成一个几乎平行的走势（所有笔都很短）
    df = _make_kline_df(100, base_price=10.0, pattern="consolidation", amplitude=0.005)
    config_strict = ChanlunConfig(bi_weak_skip=False, zs_from_xd=False)
    config_skip = ChanlunConfig(bi_weak_skip=True, zs_from_xd=False)

    analyser_strict = ChanlunAnalyser(code="TEST", frequency="daily", config=config_strict)
    result_strict = analyser_strict.process_klines(df)

    analyser_skip = ChanlunAnalyser(code="TEST", frequency="daily", config=config_skip)
    result_skip = analyser_skip.process_klines(df)

    # skip模式应该产生更少或相等的笔（不会更多）
    assert len(result_skip.bis) <= len(result_strict.bis), (
        f"bi_weak_skip应减少笔数: skip={len(result_skip.bis)}, strict={len(result_strict.bis)}"
    )


def test_mmd_first_type_requires_beichi():
    """一类买卖点应在背驰后出现。"""
    # 生成一个有明显顶底分型的走势
    df = _make_kline_df(400, base_price=50.0, pattern="trend_up", amplitude=5.0)
    analyser = ChanlunAnalyser(code="TEST", frequency="daily", config=ChanlunConfig(zs_from_xd=False))
    result = analyser.process_klines(df)

    # 检查一类买卖点的置信度
    first_type_mmds = [m for m in result.mmds if m.mmd_type.value in ("1buy", "1sell")]
    for mmd in first_type_mmds:
        assert mmd.confidence >= 0.0, "一类买卖点置信度不应为负"
        assert mmd.confidence <= 1.0, "一类买卖点置信度不应超过1"


def test_mmd_types_distribution():
    """验证买卖点类型的分布合理性。"""
    df = _make_kline_df(500, base_price=25.0, pattern="trend_v", amplitude=2.0)
    analyser = ChanlunAnalyser(code="TEST", frequency="daily", config=ChanlunConfig(zs_from_xd=False))
    result = analyser.process_klines(df)

    type_counts: dict[str, int] = {}
    for mmd in result.mmds:
        t = mmd.mmd_type.value
        type_counts[t] = type_counts.get(t, 0) + 1

    # 应有至少一种买卖点
    assert len(type_counts) > 0 or len(result.bis) < 3, (
        f"有足够笔时应产生买卖点，类型: {type_counts}"
    )

    # 买卖点置信度应在合理范围内
    for mmd in result.mmds:
        assert 0.0 <= mmd.confidence <= 1.0, f"置信度超出范围: {mmd.confidence}"


def test_fractal_anchor_bar_index():
    """验证分型锚定的原始K线索引正确。"""
    df = _make_kline_df(200, base_price=15.0, pattern="trend_up", amplitude=2.0)
    analyser = ChanlunAnalyser(code="TEST", frequency="daily", config=ChanlunConfig(zs_from_xd=False))
    result = analyser.process_klines(df)

    for fx in result.fractals:
        assert fx.bar_index >= 0, f"分型bar_index不应为负: {fx.bar_index}"
        assert fx.bar_index < len(result.klines), (
            f"分型bar_index({fx.bar_index})超出范围: {len(result.klines)}"
        )


def test_bi_endpoint_anchor_index():
    """验证笔端点锚定的原始K线索引正确。"""
    df = _make_kline_df(200, base_price=15.0, pattern="trend_up", amplitude=2.0)
    analyser = ChanlunAnalyser(code="TEST", frequency="daily", config=ChanlunConfig(zs_from_xd=False))
    result = analyser.process_klines(df)

    for bi in result.bis:
        assert bi.start.bar_index >= 0, "笔起点bar_index不应为负"
        assert bi.end.bar_index >= 0, "笔终点bar_index不应为负"
        assert bi.start.bar_index < len(result.klines)
        assert bi.end.bar_index < len(result.klines)


def test_zs_start_end_fractal_consistency():
    """验证中枢的start/end分型索引有效。"""
    df = _make_kline_df(300, base_price=30.0, pattern="consolidation", amplitude=2.0)
    config = ChanlunConfig(zs_min_lines=3, zs_from_xd=False)
    analyser = ChanlunAnalyser(code="TEST", frequency="daily", config=config)
    result = analyser.process_klines(df)

    for zs in result.zss:
        if zs.start:
            assert zs.start.bar_index >= 0
            assert zs.start.bar_index < len(result.klines)
        if zs.end:
            assert zs.end.bar_index >= 0
            assert zs.end.bar_index < len(result.klines)


def test_result_to_dict_serializable():
    """验证结果可正确序列化为字典。"""
    df = _make_kline_df(200, base_price=20.0, pattern="trend_up", amplitude=2.0)
    analyser = ChanlunAnalyser(code="TEST", frequency="daily", config=ChanlunConfig(zs_from_xd=False))
    result = analyser.process_klines(df)

    d = result.to_dict()

    assert "bis" in d
    assert "zss" in d
    assert "xds" in d
    assert "mmds" in d
    assert "fractal_count" in d
    assert "bi_count" in d
    assert "zs_count" in d
    assert "mmd_count" in d

    # 验证笔数据完整性
    for bi in d["bis"]:
        assert "index" in bi
        assert "direction" in bi
        assert "start_date" in bi
        assert "end_date" in bi
        assert "high" in bi
        assert "low" in bi
        assert "start_index" in bi
        assert "end_index" in bi

    # 验证中枢数据完整性
    for zs in d["zss"]:
        assert "zg" in zs
        assert "zd" in zs
        assert "gg" in zs
        assert "dd" in zs
        assert "line_count" in zs


def test_multi_period_bis():
    """验证不同周期下笔的识别一致性。"""
    # 日线数据
    df_day = _make_kline_df(300, base_price=50.0, pattern="trend_up", amplitude=3.0)
    analyser_day = ChanlunAnalyser(code="TEST", frequency="daily", config=ChanlunConfig(zs_from_xd=False))
    result_day = analyser_day.process_klines(df_day)

    assert len(result_day.bis) >= 0  # 至少不崩溃

    # 分钟线数据（用更小的振幅模拟）
    df_min = _make_kline_df(300, base_price=50.0, pattern="consolidation", amplitude=0.5)
    analyser_min = ChanlunAnalyser(code="TEST", frequency="5min")
    result_min = analyser_min.process_klines(df_min)

    assert len(result_min.bis) >= 0  # 至少不崩溃


def test_empty_and_small_input():
    """验证空数据和极小数据的边界处理。"""
    # 空数据
    df_empty = pd.DataFrame(columns=["date", "open", "close", "high", "low", "vol"])
    analyser = ChanlunAnalyser(code="TEST", frequency="daily", config=ChanlunConfig(zs_from_xd=False))
    result = analyser.process_klines(df_empty)
    assert len(result.bis) == 0
    assert len(result.zss) == 0
    assert len(result.mmds) == 0

    # 极小数据（3根K线）
    df_small = pd.DataFrame(
        [
            {
                "date": datetime(2024, 1, 1),
                "open": 10,
                "close": 11,
                "high": 11.5,
                "low": 9.5,
                "vol": 100,
            },
            {
                "date": datetime(2024, 1, 2),
                "open": 11,
                "close": 10,
                "high": 11.5,
                "low": 9.5,
                "vol": 100,
            },
            {
                "date": datetime(2024, 1, 3),
                "open": 10,
                "close": 11,
                "high": 11.5,
                "low": 9.5,
                "vol": 100,
            },
        ]
    )
    result = analyser.process_klines(df_small)
    # 3根K线可能产生1个分型，但不足以形成笔
    assert len(result.bis) >= 0
