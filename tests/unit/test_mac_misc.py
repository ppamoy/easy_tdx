"""mac/commands 零星边界测试（V399x）。"""

from __future__ import annotations

import json
import struct

from easy_tdx.mac.commands.kline_offset import KlineOffsetCmd
from easy_tdx.mac.commands.symbol_auction import SymbolAuctionCmd
from easy_tdx.mac.commands.symbol_belong_board import SymbolBelongBoardCmd


class TestKlineOffset:
    def test_short_body(self) -> None:
        info = KlineOffsetCmd().parse_response(b"\x00" * 4)
        assert info.total == 0
        assert info.returned == 0

    def test_full_body(self) -> None:
        body = struct.pack(">I", 100) + struct.pack("<I", 50)
        info = KlineOffsetCmd().parse_response(body)
        assert info.total == 100
        assert info.returned == 50


class TestSymbolAuction:
    def test_truncated_record(self) -> None:
        header = struct.pack("<H22sI8x", 1, "000001".encode("gbk"), 2)
        items = SymbolAuctionCmd(1, "000001").parse_response(header + b"\x00" * 10)
        assert items == []


class TestSymbolBelongBoard:
    def test_invalid_row_length_skipped(self) -> None:
        header = b"\x00" * 27
        rows = [[1, 0, "TGN", "半导体", "10.5", "10.0", 0]]
        body = header + json.dumps(rows).encode("gbk")
        items = SymbolBelongBoardCmd(1, "000001").parse_response(body)
        assert items == []
