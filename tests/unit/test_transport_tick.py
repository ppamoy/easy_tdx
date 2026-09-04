"""ex/transport/sync + symbol_tick_chart 编解码测试（V399s）。"""

from __future__ import annotations

import struct
from datetime import date

import pytest

from easy_tdx.ex.transport.sync import _recv_exact_sock
from easy_tdx.exceptions import TdxConnectionError
from easy_tdx.mac.commands.symbol_tick_chart import SymbolTickChartCmd


class _FakeSock:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = list(chunks)
        self.recv_calls: list[int] = []

    def recv(self, n: int) -> bytes:
        self.recv_calls.append(n)
        if not self.chunks:
            return b""
        return self.chunks.pop(0)


class TestRecvExactSock:
    def test_single_chunk(self) -> None:
        sock = _FakeSock([b"hello"])
        assert _recv_exact_sock(sock, 5) == b"hello"

    def test_multi_chunk(self) -> None:
        sock = _FakeSock([b"he", b"ll", b"o"])
        assert _recv_exact_sock(sock, 5) == b"hello"

    def test_closed(self) -> None:
        sock = _FakeSock([])
        with pytest.raises(TdxConnectionError, match="连接被服务器关闭"):
            _recv_exact_sock(sock, 5)


class TestSymbolTickChart:
    def test_build_request(self) -> None:
        req = SymbolTickChartCmd(1, "000001", date(2024, 1, 15)).build_request()
        assert isinstance(req, bytes)

    def test_parse_empty(self) -> None:
        # 头部 + count=0，仍需完整尾部
        body = _tick_body(count=0)
        chart = SymbolTickChartCmd(1, "000001").parse_response(body)
        assert chart.code == "000001"
        assert chart.charts == []


def _tick_body(count: int) -> bytes:
    header = struct.pack("<H22sIBfH", 1, "000001".encode("gbk"), 20240115, 0, 10.0, count)
    ticks = b""
    for _ in range(count):
        ticks += struct.pack("<HffIf", 9 * 60 + 30, 10.5, 10.4, 100, 0.0)
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
    return header + ticks + tail
