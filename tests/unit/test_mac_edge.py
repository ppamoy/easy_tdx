"""mac/commands 残余边界测试（V399v）。"""

from __future__ import annotations

import struct

from easy_tdx.mac.commands.symbol_bar import SymbolBarCmd
from easy_tdx.mac.commands.unusual import _describe_unusual
from easy_tdx.mac.enums import Period


class TestSymbolBarIntraday:
    def test_intraday_datetime(self) -> None:
        header = b"\x00" * 24 + struct.pack("<HBHI", 0, 0, 1, 0)
        # 分时: time_num 含 HHMM（9:30 → 34200 秒）
        bar = struct.pack("<II7f", 20240115, 34200, 10.0, 10.5, 9.8, 10.4, 10000.0, 100.0, 100.0)
        bars = SymbolBarCmd(1, "000001", Period.MIN_5).parse_response(header + bar)
        assert len(bars) == 1
        assert bars[0].datetime.hour == 9
        assert bars[0].datetime.minute == 30

    def test_invalid_date_skipped(self) -> None:
        header = b"\x00" * 24 + struct.pack("<HBHI", 4, 0, 1, 0)
        bar = struct.pack("<II7f", 18000101, 0, 10.0, 10.5, 9.8, 10.4, 10000.0, 100.0, 100.0)
        bars = SymbolBarCmd(1, "000001", Period.DAILY).parse_response(header + bar)
        assert bars == []


class TestUnusualRemaining:
    def test_0b_flat(self) -> None:
        data = struct.pack("<B2fI", 0, 2.0, 0.0, 0)
        assert _describe_unusual(0x0B, data)[0] == "区间放量平"

    def test_14_unknown_subtype(self) -> None:
        data = struct.pack("<B", 0x00) + struct.pack("<Bff", 0x09, 1.0, 2.0) + b"\x00" * 4
        assert _describe_unusual(0x14, data)[0] == "涨跌停(涨)"
