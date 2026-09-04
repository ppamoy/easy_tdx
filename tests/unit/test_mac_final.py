"""mac/commands 最后残余路径测试（V399w）。"""

from __future__ import annotations

import struct

from easy_tdx.mac.commands.board_members_quotes import BoardMembersQuotesCmd
from easy_tdx.mac.commands.symbol_capital_flow import SymbolCapitalFlowCmd, _to_float
from easy_tdx.mac.commands.unusual import UnusualCmd


class TestCapitalFlowEdge:
    def test_to_float_invalid(self) -> None:
        assert _to_float("x") == 0.0
        assert _to_float(None) == 0.0

    def test_parse_too_short_list(self) -> None:
        header = b"\x00" * 27
        body = header + b"[[100.0]]"
        assert SymbolCapitalFlowCmd(1, "000001").parse_response(body) is None


class TestBoardMembersQuotesFields:
    def test_parse_with_close_field(self) -> None:
        bitmap = b"\x10" + b"\x00" * 19  # bit4 = CLOSE
        header = struct.pack("<IH", 1, 1)
        row = struct.pack("<H22s44s", 1, "000001".encode("gbk"), "平安银行".encode("gbk"))
        row += struct.pack("<f", 10.5)
        items = BoardMembersQuotesCmd(881001).parse_response(bitmap + header + row)
        assert len(items) == 1
        assert items[0].fields.get("close") == 10.5


class TestUnusualTextMulti:
    def test_multiple_names(self) -> None:
        count = 1
        record = struct.pack("<H6sBBBHH", 1, b"000001", 0, 0x04, 0, 100, 0)
        data = struct.pack("<B2fI", 0, 0.05, 0, 0)
        record = record + data + b"\x00" + struct.pack("<BH", 10, 3000)
        record = record.ljust(32, b"\x00")
        body = struct.pack("<H", count) + record + "平安银行,招商银行".encode("gbk")
        items = UnusualCmd(market=1).parse_response(body)
        assert items[0].name == "平安银行"
