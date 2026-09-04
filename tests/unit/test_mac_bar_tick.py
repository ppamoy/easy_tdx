"""mac/commands symbol_bar + symbol_tick_chart 解析测试（V399u）。"""

from __future__ import annotations

import struct
from datetime import date

import pytest

from easy_tdx.mac.commands.symbol_bar import SymbolBarCmd
from easy_tdx.mac.commands.symbol_tick_chart import SymbolTickChartCmd
from easy_tdx.mac.enums import Period


class TestSymbolBar:
    def test_build_request(self) -> None:
        req = SymbolBarCmd(1, "000001", Period.DAILY).build_request()
        assert isinstance(req, bytes)

    def test_parse_daily(self) -> None:
        header = b"\x00" * 24 + struct.pack("<HBHI", 4, 0, 1, 0)
        bar = struct.pack("<II7f", 20240115, 0, 10.0, 10.5, 9.8, 10.4, 10000.0, 100.0, 100.0)
        bars = SymbolBarCmd(1, "000001", Period.DAILY).parse_response(header + bar)
        assert len(bars) == 1
        assert bars[0].close == pytest.approx(10.4)


class TestSymbolTickChart:
    def test_parse_with_tick(self) -> None:
        count = 1
        header = struct.pack("<H22sIBfH", 1, "000001".encode("gbk"), 20240115, 0, 10.0, count)
        tick = struct.pack("<HffIf", 9 * 60 + 30, 10.5, 10.4, 100, 0.0)
        tail = (
            struct.pack("<44s", "平安银行".encode("gbk"))
            + struct.pack("<BHf", 2, 0, 0.0)
            + b"\x00" * 5
            + struct.pack("<2I", 0, 0)
            + struct.pack("<5f", 9.9, 10.0, 10.5, 9.8, 10.4)
            + struct.pack("<fIf12s", 0.0, 1000, 10000.0, b"")
            + struct.pack("<2f", 0.1, 10.4)
            + struct.pack("<I", 0)
        )
        chart = SymbolTickChartCmd(1, "000001", date(2024, 1, 15)).parse_response(
            header + tick + tail
        )
        assert len(chart.charts) == 1
        assert chart.charts[0].price == pytest.approx(10.5)
