"""offline/history_financial.py 与 offline/block.py 的回归测试（V-36 延伸）。

两模块此前 0 测试（覆盖率 25.8% / 26.7%），且只有 CLI 层间接路径。
本文件用真实二进制 fixture（复用 codec 格式构造）从 offline 层直测：
- read_history_financial: .dat 直读 / .zip 提取 / 文件不存在 / 坏 zip /
  zip 无 .dat / 未知 market_byte 回退 SZ
- read_block_dat: 正常读取 / 文件不存在
- read_customer_blocks: 目录/配置缺失 / gbk 名称解析 / .blk 代码剥离市场位 /
  空文件名条目跳过
"""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path

import pytest

from easy_tdx.exceptions import TdxFileNotFoundError, TdxOfflineError
from easy_tdx.models.enums import Market
from easy_tdx.offline.block import CustomerBlock, read_block_dat, read_customer_blocks
from easy_tdx.offline.history_financial import read_history_financial

# ── fixture 构造（真实二进制，不 mock codec） ────────────────────────────


def _build_gpcw_dat(
    stocks: list[tuple[str, int, list[float]]], report_date: int = 20260331
) -> bytes:
    """按 codec/financial.py 的 gpcw .dat 格式构造最小合法文件。"""
    num_fields = 3
    report_size = num_fields * 4
    max_count = len(stocks)
    header = struct.pack("<1hI1H3L", 0, report_date, max_count, 0, report_size, 0)
    index_fmt = "<6s1c1L"
    index_size = struct.calcsize(index_fmt)
    data_start = struct.calcsize("<1hI1H3L") + max_count * index_size
    report_fmt = f"<{num_fields}f"

    chunks: list[bytes] = []
    offset = data_start
    offsets: list[int] = []
    for _code, _market, fields in stocks:
        offsets.append(offset)
        chunks.append(struct.pack(report_fmt, *fields))
        offset += 4 * num_fields

    index = b"".join(
        struct.pack(index_fmt, code.encode("ascii"), bytes([market]), offsets[i])
        for i, (code, market, _f) in enumerate(stocks)
    )
    return header + index + b"".join(chunks)


@pytest.fixture()
def gpcw_dat_file(tmp_path: Path) -> Path:
    p = tmp_path / "gpcw20260331.dat"
    p.write_bytes(_build_gpcw_dat([("600519", 1, [1.5, 2.5, 3.5]), ("000001", 0, [9.0] * 3)]))
    return p


# ── read_history_financial ───────────────────────────────────────────────


