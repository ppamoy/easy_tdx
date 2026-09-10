"""零覆盖 Web 路由契约测试——11 个此前无测试文件的路由模块行为级回归。

V387：announcement/block/board_mac/ex_market/finance/fundamental/indicator/
mac_data/mac_quotes/realtime/server 十一个路由模块在测试目录中零引用。本文件
用「mock 客户端注入 + 纯计算路由真跑 + 参数校验错误分支」三种方式补齐契约：
成功响应结构、缺失/非法参数错误分支、空数据安全降级。全程离线，不连 TDX。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pandas as pd
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient


def _small_df(n: int = 3) -> pd.DataFrame:
    """构造小型 DataFrame 供 mock 客户端返回。"""
    return pd.DataFrame(
        {
            "name": [f"r{i}" for i in range(n)],
            "value": list(range(n)),
        }
    )


def _make_app_client() -> TestClient:
    """构建 FastAPI app 并注入三个 mock 客户端，返回 TestClient。"""
    from easy_tdx.web.app import _create_app

    app = _create_app(enable_mac=True, enable_ex=True)
    app.state.tdx_client = AsyncMock()
    app.state.mac_client = AsyncMock()
    app.state.ex_client = AsyncMock()
    return TestClient(app)


# ── block / finance（标准 TDX 客户端） ───────────────────────────────────────


class TestTdxClientRouters:
    def test_block_info_success(self) -> None:
        client = _make_app_client()
        client.app.state.tdx_client.get_block_info = AsyncMock(return_value=_small_df())
        resp = client.get("/api/v1/block", params={"filename": "block_zs.dat"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 3
        assert body["data"][0]["name"] == "r0"

    def test_block_info_missing_filename(self) -> None:
        resp = _make_app_client().get("/api/v1/block")
        assert resp.status_code == 422

    def test_xdxr_success(self) -> None:
        client = _make_app_client()
        client.app.state.tdx_client.get_xdxr_info = AsyncMock(return_value=_small_df())
        resp = client.get("/api/v1/xdxr", params={"market": "SZ", "code": "000001"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 3

    def test_finance_info_success(self) -> None:
        client = _make_app_client()
        client.app.state.tdx_client.get_finance_info = AsyncMock(return_value=_small_df())
        resp = client.get("/api/v1/finance", params={"market": "SZ", "code": "000001"})
        assert resp.status_code == 200

    def test_company_category_success(self) -> None:
        client = _make_app_client()
        client.app.state.tdx_client.get_company_info_category = AsyncMock(return_value=_small_df())
        resp = client.get("/api/v1/company/category", params={"market": "SZ", "code": "000001"})
        assert resp.status_code == 200

    def test_company_content_success(self) -> None:
        client = _make_app_client()
        client.app.state.tdx_client.get_company_info_content = AsyncMock(return_value="公告正文")
        resp = client.get(
            "/api/v1/company/content",
            params={"market": "SZ", "code": "000001", "filename": "000001.txt"},
        )
        assert resp.status_code == 200
        assert resp.json()["content"] == "公告正文"

    def test_financial_file_list_success(self) -> None:
        client = _make_app_client()
        client.app.state.tdx_client.get_financial_file_list = AsyncMock(return_value=_small_df())
        resp = client.get("/api/v1/financial/file-list")
        assert resp.status_code == 200

    def test_financial_records_missing_filename(self) -> None:
        resp = _make_app_client().get("/api/v1/financial/records")
        assert resp.status_code == 422


# ── board_mac / mac_data / mac_quotes（MAC 客户端） ───────────────────────────


class TestMacClientRouters:
    def test_board_list_success(self) -> None:
        client = _make_app_client()
        client.app.state.mac_client.get_board_list = AsyncMock(return_value=_small_df())
        resp = client.get("/api/v1/board-mac/list", params={"board_type": "HY"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 3

    def test_board_members_missing_symbol(self) -> None:
        resp = _make_app_client().get("/api/v1/board-mac/members")
        assert resp.status_code == 422

    def test_board_belong_success(self) -> None:
        client = _make_app_client()
        client.app.state.mac_client.get_belong_board = AsyncMock(return_value=_small_df())
        resp = client.get("/api/v1/board-mac/belong", params={"market": "SZ", "code": "000001"})
        assert resp.status_code == 200

    def test_board_summary_success(self) -> None:
        client = _make_app_client()
        client.app.state.mac_client.get_board_summary = AsyncMock(return_value={"summary": "ok"})
        resp = client.get("/api/v1/board-mac/summary", params={"board_symbol": "881001"})
        assert resp.status_code == 200
        assert resp.json()["data"]["summary"] == "ok"

    def test_board_ranking_success(self) -> None:
        client = _make_app_client()
        client.app.state.mac_client.get_board_ranking = AsyncMock(return_value=_small_df())
        resp = client.get("/api/v1/board-mac/ranking")
        assert resp.status_code == 200

    def test_board_change_ranking_success(self) -> None:
        client = _make_app_client()
        client.app.state.mac_client.get_board_change_ranking = AsyncMock(return_value=_small_df())
        resp = client.get("/api/v1/board-mac/change-ranking")
        assert resp.status_code == 200

    def test_capital_flow_success(self) -> None:
        client = _make_app_client()
        client.app.state.mac_client.get_capital_flow = AsyncMock(return_value=_small_df())
        resp = client.get("/api/v1/mac/capital-flow", params={"market": "SZ", "code": "000001"})
        assert resp.status_code == 200

    def test_symbol_info_missing_params(self) -> None:
        resp = _make_app_client().get("/api/v1/mac/symbol-info")
        assert resp.status_code == 422

    def test_server_info_success(self) -> None:
        client = _make_app_client()
        client.app.state.mac_client.get_server_info = AsyncMock(return_value=_small_df())
        resp = client.get("/api/v1/mac/server-info")
        assert resp.status_code == 200

    def test_quote_list_success(self) -> None:
        client = _make_app_client()
        client.app.state.mac_client.get_stock_quotes_list = AsyncMock(return_value=_small_df())
        resp = client.get("/api/v1/mac/quote-list")
        assert resp.status_code == 200

    def test_auction_missing_market(self) -> None:
        resp = _make_app_client().get("/api/v1/mac/auction", params={"code": "000001"})
        assert resp.status_code == 422

    def test_unusual_success(self) -> None:
        client = _make_app_client()
        client.app.state.mac_client.get_unusual = AsyncMock(return_value=_small_df())
        resp = client.get("/api/v1/mac/unusual", params={"market": "SZ"})
        assert resp.status_code == 200


# ── ex_market（扩展市场客户端） ───────────────────────────────────────────────


class TestExMarketRouters:
    def test_ex_bars_success(self) -> None:
        client = _make_app_client()
        client.app.state.ex_client.get_instrument_bars = AsyncMock(return_value=[])
        resp = client.get("/api/v1/ex/bars", params={"market": "HK_MAIN_BOARD", "code": "00700"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_ex_quote_missing_market(self) -> None:
        resp = _make_app_client().get("/api/v1/ex/quote", params={"code": "00700"})
        assert resp.status_code == 422

    def test_ex_minute_success(self) -> None:
        client = _make_app_client()
        client.app.state.ex_client.get_minute_time_data = AsyncMock(return_value=[])
        resp = client.get("/api/v1/ex/minute", params={"market": "HK_MAIN_BOARD", "code": "00700"})
        assert resp.status_code == 200

    def test_ex_transaction_success(self) -> None:
        client = _make_app_client()
        client.app.state.ex_client.get_transaction_data = AsyncMock(return_value=[])
        resp = client.get(
            "/api/v1/ex/transaction", params={"market": "HK_MAIN_BOARD", "code": "00700"}
        )
        assert resp.status_code == 200


# ── indicator（纯计算路由） ───────────────────────────────────────────────────


class TestIndicatorRouters:
    def test_indicator_list(self) -> None:
        resp = _make_app_client().get("/api/v1/indicator/list")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_indicator_compute_success(self) -> None:
        resp = _make_app_client().post(
            "/api/v1/indicator/compute",
            json={
                "data": [
                    {"open": 10, "high": 12, "low": 9, "close": 11, "vol": 1000},
                    {"open": 11, "high": 13, "low": 10, "close": 12, "vol": 1200},
                ],
                "indicators": ["ATR"],
                "params": {"ATR": {"N": 2}},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] >= 1

    def test_indicator_compute_empty_indicators(self) -> None:
        resp = _make_app_client().post(
            "/api/v1/indicator/compute",
            json={"data": [], "indicators": []},
        )
        assert resp.status_code == 422


# ── fundamental（参数校验错误分支） ───────────────────────────────────────────


class TestFundamentalRouterValidation:
    def test_indicator_invalid_date(self) -> None:
        resp = _make_app_client().get(
            "/api/v1/fundamental/indicator/SZ/000001", params={"as_of": "not-a-date"}
        )
        assert resp.status_code == 400

    def test_indicator_cols_include_bps(self) -> None:
        """V499: 单标财务指标 API 字段应包含每股净资产 bps。"""
        from easy_tdx.web.routers.fundamental import _INDICATOR_COLS

        assert "bps" in _INDICATOR_COLS
        assert "eps" in _INDICATOR_COLS
        assert "total_shares" in _INDICATOR_COLS

    def test_screen_missing_date(self) -> None:
        resp = _make_app_client().post("/api/v1/fundamental/screen", json={})
        assert resp.status_code == 400

    def test_screen_invalid_date(self) -> None:
        resp = _make_app_client().post(
            "/api/v1/fundamental/screen", json={"date": "bad", "pool": []}
        )
        assert resp.status_code == 400

    def test_season_missing_date(self) -> None:
        resp = _make_app_client().post("/api/v1/fundamental/season", json={})
        assert resp.status_code == 400

    def test_verify_missing_dates(self) -> None:
        resp = _make_app_client().post("/api/v1/fundamental/verify", json={"pool": []})
        assert resp.status_code == 400

    def test_scan_invalid_stock_type(self) -> None:
        resp = _make_app_client().post(
            "/api/v1/fundamental/scan", json={"date": "2024-01-01", "stock_type": "bad"}
        )
        assert resp.status_code == 400


# ── announcement（参数校验 + mock 客户端） ────────────────────────────────────


class TestAnnouncementRouter:
    def test_code_too_short(self) -> None:
        resp = _make_app_client().get("/api/v1/announcements", params={"code": "123"})
        assert resp.status_code == 422

    def test_code_too_long(self) -> None:
        resp = _make_app_client().get("/api/v1/announcements", params={"code": "1234567"})
        assert resp.status_code == 422


# ── realtime（WebSocket 冒烟） ────────────────────────────────────────────────


class TestRealtimeRouter:
    def test_websocket_connect_and_invalid_json(self) -> None:
        client = _make_app_client()
        with client.websocket_connect("/api/v1/ws/realtime/SZ000001") as ws:
            ws.send_text("{invalid json")
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert msg["msg"] == "invalid JSON"


# ── server（无依赖路由） ──────────────────────────────────────────────────────


class TestServerRouter:
    def test_list_hosts(self) -> None:
        client = _make_app_client()
        # AsyncMock 的属性访问返回 Mock，HostListResponse.current_host 需要 str
        client.app.state.tdx_client._host = "test.example.com"
        resp = client.get("/api/v1/server/hosts")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == len(body["hosts"])
        assert "current_host" in body

    def test_switch_host_invalid(self) -> None:
        resp = _make_app_client().post("/api/v1/server/switch", json={"host": "not-a-real-host"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is False
