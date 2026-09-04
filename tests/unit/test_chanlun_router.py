"""chanlun.py 路由边界测试（V395）—— 缠论分析/多级别/推荐三端点。

chanlun.py 此前覆盖率 29%。本文件 mock fetch_qfq_klines 与 ChanlunAnalyser，
覆盖 analyze/multi-level/recommend 三个主端点的成功路径与数据序列化，
补齐路由层最大的覆盖率缺口。全程离线，不连 TDX。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient


def _make_df(n: int = 60) -> pd.DataFrame:
    closes = [100.0 + i * 0.1 for i in range(n)]
    return pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": closes,
            "close": closes,
            "high": [c + 1.0 for c in closes],
            "low": [c - 1.0 for c in closes],
            "vol": [1e6] * n,
            "amount": [1e8] * n,
        }
    )


def _fake_result() -> MagicMock:
    """构造可满足序列化链路的 ChanlunResult mock。"""
    r = MagicMock()
    r.code = "SZ000001"
    r.frequency = "daily"
    r.klines = []
    r.fractals = []
    r.mmds = []
    r.bis = []
    r.boll = None
    r.to_dict.return_value = {"mmds": [], "bis": [], "xds": [], "zss": [], "bcs": []}
    return r


def _make_app_client() -> TestClient:
    from easy_tdx.web.app import _create_app

    app = _create_app(enable_mac=True)
    app.state.tdx_client = AsyncMock()
    app.state.mac_client = AsyncMock()
    return TestClient(app)


class TestChanlunAnalyze:
    def test_analyze_success(self) -> None:
        client = _make_app_client()
        result = _fake_result()
        with (
            patch(
                "easy_tdx.web.routers.chanlun.fetch_qfq_klines",
                new=AsyncMock(return_value=_make_df()),
            ),
            patch("easy_tdx.chanlun.ChanlunAnalyser") as mk,
        ):
            mk.return_value.process_klines.return_value = result
            resp = client.post(
                "/api/v1/chanlun/analyze",
                json={"market": "SZ", "code": "000001", "category": "DAY"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "mmds" in body
        # 空 klines 时准确度验证返回「无信号」摘要而非崩溃
        assert body["signal_accuracy"]["summary"] == "无信号或数据不足，无法验证"


class TestChanlunMultiLevel:
    def test_multi_level_success(self) -> None:
        client = _make_app_client()
        result = _fake_result()
        with (
            patch(
                "easy_tdx.web.routers.chanlun.fetch_qfq_klines",
                new=AsyncMock(return_value=_make_df()),
            ),
            patch("easy_tdx.chanlun.ChanlunAnalyser") as mk,
            patch("easy_tdx.chanlun.multi_level.MultiLevelAnalyser") as mk_mla,
        ):
            mk.return_value.process_klines.return_value = result
            mk_mla.return_value.compute_confluence_score.return_value = 0.5
            resp = client.post(
                "/api/v1/chanlun/multi-level",
                json={
                    "market": "SZ",
                    "code": "000001",
                    "category": "DAY",
                    "low_level": "MIN_30",
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "high_level" in body
        assert body["confluence"] == 0.5


class TestChanlunRecommend:
    def test_recommend_success(self) -> None:
        client = _make_app_client()
        result = _fake_result()
        with (
            patch(
                "easy_tdx.web.routers.chanlun.fetch_qfq_klines",
                new=AsyncMock(return_value=_make_df()),
            ),
            patch("easy_tdx.chanlun.ChanlunAnalyser") as mk,
        ):
            mk.return_value.process_klines.return_value = result
            resp = client.post(
                "/api/v1/chanlun/recommend",
                json={"market": "SZ", "code": "000001", "category": "DAY"},
            )
        assert resp.status_code == 200
        body = resp.json()
        # 空结构（无买卖点）时推荐返回 error/symbol 的保守降级
        assert "symbol" in body


class TestChanlunTrain:
    def test_train_session_success(self) -> None:
        client = _make_app_client()
        result = _fake_result()
        with (
            patch(
                "easy_tdx.web.routers.chanlun.fetch_qfq_klines",
                new=AsyncMock(return_value=_make_df()),
            ),
            patch("easy_tdx.chanlun.ChanlunAnalyser") as mk,
        ):
            mk.return_value.process_klines.return_value = result
            resp = client.post(
                "/api/v1/chanlun/train/session",
                json={"market": "SZ", "code": "000001", "category": "DAY"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == "SZ000001"
        assert "candidates" in body

    def test_train_session_empty_bars(self) -> None:
        client = _make_app_client()
        with patch(
            "easy_tdx.web.routers.chanlun.fetch_qfq_klines",
            new=AsyncMock(return_value=_make_df(0)),
        ):
            resp = client.post(
                "/api/v1/chanlun/train/session",
                json={"market": "SZ", "code": "000001", "category": "DAY"},
            )
        assert resp.status_code == 200
        assert resp.json()["error"] == "未取到行情数据"

    def test_train_score_success(self) -> None:
        client = _make_app_client()
        store = MagicMock()
        store.add = MagicMock()
        with patch("easy_tdx.web.train_store.get_score_store", return_value=store):
            resp = client.post(
                "/api/v1/chanlun/train/score",
                json={
                    "player_name": "学员",
                    "score": 18,
                    "total_asked": 8,
                    "hit_count": 6,
                    "hit_rate": 75.0,
                    "code": "000001",
                    "market": "SZ",
                    "category": "DAY",
                    "count": 400,
                },
            )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_train_leaderboard_success(self) -> None:
        client = _make_app_client()
        store = MagicMock()
        store.leaderboard = MagicMock(return_value=[])
        with patch("easy_tdx.web.train_store.get_score_store", return_value=store):
            resp = client.get("/api/v1/chanlun/train/leaderboard")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0
