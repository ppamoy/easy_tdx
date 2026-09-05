"""client.py get_* 编排路径测试二（V405）。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from easy_tdx.client import TdxClient
from easy_tdx.models.enums import Market


def _client(returns) -> TdxClient:
    c = object.__new__(TdxClient)
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


class TestGetSecurityQuotes:
    def test_empty(self) -> None:
        c = _client([])
        df = c.get_security_quotes([(Market.SH, "600000")])
        assert isinstance(df, pd.DataFrame)


class TestGetBlockInfo:
    def test_zero_size(self) -> None:
        # meta 返回 size=0，无需分块
        c = _client([(0, "hash")])
        df = c.get_block_info("block_zs.dat")
        assert isinstance(df, pd.DataFrame)

    def test_chunked(self) -> None:
        # meta size=100，第一个 chunk 返回空 → break
        c = _client([(100, "hash"), b""])
        df = c.get_block_info("block_zs.dat")
        assert isinstance(df, pd.DataFrame)


class TestGetReportFile:
    def test_empty(self) -> None:
        c = _client([b""])
        assert c.get_report_file("base_info.zip") == b""

    def test_one_chunk(self) -> None:
        c = _client([b"hello", b""])
        assert c.get_report_file("base_info.zip") == b"hello"


class TestGetPriceLimits:
    def test_no_limit_window_zero(self) -> None:
        # 上市满期标的：no_limit_window_days == 0，不查 K 线
        c = _client([])
        up, down = c.get_price_limits(Market.SH, "600000", "浦发银行", 10.0)
        assert up is not None and down is not None
