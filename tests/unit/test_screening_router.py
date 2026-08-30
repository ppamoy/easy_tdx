"""长赢动态选股 API 路由测试（离线，无网络）。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pandas as pd
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

# ── 测试夹具 ───────────────────────────────────────────────────────────────────


def _make_sample_df(n: int = 300) -> pd.DataFrame:
    """生成带趋势的合成 OHLCV DataFrame。"""
    import numpy as np

    np.random.seed(42)
    close = 10 + np.cumsum(np.random.randn(n) * 0.2 + 0.05)
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {
            "datetime": dates,
            "open": (close - np.random.randn(n) * 0.1).tolist(),
            "high": (close + np.random.randn(n) * 0.1).tolist(),
            "low": (close - np.random.randn(n) * 0.1).tolist(),
            "close": close.tolist(),
            "vol": (np.random.randint(1000, 10000, n)).tolist(),
            "amount": (close * 5000).tolist(),
        }
    )


@pytest.fixture()
def mock_client() -> AsyncMock:
    """模拟 TdxClient（异步）。"""
    client = AsyncMock()
    client.get_security_bars = AsyncMock(return_value=_make_sample_df())
    return client


@pytest.fixture()
def app_client(mock_client):
    """FastAPI TestClient，注入 mock client。"""
    from fastapi.testclient import TestClient

    from easy_tdx.web.app import _create_app

    app = _create_app()
    # 把 mock client 注入到 app.state（deps.get_client 从这里读取）
    app.state.tdx_client = mock_client
    app.state.mac_client = mock_client
    return TestClient(app)


# ── 扫描接口测试 ────────────────────────────────────────────────────────────────


def test_scan_missing_date(app_client: TestClient):
    """不提供日期应返回错误。"""
    resp = app_client.post("/api/v1/screening/scan", json={"market": "SZ"})
    assert resp.status_code == 200
    body = resp.json()
    assert "error" in body


def test_scan_invalid_date(app_client: TestClient):
    """无效日期格式应返回错误。"""
    resp = app_client.post("/api/v1/screening/scan", json={"date": "not-a-date", "market": "SZ"})
    assert resp.status_code == 200
    body = resp.json()
    assert "error" in body


def test_scan_success(app_client: TestClient, mock_client: AsyncMock):
    """正常扫描应返回合格股票列表。"""
    mock_client.get_security_bars = AsyncMock(return_value=_make_sample_df(500))
    resp = app_client.post(
        "/api/v1/screening/scan",
        json={
            "date": "2023-12-01",
            "market": "SZ",
            "min_klines": 100,
            "stock_type": "all",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "qualified" in body
    assert "total_scanned" in body
    assert body["total_scanned"] <= 30  # 限制最多30只


def test_scan_sz_market(app_client: TestClient, mock_client: AsyncMock):
    """深圳市场扫描应返回深圳股票。"""
    mock_client.get_security_bars = AsyncMock(return_value=_make_sample_df(500))
    resp = app_client.post(
        "/api/v1/screening/scan",
        json={"date": "2023-12-01", "market": "SZ", "stock_type": "all"},
    )
    assert resp.status_code == 200
    body = resp.json()
    qualified = body.get("qualified", [])
    for stock in qualified:
        assert stock.get("market") == "SZ"


def test_scan_sh_market(app_client: TestClient, mock_client: AsyncMock):
    """上海市场扫描应返回上海股票。"""
    mock_client.get_security_bars = AsyncMock(return_value=_make_sample_df(500))
    resp = app_client.post(
        "/api/v1/screening/scan",
        json={"date": "2023-12-01", "market": "SH", "stock_type": "all"},
    )
    assert resp.status_code == 200
    body = resp.json()
    qualified = body.get("qualified", [])
    for stock in qualified:
        assert stock.get("market") == "SH"


# ── 评估接口测试 ────────────────────────────────────────────────────────────────


def test_evaluate_missing_params(app_client: TestClient):
    """不提供 code 或 date 应返回错误。"""
    resp = app_client.post("/api/v1/screening/evaluate", json={"market": "SZ"})
    assert resp.status_code == 200
    body = resp.json()
    assert "error" in body


def test_evaluate_invalid_date(app_client: TestClient):
    """无效日期应返回错误。"""
    resp = app_client.post(
        "/api/v1/screening/evaluate",
        json={"market": "SZ", "code": "000001", "date": "bad"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "error" in body


def test_evaluate_success(app_client: TestClient, mock_client: AsyncMock):
    """正常评估应返回质量分数和分类。"""
    mock_client.get_security_bars = AsyncMock(return_value=_make_sample_df(500))
    resp = app_client.post(
        "/api/v1/screening/evaluate",
        json={"market": "SZ", "code": "000001", "date": "2023-12-01"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "score" in body
    assert "classification" in body
    assert "chanlun" in body
    assert 0 <= body["score"] <= 100


def test_evaluate_insufficient_data(app_client: TestClient, mock_client: AsyncMock):
    """数据不足时应返回错误。"""
    mock_client.get_security_bars = AsyncMock(return_value=None)
    resp = app_client.post(
        "/api/v1/screening/evaluate",
        json={"market": "SZ", "code": "000001", "date": "2023-12-01"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "error" in body


# ── 筛选逻辑测试 ────────────────────────────────────────────────────────────────


def test_stock_type_filter_tree(app_client: TestClient, mock_client: AsyncMock):
    """tree 类型筛选应只返回树型企业。"""
    mock_client.get_security_bars = AsyncMock(return_value=_make_sample_df(600))
    resp = app_client.post(
        "/api/v1/screening/scan",
        json={"date": "2023-12-01", "market": "SZ", "stock_type": "tree"},
    )
    assert resp.status_code == 200
    body = resp.json()
    qualified = body.get("qualified", [])
    # 由于 mock 数据固定，可能没有 tree 类型，但不应报错
    for stock in qualified:
        assert stock.get("classification") == "tree"


def test_quality_score_range(app_client: TestClient, mock_client: AsyncMock):
    """质量分数应在 0-100 范围内。"""
    mock_client.get_security_bars = AsyncMock(return_value=_make_sample_df(500))
    resp = app_client.post(
        "/api/v1/screening/evaluate",
        json={"market": "SZ", "code": "000001", "date": "2023-12-01"},
    )
    body = resp.json()
    assert 0 <= body["score"] <= 100


def test_classification_values(app_client: TestClient, mock_client: AsyncMock):
    """分类应为 tree/grain/vegetable 之一。"""
    mock_client.get_security_bars = AsyncMock(return_value=_make_sample_df(500))
    resp = app_client.post(
        "/api/v1/screening/evaluate",
        json={"market": "SZ", "code": "000001", "date": "2023-12-01"},
    )
    body = resp.json()
    assert body["classification"] in ("tree", "grain", "vegetable")


# ── 边界条件测试 ────────────────────────────────────────────────────────────────


def test_scan_empty_market(app_client: TestClient):
    """不支持的市场应返回空列表。"""
    resp = app_client.post(
        "/api/v1/screening/scan",
        json={"date": "2023-12-01", "market": "UNSUPPORTED"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("qualified", []) == []
    assert body.get("total_scanned", 0) == 0


def test_scan_max_stocks_limit(app_client: TestClient, mock_client: AsyncMock):
    """扫描数量不应超过限制（30只）。"""
    mock_client.get_security_bars = AsyncMock(return_value=_make_sample_df(500))
    resp = app_client.post(
        "/api/v1/screening/scan",
        json={"date": "2023-12-01", "market": "SZ", "stock_type": "all"},
    )
    body = resp.json()
    assert body.get("total_scanned", 0) <= 30


def test_scan_sorted_by_quality(app_client: TestClient, mock_client: AsyncMock):
    """合格股票应按质量分数降序排列。"""
    mock_client.get_security_bars = AsyncMock(return_value=_make_sample_df(500))
    resp = app_client.post(
        "/api/v1/screening/scan",
        json={"date": "2023-12-01", "market": "SZ", "stock_type": "all"},
    )
    body = resp.json()
    qualified = body.get("qualified", [])
    if len(qualified) > 1:
        scores = [s.get("quality_score", 0) for s in qualified]
        assert scores == sorted(scores, reverse=True)
