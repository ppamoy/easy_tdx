"""mac/client.py qfq 重算 + 逐笔分页测试（V412）。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

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


class TestLocalRecomputeQfq:
    def test_no_xdxr_returns_original(self) -> None:
        c = _client()
        c._fetch_xdxr_records = MagicMock(return_value=None)
        df = pd.DataFrame({"close": [10.0]})
        out = c._local_recompute_qfq(df, 1, "000001")
        assert out is df


class TestGetTransactions:
    def test_empty(self) -> None:
        c = _client()
        c._execute = MagicMock(return_value=[])
        df = c.get_transactions(1, "000001")
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_pagination_stops(self) -> None:
        from datetime import time

        from easy_tdx.mac.models import MacTransaction

        c = _client()
        item = MacTransaction(time=time(9, 30), price=10.0, vol=100, trade_count=5, bs_flag=0)
        # 第一页 1 条（< page_size=1000），停止
        c._execute = MagicMock(return_value=[item])
        df = c.get_transactions(1, "000001", count=10)
        assert isinstance(df, pd.DataFrame)
