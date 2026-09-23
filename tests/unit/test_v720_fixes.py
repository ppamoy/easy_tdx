"""V720 飞轮第 2 轮修复的回归测试。

覆盖（缺陷编号对应 docs/FLYWHEEL_ROUND2.md）：
- D1  /diagnosis/quick 显式传 mac_client（此前裸 Depends 对象 100% 500）；
- D2  bars 系 start/越界与 date 边界在参数层 422（chanlun start 同）；
- D3  松散 dict 端点形状守卫：pool/symbols/train-score/learn-mistakes → 400；
- D4  monitor/create 先校验后建任务（interval/threshold 非法 → 400 且无孤儿任务）；
- D5  /market/strength 无 TDX_HOME → 503 + 可读指引；
- D7  backtest 未知任务 404（对齐全站任务轮询语义）；
- D8  multi-level 非法 category/low_level → 400（不再静默回落 daily）；
- D9  alert_store limit<=0 → 空列表；
- D10 sina 无效代码 → 422（参数层拦截，不再穿透到上游 503）；
- D11 空数据故障转移总时间预算（超预算返回空数据 + warning，正常路径不受影响）。

全程离线：外部依赖（fetch_qfq_klines / StrengthRanker / TdxClient）全部 mock。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from easy_tdx.web import create_app


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _bars_df(n: int) -> pd.DataFrame:
    closes = [100.0 + i * 0.1 for i in range(n)]
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": closes,
            "close": closes,
            "high": [c + 1.0 for c in closes],
            "low": [c - 1.0 for c in closes],
            "vol": [1e6] * n,
            "amount": [1e8] * n,
        }
    )


# ── D1: /diagnosis/quick 显式传 mac_client ──────────────────────────────────


class TestD1QuickDiagnosis:
    def test_quick_diagnosis_returns_analysis_not_500(self, client: TestClient) -> None:
        """mock 掉取数后 GET /diagnosis/quick 必须 200/数据不足分支，绝不 500。

        回归锚点：此前 quick_diagnosis 直接调 diagnose_stock(req, client)，
        diagnose_stock 的默认参数 Depends(get_mac_client_optional) 不经 FastAPI
        DI 不解析 → 'Depends' object has no attribute 'get_stock_kline' → 500。
        """
        resp = client.get("/api/v1/diagnosis/quick", params={"market": "SH", "code": "600519"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # 走到 diagnose_stock 内部的完整分析：action/score/chanlun 等字段，
        # 或数据不足分支（error）——只要不是 500 的 Internal Server Error 即可。
        assert ("action" in body and "score" in body) or ("error" in body)

    def test_quick_diagnosis_passes_mac_client(self) -> None:
        """结构级锚定：quick_diagnosis 签名含 mac_client 且显式传入 diagnose_stock。"""
        import inspect

        from easy_tdx.web.routers import diagnosis as dia

        sig = inspect.signature(dia.quick_diagnosis)
        assert "mac_client" in sig.parameters, (
            "quick_diagnosis 必须声明 mac_client = Depends(get_mac_client_optional)"
        )
        src = inspect.getsource(dia.quick_diagnosis)
        assert "diagnose_stock(req, client, mac_client)" in src, (
            "调用 diagnose_stock 时必须显式传 mac_client"
        )

    def test_quick_diagnosis_requires_code(self, client: TestClient) -> None:
        resp = client.get("/api/v1/diagnosis/quick", params={"market": "SH"})
        assert resp.status_code == 200
        assert resp.json()["error"] == "请提供股票代码"


# ── D2: 参数边界 ────────────────────────────────────────────────────────────


class TestD2ParamBounds:
    def test_bars_start_over_uint16_is_422(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/bars", params={"market": "SH", "code": "600519", "start": 999999999}
        )
        assert resp.status_code == 422

    def test_bars_index_start_over_uint16_is_422(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/bars/index",
            params={"market": "SH", "code": "000001", "start": 999999999},
        )
        assert resp.status_code == 422

    def test_transaction_start_over_uint16_is_422(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/transaction",
            params={"market": "SH", "code": "600519", "start": 70000},
        )
        assert resp.status_code == 422

    def test_minute_history_negative_date_is_422(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/minute/history", params={"market": "SH", "code": "600519", "date": -1}
        )
        assert resp.status_code == 422

    def test_transaction_history_bad_date_is_422(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/transaction/history",
            params={"market": "SH", "code": "600519", "date": 100000000},
        )
        assert resp.status_code == 422

    def test_chanlun_analyze_start_over_uint16_is_422(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/chanlun/analyze",
            json={"market": "SZ", "code": "000001", "start": 999999999},
        )
        assert resp.status_code == 422

    def test_chanlun_start_boundary_values_accepted(self, client: TestClient) -> None:
        """边界值 65535 应通过参数校验（到达业务层后由 mock 吸收）。"""
        with patch(
            "easy_tdx.web.routers.chanlun.fetch_qfq_klines",
            new=AsyncMock(return_value=_bars_df(0)),
        ):
            resp = client.post(
                "/api/v1/chanlun/analyze",
                json={"market": "SZ", "code": "000001", "start": 65535},
            )
        assert resp.status_code == 200


# ── D3: 松散 dict 端点形状守卫 ──────────────────────────────────────────────


class TestD3ShapeGuards:
    def test_screen_pool_string_is_400(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/stock-pick/screen",
            json={"date": "2026-09-01", "pool": "abc"},
        )
        assert resp.status_code == 400
        assert "pool" in resp.json()["detail"]

    def test_screen_async_pool_non_dict_element_is_400(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/stock-pick/screen/async",
            json={"date": "2026-09-01", "pool": ["SH600519"]},
        )
        assert resp.status_code == 400
        assert "pool" in resp.json()["detail"]

    def test_dashboard_async_pool_string_is_400(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/stock-pick/dashboard/async",
            json={"date": "2026-09-01", "pool": "abc"},
        )
        assert resp.status_code == 400
        assert "pool" in resp.json()["detail"]

    def test_screen_valid_pool_accepted(self, client: TestClient) -> None:
        """合法 {market, code} 对象池不受影响（形状校验不误伤）。"""
        from easy_tdx.web.routers import stock_pick as sp

        with patch.object(sp, "_screen_run_sync", return_value={"total": 0, "results": []}):
            resp = client.post(
                "/api/v1/stock-pick/screen",
                json={
                    "date": "2026-09-01",
                    "pool": [{"market": "SH", "code": "600519"}],
                },
            )
        assert resp.status_code == 200, resp.text

    def test_timing_symbols_string_element_is_400(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/stock-pick/timing",
            json={"date": "2026-09-01", "symbols": ["SH600519"]},
        )
        assert resp.status_code == 400
        assert "symbols" in resp.json()["detail"]

    def test_timing_symbols_valid_still_200(self, client: TestClient) -> None:
        """合法 symbols 走到业务层（mock 后返回空结果结构），不再 500。"""
        from easy_tdx.web.routers import stock_pick as sp

        with (
            patch.object(sp, "_fetch_window", new=AsyncMock(return_value=_bars_df(0))),
            patch.object(sp, "_run_timing_one", return_value={"symbol": "SH:600519"}),
            patch("easy_tdx.fundamental.pipeline.detect_season_for_date", return_value=None),
        ):
            resp = client.post(
                "/api/v1/stock-pick/timing",
                json={
                    "date": "2026-09-01",
                    "symbols": [{"market": "SH", "code": "600519"}],
                },
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["results"][0]["symbol"] == "SH:600519"

    def test_train_score_bad_score_is_400(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/chanlun/train/score",
            json={"player_name": "学员", "score": "abc", "total_asked": 8, "hit_count": 6},
        )
        assert resp.status_code == 400
        assert "score" in resp.json()["detail"]

    def test_train_score_bad_hit_rate_is_400(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/chanlun/train/score",
            json={"score": 10, "hit_rate": [1.0]},
        )
        assert resp.status_code == 400
        assert "hit_rate" in resp.json()["detail"]

    def test_train_score_bad_total_asked_is_400(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/chanlun/train/score",
            json={"score": 10, "total_asked": "abc"},
        )
        assert resp.status_code == 400
        assert "total_asked" in resp.json()["detail"]

    def test_train_score_valid_payload_still_200(self, client: TestClient) -> None:
        store = MagicMock()
        with patch("easy_tdx.web.train_store.get_score_store", return_value=store):
            resp = client.post(
                "/api/v1/chanlun/train/score",
                json={"player_name": "学员", "score": 18, "total_asked": 8, "hit_count": 6},
            )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_learn_mistakes_array_field_is_400(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/learn/mistakes",
            json={"player": "学员", "explanation": ["a", "b"]},
        )
        assert resp.status_code == 400
        assert "explanation" in resp.json()["detail"]

    def test_learn_mistakes_valid_scalar_still_200(self, client: TestClient) -> None:
        store = MagicMock()
        with patch("easy_tdx.web.train_store.get_score_store", return_value=store):
            resp = client.post(
                "/api/v1/learn/mistakes",
                json={"player": "学员", "symbol": "SZ000001", "user_choice": "买"},
            )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


# ── D4: monitor/create 先校验后建任务 ───────────────────────────────────────


class TestD4MonitorCreateValidation:
    def _post(self, client: TestClient, interval: object, threshold: object = 0.7):
        return client.post(
            "/api/v1/monitor/create",
            json={
                "stocks": [{"market": "SZ", "code": "000001"}],
                "confidence_threshold": threshold,
                "interval_seconds": interval,
            },
        )

    @pytest.mark.parametrize("interval", ["abc", -5, 90000, 1.5, [60]])
    def test_bad_interval_is_400_and_no_task_created(
        self, client: TestClient, interval: object
    ) -> None:
        from easy_tdx.web.routers import monitor as mon

        with (
            patch.object(
                mon._monitor, "create_task", new=AsyncMock(return_value="t-orphan")
            ) as mock_create,
            patch.object(mon._monitor, "start_periodic_check", new=AsyncMock()),
        ):
            resp = self._post(client, interval)
        assert resp.status_code == 400
        assert "interval_seconds" in resp.json()["detail"]
        assert mock_create.await_count == 0, "校验失败时不得创建任务（孤儿任务）"

    @pytest.mark.parametrize("threshold", ["high", 1.5, -0.1, [0.7]])
    def test_bad_threshold_is_400_and_no_task_created(
        self, client: TestClient, threshold: object
    ) -> None:
        from easy_tdx.web.routers import monitor as mon

        with (
            patch.object(
                mon._monitor, "create_task", new=AsyncMock(return_value="t-orphan")
            ) as mock_create,
            patch.object(mon._monitor, "start_periodic_check", new=AsyncMock()),
        ):
            resp = self._post(client, 60, threshold)
        assert resp.status_code == 400
        assert "confidence_threshold" in resp.json()["detail"]
        assert mock_create.await_count == 0

    def test_valid_interval_zero_ok(self, client: TestClient) -> None:
        """interval=0 语义为「不自动检查」，必须仍可用。"""
        from easy_tdx.web.routers import monitor as mon

        with (
            patch.object(mon._monitor, "create_task", new=AsyncMock(return_value="t1")),
            patch.object(mon._monitor, "start_periodic_check", new=AsyncMock()) as mk_start,
        ):
            resp = self._post(client, 0)
        assert resp.status_code == 200
        assert resp.json()["task_id"] == "t1"
        assert mk_start.await_count == 0, "interval=0 不应启动后台轮询"


# ── D5: /market/strength 环境缺失 → 503 ─────────────────────────────────────


class TestD5MarketStrengthUnavailable:
    def test_tdx_offline_error_is_503_with_guidance(self, client: TestClient) -> None:
        from easy_tdx.exceptions import TdxOfflineError

        with patch("easy_tdx.screen.strength.StrengthRanker") as mk:
            mk.side_effect = TdxOfflineError("无法定位通达信安装目录")
            resp = client.get("/api/v1/market/strength")
        assert resp.status_code == 503
        detail = resp.json()["detail"]
        assert "TDX_HOME" in detail
        assert "行情强度数据不可用" in detail

    def test_other_exceptions_still_500(self, client: TestClient) -> None:
        """窄捕获：其他异常不受影响，仍走全局 500 处理器。"""
        with patch("easy_tdx.screen.strength.StrengthRanker") as mk:
            mk.side_effect = RuntimeError("boom")
            resp = client.get("/api/v1/market/strength")
        assert resp.status_code == 500


# ── D7: backtest 未知任务 404 ────────────────────────────────────────────────


class TestD7BacktestUnknownTask:
    def test_unknown_task_is_404(self, client: TestClient) -> None:
        resp = client.get("/api/v1/backtest/tasks/nonexistent")
        assert resp.status_code == 404
        assert "未知任务" in resp.json()["detail"]


# ── D8: multi-level 频率白名单 ──────────────────────────────────────────────


class TestD8MultiLevelFrequency:
    def test_bad_category_is_400(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/chanlun/multi-level",
            json={"market": "SZ", "code": "000001", "category": "HOUR4"},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "HOUR4" in detail
        assert "DAY" in detail  # 提示合法值

    def test_bad_low_level_is_400(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/chanlun/multi-level",
            json={"market": "SZ", "code": "000001", "category": "DAY", "low_level": "MIN_7"},
        )
        assert resp.status_code == 400
        assert "MIN_7" in resp.json()["detail"]

    def test_empty_low_level_defaults_to_30min(self, client: TestClient) -> None:
        """空低级别 = 默认 30min（保留原语义，不应 400）。"""
        with (
            patch(
                "easy_tdx.web.routers.chanlun.fetch_qfq_klines",
                new=AsyncMock(return_value=_bars_df(0)),
            ),
            patch("easy_tdx.chanlun.ChanlunAnalyser") as mk_analyser,
            patch("easy_tdx.chanlun.multi_level.MultiLevelAnalyser") as mk_mla,
        ):
            result = MagicMock()
            result.klines = []
            result.fractals = []
            result.bis = []
            result.to_dict.return_value = {"bis": [], "mmds": []}
            mk_analyser.return_value.process_klines.return_value = result
            mk_mla.return_value.compute_confluence_score.return_value = 0.5
            mk_mla.return_value.query_low_level_qs.return_value = {}
            resp = client.post(
                "/api/v1/chanlun/multi-level",
                json={"market": "SZ", "code": "000001", "category": "DAY", "low_level": ""},
            )
        assert resp.status_code == 200, resp.text
        # low 级别 ChanlunAnalyser 应以 30min 创建
        freqs = [c.kwargs.get("frequency") for c in mk_analyser.call_args_list]
        assert "30min" in freqs


# ── D9: alert_store limit<=0 → 空列表 ───────────────────────────────────────


class TestD9AlertStoreLimit:
    def test_limit_zero_returns_empty(self) -> None:
        from easy_tdx.web.alert_store import clear_alerts, push_alert, recent_alerts

        clear_alerts()
        try:
            push_alert({"source": "monitor", "text": "x"})
            assert recent_alerts(0) == []
            assert recent_alerts(-1) == []
            assert len(recent_alerts(1)) == 1
        finally:
            clear_alerts()

    def test_alerts_endpoint_limit_zero_is_empty(self, client: TestClient) -> None:
        from easy_tdx.web.alert_store import clear_alerts, push_alert

        clear_alerts()
        try:
            push_alert({"source": "monitor", "text": "x"})
            resp = client.get("/api/v1/monitor/alerts", params={"limit": 0})
            assert resp.status_code == 200
            assert resp.json()["count"] == 0
            assert resp.json()["alerts"] == []
        finally:
            clear_alerts()


# ── D10: sina 无效代码 422（此前穿透到上游 503）──────────────────────────────


class TestD10SinaInvalidCode:
    def test_invalid_code_is_422_not_503(self, client: TestClient) -> None:
        resp = client.get("/api/v1/sina/financial-report", params={"code": "abc123"})
        assert resp.status_code == 422

    def test_short_code_is_422(self, client: TestClient) -> None:
        resp = client.get("/api/v1/sina/financial-report", params={"code": "60051"})
        assert resp.status_code == 422


# ── D11: 空数据故障转移总时间预算 ────────────────────────────────────────────


class TestD11FailoverTimeBudget:
    def test_sync_budget_returns_empty_and_warns(self) -> None:
        """预算耗尽后不再逐台尝试：返回空 + warning 一次。"""
        import logging
        import time as time_mod

        from easy_tdx.client import TdxClient
        from easy_tdx.commands.security_count import GetSecurityCountCmd
        from easy_tdx.models.enums import Market

        c = TdxClient("bad-host", 7709, 1.0, auto_reconnect=True, heartbeat_interval=0)
        with (
            patch.object(c, "_reconnect") as mk_reconnect,
            patch("easy_tdx.client.ping_all", return_value=[("h1", 0.01), ("h2", 0.02)]),
            patch("easy_tdx.client.save_best_host"),
            patch.object(TdxClient, "_FAILOVER_TIME_BUDGET_SEC", 0.0),
            patch.object(c, "_execute", return_value=[]),
            patch.object(logging.getLogger("easy_tdx.client"), "warning") as mk_warn,
        ):
            # 预算=0：第一次 _try 就判定超时
            started = time_mod.monotonic()
            result = c._find_host_returning_data(GetSecurityCountCmd(Market.SH))
            elapsed = time_mod.monotonic() - started

        assert result == []
        assert mk_reconnect.call_count == 0, "预算耗尽不应再重连候选主机"
        assert elapsed < 1.0, "预算路径应立即返回，不逐台实测"
        mk_warn.assert_called_once()
        assert "预算" in mk_warn.call_args[0][0]

    def test_sync_normal_path_unaffected(self) -> None:
        """正常路径：第二台候选有数据 → 切换并返回，预算逻辑不干预。"""
        from easy_tdx.client import TdxClient
        from easy_tdx.commands.security_count import GetSecurityCountCmd
        from easy_tdx.models.enums import Market

        c = TdxClient("bad-host", 7709, 1.0, auto_reconnect=True, heartbeat_interval=0)
        exec_results = iter([[], [123], [123]])  # 第1台空、第2台有数据、切机后重取

        def _fake_execute(_cmd: object) -> list[int]:
            return next(exec_results)

        with (
            patch.object(c, "_reconnect") as mk_reconnect,
            patch("easy_tdx.client.ping_all", return_value=[("h1", 0.01), ("h2", 0.02)]),
            patch("easy_tdx.client.save_best_host"),
            patch.object(c, "_execute", side_effect=_fake_execute),
        ):
            result = c._find_host_returning_data(GetSecurityCountCmd(Market.SH))

        assert result == [123]
        reconnect_hosts = [call.args[0] for call in mk_reconnect.call_args_list]
        assert reconnect_hosts[0] == "h1"

    @pytest.mark.asyncio
    async def test_async_budget_returns_empty_and_warns(self) -> None:
        """async 版预算耗尽语义与 sync 一致。"""
        import logging

        from easy_tdx.client import AsyncTdxClient
        from easy_tdx.commands.security_count import GetSecurityCountCmd
        from easy_tdx.models.enums import Market

        c = AsyncTdxClient("bad-host", 7709, 1.0, auto_reconnect=True, heartbeat_interval=0)
        with (
            patch.object(c, "_areconnect", new=AsyncMock()) as mk_reconnect,
            patch("easy_tdx.client.ping_all", return_value=[("h1", 0.01), ("h2", 0.02)]),
            patch("easy_tdx.client.save_best_host"),
            patch.object(AsyncTdxClient, "_FAILOVER_TIME_BUDGET_SEC", 0.0),
            patch.object(c, "_execute", new=AsyncMock(return_value=[])),
            patch.object(logging.getLogger("easy_tdx.client"), "warning") as mk_warn,
        ):
            result = await c._find_host_returning_data(GetSecurityCountCmd(Market.SH))

        assert result == []
        assert mk_reconnect.await_count == 0
        mk_warn.assert_called_once()

    def test_budget_constant_exists_on_both_clients(self) -> None:
        """预算常量同时挂载在 sync/async 两个 client（防回归锚点）。"""
        from easy_tdx.client import AsyncTdxClient, TdxClient

        assert 0 < TdxClient._FAILOVER_TIME_BUDGET_SEC <= 60
        assert AsyncTdxClient._FAILOVER_TIME_BUDGET_SEC == TdxClient._FAILOVER_TIME_BUDGET_SEC
