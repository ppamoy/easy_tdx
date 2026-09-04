"""mac/commands/unusual.py 协议编解码与纯函数测试（V399g）。

覆盖 _describe_unusual 全部异动类型分支 + UnusualCmd.build_request /
parse_response 编解码（离线，不触网）。
"""

from __future__ import annotations

import struct

from easy_tdx.mac.commands.unusual import UnusualCmd, _describe_unusual


def _data(*vals, fmt="<B2fI"):
    return struct.pack(fmt, *vals)


class TestDescribeUnusual:
    def test_short_data(self) -> None:
        assert _describe_unusual(0x03, b"") == ("", "")

    def test_type_03_buy(self) -> None:
        desc, val = _describe_unusual(0x03, _data(0x00, 1.5, 2.5, 100))
        assert desc == "主力买入"
        assert val == "1.50/2.50"

    def test_type_04(self) -> None:
        desc, val = _describe_unusual(0x04, _data(0, 0.05, 0, 0))
        assert desc == "加速拉升"
        assert val == "5.00%"

    def test_type_0a(self) -> None:
        desc, val = _describe_unusual(0x0A, _data(0, 0.03, 0, 0))
        assert desc == "单笔冲涨"
        assert val == "3.00%"

    def test_type_14_subtype(self) -> None:
        data = struct.pack("<B", 0x00) + struct.pack("<Bff", 0x02, 1.0, 2.0) + b"\x00" * 4
        desc, val = _describe_unusual(0x14, data)
        assert desc == "封涨停板"
        assert val == "1.00/2.00"

    def test_unknown_type(self) -> None:
        desc, val = _describe_unusual(0xFF, _data(0, 0, 0, 0))
        assert desc == "异动类型0xff"
        assert val == ""


class TestUnusualCmd:
    def test_build_request(self) -> None:
        cmd = UnusualCmd(market=1, start=0, count=10)
        req = cmd.build_request()
        assert isinstance(req, bytes)
        assert len(req) > 0

    def test_count_capped(self) -> None:
        cmd = UnusualCmd(market=0, start=0, count=9999)
        assert cmd._count == 600

    def test_parse_response(self) -> None:
        # count=1, one 32-byte record + text section "平安银行"
        count = 1
        record = struct.pack("<H6sBBBHH", 1, b"000001", 0, 0x04, 0, 100, 0)
        # data section for _describe_unusual at offset+15..+28 (13 bytes)
        data = _data(0, 0.05, 0, 0)
        record = record + data + b"\x00" + struct.pack("<BH", 10, 3000)
        record = record.ljust(32, b"\x00")
        body = struct.pack("<H", count) + record + "平安银行".encode("gbk")
        items = UnusualCmd(market=1).parse_response(body)
        assert len(items) == 1
        assert items[0].code == "000001"
        assert items[0].name == "平安银行"
        assert items[0].desc == "加速拉升"
