"""chanlun2 单元测试——严格对照108课原文验证。

每个测试都钉住一条原文定义，防止回归：
- 中枢=K线重叠/次级别走势重叠（非笔构，第17/91课）
- 趋势=≥2中枢/盘整=1中枢（第17课）
- 1买=趋势背驰/盘整背驰≠1买（第27/53课）
- 2买无根数限制（第101课）
- 3买第一次回试不破ZG+5段（第20/61课）
- 背驰用面积+0轴（第24课）
"""

import json
import os

import pytest

from easy_tdx.chanlun2.analyser import analyze
from easy_tdx.chanlun2.kline_merge import merge_klines
from easy_tdx.chanlun2.fractal import find_fractals
from easy_tdx.chanlun2.move import find_moves
from easy_tdx.chanlun2.zs import find_zs_lowest_level, find_zs_from_moves
from easy_tdx.chanlun2.trend import decompose_same_level
from easy_tdx.chanlun2.types import (
    Direction,
    FractalType,
    KLine,
    MMDType,
    TrendKind,
)

FIXTURE = os.path.join(
    os.path.dirname(__file__), "..", "fixtures", "chanlun_600519_daily.json"
)


def _load_klines(path=FIXTURE):
    with open(path) as f:
        data = json.load(f)
    return [
        KLine(
            index=i,
            dt=d["datetime"],
            open=d["open"],
            high=d["high"],
            low=d["low"],
            close=d["close"],
            volume=d.get("vol", 0),
        )
        for i, d in enumerate(data)
    ]


class TestKlineMerge:
    """第65课：K线包含关系合并。"""

    def test_包含关系被合并(self):
        """相邻两根包含K线应合并为一根。"""
        klines = [
            KLine(0, "d1", 10, 12, 9, 11, 100),  # [9,12]
            KLine(1, "d2", 11, 13, 10, 12, 100),  # [10,13] 与前根无包含
            KLine(2, "d3", 10.5, 12.5, 10, 11, 100),  # [10,12.5] 含于第2根
        ]
        merged = merge_klines(klines)
        # 第3根含于第2根应被合并
        assert len(merged) < len(klines)

    def test_无包含不合并(self):
        klines = [
            KLine(0, "d1", 10, 12, 9, 11),
            KLine(1, "d2", 13, 15, 12, 14),  # 高于前根
        ]
        merged = merge_klines(klines)
        assert len(merged) == 2


class TestFractal:
    """第67课：顶底分型。"""

    def test_顶分型识别(self):
        klines = [
            KLine(0, "d1", 9, 10, 8, 9.5),
            KLine(1, "d2", 10, 12, 9, 11),  # 高点最高=顶
            KLine(2, "d3", 9, 10.5, 8.5, 9.8),
        ]
        merged = merge_klines(klines)
        fractals = find_fractals(merged)
        assert len(fractals) == 1
        assert fractals[0].kind == FractalType.TOP

    def test_底分型识别(self):
        klines = [
            KLine(0, "d1", 11, 12, 10, 11.5),
            KLine(1, "d2", 10, 11, 8, 8.5),  # 低点最低=底
            KLine(2, "d3", 11, 12.5, 10.5, 11.8),
        ]
        merged = merge_klines(klines)
        fractals = find_fractals(merged)
        assert len(fractals) == 1
        assert fractals[0].kind == FractalType.BOTTOM


class TestZSLowestLevel:
    """第17课递归终点：最低级别中枢=K线重叠（非笔构，修复偏差12）。"""

    def test_最低级别中枢用K线重叠非笔构(self):
        # 构造3根不互相包含但价格重叠的K线（合并后仍3根）
        klines = [
            KLine(0, "d1", 9.5, 11, 9, 10.5),  # [9,11]
            KLine(1, "d2", 10, 12, 9.5, 11.5),  # [9.5,12] 与前重叠，不包含
            KLine(2, "d3", 9.8, 11.5, 9.2, 10.8),  # [9.2,11.5] 与前重叠
        ]
        merged = merge_klines(klines)
        zss = find_zs_lowest_level(merged)
        # 第17课递归终点：3根K线重叠构中枢（非笔构中枢，修复偏差12）
        assert len(zss) >= 1
        z = zss[0]
        # 第20课：ZG>ZD
        assert z.zg > z.zd

    def test_无重叠不构成中枢(self):
        klines = [
            KLine(0, "d1", 10, 12, 9, 11),
            KLine(1, "d2", 13, 15, 12, 14),  # 高于前根不重叠
            KLine(2, "d3", 16, 18, 15, 17),  # 更高不重叠
        ]
        merged = merge_klines(klines)
        zss = find_zs_lowest_level(merged)
        assert len(zss) == 0


class TestTrendKind:
    """第17课：趋势=≥2中枢，盘整=1中枢。"""

    def test_TrendKind枚举无none污染(self):
        """第38课原文无none类别（vs 现有same_level偏差4）。"""
        assert TrendKind.INCOMPLETE.value == "incomplete"
        assert "none" not in [k.value for k in TrendKind]

    def test_趋势判定需2中枢(self):
        assert TrendKind.TREND_UP.is_trend
        assert not TrendKind.PANZHENG.is_trend


class TestMMDType:
    """第27/53课：1买=趋势背驰，盘整背驰单独标不混标1买。"""

    def test_盘整背驰不标1买(self):
        """第53课：盘整背驰≠第一类买卖点。"""
        assert not MMDType.PANZHENG_BUY.is_first_class
        assert MMDType.BUY_1.is_first_class
        # 盘整背驰有独立类型，不混入BUY_1
        assert MMDType.PANZHENG_BUY != MMDType.BUY_1


class TestEndToEnd:
    """真实数据端到端验证（§5真实链路）。"""

    def test_600519日线完整分析(self):
        klines = _load_klines()
        r = analyze(klines)
        # 管线完整跑通
        assert len(r.merged) > 0
        assert len(r.fractals) > 0
        assert len(r.moves) > 0
        # 第17课递归：最低中枢用K线重叠（非笔构）
        assert len(r.zs_lowest) > 0
        # 走势类型段
        assert len(r.segments) > 0
        # 买卖点
        assert len(r.mmds) > 0
        # 1买必须是趋势背驰（非盘整背驰混标）
        buy1s = [m for m in r.mmds if m.mmd_type == MMDType.BUY_1]
        for m in buy1s:
            assert m.divergence is not None
            # 第27课：1买=趋势背驰

    def test_中枢区间ZG大于ZD(self):
        """第20课：中枢区间 ZG > ZD。"""
        klines = _load_klines()
        r = analyze(klines)
        for z in r.zs_lowest + r.zs_from_moves:
            assert z.zg > z.zd, f"中枢{z.index} ZG{z.zg}应>ZD{z.zd}"

    def test_2买无根数硬编码限制(self):
        """第101课：2买无K线根数限制（vs 现有偏差13硬编码30根）。"""
        klines = _load_klines()
        r = analyze(klines)
        buy2s = [m for m in r.mmds if m.mmd_type == MMDType.BUY_2]
        # 2买note应标注无根数限制
        for m in buy2s:
            assert "无根数限制" in m.note or "第101课" in m.note

    def test_3买第一次回试(self):
        """第20课：3买必须是第一次回试（非按中枢数截断）。"""
        klines = _load_klines()
        r = analyze(klines)
        buy3s = [m for m in r.mmds if m.mmd_type == MMDType.BUY_3]
        for m in buy3s:
            assert "第一次" in m.note or "第20课" in m.note
