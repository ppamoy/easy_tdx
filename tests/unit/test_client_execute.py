"""client.py TdxClient._execute 韧性路径测试（V403）。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from easy_tdx.client import TdxClient
from easy_tdx.exceptions import TdxConnectionError


class _Cmd:
    def build_request(self) -> bytes:
        return b"req"

    def parse_response(self, body: bytes) -> int:
        return 42


def _client(conn, auto_reconnect: bool = True) -> TdxClient:
    c = object.__new__(TdxClient)
    c._conn = conn
    c._host = "1.2.3.4"
    c._port = 7709
    c._auto_reconnect = auto_reconnect
    return c


class TestExecute:
    def test_success(self) -> None:
        conn = MagicMock()
        conn.execute.return_value = 42
        c = _client(conn)
        assert c._execute(_Cmd()) == 42

    def test_no_reconnect_raises(self) -> None:
        conn = MagicMock()
        conn.execute.side_effect = TdxConnectionError("boom")
        c = _client(conn, auto_reconnect=False)
        with pytest.raises(TdxConnectionError):
            c._execute(_Cmd())

    def test_retry_then_success(self) -> None:
        conn = MagicMock()
        conn.execute.side_effect = [TdxConnectionError("boom"), 42]
        c = _client(conn)
        # 直接替换 _reconnect 避免真实 socket；重试延迟用 0 缩短
        c._reconnect = MagicMock()
        import easy_tdx.client as mod

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(mod, "_RETRY_DELAYS", (0, 0))
        try:
            assert c._execute(_Cmd()) == 42
        finally:
            monkeypatch.undo()