class TestReadHistoryFinancial:
    def test_dat_file_returns_records(self, gpcw_dat_file: Path) -> None:
        records = read_history_financial(gpcw_dat_file)
        assert len(records) == 2
        sh = [r for r in records if r.code == "600519"][0]
        assert sh.market == Market.SH
        assert sh.report_date == 20260331
        assert sh.fields == [1.5, 2.5, 3.5]
        sz = [r for r in records if r.code == "000001"][0]
        assert sz.market == Market.SZ

    def test_zip_file_extracts_dat(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "gpcw20260331.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("gpcw20260331.dat", _build_gpcw_dat([("600519", 1, [2.0] * 3)]))
        records = read_history_financial(zip_path)
        assert len(records) == 1
        assert records[0].code == "600519"
        assert records[0].fields == [2.0, 2.0, 2.0]

    def test_unknown_market_byte_falls_back_to_sz(self, tmp_path: Path) -> None:
        """market_byte=9（非法）→ 回退 Market.SZ 而非抛异常。"""
        p = tmp_path / "gpcw.dat"
        p.write_bytes(_build_gpcw_dat([("600519", 9, [1.0] * 3)]))
        records = read_history_financial(p)
        assert records[0].market == Market.SZ

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(TdxFileNotFoundError, match="不存在"):
            read_history_financial(tmp_path / "nope.dat")

    def test_bad_zip_raises_tdx_offline_error(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.zip"
        p.write_bytes(b"PK\x03\x04-not-a-real-zip")
        with pytest.raises(TdxOfflineError, match="无效的 zip"):
            read_history_financial(p)

    def test_zip_without_dat_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.zip"
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr("readme.txt", "no dat here")
        with pytest.raises(TdxOfflineError, match="未找到 .dat"):
            read_history_financial(p)


# ── read_block_dat ───────────────────────────────────────────────────────


class TestReadBlockDat:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(TdxFileNotFoundError, match="板块数据文件不存在"):
            read_block_dat(tmp_path / "block_zs.dat")

    def test_valid_file_delegates_to_codec(self, tmp_path: Path) -> None:
        """用 codec/block.py 的真实格式构造 1 条记录，验证 offline 层透传。"""
        # 格式：384B header + 2B count + 2813B/条
        # （9s gbk 名称 + H stock_count + H type + 2800s 代码区，7B/代码）
        name = "YZCY".encode("gbk").ljust(9, b"\x00")
        begin = name + struct.pack("<HH", 1, 0)  # stock_count=1
        codes = b"600519" + b"\x00" + b"\x00" * (2800 - 7)
        body = begin + codes
        p = tmp_path / "block_yz.dat"
        p.write_bytes(b"\x00" * 384 + struct.pack("<H", 1) + body)
        blocks = read_block_dat(p)
        assert len(blocks) == 1
        assert blocks[0].name == "YZCY"
        assert "600519" in blocks[0].codes


# ── read_customer_blocks ─────────────────────────────────────────────────


def _write_cfg_entry(name: str, blk_filename: str) -> bytes:
    """blocknew.cfg 条目：50B gbk 名称 + 70B gbk 文件名（120 字节）。"""
    return name.encode("gbk").ljust(50, b"\x00") + blk_filename.encode("gbk").ljust(70, b"\x00")


class TestReadCustomerBlocks:
    def test_missing_dir_raises(self, tmp_path: Path) -> None:
        with pytest.raises(TdxOfflineError, match="目录不存在"):
            read_customer_blocks(tmp_path / "nowhere")

    def test_missing_cfg_raises(self, tmp_path: Path) -> None:
        (tmp_path / "T0002").mkdir()
        with pytest.raises(TdxOfflineError, match="配置文件不存在"):
            read_customer_blocks(tmp_path / "T0002")

    def test_reads_names_and_codes(self, tmp_path: Path) -> None:
        d = tmp_path / "T0002"
        d.mkdir()
        (d / "blocknew.cfg").write_bytes(_write_cfg_entry("自选AI", "block_ai"))
        (d / "block_ai.blk").write_text("1600519\n0000002\n", encoding="utf-8")
        blocks = read_customer_blocks(d)
        assert len(blocks) == 1
        b = blocks[0]
        assert isinstance(b, CustomerBlock)
        assert b.blockname == "自选AI"
        assert b.block_type == "block_ai"
        assert b.codes == ["600519", "000002"]  # 首位市场标识被剥离

    def test_empty_filename_entry_skipped(self, tmp_path: Path) -> None:
        d = tmp_path / "T0002"
        d.mkdir()
        cfg = _write_cfg_entry("空条目", "") + _write_cfg_entry("有内容", "blk1")
        (d / "blocknew.cfg").write_bytes(cfg)
        (d / "blk1.blk").write_text("1600519\n", encoding="utf-8")
        blocks = read_customer_blocks(d)
        assert [b.blockname for b in blocks] == ["有内容"]

    def test_trailing_partial_entry_ignored(self, tmp_path: Path) -> None:
        """尾部不足 120 字节的残条目不崩溃也不产出。"""
        d = tmp_path / "T0002"
        d.mkdir()
        (d / "blocknew.cfg").write_bytes(_write_cfg_entry("A", "ba") + "残缺".encode("gbk"))
        (d / "ba.blk").write_text("1600001\n", encoding="utf-8")
        blocks = read_customer_blocks(d)
        assert [b.blockname for b in blocks] == ["A"]
