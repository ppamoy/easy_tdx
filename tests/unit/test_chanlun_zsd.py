"""走势段/趋势段金标测试（V653）。

锁定 find_zsds / find_qsds 的合并与趋势过滤行为，以及 ChanlunAnalyser
管道中 zsds/qsds 的序列化输出。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from easy_tdx.chanlun import ChanlunAnalyser
from easy_tdx.chanlun.types import FX, XD, CLKline, Direction, FXType
from easy_tdx.chanlun.zsd import _is_trending, find_qsds, find_zsds

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"

# (方向, 起点, 终点, 区间高, 区间低)。相邻线段共享端点，符合真实线段划分。
XD_SEQ = [
    ("up", 100.0, 110.0, 112.0, 98.0),
    ("up", 110.0, 120.0, 122.0, 108.0),
    ("down", 120.0, 105.0, 122.0, 104.0),
    ("down", 105.0, 95.0, 106.0, 94.0),
    ("up", 95.0, 115.0, 116.0, 94.0),
]


def _fx(fx_type: FXType, val: float, bar_index: int) -> FX:
    k = CLKline(
        k_index=bar_index,
        date=datetime(2020, 1, 1) + timedelta(days=bar_index),
        open=0.0,
        close=0.0,
        high=0.0,
        low=0.0,
        amount=0.0,
        index=bar_index,
    )
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
    endpoints = [s[1] for s in XD_SEQ] + [XD_SEQ[-1][2]]
    points = [
        _fx(FXType.DI if i % 2 == 0 else FXType.DING, val, i * 10)
        for i, val in enumerate(endpoints)
    ]
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


def test_find_zsds_golden() -> None:
    """同向线段合并为走势段，方向反转开启新走势段。"""
    zsds = find_zsds(_make_xds())

    assert len(zsds) == 3
    assert [(z.direction.value, z.start.val, z.end.val) for z in zsds] == [
        ("up", 100.0, 120.0),
        ("down", 120.0, 95.0),
        ("up", 95.0, 115.0),
    ]
    # 走势段区间必须覆盖其包含的线段
    assert zsds[0].high == 122.0
    assert zsds[0].low == 98.0


def test_find_qsds_golden() -> None:
    """趋势段 = 终点方向与起点方向一致且创新极值的走势段。"""
    qsds = find_qsds(_make_xds())

    assert len(qsds) == 3
    assert [q.direction.value for q in qsds] == ["up", "down", "up"]


def test_qsds_are_subset_of_zsds() -> None:
    """趋势段必须是某个走势段（端点+方向完全一致），即 QSD ⊆ ZSD。"""
    qsds = find_qsds(_make_xds())
    zsds = find_zsds(_make_xds())

    zsd_keys = {
        (z.direction.value, z.start.val, z.end.val, z.start.bar_index, z.end.bar_index)
        for z in zsds
    }
    for q in qsds:
        key = (q.direction.value, q.start.val, q.end.val, q.start.bar_index, q.end.bar_index)
        assert key in zsd_keys


def test_find_zsds_endpoints_share_pivots() -> None:
    """相邻走势段首尾相连，端点分型共享。"""
    zsds = find_zsds(_make_xds())
    for i in range(len(zsds) - 1):
        assert zsds[i].end.bar_index == zsds[i + 1].start.bar_index
        assert zsds[i].end.val == zsds[i + 1].start.val
        assert zsds[i].direction != zsds[i + 1].direction


def test_is_trending_down_requires_new_low() -> None:
    """向下趋势段必须创新低；终点未创新低时不算趋势。"""
    zsd = XD(
        start=_fx(FXType.DING, 100.0, 0),
        end=_fx(FXType.DI, 110.0, 10),
        direction=Direction.DOWN,
        index=0,
        high=110.0,
        low=100.0,
    )
    assert not _is_trending(zsd, [], 0)

    zsd.end = _fx(FXType.DI, 90.0, 10)
    zsd.low = 90.0
    assert _is_trending(zsd, [], 0)


def test_find_zsds_empty_and_single() -> None:
    """空输入返回空；单线段也返回一个走势段。"""
    assert find_zsds([]) == []
    single = find_zsds(_make_xds()[:1])
    assert len(single) == 1
    assert single[0].start.val == 100.0
    assert single[0].end.val == 110.0


def test_find_qsds_empty_and_single() -> None:
    """趋势段至少需要 2 根线段；空输入/单线段均返回空。"""
    assert find_qsds([]) == []
    assert find_qsds(_make_xds()[:1]) == []


def test_find_zsds_group_covers_middle_extremes() -> None:
    """同向线段组超过 2 根时，走势段区间必须覆盖中间线段的极值。"""
    endpoints = [100.0, 110.0, 120.0, 130.0]
    points = [
        _fx(FXType.DI if i % 2 == 0 else FXType.DING, val, i * 10)
        for i, val in enumerate(endpoints)
    ]
    xds = [
        XD(start=points[0], end=points[1], direction=Direction.UP, index=0, high=115.0, low=95.0),
        XD(start=points[1], end=points[2], direction=Direction.UP, index=1, high=135.0, low=85.0),
        XD(start=points[2], end=points[3], direction=Direction.UP, index=2, high=125.0, low=105.0),
    ]
    zsds = find_zsds(xds)
    assert len(zsds) == 1
    assert zsds[0].high == 135.0
    assert zsds[0].low == 85.0


def test_analyser_serializes_zsds_qsds() -> None:
    """真实行情管道输出 zsds/qsds，且数量与线段数一致（每根线段各成一段）。"""
    rows = json.loads((FIXTURE_DIR / "chanlun_000001_daily.json").read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    result = ChanlunAnalyser(code="000001", frequency="daily").process_klines(df)
    d = result.to_dict()

    assert "zsds" in d and "qsds" in d
    assert d["zsd_count"] == len(result.zsds)
    assert d["qsd_count"] == len(result.qsds)
    assert len(d["zsds"]) == len(result.zsds)
    assert len(d["qsds"]) == len(result.qsds)
    assert d["zsds"][0]["direction"] == result.zsds[0].direction.value
    assert d["qsds"][0]["start_index"] == result.qsds[0].start.bar_index


def test_xd_level_payload_includes_zsds_qsds() -> None:
    """线段级别 payload 也包含递归走势段/趋势段序列化。"""
    from easy_tdx.chanlun.analyser import ChanlunResult
    from easy_tdx.chanlun.recursive import compute_recursive_level

    xds = _make_xds()
    rec = compute_recursive_level(xds)
    result = ChanlunResult(code="000001", frequency="daily")
    result.xds = xds
    result.xds_l1 = rec.xds
    result.zss_l1 = rec.zss
    result.mmds_l1 = rec.mmds
    result.bcs_l1 = rec.bcs
    result.zsds_l1 = rec.zsds
    result.qsds_l1 = rec.qsds

    payload = result._level_payload(
        "线段级别",
        result.xds,
        result.xds_l1,
        result.zss_l1,
        result.mmds_l1,
        result.bcs_l1,
        result.zsds_l1,
        result.qsds_l1,
    )

    assert len(payload["zsds"]) == len(result.zsds_l1)
    assert len(payload["qsds"]) == len(result.qsds_l1)
    assert payload["zsd_count"] == len(result.zsds_l1)
    assert payload["qsd_count"] == len(result.qsds_l1)
    assert payload["zsds"][0]["direction"] == result.zsds_l1[0].direction.value
