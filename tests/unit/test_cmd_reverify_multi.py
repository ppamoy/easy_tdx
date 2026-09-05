"""cli/cmd_reverify.py _reverify_multi 错误分支测试（V402）。"""

from __future__ import annotations

import pytest

from easy_tdx.cli import cmd_reverify, conn


class _FakeClient:
    def __init__(self, kline_len: int = 0) -> None:
        self._kline_len = kline_len

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get_stock_kline(self, *args, **kwargs):
        if self._kline_len == 0:
            return None
        import pandas as pd

        return pd.DataFrame({"close": [1.0] * self._kline_len})


class TestReverifyMultiBranches:
    def _ctx(self, items):
        return {"items": items}

    def test_unknown_market(self, monkeypatch) -> None:
        monkeypatch.setattr(conn, "get_mac_client", lambda: _FakeClient())
        with pytest.raises(ValueError, match="所有策略槽位行情/注册失败"):
            cmd_reverify._reverify_multi(
                None,
                self._ctx([{"strategy": "ma_cross", "symbol": "HK:00700"}]),
                500,
                "DAILY",
                "NONE",
                1e6,
                0.0003,
                0.0,
                "next_open",
                "2024-01-01",
            )

    def test_unregistered_strategy(self, monkeypatch) -> None:
        monkeypatch.setattr(conn, "get_mac_client", lambda: _FakeClient())
        with pytest.raises(ValueError, match="所有策略槽位行情/注册失败"):
            cmd_reverify._reverify_multi(
                None,
                self._ctx([{"strategy": "not_real", "symbol": "SZ:000001"}]),
                500,
                "DAILY",
                "NONE",
                1e6,
                0.0003,
                0.0,
                "next_open",
                "2024-01-01",
            )

    def test_insufficient_kline(self, monkeypatch) -> None:
        monkeypatch.setattr(conn, "get_mac_client", lambda: _FakeClient(kline_len=10))
        with pytest.raises(ValueError, match="所有策略槽位行情/注册失败"):
            cmd_reverify._reverify_multi(
                None,
                self._ctx([{"strategy": "ma_cross", "symbol": "SZ:000001"}]),
                500,
                "DAILY",
                "NONE",
                1e6,
                0.0003,
                0.0,
                "next_open",
                "2024-01-01",
            )
