"""mac/client.py get_board_ranking 测试（V409）。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from easy_tdx.mac.client import MacClient


def _client() -> MacClient:
    c = object.__new__(MacClient)
    c._conn = MagicMock()
    c._host = "1.2.3.4"
    c._port = 7709
    c._auto_reconnect = False
    return c


class TestGetBoardRanking:
    def test_invalid_sort(self) -> None:
        c = _client()
        with pytest.raises(ValueError, match="sort_by 必须是"):
            c.get_board_ranking(sort_by="nope")

    def test_empty_boards(self) -> None:
        c = _client()
        c.get_board_list = MagicMock(return_value=pd.DataFrame())
        df = c.get_board_ranking()
        assert df.empty

    def test_full_ranking(self) -> None:
        c = _client()
        boards = pd.DataFrame(
            [
                {"code": "881001", "name": "板块A", "price": 10.5, "pre_close": 10.0},
                {"code": "881002", "name": "板块B", "price": 9.5, "pre_close": 10.0},
            ]
        )
        c.get_board_list = MagicMock(return_value=boards)
        c.get_board_summary = MagicMock(
            side_effect=[
                {
                    "amount": 100.0,
                    "vol": 1000,
                    "main_net_amount": 10.0,
                    "up_count": 5,
                    "down_count": 3,
                    "member_count": 8,
                },
                {
                    "amount": 200.0,
                    "vol": 2000,
                    "main_net_amount": 20.0,
                    "up_count": 2,
                    "down_count": 6,
                    "member_count": 8,
                },
            ]
        )
        df = c.get_board_ranking(top_n=10, sort_by="amount")
        assert len(df) == 2
        assert df.iloc[0]["code"] == "881002"  # amount 大者在前（降序）


class TestGetStockQuotes:
    def test_empty(self) -> None:
        c = _client()
        c._execute = MagicMock(return_value=[])
        df = c.get_stock_quotes([(1, "000001")])
        assert isinstance(df, pd.DataFrame)
