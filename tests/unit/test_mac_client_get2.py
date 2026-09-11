"""mac/client.py get_* 编排路径测试二（V407）。"""

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


class TestMacGetMethods2:
    def test_chart_sampling(self) -> None:
        c = _client([[10.0, 11.0]])
        df = c.get_chart_sampling(1, "000001")
        assert list(df["price"]) == [10.0, 11.0]

    def test_board_list_empty(self) -> None:
        c = _client([])
        df = c.get_board_list()
        assert isinstance(df, pd.DataFrame)

    def test_board_list_pagination_stops(self) -> None:
        # 第一页 1 条（< page_size），后续不请求
        c = _client([[]])  # 空列表 -> 第一页返回空
        df = c.get_board_list(count=10)
        assert isinstance(df, pd.DataFrame)

    def test_stock_quotes_list_last_batch_page_size(self) -> None:
        """V553: count 非 80 整数倍时最后一批 page_size 不超过剩余量（不超取）。"""
        calls: list[int] = []

        def fake_execute(cmd):
            calls.append(cmd._page_size)
            return [
                SimpleNamespace(market="SH", code="600000", name="x", fields={})
            ] * cmd._page_size

        c = _client([])
        c._execute = MagicMock(side_effect=fake_execute)
        c.get_stock_quotes_list(0, count=100)
        assert calls == [80, 20]

    def test_file_meta(self) -> None:
        c = _client([])
        assert isinstance(c.get_file_meta("gpcw.zip"), pd.DataFrame)

    def test_download_file_chunk(self) -> None:
        c = _client(b"chunk")
        assert c.download_file_chunk("f.zip", 1, 0, 100) == b"chunk"

    def test_download_file_auto_size(self) -> None:
        # meta.size=3, 然后 chunk 返回 b"abc" 再返回空
        meta = SimpleNamespace(size=3)
        c = _client([meta, b"abc"])
        assert c.download_file("f.zip") == bytearray(b"abc")

    def test_goods_list(self) -> None:
        c = _client([])
        assert isinstance(c.get_goods_list(0), pd.DataFrame)
