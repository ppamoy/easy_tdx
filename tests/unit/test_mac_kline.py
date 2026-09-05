"""mac/client.py K线分页编排测试（V410）。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from easy_tdx.mac.client import MacClient
from easy_tdx.mac.enums import Adjust, Period


def _client() -> MacClient:
    c = object.__new__(MacClient)
    c._conn = MagicMock()
    c._host = "1.2.3.4"
    c._port = 7709
    c._auto_reconnect = False
    c._timeout = 5.0
    c._xdxr_cache = {}
    return c


class TestFetchKlinePages:
    def test_empty(self) -> None:
        c = _client()
        c._execute = MagicMock(return_value=[])
        assert c._fetch_kline_pages(1, "000001", Period.DAILY, 0, 100, 1, Adjust.NONE) == []

    def test_pagination_stops(self) -> None:
        c = _client()
        # 第一页 1 条（< page_size=700），停止
        c._execute = MagicMock(return_value=[object()])
        bars = c._fetch_kline_pages(1, "000001", Period.DAILY, 0, 100, 1, Adjust.NONE)
        assert len(bars) == 1


class TestGetStockKline:
    def test_empty(self) -> None:
        c = _client()
        c._fetch_kline_pages = MagicMock(return_value=[])
        df = c.get_stock_kline(1, "000001")
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_with_indicators_empty(self) -> None:
        c = _client()
        c.get_stock_kline = MagicMock(return_value=pd.DataFrame())
        df = c.get_stock_kline_with_indicators(1, "000001", ["MACD"])
        assert df.empty
