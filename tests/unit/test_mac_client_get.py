"""mac/client.py get_* 编排路径测试（V406）。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from easy_tdx.mac.client import MacClient


def _client(returns) -> MacClient:
    c = object.__new__(MacClient)
    c._conn = MagicMock()
    c._host = "1.2.3.4"
    c._port = 7709
    c._auto_reconnect = False
    c._execute = MagicMock(return_value=returns)
    return c


class TestMacGetMethods:
    def test_symbol_info(self) -> None:
        c = _client([])
        assert isinstance(c.get_symbol_info(1, "000001"), pd.DataFrame)

    def test_belong_board(self) -> None:
        c = _client([])
        assert isinstance(c.get_belong_board(1, "000001"), pd.DataFrame)

    def test_capital_flow_none(self) -> None:
        c = _client(None)
        df = c.get_capital_flow(1, "000001")
        assert df.empty

    def test_auction(self) -> None:
        c = _client([])
        assert isinstance(c.get_auction(1, "000001"), pd.DataFrame)

    def test_unusual(self) -> None:
        c = _client([])
        assert isinstance(c.get_unusual(1), pd.DataFrame)

    def test_server_info(self) -> None:
        c = _client([])
        assert isinstance(c.get_server_info(), pd.DataFrame)

    def test_kline_offset(self) -> None:
        c = _client([])
        assert isinstance(c.get_kline_offset(), pd.DataFrame)
