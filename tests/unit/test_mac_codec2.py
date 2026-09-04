"""mac/commands 协议编解码测试二（V399m）。

覆盖 symbol_capital_flow / symbol_auction / chart_sampling 的
build_request / parse_response，离线可测。
"""

from __future__ import annotations

import json
import struct

from easy_tdx.mac.commands.chart_sampling import ChartSamplingCmd
from easy_tdx.mac.commands.symbol_auction import SymbolAuctionCmd
from easy_tdx.mac.commands.symbol_capital_flow import SymbolCapitalFlowCmd


class TestSymbolCapitalFlow:
    def test_build_request(self) -> None:
        req = SymbolCapitalFlowCmd(1, "000001").build_request()
        assert isinstance(req, bytes)
        assert len(req) > 0

    def test_parse_short(self) -> None:
        assert SymbolCapitalFlowCmd(1, "000001").parse_response(b"\x00" * 10) is None

    def test_parse_full(self) -> None:
        header = b"\x00" * 27
        rows = [[100.0, 50.0, 30.0, 20.0], [200.0, 150.0, 60.0, 40.0, 10.0, 5.0]]
        body = header + json.dumps(rows).encode("gbk")
        flow = SymbolCapitalFlowCmd(1, "000001").parse_response(body)
        assert flow is not None
        assert flow.main_in == 100.0
        assert flow.main_net == 50.0
        assert flow.large_net == 40.0
        assert flow.mid_net == 10.0


class TestSymbolAuction:
    def test_build_request(self) -> None:
        req = SymbolAuctionCmd(1, "000001").build_request()
        assert isinstance(req, bytes)

    def test_parse_empty(self) -> None:
        # count=0
        body = struct.pack("<H22sI8x", 1, "000001".encode("gbk"), 0)
        items = SymbolAuctionCmd(1, "000001").parse_response(body)
        assert items == []

    def test_parse_item(self) -> None:
        header = struct.pack("<H22sI8x", 1, "000001".encode("gbk"), 1)
        item = struct.pack("<IfIi", 9 * 3600 + 25 * 60, 10.5, 100, 200)
        body = header + item
        items = SymbolAuctionCmd(1, "000001").parse_response(body)
        assert len(items) == 1
        assert items[0].price == 10.5


class TestChartSampling:
    def test_build_request(self) -> None:
        req = ChartSamplingCmd(market=1, code="000001").build_request()
        assert isinstance(req, bytes)

    def test_parse_short(self) -> None:
        assert ChartSamplingCmd(1, "000001").parse_response(b"\x00" * 10) == []

    def test_parse_prices(self) -> None:
        header = b"\x00" * 40 + struct.pack("<H", 2)
        p1 = struct.pack("<f", 10.5)
        p2 = struct.pack("<f", 11.5)
        body = header + p1 + p2
        prices = ChartSamplingCmd(1, "000001").parse_response(body)
        assert prices == [10.5, 11.5]
