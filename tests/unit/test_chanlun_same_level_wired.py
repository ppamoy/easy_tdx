"""V853 沉淀测试：第38课同级别分解接线（AGENTS.md §7）。

背景：`same_level.decompose_same_level` 此前为 dead module（0 调用方，规则就绪但
analyser/router 从不调用它——见 docs/CHANLUN_FIDELITY_AUDIT_V852.md §2.4）。
V853 在 `process_klines` 末尾接入并经 `to_dict()` 暴露。

本测试锁接线存在：若有人删掉 `ChanlunResult.same_level_segments` 填充或
`to_dict()` 的序列化，本测试即失败——堵死「实现未接入」这类沉默回归。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pandas as pd

from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig


def _synth_df(n: int = 120) -> pd.DataFrame:
    """合成一段有上下震荡的日线，保证能切出笔/中枢。"""
    import math
    rows = []
    base = 10.0
    for i in range(n):
        # 两中枢的下跌 + 反弹形态
        v = base + 6 * math.sin(i / 9.0) - 0.04 * i
        o = v + 0.2
        c = v - 0.2
        rows.append({
            "datetime": datetime(2024, 1, 1) + timedelta(days=i),
            "open": o, "close": c,
            "high": max(o, c) + 0.3, "low": min(o, c) - 0.3,
            "vol": 100000,
        })
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df.rename(columns={"datetime": "date"})


def test_same_level_segments_wired_in_result():
    """第38课同级别分解必须在 process_klines 结果里产出（非空）。"""
    r = ChanlunAnalyser(code="TEST", frequency="daily",
                        config=ChanlunConfig(zs_from_xd=False)).process_klines(_synth_df())
    assert hasattr(r, "same_level_segments"), "ChanlunResult 缺 same_level_segments 字段（接线被删?）"
    assert len(r.same_level_segments) > 0, (
        f"same_level_segments 为空——第38课分解未接入或 bis 不足。"
        f"bis={len(r.bis)} segments={r.same_level_segments}"
    )
    # 第38课：每段是走势类型，盘整(1中枢)或趋势(≥2中枢)或未完成
    seg0 = r.same_level_segments[0]
    assert hasattr(seg0, "lines"), "TrendSegment 缺 lines"
    assert hasattr(seg0, "is_panzheng"), "TrendSegment 缺 is_panzheng"


def test_same_level_segments_serialized_in_to_dict():
    """to_dict() 必须把 same_level_segments 序列化进 API 响应。"""
    r = ChanlunAnalyser(code="TEST", frequency="daily",
                        config=ChanlunConfig(zs_from_xd=False)).process_klines(_synth_df())
    d = r.to_dict()
    assert "same_level_segments" in d, "to_dict() 未含 same_level_segments（序列化被删?）"
    sl = d["same_level_segments"]
    assert isinstance(sl, list) and len(sl) > 0
    # 必须可 JSON 序列化（前端消费）
    js = json.dumps(sl, default=str)
    assert len(js) > 0
    # 每段含第38课关键字段
    s0 = sl[0]
    for k in ("kind", "n_segments", "is_panzheng", "is_trend",
              "has_zs", "lines", "zss"):
        assert k in s0, f"段序列化缺字段 {k}（前端会渲染失败）"
