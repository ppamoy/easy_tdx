"""mac/commands 协议编解码测试四（V399o）。

覆盖 symbol_transaction / file_query（FileListCmd/FileDownloadCmd），离线可测。
"""

from __future__ import annotations

import struct
from datetime import date

from easy_tdx.mac.commands.file_query import FileDownloadCmd, FileListCmd
from easy_tdx.mac.commands.symbol_transaction import SymbolTransactionCmd


class TestSymbolTransaction:
    def test_build_request(self) -> None:
        req = SymbolTransactionCmd(1, "000001", date(2024, 1, 15)).build_request()
        assert isinstance(req, bytes)

    def test_parse_empty(self) -> None:
        body = b"\x00" * 29 + struct.pack("<H", 0)
        assert SymbolTransactionCmd(1, "000001").parse_response(body) == []

    def test_parse_item(self) -> None:
        header = b"\x00" * 29 + struct.pack("<H", 1) + b"\x00" * 8
        item = struct.pack("<IfIIH", 9 * 3600 + 30 * 60, 10.5, 100, 5, 0)
        items = SymbolTransactionCmd(1, "000001").parse_response(header + item)
        assert len(items) == 1
        assert items[0].price == 10.5
        assert items[0].vol == 100


class TestFileList:
    def test_build_request(self) -> None:
        req = FileListCmd("gpcw20240331.zip").build_request()
        assert isinstance(req, bytes)

    def test_parse(self) -> None:
        meta = struct.pack("<IIb", 100, 2000, 1) + b"abc123" + b"\x00" * 26
        f = FileListCmd("x").parse_response(meta)
        assert f.offset == 100
        assert f.size == 2000
        assert f.hash == "abc123"


class TestFileDownload:
    def test_build_request(self) -> None:
        req = FileDownloadCmd("gpcw20240331.zip", index=1, offset=0, size=1000).build_request()
        assert isinstance(req, bytes)

    def test_parse_short(self) -> None:
        assert FileDownloadCmd("x").parse_response(b"\x00" * 4) == b""

    def test_parse(self) -> None:
        data = FileDownloadCmd("x").parse_response(b"\x00" * 8 + b"CONTENT")
        assert data == b"CONTENT"
