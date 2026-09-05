"""mac/client.py get_* 编排路径测试三（V408）。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd

from easy_tdx.mac.client import MacClient


def _client(returns) -> MacClient:
    c = object.__new__(MacClient)
    c._conn = MagicMock()
    c._host = "1.2.3.4"
    c._port = 7709
    c._auto_reconnect = False
    if isinstance(returns, list) and len(returns) > 1:
        c._execute = MagicMock(side_effect=returns)
    else:
        c._execute = MagicMock(
            return_value=returns[0] if isinstance(returns, list) and returns else returns
        )
    return c


class TestMacGetMethods3:
    def test_tick_chart_empty(self) -> None:
        chart = SimpleNamespace(charts=[])
        c = _client(chart)
        df = c.get_tick_chart(1, "000001", 20240115)
        assert isinstance(df, pd.DataFrame)

    def test_tick_charts_empty(self) -> None:
        chart = SimpleNamespace(charts=[])
        c = _client(chart)
        df = c.get_tick_charts(1, "000001")
        assert isinstance(df, pd.DataFrame)

    def test_board_members_empty(self) -> None:
        c = _client([])
        df = c.get_board_members("881001")
        assert isinstance(df, pd.DataFrame)

    def test_board_summary(self) -> None:
        # mock get_board_members 返回一个含 close/pre_close/vol 的小 df
        df = pd.DataFrame({"close": [10.0, 9.0], "pre_close": [9.5, 9.5], "vol": [100, 200]})
        c = _client([])
        c.get_board_members = MagicMock(return_value=df)
        summary = c.get_board_summary("881001")
        assert summary["member_count"] == 2
        assert summary["up_count"] == 1
        assert summary["vol"] == 300

    def test_transactions_empty(self) -> None:
        c = _client([])
        df = c.get_transactions(1, "000001")
        assert isinstance(df, pd.DataFrame)
