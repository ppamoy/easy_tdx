"""诊断路由测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

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
        result = await diagnose_stock(req, mock_client)
        assert "error" in result
