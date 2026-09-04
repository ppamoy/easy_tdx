"""cli/cmd_company.py 纯函数/离线 mock 测试（V399h）。

覆盖 _read_full_section 分块读取循环 + _resolve_filename 命中/未命中分支，
用 mock client 离线构造。
"""

from __future__ import annotations

import pandas as pd
import pytest

from easy_tdx.cli.cmd_company import (
    _read_full_section,
    _resolve_filename,
    _ResolveError,
)
from easy_tdx.models.enums import Market


class _MockClient:
    def __init__(self) -> None:
        self.chunks: list[str] = []
        self.df = pd.DataFrame()

    def get_company_info_content(self, market, code, filename, pos, n) -> str:
        self.chunks.append((pos, n))
        if pos >= 40000:
            return ""
        return "X" * n

    def get_company_info_category(self, market, code) -> pd.DataFrame:
        return self.df


class TestReadFullSection:
    def test_single_chunk(self) -> None:
        c = _MockClient()
        out = _read_full_section(c, Market.SZ, "000001", "f.txt", 0, 100)
        assert out == "X" * 100
        assert len(c.chunks) == 1

    def test_multi_chunk(self) -> None:
        c = _MockClient()
        out = _read_full_section(c, Market.SZ, "000001", "f.txt", 0, 30720 + 5)
        assert len(out) == 30720 + 5
        assert len(c.chunks) == 2

    def test_empty_stops(self) -> None:
        c = _MockClient()
        out = _read_full_section(c, Market.SZ, "000001", "f.txt", 40000, 100)
        assert out == ""
        assert len(c.chunks) == 1


class TestResolveFilename:
    def _df(self) -> pd.DataFrame:
        return pd.DataFrame([{"name": "半导体", "filename": "TGN123", "start": 0, "length": 5000}])

    def test_hit(self) -> None:
        c = _MockClient()
        c.df = self._df()
        filename, start, length, ok = _resolve_filename(c, Market.SZ, "000001", "半导体")
        assert filename == "TGN123"
        assert start == 0
        assert length == 5000
        assert ok is True

    def test_miss_raises(self) -> None:
        c = _MockClient()
        c.df = self._df()
        with pytest.raises(_ResolveError):
            _resolve_filename(c, Market.SZ, "000001", "不存在")

    def test_empty_df_raises(self) -> None:
        c = _MockClient()
        with pytest.raises(_ResolveError):
            _resolve_filename(c, Market.SZ, "000001", "半导体")
