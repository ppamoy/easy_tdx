"""mac/commands/unusual.py 补充分支测试（V399q）。"""

from __future__ import annotations

import struct

from easy_tdx.mac.commands.unusual import _describe_unusual


def _data(*vals):
    return struct.pack("<B2fI", *vals)


def _type14(sub: int) -> bytes:
    return struct.pack("<B", 0x00) + struct.pack("<Bff", sub, 1.0, 2.0) + b"\x00" * 4


class TestRemainingBranches:
    def test_05(self) -> None:
        assert _describe_unusual(0x05, _data(0, 0.05, 0, 0))[0] == "加速下跌"

    def test_06(self) -> None:
        assert _describe_unusual(0x06, _data(0, 0.05, 0, 0))[0] == "低位反弹"

    def test_07(self) -> None:
        assert _describe_unusual(0x07, _data(0, 0.05, 0, 0))[0] == "高位回落"

    def test_08(self) -> None:
        assert _describe_unusual(0x08, _data(0, 0.05, 0, 0))[0] == "撑杆跳高"

    def test_09(self) -> None:
        assert _describe_unusual(0x09, _data(0, 0.05, 0, 0))[0] == "平台跳水"

    def test_0b(self) -> None:
        assert _describe_unusual(0x0B, _data(0, 2.0, 0.5, 0))[0] == "区间放量涨"

    def test_0c(self) -> None:
        assert _describe_unusual(0x0C, _data(0, 0, 0, 0))[0] == "区间缩量"

    def test_10(self) -> None:
        assert _describe_unusual(0x10, _data(0, 0, 0, 100))[0] == "大单托盘"

    def test_11(self) -> None:
        assert _describe_unusual(0x11, _data(0, 1.0, 2.0, 0))[0] == "大单压盘"

    def test_12(self) -> None:
        assert _describe_unusual(0x12, _data(0, 0, 0, 0))[0] == "大单锁盘"

    def test_13(self) -> None:
        assert _describe_unusual(0x13, _data(0, 1.0, 2.0, 0))[0] == "竞价试买"

    def test_14_subtype_01(self) -> None:
        assert _describe_unusual(0x14, _type14(0x01))[0] == "逼近涨停"

    def test_14_subtype_04(self) -> None:
        assert _describe_unusual(0x14, _type14(0x04))[0] == "封涨大减"

    def test_14_subtype_05(self) -> None:
        assert _describe_unusual(0x14, _type14(0x05))[0] == "打开涨停"
