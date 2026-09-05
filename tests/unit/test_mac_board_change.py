"""mac/client.py get_board_change_ranking 测试（V411）。"""

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
    c._timeout = 5.0
    c._xdxr_cache = {}
    return c


class TestGetBoardChangeRanking:
    def test_invalid_days(self) -> None:
        c = _client()
        with pytest.raises(ValueError, match="days 必须"):
            c.get_board_change_ranking(days=0)

    def test_empty_boards(self) -> None:
        c = _client()
        c.get_board_list = MagicMock(return_value=pd.DataFrame())
        df = c.get_board_change_ranking()
        assert df.empty
        assert "change_pct" in df.columns

    def test_full_ranking(self) -> None:
        c = _client()
        boards = pd.DataFrame([{"code": "881001", "name": "板块A", "market": 1}])
        kline = pd.DataFrame(
            {
                "datetime": pd.to_datetime(["2024-01-01", "2024-01-05", "2024-01-10"]),
                "close": [10.0, 10.5, 11.0],
            }
        )
        c.get_board_list = MagicMock(return_value=boards)
        c.get_stock_kline = MagicMock(return_value=kline)
        df = c.get_board_change_ranking(days=2)
        assert len(df) == 1
        assert df.iloc[0]["code"] == "881001"
        assert df.iloc[0]["change_pct"] == pytest.approx(10.0)
