"""mac/commands/server_info.py 协议编解码测试（V399k）。"""

from __future__ import annotations

import struct

from easy_tdx.mac.commands.server_info import ServerInfoCmd


def _full_body() -> bytes:
    count = struct.pack("<H", 1)
    flags = b"\x00" * 8
    tag = b"\x00" * 3
    reserved = b"\x00" * 9
    today = struct.pack("<I", 20240115)
    ts1 = struct.pack("<I", 0)
    session1 = struct.pack("<8H", 9 * 60 + 30, 11 * 60 + 30, 13 * 60, 15 * 60, 0, 0, 0, 0)
    session2 = struct.pack("<8H", 0, 0, 0, 0, 0, 0, 0, 0)
    flag = b"\x00"
    last = struct.pack("<I", 20240112)
    ts2 = struct.pack("<I", 0)
    param1 = struct.pack("<I", 100)
    param2 = struct.pack("<I", 200)
    body = (
        count
        + flags
        + tag
        + reserved
        + today
        + ts1
        + session1
        + session2
        + flag
        + last
        + ts2
        + param1
        + param2
    )
    return body.ljust(87, b"\x00")


class TestServerInfoCmd:
    def test_build_request(self) -> None:
        req = ServerInfoCmd().build_request()
        assert isinstance(req, bytes)
        assert len(req) > 68

    def test_parse_short(self) -> None:
        s = ServerInfoCmd().parse_response(b"\x00" * 10)
        assert s.today == ""
        assert s.last_trading_day == ""

    def test_parse_full(self) -> None:
        s = ServerInfoCmd().parse_response(_full_body())
        assert s.today == "2024-01-15"
        assert s.last_trading_day == "2024-01-12"
        assert s.market_param_1 == 100
        assert s.market_param_2 == 200
        assert s.sessions_1[0]["open"] == "9:30"
