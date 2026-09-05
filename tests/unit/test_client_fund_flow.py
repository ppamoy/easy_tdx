"""client.py fund_flow 编排测试（V413）。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from easy_tdx.client import TdxClient
from easy_tdx.models.enums import Market


def _client() -> TdxClient:
    c = object.__new__(TdxClient)
    c._conn = MagicMock()
    c._host = "1.2.3.4"
    c._port = 7709
    c._auto_reconnect = False
    c._execute = MagicMock(return_value=[])
    return c


class TestGetFundFlow:
    def test_empty_records(self) -> None:
        c = _client()
        df = c.get_fund_flow(Market.SH, "600000")
        assert isinstance(df, pd.DataFrame)


class TestGetHistoryFundFlow:
    def test_empty(self) -> None:
        c = _client()
        c._fetch_fund_flow_records = MagicMock(return_value=[])
        df = c.get_history_fund_flow(Market.SH, "600000", 0, 100)
        assert isinstance(df, pd.DataFrame)
        assert df.empty


class TestGetMinuteTime:
    def test_empty(self) -> None:
        c = _client()
        df = c.get_minute_time_data(Market.SH, "600000")
        assert isinstance(df, pd.DataFrame)

    def test_history_empty(self) -> None:
        c = _client()
        df = c.get_history_minute_time_data(Market.SH, "600000", 20240115)
        assert isinstance(df, pd.DataFrame)
