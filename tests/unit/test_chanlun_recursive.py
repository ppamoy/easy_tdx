"""缠论多级别递归金标测试（V651）。

锁定「以低级别线段作为高级别笔」的递归输出：
- 手工人造线段序列 → 高级别线段/线段中枢/背驰计数与几何不变量；
- 真实行情 fixture → to_dict 输出 bi/xd 两层结构且不破坏单级别序列化。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from easy_tdx.chanlun import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.recursive import RecursiveLevelResult, compute_recursive_level
from easy_tdx.chanlun.types import FX, XD, CLKline, Direction, FXType

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"

# 手工人造线段：方向交替、高低点逐步抬升/回落，使特征序列在高级别上
# 先形成向上线段顶分型、再形成向下线段底分型，保证递归输出确定。
XD_SEQ = [
    ("up", 100.0, 110.0, 112.0, 98.0),
    ("down", 110.0, 102.0, 112.0, 98.0),
    ("up", 102.0, 112.0, 114.0, 100.0),
    ("down", 112.0, 108.0, 120.0, 104.0),
    ("up", 108.0, 122.0, 124.0, 106.0),
    ("down", 122.0, 98.0, 108.0, 96.0),
    ("up", 98.0, 118.0, 120.0, 96.0),
    ("down", 118.0, 104.0, 120.0, 102.0),
    ("up", 104.0, 116.0, 118.0, 102.0),
    ("down", 116.0, 100.0, 118.0, 98.0),
]


def _k(bar_index: int) -> CLKline:
    return CLKline(
        k_index=bar_index,
        date=datetime(2020, 1, 1) + timedelta(days=bar_index),
        open=0.0,
        close=0.0,
        high=0.0,
        low=0.0,
        amount=0.0,
        index=bar_index,
    )


def _fx(fx_type: FXType, val: float, bar_index: int) -> FX:
    k = _k(bar_index)
    return FX(
        fx_type=fx_type,
        k=k,
        klines=[k],
        val=val,
        index=bar_index,
        done=True,
        bar_index=bar_index,
    )


def _make_xds() -> list[XD]:
    """构造端点共享的低级别线段序列，与真实线段划分首尾相连一致。"""
    endpoints = [seq[1] for seq in XD_SEQ] + [XD_SEQ[-1][2]]
    points: list[FX] = []
    for i, val in enumerate(endpoints):
        fx_type = FXType.DI if i % 2 == 0 else FXType.DING
        points.append(_fx(fx_type, val, i * 10))

    xds: list[XD] = []
    for i, (direction, start_val, end_val, high, low) in enumerate(XD_SEQ):
        d = Direction.UP if direction == "up" else Direction.DOWN
        xds.append(
            XD(
                start=points[i],
                end=points[i + 1],
                direction=d,
                index=i,
                high=high,
                low=low,
            )
        )
    return xds


def test_recursive_level_golden_counts() -> None:
    """人造线段序列的递归高级别输出必须与金标完全一致。"""
    result = compute_recursive_level(_make_xds(), config=ChanlunConfig(xd_bi_pohuai=False))

    assert isinstance(result, RecursiveLevelResult)
    # 高级别线段：先向上 100→112，再向下 112→98
    assert len(result.xds) == 2
    assert result.xds[0].direction == Direction.UP
    assert result.xds[0].start.val == 100.0
    assert result.xds[0].end.val == 112.0
    assert result.xds[1].direction == Direction.DOWN
    assert result.xds[1].end.val == 98.0

    # 高级别线段中枢：全部 10 根低级别线段重叠，ZG=112/ZD=100
    assert len(result.zss) == 1
    assert result.zss[0].zg == 112.0
    assert result.zss[0].zd == 100.0
    assert result.zss[0].line_count == 10

    # 高级别背驰：向下线段力度衰竭
    assert len(result.bcs) == 1
    assert result.bcs[0].bc is True

    # 该人造序列不触发三类买卖点，但结果必须是可序列化的列表
    assert result.mmds == []


def test_recursive_level_geometry_invariants() -> None:
    """递归线段端点首尾相连、方向交替；中枢区间满足 ZG>ZD。"""
    result = compute_recursive_level(_make_xds(), config=ChanlunConfig(xd_bi_pohuai=False))

    for xd in result.xds:
        if xd.direction == Direction.UP:
            assert xd.end.val > xd.start.val
        else:
            assert xd.end.val < xd.start.val
        assert xd.low <= xd.start.val <= xd.high
        assert xd.low <= xd.end.val <= xd.high

    for i in range(len(result.xds) - 1):
        assert result.xds[i].end.bar_index == result.xds[i + 1].start.bar_index
        assert result.xds[i].end.val == result.xds[i + 1].start.val
        assert result.xds[i].direction != result.xds[i + 1].direction

    for zs in result.zss:
        assert zs.zg > zs.zd
        assert zs.gg >= zs.zg
        assert zs.dd <= zs.zd


def test_recursive_level_insufficient_lines_returns_empty() -> None:
    """少于 3 根低级别线段时返回空结果，不抛异常。"""
    result = compute_recursive_level([], config=ChanlunConfig(xd_bi_pohuai=False))
    assert result.xds == [] and result.zss == [] and result.mmds == [] and result.bcs == []
    assert result.zsds == [] and result.qsds == []

    result = compute_recursive_level(_make_xds()[:2], config=ChanlunConfig(xd_bi_pohuai=False))
    assert result.xds == [] and result.zss == [] and result.mmds == [] and result.bcs == []
    assert result.zsds == [] and result.qsds == []


def test_to_dict_outputs_two_levels() -> None:
    """to_dict 输出 bi/xd 两层结构，且与单级别顶层数组一致。"""
    rows = json.loads((FIXTURE_DIR / "chanlun_000001_daily.json").read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    result = ChanlunAnalyser(
        code="000001", frequency="daily", config=ChanlunConfig(xd_bi_pohuai=False)
    ).process_klines(df)
    d = result.to_dict()

    assert set(d["levels"].keys()) == {"bi", "xd"}

    bi_level = d["levels"]["bi"]
    assert bi_level["name"] == "笔级别"
    assert bi_level["bi_count"] == d["bi_count"]
    assert bi_level["xd_count"] == d["xd_count"]
    assert bi_level["zs_count"] == d["zs_count"]
    assert bi_level["mmd_count"] == d["mmd_count"]
    assert bi_level["bc_count"] == d["bc_count"]
    assert bi_level["zsd_count"] == d["zsd_count"]
    assert bi_level["qsd_count"] == d["qsd_count"]
    assert len(bi_level["bis"]) == d["bi_count"]
    assert len(bi_level["xds"]) == d["xd_count"]

    xd_level = d["levels"]["xd"]
    assert xd_level["name"] == "线段级别"
    # 高级别「笔」= 本级别线段；fixture 只有 2 根线段，不足以递归出更高级别线段
    assert xd_level["bi_count"] == d["xd_count"]
    assert xd_level["xd_count"] == 0
    assert xd_level["zsd_count"] == 0
    assert xd_level["qsd_count"] == 0
    assert xd_level["zss"] == []
    assert xd_level["mmds"] == []
    assert xd_level["bcs"] == []


def test_recursive_module_exported_from_package() -> None:
    """递归 API 通过 chanlun 包对外导出。"""
    from easy_tdx.chanlun import RecursiveLevelResult as ExportedResult
    from easy_tdx.chanlun import compute_recursive_level as exported_compute

    assert ExportedResult is RecursiveLevelResult
    assert exported_compute is compute_recursive_level
