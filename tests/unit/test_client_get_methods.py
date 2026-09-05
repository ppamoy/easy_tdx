"""client.py get_* 编排路径测试（V404）。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd

from easy_tdx.client import TdxClient
from easy_tdx.models.enums import Market


def _client(return_value) -> TdxClient:
    c = object.__new__(TdxClient)
    c._conn = MagicMock()
    c._host = "1.2.3.4"
    c._port = 7709
    c._auto_reconnect = False
    c._execute = MagicMock(return_value=return_value)
    return c


class TestGetSecurityCount:
    def test_passthrough(self) -> None:
        c = _client(123)
        assert c.get_security_count(Market.SH) == 123


class TestGetSecurityList:
    def test_empty(self) -> None:
        c = _client([])
        df = c.get_security_list(Market.SH, 0)
        assert isinstance(df, pd.DataFrame)


class TestGetXdxrFinanceCompany:
    def test_xdxr(self) -> None:
        c = _client([])
        assert isinstance(c.get_xdxr_info(Market.SH, "600000"), pd.DataFrame)

    def test_finance(self) -> None:
        c = _client([])
        assert isinstance(c.get_finance_info(Market.SH, "600000"), pd.DataFrame)

    def test_company_category(self) -> None:
        c = _client([])
        assert isinstance(c.get_company_info_category(Market.SH, "600000"), pd.DataFrame)

    def test_company_content(self) -> None:
        c = _client("文本")
        assert c.get_company_info_content(Market.SH, "600000", "f.txt", 0, 100) == "文本"


class TestGetMarketStat:
    def test_market_stat(self) -> None:
        q0 = SimpleNamespace(price=10.0, open=20.0, low=30.0, high=100.0, amount=1e6, vol=2e6)
        q1 = SimpleNamespace(price=3.0, open=0, low=0, high=0, amount=0, vol=0)
        q2 = SimpleNamespace(price=5.0, open=7.0, low=0, high=0, amount=0, vol=0)
        c = _client([q0, q1, q2])
        df = c.get_market_stat()
        assert df.iloc[0]["total_count"] == 1000
        assert df.iloc[0]["up_count"] == 100
        assert df.iloc[0]["limit_up_count"] == 50

    def test_market_stat_raises_when_empty(self) -> None:
        c = _client([])
        c._auto_reconnect = False
        import pytest

        with pytest.raises(RuntimeError, match="无法获取市场统计数据"):
            c.get_market_stat()
