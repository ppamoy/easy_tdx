"""mac/commands 协议编解码测试五（V399p）。

覆盖 symbol_tick_chart / symbol_quotes / board_members_quotes 的
build_request 与 parse_response（空字段位图路径），离线可测。
"""

from __future__ import annotations

import struct
from datetime import date

import pytest

from easy_tdx.mac.commands.board_members_quotes import BoardMembersQuotesCmd
from easy_tdx.mac.commands.symbol_quotes import SymbolQuotesCmd
from easy_tdx.mac.commands.symbol_tick_chart import SymbolTickChartCmd


class TestSymbolTickChart:
    def test_build_request(self) -> None:
        req = SymbolTickChartCmd(1, "000001", date(2024, 1, 15)).build_request()
        assert isinstance(req, bytes)

    def test_build_today(self) -> None:
        req = SymbolTickChartCmd(1, "000001").build_request()
        assert isinstance(req, bytes)


class TestSymbolQuotes:
    def test_empty_stocks_raises(self) -> None:
        with pytest.raises(ValueError, match="stocks 不能为空"):
            SymbolQuotesCmd([])

    def test_build_request(self) -> None:
        req = SymbolQuotesCmd([(1, "000001")]).build_request()
        assert isinstance(req, bytes)

    def test_parse_no_fields(self) -> None:
        bitmap = b"\x00" * 20
        header = struct.pack("<IH", 1, 1)
        row = struct.pack("<H22s44s", 1, "000001".encode("gbk"), "平安银行".encode("gbk"))
        items = SymbolQuotesCmd([(1, "000001")]).parse_response(bitmap + header + row)
        assert len(items) == 1
        assert items[0].code == "000001"
        assert items[0].name == "平安银行"


class TestBoardMembersQuotes:
    def test_build_request(self) -> None:
        req = BoardMembersQuotesCmd(board_code=881001).build_request()
        assert isinstance(req, bytes)

    def test_parse_no_fields(self) -> None:
        bitmap = b"\x00" * 20
        header = struct.pack("<IH", 1, 1)
        row = struct.pack("<H22s44s", 1, "000001".encode("gbk"), "平安银行".encode("gbk"))
        items = BoardMembersQuotesCmd(881001).parse_response(bitmap + header + row)
        assert len(items) == 1
        assert items[0].code == "000001"
