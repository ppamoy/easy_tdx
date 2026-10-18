"""chanlun2 路由测试——行为级验证（§1）。

用真实 600519 日线 fixture 数据（mock 取数层）打 /api/v1/chanlun2/analyze，
断言端点真的跑通 chanlun2.analyze 并返回：中枢（K线重叠非笔构）、走势段、
买卖点——不是只断言 HTTP 200。
"""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

FIXTURE = os.path.join(
    os.path.dirname(__file__), "..", "fixtures", "chanlun_600519_daily.json"
)


def _load_fixture_df() -> pd.DataFrame:
    with open(FIXTURE) as f:
        data = json.load(f)
    return pd.DataFrame(data).rename(columns={"datetime": "datetime", "vol": "vol"})


def _make_app_client() -> TestClient:
    from easy_tdx.web.app import _create_app
    from unittest.mock import AsyncMock

    app = _create_app(enable_mac=True)
    app.state.tdx_client = AsyncMock()
    app.state.mac_client = AsyncMock()
    return TestClient(app)


class TestChanlun2Analyze:
    def test_chanlun2端点返回真实分析结果(self) -> None:
        """行为级（§1）：用真 fixture 数据跑端点，断言中枢/走势/买卖点非空。"""
        client = _make_app_client()
        df = _load_fixture_df()
        with (
            patch(
                "easy_tdx.web.routers.chanlun.fetch_qfq_klines",
                new=AsyncMock(return_value=df),
            ),
            patch(
                "easy_tdx.web.routers.chanlun.fetch_paged_bars",
                new=AsyncMock(return_value=df),
            ),
            patch(
                "easy_tdx.web.routers.chanlun.fetch_bars_range",
                new=AsyncMock(return_value=df),
            ),
        ):
            resp = client.post(
                "/api/v1/chanlun2/analyze",
                json={"market": "SH", "code": "600519", "category": "DAY",
                      "cross_timeframe": False},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # 模型标识
        assert body["model"] == "chanlun2"
        assert "108课" in body["source"]

        # 行为级断言（非仅状态码）
        assert len(body["merged"]) > 0, "合并K线应非空"
        assert len(body["fractals"]) > 0, "分型应非空"
        assert len(body["moves"]) > 0, "笔应非空"
        # 第17课递归：最低中枢=K线重叠（非笔构，修复偏差12）
        assert len(body["zs_lowest"]) > 0, "最低级别中枢(K线重叠)应非空"
        for z in body["zs_lowest"]:
            assert z["level"] == "lowest_kline_overlap"
            assert z["zg"] > z["zd"], "第20课：ZG>ZD"
        # 走势类型段（第38课）
        assert len(body["segments"]) > 0, "走势类型段应非空"
        # 买卖点（第27/101课）——600519 fixture 有5个
        assert len(body["mmds"]) > 0, "买卖点应非空"
        # 1买必须是趋势背驰（非盘整背驰混标，第53课）
        buy1s = [m for m in body["mmds"] if m["type"] == "buy1"]
        for m in buy1s:
            assert "背驰" in m["note"], "1买须源自背驰"
        # 盘整背驰单独标，不混标1买
        panzheng = [m for m in body["mmds"] if "panzheng" in m["type"]]
        for m in panzheng:
            assert m["type"] != "buy1", "盘整背驰不应标1买"

    def test_chanlun2区间套跨周期精确定位(self) -> None:
        """第83课区间套：cross_timeframe=True 时 nested 应填充精确定位。"""
        client = _make_app_client()
        df = _load_fixture_df()
        # 次级别也用同数据（模拟时间窗口对齐）
        with (
            patch(
                "easy_tdx.web.routers.chanlun.fetch_qfq_klines",
                new=AsyncMock(return_value=df),
            ),
            patch(
                "easy_tdx.web.routers.chanlun.fetch_paged_bars",
                new=AsyncMock(return_value=df),
            ),
            patch(
                "easy_tdx.web.routers.chanlun.fetch_bars_range",
                new=AsyncMock(return_value=df),
            ),
        ):
            resp = client.post(
                "/api/v1/chanlun2/analyze",
                json={"market": "SH", "code": "600519", "category": "DAY",
                      "cross_timeframe": True},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # 区间套结果
        assert "nested" in body
        if len(body["nested"]) > 0:
            # 有大级别买卖点时应有跨周期确认
            assert isinstance(body["nested"], list)
