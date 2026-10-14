"""V723 日期区间取数路由接线测试。

- /bars?start_date= 走 fetch_bars_range（mock 验证参数透传与响应契约）；
- /chanlun/analyze 携带 start_date 时取数分流到 fetch_bars_range，
  且不再只截「最新窗口」（V599 截断在服务端区间取数后仍兼容）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pandas as pd
from fastapi.testclient import TestClient

from easy_tdx.web.app import _create_app


def _bars_df(n: int = 300, start: str = "2024-01-02") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.bdate_range(start, periods=n),
            "open": [1.0] * n,
            "close": [2.0] * n,
            "high": [3.0] * n,
            "low": [0.5] * n,
            "vol": [100.0] * n,
            "amount": [1000.0] * n,
        }
    )


def _client() -> TestClient:
    app = _create_app()
    return TestClient(app)


def test_bars_start_date_routes_to_range() -> None:
    """start_date 给定时 /bars 走 fetch_bars_range，返回全量切片。"""
    df = _bars_df(50, start="2019-03-04")
    fake = AsyncMock(return_value=df)
    with patch("easy_tdx.web.klines.fetch_bars_range", fake):
        client = _client()
        resp = client.get(
            "/api/v1/bars",
            params={
                "market": "SZ",
                "code": "000001",
                "category": "DAY",
                "start_date": "2019-03-04",
                "end_date": "2019-05-10",
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 50
    assert body["total_returned"] == 50
    assert body["data"][0]["date"].startswith("2019-03-04")
    # 参数透传正确
    kwargs = fake.await_args.kwargs
    assert kwargs["start_date"] == "2019-03-04"
    assert kwargs["end_date"] == "2019-05-10"


def test_bars_without_start_date_keeps_legacy_path() -> None:
    """不带 start_date 时维持原语义（单页协议取数，不走区间翻页）。"""
    from easy_tdx.web.deps import get_client

    df = _bars_df(10)
    fake_qfq = AsyncMock(return_value=df)
    fake_tdx = AsyncMock()
    fake_tdx.get_security_bars = AsyncMock(return_value=df)
    app = _create_app()
    app.dependency_overrides[get_client] = lambda: fake_tdx
    with patch("easy_tdx.web.klines.fetch_qfq_klines", fake_qfq):
        client = TestClient(app)
        resp = client.get(
            "/api/v1/bars",
            params={"market": "SZ", "code": "000001", "category": "DAY", "count": 10},
        )
    assert resp.status_code == 200
    assert resp.json()["count"] == 10
    fake_tdx.get_security_bars.assert_awaited_once()


def test_chanlun_analyze_start_date_uses_range_fetch() -> None:
    """analyze 带 start_date：取数分流到 fetch_bars_range（非最新窗口截断）。"""
    df = _bars_df(120, start="2021-06-01")
    fake_range = AsyncMock(return_value=df.copy())
    with (
        patch("easy_tdx.web.routers.chanlun.fetch_bars_range", fake_range),
        patch("easy_tdx.web.routers.chanlun.fetch_qfq_klines", AsyncMock()) as fake_qfq,
    ):
        client = _client()
        resp = client.post(
            "/api/v1/chanlun/analyze",
            json={
                "market": "SZ",
                "code": "000001",
                "category": "DAY",
                "start": 0,
                "count": 800,
                "start_date": "2021-06-01",
                "end_date": "2021-12-31",
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # analyze 契约：K 线数量反映区间切片结果（bars 列表由前端经 /bars 另取）
    assert body["kline_count"] == 120
    assert body["fractal_count"] >= 0
    # 历史区间路径生效：单页协议取数未被调用
    fake_qfq.assert_not_awaited()
    kwargs = fake_range.await_args.kwargs
    assert kwargs["start_date"] == "2021-06-01"
    assert kwargs["end_date"] == "2021-12-31"


def test_chanlun_analyze_without_dates_unchanged() -> None:
    """不带日期时行为不变（仍走 fetch_qfq_klines 单页）。

    ⚠️ 必须先清缓存：`/chanlun/analyze` 无日期范围时会命中
    `audit_data/chanlun_cache.db` 的 SQLite 缓存（chanlun.py:532-536 提前 return），
    导致 `fetch_qfq_klines` 一次都不被调用。该缓存是**落盘共享状态**，
    同一条用例第一次跑通过、第二次跑就失败（2026-10-14 实测复现），
    与 chanlun 模型代码无关。
    """
    import sqlite3

    from easy_tdx.web.chanlun_cache import _DB_PATH

    df = _bars_df(60)
    fake_qfq = AsyncMock(return_value=df.copy())
    with (
        patch("easy_tdx.web.routers.chanlun.fetch_bars_range", AsyncMock()) as fake_range,
        patch("easy_tdx.web.routers.chanlun.fetch_qfq_klines", fake_qfq),
    ):
        client = _client()
        # 清掉本用例的目标缓存条目，强制走真实取数路径
        _conn = sqlite3.connect(str(_DB_PATH))
        try:
            _conn.execute(
                "DELETE FROM chanlun_cache WHERE market=? AND code=? AND category=?",
                ("SZ", "000001", "DAY"),
            )
            _conn.commit()
        finally:
            _conn.close()
        resp = client.post(
            "/api/v1/chanlun/analyze",
            json={"market": "SZ", "code": "000001", "category": "DAY", "count": 60, "cross_timeframe": False},
        )
    assert resp.status_code == 200
    fake_range.assert_not_awaited()
    fake_qfq.assert_awaited_once()
