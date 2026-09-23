"""V721（飞轮第 3 轮）修复回归测试。

覆盖（对应 docs/FLYWHEEL_ROUND3.md）：
- D12 monitor/list 每项含 stocks 数组；
- D14 backtest symbol 宽进严处归一（SZ000001/sz:000001 → SZ:000001，
  ABC123/裸 6 位仍 422/校验失败；None 穿透；stocks 列表逐元素归一）
  + screening scan 产出 symbol 为「市场:代码」口径；
- D15 fetch_qfq_klines MAC 客户端异常回退 TDX（空 df 回退语义不变）；
- D17 同步 /stock-pick/screen 对 run_screen 结果按 top_n 截断。

全程离线：外部依赖（create_task / fetch_qfq_klines / run_screen）全部 mock。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from easy_tdx.web import create_app  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _fake_ohlcv(n: int = 60) -> list[dict[str, object]]:
    """构造最小可用 OHLCV（仅过 schema，不跑真实回测路由）。"""
    return [
        {
            "datetime": f"2025-01-{i + 1:02d}",
            "open": 10.0,
            "high": 10.5,
            "low": 9.5,
            "close": 10.2,
            "vol": 1000.0,
            "amount": 10200.0,
        }
        for i in range(n)
    ]


# ── D12: monitor/list 补 stocks 字段 ─────────────────────────────────────────


class TestD12MonitorListStocks:
    def test_list_items_include_stocks(self, client: TestClient) -> None:
        from easy_tdx.web.routers import monitor as mon

        task = mon.MonitorTask(
            task_id="t-v721",
            stocks=[{"market": "SZ", "code": "000001"}, {"market": "SH", "code": "600519"}],
            category="DAY",
            confidence_threshold=0.7,
        )
        with patch.dict(mon._monitor._tasks, {"t-v721": task}, clear=True):
            resp = client.get("/api/v1/monitor/list")
        assert resp.status_code == 200
        tasks = resp.json()["tasks"]
        assert len(tasks) == 1
        assert tasks[0]["stocks"] == [
            {"market": "SZ", "code": "000001"},
            {"market": "SH", "code": "600519"},
        ]
        assert tasks[0]["stock_count"] == 2

    def test_list_empty_stocks_is_empty_list_not_null(self, client: TestClient) -> None:
        """空任务 stocks 也应是 []（前端 ?? 0 兜底之外的结构保证）。"""
        from easy_tdx.web.routers import monitor as mon

        task = mon.MonitorTask(
            task_id="t-empty",
            stocks=[],
            category="DAY",
            confidence_threshold=0.7,
        )
        with patch.dict(mon._monitor._tasks, {"t-empty": task}, clear=True):
            resp = client.get("/api/v1/monitor/list")
        assert resp.status_code == 200
        assert resp.json()["tasks"][0]["stocks"] == []


# ── D14: backtest symbol 宽进严处 ────────────────────────────────────────────


class TestD14SymbolNormalization:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("SZ000001", "SZ:000001"),  # 市场前缀无冒号
            ("sz:000001", "SZ:000001"),  # 小写冒号
            ("SZ:000001", "SZ:000001"),  # 规范形态原样通过
            ("  SH600519  ", "SH:600519"),  # 首尾空白容忍
        ],
    )
    def test_backtest_request_normalizes_symbol(self, raw: str, expected: str) -> None:
        from easy_tdx.web.backtest_schemas import BacktestRequest

        req = BacktestRequest(strategy="ma_cross", symbol=raw)
        assert req.symbol == expected

    def test_backtest_request_none_passthrough(self) -> None:
        """Optional symbol 的 None 必须原样穿透（ohlcv-only 请求）。"""
        from easy_tdx.web.backtest_schemas import BacktestRequest

        req = BacktestRequest(strategy="ma_cross", ohlcv=_fake_ohlcv())
        assert req.symbol is None

    @pytest.mark.parametrize(
        "bad",
        [
            "ABC123",  # 无市场前缀的非数字
            "123456",  # 裸 6 位（backtest 不推断市场）
            "SZ:12",  # 代码不足 6 位
            "ZZ000001",  # 未知市场前缀
            "SZ:00000A",  # 代码含字母
        ],
    )
    def test_backtest_request_rejects_invalid(self, bad: str) -> None:
        from easy_tdx.web.backtest_schemas import BacktestRequest

        with pytest.raises(ValueError):
            BacktestRequest(strategy="ma_cross", symbol=bad)

    def test_stocks_list_elements_normalized(self) -> None:
        from easy_tdx.web.backtest_schemas import PortfolioBacktestRequest

        req = PortfolioBacktestRequest(
            strategy="ma_cross",
            stocks=["sz000001", "SH600519", "BJ:835185"],
        )
        assert req.stocks == ["SZ:000001", "SH:600519", "BJ:835185"]

    def test_stocks_rejects_bare_code(self) -> None:
        from easy_tdx.web.backtest_schemas import PortfolioBacktestRequest

        with pytest.raises(ValueError):
            PortfolioBacktestRequest(strategy="ma_cross", stocks=["600519"])

    def test_multi_strategy_item_normalized(self) -> None:
        from easy_tdx.web.backtest_schemas import MultiStrategyItem

        item = MultiStrategyItem(strategy="ma_cross", symbol="sh601088")
        assert item.symbol == "SH:601088"

    def test_optimize_all_symbol_normalized(self) -> None:
        from easy_tdx.web.backtest_schemas import OptimizeAllBacktestRequest

        req = OptimizeAllBacktestRequest(symbol="sz000001")
        assert req.symbol == "SZ:000001"

    def test_route_rejects_abc123_with_422(self, client: TestClient) -> None:
        """端到端：非法 symbol 经 FastAPI 校验层 → 422（不再 500/200）。"""
        resp = client.post(
            "/api/v1/backtest/run/async",
            json={"strategy": "ma_cross", "symbol": "ABC123", "count": 50},
        )
        assert resp.status_code == 422

    def test_route_rejects_bare_six_digits_with_422(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/backtest/run/async",
            json={"strategy": "ma_cross", "symbol": "123456", "count": 50},
        )
        assert resp.status_code == 422

    def test_route_accepts_sz_prefix_symbol_202(self, client: TestClient) -> None:
        """端到端：SZ000001 → 202（归一为 SZ:000001，取行情阶段 mock）。

        原实现 pattern 直接 422；修复后进入取行情（此处 mock fetch 命中），
        归一后的 stocks 已是规范口径。
        """
        from easy_tdx.web.routers import backtest as bt

        fetch_mock = AsyncMock(return_value=[MagicMock()])
        with patch.object(bt, "_fetch_portfolio_bars", fetch_mock):
            resp = client.post(
                "/api/v1/backtest/portfolio/run/async",
                json={"strategy": "ma_cross", "stocks": ["sz000001", "SH600519"]},
            )
        assert resp.status_code == 202, resp.text
        assert fetch_mock.await_count == 1
        called = fetch_mock.await_args
        assert called.args[1] == ["SZ:000001", "SH:600519"]

    def test_scan_symbol_uses_market_colon_code(self, client: TestClient) -> None:
        """scan 产出 symbol 统一为「市场:代码」（原 SZ000001）。"""
        from easy_tdx.web.routers import screening as sc

        rows = [
            {
                "valid": True,
                "code": "000001",
                "market": "SZ",
                "symbol": "SZ:000001",
                "quality_score": 80,
                "classification": "tree",
                "kline_count": 500,
                "bi_count": 3,
                "zs_count": 2,
                "buy_1_count": 0,
                "sell_1_count": 0,
                "buy_2_count": 0,
                "sell_2_count": 0,
                "latest_mmd": None,
            }
        ]
        with (
            patch.object(sc, "_get_stock_list", new=AsyncMock(return_value=["000001"])),
            patch.object(sc, "_analyze_stock", new=AsyncMock(return_value=rows[0])),
            patch.object(sc, "_pass_screening", return_value=True),
        ):
            resp = client.post(
                "/api/v1/screening/scan",
                json={"date": "2025-06-02", "market": "SZ"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["qualified"][0]["symbol"] == "SZ:000001"

    def test_scan_symbol_matches_backtest_schema_now(self) -> None:
        """口径对齐断言：scan 的新格式必须能直接过 backtest symbol 校验。"""
        from easy_tdx.web.backtest_schemas import BacktestRequest

        req = BacktestRequest(strategy="ma_cross", symbol="SZ:000001")
        assert req.symbol == "SZ:000001"


# ── D15: fetch_qfq_klines MAC 异常回退 ───────────────────────────────────────


def _bars_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "datetime": pd.date_range("2025-01-01", periods=5, freq="B"),
            "open": [10.0] * 5,
            "high": [10.5] * 5,
            "low": [9.5] * 5,
            "close": [10.2] * 5,
            "vol": [1000] * 5,
            "amount": [10200.0] * 5,
        }
    )


class TestD15FetchQfqKlinesFallback:
    @pytest.mark.asyncio
    async def test_mac_exception_falls_back_to_tdx(self) -> None:
        """MAC 客户端抛异常 → 回退 TDX 数据，不向上抛。"""
        from easy_tdx.web.klines import fetch_qfq_klines

        mac = MagicMock()
        mac.get_stock_kline = AsyncMock(side_effect=RuntimeError("zlib decompress error"))
        tdx = MagicMock()
        tdx.get_security_bars = AsyncMock(return_value=_bars_df())

        df = await fetch_qfq_klines(mac, tdx, "SZ", "000001", "DAY", 0, 100)

        assert len(df) == 5
        assert tdx.get_security_bars.await_count == 1
        mac.get_stock_kline.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mac_empty_df_fallback_unchanged(self) -> None:
        """MAC 返回空 df → 原有回退语义不变。"""
        from easy_tdx.web.klines import fetch_qfq_klines

        mac = MagicMock()
        mac.get_stock_kline = AsyncMock(return_value=pd.DataFrame())
        tdx = MagicMock()
        tdx.get_security_bars = AsyncMock(return_value=_bars_df())

        df = await fetch_qfq_klines(mac, tdx, "SZ", "000001", "DAY", 0, 100)

        assert len(df) == 5
        tdx.get_security_bars.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mac_ok_short_circuits_tdx(self) -> None:
        """MAC 正常返回 → 不触发 TDX（回退只该是兜底）。"""
        from easy_tdx.web.klines import fetch_qfq_klines

        mac = MagicMock()
        mac.get_stock_kline = AsyncMock(return_value=_bars_df())
        tdx = MagicMock()
        tdx.get_security_bars = AsyncMock(side_effect=AssertionError("不应调用 TDX"))

        df = await fetch_qfq_klines(mac, tdx, "SZ", "000001", "DAY", 0, 100)

        assert len(df) == 5
        tdx.get_security_bars.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_mac_none_skips_to_tdx(self) -> None:
        """mac_client=None → 直接走 TDX（既有语义）。"""
        from easy_tdx.web.klines import fetch_qfq_klines

        tdx = MagicMock()
        tdx.get_security_bars = AsyncMock(return_value=_bars_df())

        df = await fetch_qfq_klines(None, tdx, "SZ", "000001", "DAY", 0, 100)

        assert len(df) == 5

    @pytest.mark.asyncio
    async def test_mac_exception_with_tdx_also_failing_raises(self) -> None:
        """MAC 异常且 TDX 也失败 → 最终向上抛 TDX 的异常（不吞错）。"""
        from easy_tdx.web.klines import fetch_qfq_klines

        mac = MagicMock()
        mac.get_stock_kline = AsyncMock(side_effect=RuntimeError("mac down"))
        tdx = MagicMock()
        tdx.get_security_bars = AsyncMock(side_effect=RuntimeError("tdx down"))

        with pytest.raises(RuntimeError, match="tdx down"):
            await fetch_qfq_klines(mac, tdx, "SZ", "000001", "DAY", 0, 100)


# ── D17: 同步 screen pool 路径 top_n 截断 ────────────────────────────────────


class TestD17SyncScreenTopN:
    def _fake_run_screen_out(self, n: int) -> dict[str, object]:
        return {
            "date": "2025-06-02",
            "pool_size": n,
            "results": [
                {
                    "market": "SZ",
                    "code": f"{600000 + i}",
                    "category": "tree",
                    "score": 90.0 - i,
                    "scores": {"tree": 90.0 - i},
                    "indicators": {},
                    "details": {},
                }
                for i in range(n)
            ],
        }

    def test_pool_results_truncated_to_top_n(self, client: TestClient) -> None:
        """run_screen 返回 29 条、top_n=5 → 返回 5 条（按质量分序截断）。"""
        from easy_tdx.web.routers import stock_pick as sp

        with patch.object(
            sp,
            "_screen_run_sync",
            return_value=self._fake_run_screen_out(29),
        ):
            payload = {
                "date": "2025-06-02",
                "top_n": 5,
                "pool": [{"market": "SH", "code": "600519"}],
            }
            resp = client.post("/api/v1/stock-pick/screen", json=payload)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["results"]) == 5
        assert body["total"] == 5

    def test_top_n_larger_than_results_no_pad(self, client: TestClient) -> None:
        """top_n 大于结果数 → 原样返回，不补齐。"""
        from easy_tdx.web.routers import stock_pick as sp

        with patch.object(
            sp,
            "_screen_run_sync",
            return_value=self._fake_run_screen_out(3),
        ):
            payload = {
                "date": "2025-06-02",
                "top_n": 50,
                "pool": [{"market": "SH", "code": "600519"}],
            }
            resp = client.post("/api/v1/stock-pick/screen", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["results"]) == 3
        assert body["total"] == 3

    def test_helper_truncates_payload_directly(self) -> None:
        """_apply_top_n 纯函数语义：截断 results 并同步 total。"""
        from easy_tdx.web.routers.stock_pick import _apply_top_n

        payload: dict[str, object] = {
            "total": 29,
            "results": [{"symbol": f"SZ:60000{i:02d}"} for i in range(29)],
        }
        out = _apply_top_n(payload, 5)
        assert len(out["results"]) == 5  # type: ignore[arg-type]
        assert out["total"] == 5

    def test_local_pool_path_truncated_too(self, client: TestClient) -> None:
        """本地沉淀池路径同样受 top_n 输出上限约束。"""
        local = {
            "date": "2025-06-02",
            "updated_at": "2025-06-02T08:00:00",
            "results": [
                {
                    "symbol": f"SZ:60000{i:02d}",
                    "market": "SZ",
                    "code": f"6000{i:02d}",
                    "category": "tree",
                    "score": 90.0 - i,
                    "scores": {},
                    "details": {},
                    "indicators": {},
                    "data_source": "local",
                }
                for i in range(29)
            ],
        }
        with patch(
            "easy_tdx.fundamental.changying_pool.load_changying_pool",
            return_value=local,
        ):
            resp = client.post(
                "/api/v1/stock-pick/screen",
                json={"date": "2025-06-02", "top_n": 5},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["source"] == "local"
        assert len(body["results"]) == 5
        assert body["total"] == 5

    def test_docstring_documents_top_n_semantics(self) -> None:
        """路由 docstring 注明「top_n 在同步池路径为输出上限」（防回退锚定）。"""
        import inspect

        from easy_tdx.web.routers.stock_pick import stock_pick_screen

        doc = inspect.getdoc(stock_pick_screen) or ""
        assert "top_n 在同步池路径为输出上限" in doc
