"""mac/commands/symbol_belong_board.py 协议编解码测试（V399l）。"""

from __future__ import annotations

import json

from easy_tdx.mac.commands.symbol_belong_board import (
    SymbolBelongBoardCmd,
    _to_float,
    _to_int,
)


class TestSafeConverters:
    def test_to_float(self) -> None:
        assert _to_float("3.5") == 3.5
        assert _to_float(None) == 0.0
        assert _to_float("x") == 0.0

    def test_to_int(self) -> None:
        assert _to_int("7") == 7
        assert _to_int(None) == 0
        assert _to_int("x") == 0


class TestSymbolBelongBoardCmd:
    def test_build_request(self) -> None:
        req = SymbolBelongBoardCmd(market=1, code="000001").build_request()
        assert isinstance(req, bytes)
        assert len(req) > 0

    def test_parse_short(self) -> None:
        assert SymbolBelongBoardCmd(1, "000001").parse_response(b"\x00" * 10) == []

    def test_parse_full(self) -> None:
        header = b"\x00" * 27
        rows = [[1, 0, "TGN", "半导体", "10.5", "10.0", 0, 0, 0]]
        body = header + json.dumps(rows).encode("gbk")
        items = SymbolBelongBoardCmd(1, "000001").parse_response(body)
        assert len(items) == 1
        assert items[0].board_name == "半导体"
        assert items[0].close == 10.5

    def test_parse_empty_list(self) -> None:
        body = b"\x00" * 27 + b"[]"
        assert SymbolBelongBoardCmd(1, "000001").parse_response(body) == []
