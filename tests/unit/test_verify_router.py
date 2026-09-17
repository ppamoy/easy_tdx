"""web/routers/verify.py 契约测试（V419）。

覆盖：VERIFY_POOL 结构、_bars_to_df 转换、_analyze mmd.zs_index 关联、
list/detail 接口契约（mock 预跑缓存，不触网）。
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from easy_tdx.web.routers.verify import (
    VERIFY_POOL,
    _analyze,
    _bars_to_df,
    _fetch_online_df,
    router,
)


def _df(n: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    close = 100.0 + np.cumsum(rng.normal(0.03, 1.0, n))
    high = close + rng.uniform(0.3, 1.5, n)
    low = close - rng.uniform(0.3, 1.5, n)
    open_ = low + rng.uniform(0, high - low, n)
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": open_,
            "close": close,
            "high": high,
            "low": low,
            "vol": rng.integers(1000, 10000, n).astype(float),
            "amount": rng.integers(1e7, 1e8, n).astype(float),
        }
    )


class TestPool:
    def test_20_stocks(self) -> None:
        assert len(VERIFY_POOL) == 20

    def test_fields(self) -> None:
        for item in VERIFY_POOL:
            assert "code" in item and "name" in item and "market" in item
            assert item["market"] in ("SH", "SZ")

    def test_unique_codes(self) -> None:
        codes = [i["code"] for i in VERIFY_POOL]
        assert len(set(codes)) == 20


class TestBarsToDf:
    def test_convert(self) -> None:
        bars = [
            SimpleNamespace(
                year=2024, month=1, day=2, open=10, high=11, low=9, close=10.5, vol=100, amount=1000
            ),
            SimpleNamespace(
                year=2024,
                month=1,
                day=3,
                open=10.5,
                high=11.5,
                low=10,
                close=11,
                vol=120,
                amount=1200,
            ),
        ]
        df = _bars_to_df(bars)
        assert len(df) == 2
        assert "date" in df.columns
        assert df.iloc[0]["date"] == datetime(2024, 1, 2)


class TestOnlineFallback:
    def test_client_none_returns_none(self) -> None:
        """V427: 客户端不可用时在线回退降级为 None（不抛错）。"""
        import asyncio

        df = asyncio.run(_fetch_online_df(None, None, "SH", "600519"))
        assert df is None


class TestAnalyze:
    def test_mmd_zs_index_field(self) -> None:
        result = _analyze(_df(), "SH", "600000")
        assert "mmds" in result
        assert "zss" in result
        for mmd in result["mmds"]:
            assert "zs_index" in mmd

    def test_frequency_passthrough(self) -> None:
        """周期参数传入分析器后仍能正常序列化（分钟级也不抛错）。"""
        result = _analyze(_df(), "SH", "600000", frequency="30min")
        assert "bars" in result
        assert len(result["bars"]) == len(_df())


class TestRoutes:
    @pytest.fixture()
    def client(self) -> TestClient:
        from fastapi import FastAPI

        a = FastAPI()
        # V427: verify 端点依赖 get_client/get_mac_client_optional，测试注入 None
        a.state.tdx_client = None
        a.state.mac_client = None
        a.include_router(router, prefix="/api/v1")
        return TestClient(a)

    def test_list(self, client: TestClient) -> None:
        r = client.get("/api/v1/verify/signals/list")
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 20
        assert len(d["items"]) == 20
        assert "status" in d["items"][0]

    def test_detail_unknown(self, client: TestClient) -> None:
        r = client.get("/api/v1/verify/signals/detail", params={"code": "999999"})
        assert r.status_code == 200
        assert "error" in r.json()

    def test_detail_non_day_needs_online_client(self, client: TestClient) -> None:
        """非日线周期走现场取数；测试环境无在线客户端时应返回数据不足错误。"""
        r = client.get(
            "/api/v1/verify/signals/detail",
            params={"code": "600519", "category": "MIN_30"},
        )
        assert r.status_code == 200
        assert "error" in r.json()
