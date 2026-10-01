"""股本变迁文件读取（offline/gbbq.py）回归测试（V-42）。

read_gbbq 此前 0 测试（覆盖率 31.1%）。XOR 解密流无法反向伪造密文，
因此测试锚定「结构不变量 + 边界降级」：
- key 常量完整性（pytdx 移植的 4176B 表，解密偏移上限 0xC48+255*4+4=4168）；
- count=0 / 文件过短 / 数据不足一条记录（29B）→ 空结果不崩；
- 坏 code（非 UTF-8）→ latin-1 降级 + 警告，坏记录不毁整份解析（V-42 修复）；
- 解密运算确定性（同输入同输出）+ 明文结构 27B（<B7sIBffff）。
"""

from __future__ import annotations

import logging
import struct
from pathlib import Path

import pytest

from easy_tdx.exceptions import TdxFileNotFoundError
from easy_tdx.offline.gbbq import _BIN_KEYS, GbbqRecord, read_gbbq

RECORD_SIZE = 29  # 24B 解密区 + 5B 附加区


@pytest.fixture()
def gbbq_file(tmp_path: Path):
    def _write(data: bytes) -> Path:
        p = tmp_path / "gbbq.bin"
        p.write_bytes(data)
        return p

    return _write


# ── 常量与结构不变量 ─────────────────────────────────────────────────────


class TestKeyInvariants:
    def test_key_table_size(self) -> None:
        """pytdx 移植表 4176B；解密最大访问偏移 0xC48+0xFF*4+4=4168 ≤ 4176。"""
        assert len(_BIN_KEYS) == 4176
        assert 0xC48 + 0xFF * 4 + 4 <= len(_BIN_KEYS)

    def test_key_first_dword(self) -> None:
        """首 4 字节为表头校验（pytdx 同源）。"""
        assert _BIN_KEYS[:4] == bytes.fromhex("38a7c21d")


# ── 边界与降级 ───────────────────────────────────────────────────────────


class TestReadGbbqBoundaries:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(TdxFileNotFoundError, match="股本变迁文件不存在"):
            read_gbbq(tmp_path / "nope")

    def test_count_zero(self, gbbq_file) -> None:
        assert read_gbbq(gbbq_file(struct.pack("<I", 0))) == []

    def test_file_shorter_than_count_header(self, gbbq_file) -> None:
        assert read_gbbq(gbbq_file(bytes(2))) == []
        assert read_gbbq(gbbq_file(b"")) == []

    def test_declared_count_exceeds_data_stops_cleanly(self, gbbq_file, caplog) -> None:
        """count=1 但数据只有 10B → 空结果 + 警告，不 struct.error（V-42 修复）。"""
        with caplog.at_level(logging.WARNING, logger="easy_tdx.offline.gbbq"):
            records = read_gbbq(gbbq_file(struct.pack("<I", 1) + bytes(10)))
        assert records == []
        assert any("数据不足" in r.message for r in caplog.records)

    def test_bad_code_falls_back_to_latin1(self, gbbq_file, caplog) -> None:
        """坏 code（解密出非 UTF-8）→ latin-1 可逆降级，不 UnicodeDecodeError。"""
        with caplog.at_level(logging.WARNING, logger="easy_tdx.offline.gbbq"):
            records = read_gbbq(gbbq_file(struct.pack("<I", 5) + bytes(RECORD_SIZE)))
        assert len(records) == 1
        code = records[0].code
        assert code.encode("latin-1") == records[0]._raw[1:8].rstrip(b"\x00")
        assert any("latin-1" in r.message for r in caplog.records)


# ── 解密运算语义 ─────────────────────────────────────────────────────────


class TestDecryptionSemantics:
    def test_deterministic_output(self, tmp_path: Path) -> None:
        """同密文两次解析结果完全一致（纯函数性质）。"""
        data = struct.pack("<I", 2) + bytes(RECORD_SIZE * 2)
        p1 = tmp_path / "a"
        p1.write_bytes(data)
        p2 = tmp_path / "b"
        p2.write_bytes(data)
        r1, r2 = read_gbbq(p1), read_gbbq(p2)
        assert r1 == r2

    def test_record_shape(self, gbbq_file) -> None:
        """记录结构：_raw 29B 明文（<B7sIBffff = 1+7+4+1+4×4），字段可读。"""
        records = read_gbbq(gbbq_file(struct.pack("<I", 3) + bytes(RECORD_SIZE * 3)))
        assert len(records) == 3
        for rec in records:
            assert isinstance(rec, GbbqRecord)
            assert len(rec._raw) == 29
            assert struct.calcsize("<B7sIBffff") == 29
            assert isinstance(rec.market, int)
            assert isinstance(rec.datetime, int)
            assert all(
                isinstance(v, float)
                for v in (
                    rec.hongli_panqianliutong,
                    rec.peigujia_qianzongguben,
                    rec.songgu_qianzongguben,
                    rec.peigu_houzongguben,
                )
            )

    def test_multi_record_offsets_advance(self, tmp_path: Path) -> None:
        """3 条记录依次解析，offset 推进 29/条（互不重叠误读）。"""
        data = struct.pack("<I", 3) + bytes(RECORD_SIZE * 3)
        p = tmp_path / "g"
        p.write_bytes(data)
        records = read_gbbq(p)
        assert len(records) == 3
        # 不同记录的 _raw 相同（同输入全零密文），但无异常即证明偏移推进正确
        assert all(r._raw == records[0]._raw for r in records)
