"""诊断路由测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest


def test_diagnosis_module_imports() -> None:
    """诊断模块可正确导入。"""
    import easy_tdx.web.routers.diagnosis as mod

    assert hasattr(mod, "router")
    assert callable(mod.diagnose_stock)
    assert callable(mod.quick_diagnosis)


def test_diagnosis_router_has_routes() -> None:
    """诊断路由包含预期端点。"""
    from easy_tdx.web.routers.diagnosis import router

    paths = [route.path for route in router.routes]
    assert any("/diagnosis/analyze" in p for p in paths)


@pytest.mark.asyncio
async def test_diagnose_missing_code() -> None:
    """缺少股票代码返回错误。"""
    from easy_tdx.web.schemas import StockIdentifier

    # code 少于 6 位会触发 Pydantic 验证错误（在构造时即抛出）
    with pytest.raises(Exception):
        StockIdentifier(market="SZ", code="123")


@pytest.mark.asyncio
async def test_diagnose_no_data() -> None:
    """无数据时返回错误。"""
    from easy_tdx.web.routers.diagnosis import diagnose_stock
    from easy_tdx.web.schemas import StockIdentifier

    with patch("easy_tdx.web.routers.diagnosis.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get_security_bars = AsyncMock(return_value=None)
        mock_get_client.return_value = mock_client

        req = StockIdentifier(market="SZ", code="000001")
        result = await diagnose_stock(req, mock_client, mac_client=None)
        assert "error" in result


# ── V102 建议回放实证（advice-simulate） ────────────────────────────────────


def _fake_mmd(mmd_type: str, idx: int, low: float = 98.0, high: float = 102.0):
    """构造带有效笔/中枢的模拟买卖点。"""
    from easy_tdx.chanlun.types import MMD, MMDType

    t = {"buy3": MMDType.BUY_3, "sell3": MMDType.SELL_3}[mmd_type]
    mmd = MMD(mmd_type=t, msg=f"{mmd_type}测试")
    mmd.bi = MagicMock()
    mmd.bi.end = MagicMock()
    mmd.bi.end.k = MagicMock()
    mmd.bi.end.k.k_index = idx
    mmd.bi.low = low
    mmd.bi.high = high
    mmd.zs = MagicMock()
    mmd.zs.zg = high + 3.0
    mmd.zs.zd = low - 3.0
    return mmd


def _fake_result(mmds: list) -> MagicMock:
    result = MagicMock()
    result.mmds = mmds
    result.klines = []
    return result


def test_collect_v102_advices_long_and_short() -> None:
    """_collect_v102_advices 提取 3买/3卖 建议并标注方向。"""
    from easy_tdx.web.routers.diagnosis import _collect_v102_advices

    closes = [100.0] * 60
    highs = [101.0] * 60
    lows = [99.0] * 60
    mmds = [_fake_mmd("buy3", 10), _fake_mmd("sell3", 30)]
    result = _fake_result(mmds)

    advices = _collect_v102_advices(result, closes, highs, lows, max_hold=8)

    assert len(advices) == 2
    long_adv = next(a for a in advices if a["direction"] == "long")
    short_adv = next(a for a in advices if a["direction"] == "short")
    assert long_adv["entry_idx"] == 10
    assert long_adv["entry_price"] > 0
    assert long_adv["stop_loss"] < long_adv["entry_price"] < long_adv["take_profit_1"]
    assert short_adv["entry_idx"] == 30
    assert short_adv["stop_loss"] > short_adv["entry_price"] > short_adv["take_profit_1"]


def test_collect_v102_advices_skips_non_3_signals() -> None:
    """非 3买/3卖 信号不生成可回放建议。"""
    from easy_tdx.chanlun.types import MMDType
    from easy_tdx.web.routers.diagnosis import _collect_v102_advices

    closes = [100.0] * 60
    highs = [101.0] * 60
    lows = [99.0] * 60
    buy1 = _fake_mmd("buy3", 10)
    buy1.mmd_type = MMDType.BUY_1
    mmds = [buy1, _fake_mmd("buy3", 20)]
    result = _fake_result(mmds)

    advices = _collect_v102_advices(result, closes, highs, lows, max_hold=8)
    assert len(advices) == 1
    assert advices[0]["entry_idx"] == 20


@pytest.mark.asyncio
async def test_advice_simulate_no_data() -> None:
    """无行情数据时返回错误。"""
    from easy_tdx.web.routers.diagnosis import advice_simulate
    from easy_tdx.web.schemas import AdviceSimulateRequest

    with patch("easy_tdx.web.routers.diagnosis.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get_security_bars = AsyncMock(return_value=None)
        mock_get_client.return_value = mock_client

        req = AdviceSimulateRequest(market="SZ", code="000001")
        result = await advice_simulate(req, mock_client, mac_client=None)
        assert "error" in result


@pytest.mark.asyncio
async def test_advice_simulate_insufficient_data() -> None:
    """行情数据不足 30 根时返回错误。"""
    from easy_tdx.web.routers.diagnosis import advice_simulate
    from easy_tdx.web.schemas import AdviceSimulateRequest

    small = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=10, freq="D"),
            "open": [10.0] * 10,
            "close": [10.0] * 10,
            "high": [10.5] * 10,
            "low": [9.5] * 10,
            "vol": [1e6] * 10,
        }
    )
    with patch("easy_tdx.web.routers.diagnosis.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get_security_bars = AsyncMock(return_value=small)
        mock_get_client.return_value = mock_client

        req = AdviceSimulateRequest(market="SZ", code="000001")
        result = await advice_simulate(req, mock_client, mac_client=None)
        assert "error" in result


@pytest.mark.asyncio
async def test_advice_simulate_no_3_signals() -> None:
    """行情无 3买/3卖 信号时返回提示。"""
    from easy_tdx.web.routers.diagnosis import advice_simulate
    from easy_tdx.web.schemas import AdviceSimulateRequest

    df = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=120, freq="D"),
            "open": [10.0] * 120,
            "close": [10.0] * 120,
            "high": [10.5] * 120,
            "low": [9.5] * 120,
            "vol": [1e6] * 120,
        }
    )
    with (
        patch("easy_tdx.web.routers.diagnosis.get_client") as mock_get_client,
        patch("easy_tdx.chanlun.ChanlunAnalyser") as mock_analyser,
    ):
        mock_client = AsyncMock()
        mock_client.get_security_bars = AsyncMock(return_value=df)
        mock_get_client.return_value = mock_client
        mock_analyser.return_value.process_klines.return_value = _fake_result([])

        req = AdviceSimulateRequest(market="SZ", code="000001")
        result = await advice_simulate(req, mock_client, mac_client=None)
        assert result["advice_count"] == 0
        assert result["report"] is None
        assert "未发现" in result["message"]


@pytest.mark.asyncio
async def test_advice_simulate_full_path() -> None:
    """有 3买 信号时返回回放报告。"""
    from easy_tdx.web.routers.diagnosis import advice_simulate
    from easy_tdx.web.schemas import AdviceSimulateRequest

    closes = [100.0] * 120
    highs = [101.0] * 120
    lows = [99.0] * 120
    df = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=120, freq="D"),
            "open": closes,
            "close": closes,
            "high": highs,
            "low": lows,
            "vol": [1e6] * 120,
        }
    )

    class _FakeKline:
        def __init__(self, close: float, high: float, low: float) -> None:
            self.open = close
            self.close = close
            self.high = high
            self.low = low

    result = MagicMock()
    result.mmds = [_fake_mmd("buy3", 10)]
    result.klines = [_FakeKline(c, h, lo) for c, h, lo in zip(closes, highs, lows)]

    with (
        patch("easy_tdx.web.routers.diagnosis.get_client") as mock_get_client,
        patch("easy_tdx.chanlun.ChanlunAnalyser") as mock_analyser,
    ):
        mock_client = AsyncMock()
        mock_client.get_security_bars = AsyncMock(return_value=df)
        mock_get_client.return_value = mock_client
        mock_analyser.return_value.process_klines.return_value = result

        req = AdviceSimulateRequest(market="SZ", code="000001")
        resp = await advice_simulate(req, mock_client, mac_client=None)
        assert resp["advice_count"] == 1
        assert resp["report"]["count"] == 1
        assert "avg_return" in resp["report"]
