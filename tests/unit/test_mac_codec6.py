"""mac/commands symbol_quotes 字段位图路径 + unusual 文本段测试（V399r）。"""

from __future__ import annotations

import struct

from easy_tdx.mac.commands.symbol_quotes import SymbolQuotesCmd
from easy_tdx.mac.commands.unusual import UnusualCmd


class TestSymbolQuotesWithField:
    def test_parse_close_field(self) -> None:
        # 位图 bit4 = CLOSE (<f)
        bitmap = b"\x10" + b"\x00" * 19
        header = struct.pack("<IH", 1, 1)
        row = struct.pack("<H22s44s", 1, "000001".encode("gbk"), "平安银行".encode("gbk"))
        row += struct.pack("<f", 10.5)
        items = SymbolQuotesCmd([(1, "000001")]).parse_response(bitmap + header + row)
        assert len(items) == 1
        assert items[0].code == "000001"
        assert items[0].fields.get("close") == 10.5


class TestUnusualTextSection:
    def test_name_from_text(self) -> None:
        count = 1
        record = struct.pack("<H6sBBBHH", 1, b"000001", 0, 0x04, 0, 100, 0)
        data = struct.pack("<B2fI", 0, 0.05, 0, 0)
        record = record + data + b"\x00" + struct.pack("<BH", 10, 3000)
        record = record.ljust(32, b"\x00")
        body = struct.pack("<H", count) + record + "平安银行".encode("gbk")
        items = UnusualCmd(market=1).parse_response(body)
        assert items[0].name == "平安银行"
