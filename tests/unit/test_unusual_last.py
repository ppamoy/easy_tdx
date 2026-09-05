"""mac/commands unusual 最后残余分支测试（V399y）。"""

from __future__ import annotations

import struct

from easy_tdx.mac.commands.unusual import UnusualCmd


class TestUnusualLast:
    def test_parse_truncated_records(self) -> None:
        # count=5 但 body 只够 1 条记录 → 循环 break
        count = 5
        record = struct.pack("<H6sBBBHH", 1, b"000001", 0, 0x04, 0, 100, 0)
        data = struct.pack("<B2fI", 0, 0.05, 0, 0)
        record = record + data + b"\x00" + struct.pack("<BH", 10, 3000)
        record = record.ljust(32, b"\x00")
        body = struct.pack("<H", count) + record + "平安银行".encode("gbk")
        items = UnusualCmd(market=1).parse_response(body)
        assert len(items) == 1
