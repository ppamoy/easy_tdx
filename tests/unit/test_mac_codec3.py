"""mac/commands 协议编解码测试三（V399n）。

覆盖 board_list / symbol_info / goods_list 的 build_request / parse_response，
离线可测。
"""

from __future__ import annotations

import struct

import pytest

from easy_tdx.mac.commands.board_list import BoardListCmd
from easy_tdx.mac.commands.goods_list import GoodsListCmd
from easy_tdx.mac.commands.symbol_info import SymbolInfoCmd


class TestBoardList:
    def test_build_request(self) -> None:
        req = BoardListCmd().build_request()
        assert isinstance(req, bytes)

    def test_parse_empty(self) -> None:
        body = struct.pack("<HH", 0, 0)
        assert BoardListCmd().parse_response(body) == []

    def test_parse_record(self) -> None:
        record_fmt = "<H6s16s44sfffH6s16s44sfff"
        rec = struct.pack(
            record_fmt,
            0,
            "TGN".encode("gbk"),
            b"",
            "半导体".encode("gbk"),
            10.5,
            1.2,
            10.0,
            0,
            "000001".encode("gbk"),
            b"",
            "平安银行".encode("gbk"),
            10.5,
            1.2,
            10.0,
        )
        body = struct.pack("<HH", 2, 1) + rec
        items = BoardListCmd().parse_response(body)
        assert len(items) == 1
        assert items[0].name == "半导体"
        assert items[0].symbol_name == "平安银行"


class TestSymbolInfo:
    def test_build_request(self) -> None:
        req = SymbolInfoCmd(1, "000001").build_request()
        assert isinstance(req, bytes)

    def test_parse(self) -> None:
        # identity at offset 8: H22s44s; core at 96: III5ffIfII; extra at 148: HIf20xI3f
        identity = struct.pack("<H22s44s", 1, "000001".encode("gbk"), "平安银行".encode("gbk"))
        body = b"\x00" * 8 + identity + b"\x00" * (96 - 8 - 68)
        core = struct.pack(
            "<III5ffIfII",
            20240115,
            93000,
            1,
            10.0,
            10.2,
            11.0,
            9.8,
            10.5,
            1.5,
            1000,
            1000000.0,
            500,
            500,
        )
        body += core
        body += b"\x00" * (148 - 96 - struct.calcsize("<III5ffIfII"))
        extra = struct.pack("<HIf20xI3f", 2, 0, 0.0, 0, 0.1, 10.0, 0.0)
        body += extra
        info = SymbolInfoCmd(1, "000001").parse_response(body)
        assert info.code == "000001"
        assert info.name == "平安银行"
        assert info.close == 10.5


class TestGoodsList:
    def test_count_cap(self) -> None:
        with pytest.raises(ValueError, match="count 不能超过"):
            GoodsListCmd(0, count=1001)

    def test_build_request(self) -> None:
        req = GoodsListCmd(market=0).build_request()
        assert isinstance(req, bytes)

    def test_parse_empty(self) -> None:
        items = GoodsListCmd(0).parse_response(struct.pack("<H", 0))
        assert items == []

    def test_parse_record(self) -> None:
        rec_fmt = "<H23sHIBfffHH"
        rec = struct.pack(rec_fmt, 0, "螺纹钢".encode("gbk"), 1, 2, 3, 4000.0, 4001.0, 4002.0, 4, 5)
        body = struct.pack("<H", 1) + rec
        items = GoodsListCmd(0).parse_response(body)
        assert len(items) == 1
        assert items[0].name == "螺纹钢"
        assert items[0].code == [4000.0, 4001.0, 4002.0]
