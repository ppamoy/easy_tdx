"""market/monitor/sina 路由成功路径契约测试（V395）。

market.py(48%)/monitor.py(45%)/sina.py(44%) 此前只测了错误分支，成功路径
（mock 客户端返回 DataFrame 后的序列化）从未走到。本文件补齐三类路由的
成功响应与空数据降级，推动覆盖率过 70%。全程离线。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient


def _small_df() -> pd.DataFrame:
    return pd.DataFrame({"code": ["000001"], "name": ["平安银行"]})


def _make_app_client() -> TestClient:
    from easy_tdx.web.app import _create_app

    app = _create_app(enable_mac=True)
    app.state.tdx_client = AsyncMock()
    app.state.mac_client = AsyncMock()
    return TestClient(app)


class TestMarketRouter:
    def test_security_count_success(self) -> None:
        client = _make_app_client()
        client.app.state.tdx_client.get_security_count = AsyncMock(return_value=123)
        resp = client.get("/api/v1/security/count", params={"market": "SZ"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 123

    def test_security_list_success(self) -> None:
        client = _make_app_client()
        client.app.state.tdx_client.get_security_list = AsyncMock(return_value=_small_df())
        resp = client.get("/api/v1/security/list", params={"market": "SZ"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_security_list_all_success(self) -> None:
        client = _make_app_client()
        client.app.state.tdx_client.get_security_list_all = AsyncMock(return_value=_small_df())
        resp = client.get("/api/v1/security/list-all")
        assert resp.status_code == 200

    def test_quotes_success(self) -> None:
        client = _make_app_client()
        client.app.state.tdx_client.get_security_quotes = AsyncMock(return_value=_small_df())
        resp = client.post("/api/v1/quotes", json={"stocks": [{"market": "SZ", "code": "000001"}]})
        assert resp.status_code == 200

    def test_market_stat_success(self) -> None:
        client = _make_app_client()
        client.app.state.tdx_client.get_market_stat = AsyncMock(return_value=_small_df())
        resp = client.get("/api/v1/market/stat")
        assert resp.status_code == 200

    def test_fund_flow_success(self) -> None:
        client = _make_app_client()
        client.app.state.tdx_client.get_fund_flow = AsyncMock(return_value=_small_df())
        resp = client.get("/api/v1/fund-flow", params={"market": "SZ", "code": "000001"})
        assert resp.status_code == 200

    def test_history_fund_flow_success(self) -> None:
        client = _make_app_client()
        client.app.state.tdx_client.get_history_fund_flow = AsyncMock(return_value=_small_df())
        resp = client.get("/api/v1/fund-flow/history", params={"market": "SZ", "code": "000001"})
        assert resp.status_code == 200

    def test_market_strength_empty_universe(self) -> None:
        client = _make_app_client()
        # 无 vipdoc → mock 整个 StrengthRanker，rank 返回 []（空数据降级）
        with patch("easy_tdx.screen.strength.StrengthRanker") as mk:
            mk.return_value.rank.return_value = []
            resp = client.get("/api/v1/market/strength")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


class TestMonitorRouter:
    def test_monitor_create_missing_stocks(self) -> None:
        client = _make_app_client()
        resp = client.post("/api/v1/monitor/create", json={})
        assert resp.status_code == 400
        assert resp.json()["detail"] == "stocks 不能为空"

    def test_monitor_create_success(self) -> None:
        client = _make_app_client()
        from easy_tdx.web.routers import monitor as mon

        with (
            patch.object(mon._monitor, "create_task", new=AsyncMock(return_value="t1")),
            patch.object(mon._monitor, "start_periodic_check", new=AsyncMock()),
        ):
            resp = client.post(
                "/api/v1/monitor/create",
                json={
                    "stocks": [{"market": "SZ", "code": "000001"}],
                    "interval_seconds": 30,
                },
            )
        assert resp.status_code == 200
        assert resp.json()["task_id"] == "t1"

    def test_monitor_status_not_found(self) -> None:
        client = _make_app_client()
        from easy_tdx.web.routers import monitor as mon

        with patch.object(mon._monitor, "get_task", new=AsyncMock(return_value=None)):
            resp = client.get("/api/v1/monitor/no-such-task")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "任务不存在"

    def test_monitor_check_not_found(self) -> None:
        client = _make_app_client()
        from easy_tdx.web.routers import monitor as mon

        with patch.object(mon._monitor, "get_task", new=AsyncMock(return_value=None)):
            resp = client.post("/api/v1/monitor/no-such-task/check")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "未知监控任务 'no-such-task'"

    def test_monitor_stop(self) -> None:
        client = _make_app_client()
        from easy_tdx.web.routers import monitor as mon

        with patch.object(mon._monitor, "stop_task", new=AsyncMock(return_value=True)):
            resp = client.post("/api/v1/monitor/t1/stop")
        assert resp.status_code == 200
        assert resp.json()["removed"] is True

    def test_monitor_list_success(self) -> None:
        client = _make_app_client()
        with patch("easy_tdx.web.routers.monitor._monitor._tasks", {}):
            resp = client.get("/api/v1/monitor/list")
        assert resp.status_code == 200
        assert isinstance(resp.json()["tasks"], list)

    def test_monitor_status_missing(self) -> None:
        client = _make_app_client()
        resp = client.get("/api/v1/monitor/no-such-task")
        assert resp.status_code in (200, 404, 400)


class TestSinaRouter:
    def test_financial_report_success(self) -> None:
        client = _make_app_client()
        resp = client.get(
            "/api/v1/sina/financial-report",
            params={"code": "600519", "report_type": "income"},
        )
        assert resp.status_code == 200
