"""ex/commands 解析层回归测试（V-38，openspec 2.2/2.4 延伸治理）。

8 个 ex 命令类此前只有重连测试引用，parse_response 二进制解析几乎零覆盖
（覆盖率 24-28%）。本文件按 codec 真实 wire 格式构造响应体，锁定：
- 合法响应 → 正确字段（gbk 解码、zipday 日期压缩、时间换算）
- 短体/截断响应 → 不抛异常，返回空或部分记录
- count=0 / 空体 → 空结果
覆盖命令：markets / instrument_count / instrument_info / instrument_quote /
instrument_bars / history_bars_range / minute_time / transaction。
"""

from __future__ import annotations

import struct

import pytest

from easy_tdx.commands.base import BaseCommand
from easy_tdx.ex.commands.get_history_bars_range import GetExHistoryInstrumentBarsRangeCmd
from easy_tdx.ex.commands.get_instrument_bars import GetExInstrumentBarsCmd
from easy_tdx.ex.commands.get_instrument_count import GetExInstrumentCountCmd
from easy_tdx.ex.commands.get_instrument_info import GetExInstrumentInfoCmd
from easy_tdx.ex.commands.get_instrument_quote import GetExInstrumentQuoteCmd
from easy_tdx.ex.commands.get_instrument_quote_list import GetExInstrumentQuoteListCmd
from easy_tdx.ex.commands.get_markets import GetExMarketsCmd
from easy_tdx.ex.commands.get_minute_time import GetExMinuteTimeDataCmd
from easy_tdx.ex.commands.get_transaction import GetExTransactionDataCmd
from easy_tdx.exceptions import TdxCommandError

# ── fixture 构造（真实 wire 格式） ───────────────────────────────────────


def _market_entry(category: int, name: str, market: int, short: str) -> bytes:
    """GetMarkets 每条 64B：前 36B = B category + 32s name + B market + 2s short。"""
    return (
        struct.pack("<B32sB2s", category, name.encode("gbk"), market, short.encode("gbk"))
        + b"\x00" * 28
    )


def _instrument_entry(category: int, market: int, code: str, name: str, desc: str) -> bytes:
    """GetInstrumentInfo 每条 64B：前 40B = B + B + 3s + 9s code + 17s name + 9s desc。"""
    return (
        struct.pack(
            "<BB3s9s17s9s",
            category,
            market,
            b"\x00" * 3,
            code.encode("gbk"),
            name.encode("gbk"),
            desc.encode("gbk"),
        )
        + b"\x00" * 24
    )


def _zipday(year: int, month: int, day: int) -> int:
    return ((year - 2004) << 11) + month * 100 + day


# ── GetExMarketsCmd ──────────────────────────────────────────────────────


class TestGetExMarketsCmd:
    def test_parse_two_markets(self) -> None:
        body = (
            struct.pack("<H", 2)
            + _market_entry(1, "全球指数", 8, "DP")
            + _market_entry(2, "香港主板", 47, "HK")
        )
        markets = GetExMarketsCmd().parse_response(body)
        assert [m.name for m in markets] == ["全球指数", "香港主板"]
        assert markets[0].market == 8 and markets[0].category == 1
        assert markets[1].short_name == "HK"

    def test_skip_zero_entry(self) -> None:
        """category=0 且 market=0 的占位条目跳过。"""
        body = struct.pack("<H", 2) + _market_entry(0, "", 0, "") + _market_entry(1, "X", 1, "x")
        markets = GetExMarketsCmd().parse_response(body)
        assert len(markets) == 1 and markets[0].name == "X"

    def test_short_body_returns_empty(self) -> None:
        assert GetExMarketsCmd().parse_response(b"\x01") == []
        assert GetExMarketsCmd().parse_response(b"") == []

    def test_truncated_entries_partial(self) -> None:
        body = struct.pack("<H", 5) + _market_entry(1, "A", 1, "a")
        assert len(GetExMarketsCmd().parse_response(body)) == 1


# ── GetExInstrumentCountCmd ──────────────────────────────────────────────


class TestGetExInstrumentCountCmd:
    def test_parse_count(self) -> None:
        body = b"\x00" * 19 + struct.pack("<I", 12345) + b"\x00" * 4
        assert GetExInstrumentCountCmd().parse_response(body) == 12345

    def test_short_body_returns_zero(self) -> None:
        assert GetExInstrumentCountCmd().parse_response(b"\x00" * 22) == 0


# ── GetExInstrumentInfoCmd ───────────────────────────────────────────────


class TestGetExInstrumentInfoCmd:
    def test_parse_entries(self) -> None:
        body = struct.pack("<IH", 0, 2)
        body += _instrument_entry(1, 8, "GC0001", "黄金连续", "主力合约")
        body += _instrument_entry(2, 47, "00700", "腾讯控股", "HK")
        infos = GetExInstrumentInfoCmd(0, 2).parse_response(body)
        assert [i.code for i in infos] == ["GC0001", "00700"]
        assert infos[0].name == "黄金连续"
        assert infos[1].market == 47

    def test_declared_count_exceeds_body_partial(self) -> None:
        body = struct.pack("<IH", 0, 5) + _instrument_entry(1, 8, "X", "n", "d")
        infos = GetExInstrumentInfoCmd(0, 5).parse_response(body)
        assert len(infos) == 1

    def test_short_header_returns_empty(self) -> None:
        assert GetExInstrumentInfoCmd(0, 1).parse_response(b"\x00" * 5) == []

    def test_build_request_layout(self) -> None:
        req = GetExInstrumentInfoCmd(100, 50).build_request()
        assert req[:12] == bytes.fromhex("01 04 48 67 00 01 08 00 08 00 f5 23")
        assert struct.unpack("<IH", req[12:]) == (100, 50)


# ── GetExInstrumentQuoteCmd ──────────────────────────────────────────────


class TestGetExInstrumentQuoteCmd:
    def _quote_body(self, price: float = 123.5) -> bytes:
        # 10B 头（market+code）+ 4B unknown + 136B 五档区
        head = struct.pack("<B9s", 8, b"GC0001") + b"\x00" * 4
        floats = struct.pack(
            "<fffff", 120.0, 121.0, 125.0, 119.0, price
        )  # pre_close/open/high/low/price
        ints = struct.pack("<IIIIIIIII", 10, 1000, 500, 300, 700, 0, 0, 0, 0)
        bid = struct.pack("<fffff", 123.4, 123.3, 123.2, 123.1, 123.0)
        bid_vol = struct.pack("<IIIII", 5, 10, 15, 20, 25)
        ask = struct.pack("<fffff", 123.6, 123.7, 123.8, 123.9, 124.0)
        ask_vol = struct.pack("<IIIII", 6, 11, 16, 21, 26)
        return head + floats + ints + bid + bid_vol + ask + ask_vol

    def test_parse_quote(self) -> None:
        q = GetExInstrumentQuoteCmd(8, "GC0001").parse_response(self._quote_body())
        assert q is not None
        assert q.market == 8 and q.code == "GC0001"
        assert q.price == pytest.approx(123.5)
        assert q.pre_close == pytest.approx(120.0)
        assert q.bid1 == pytest.approx(123.4) and q.ask1 == pytest.approx(123.6)
        assert q.bid_vol1 == 5 and q.ask_vol5 == 26

    def test_short_body_returns_none(self) -> None:
        assert GetExInstrumentQuoteCmd(8, "X").parse_response(b"\x00" * 100) is None


# ── GetExInstrumentBarsCmd ───────────────────────────────────────────────


class TestGetExInstrumentBarsCmd:
    def _bars_body(self, day: int, n: int = 2) -> bytes:
        # 18B 头 + 2B count + n×(4B 日期 + 28B OHLC)
        records = b""
        for i in range(n):
            records += struct.pack("<I", day + i)
            records += struct.pack("<ffffIIf", 100.0 + i, 105.0, 99.0, 104.0 + i, 5000, 3000, 104.0)
        return b"\x00" * 18 + struct.pack("<H", n) + records

    def test_parse_day_bars(self) -> None:
        bars = GetExInstrumentBarsCmd(4, 8, "GC0001").parse_response(self._bars_body(20260901))
        assert len(bars) == 2
        assert bars[0].year == 2026 and bars[0].month == 9 and bars[0].day == 1
        assert bars[0].hour == 15 and bars[0].minute == 0  # 日线收盘约定
        assert bars[1].close == pytest.approx(105.0)
        assert bars[0].position == 5000 and bars[0].trade == 3000
        # 现状语义锁定（V-38 审计注记）：amount 读 pos+16，与 <ffffIIf 布局中
        # position（第 5 字段，offset 16-19）同源——即 position 的 float 重解读。
        # 行为确定；真实持仓/成交额语义待真机数据校准。
        assert bars[0].amount == struct.unpack("<f", struct.pack("<I", 5000))[0]

    def test_minute_category_uses_zipday(self) -> None:
        body = b"\x00" * 18 + struct.pack("<H", 1)
        body += struct.pack("<H", _zipday(2026, 9, 1)) + struct.pack("<H", 570)  # 09:30
        body += struct.pack("<ffffIIf", 1.0, 2.0, 0.5, 1.5, 10, 20, 1.5)
        bars = GetExInstrumentBarsCmd(0, 8, "X").parse_response(body)
        assert len(bars) == 1
        assert (bars[0].hour, bars[0].minute) == (9, 30)

    def test_too_short_returns_empty(self) -> None:
        assert GetExInstrumentBarsCmd(4, 8, "X").parse_response(b"\x00" * 19) == []


# ── GetExHistoryInstrumentBarsRangeCmd ─────────────────────────────────────────────


class TestGetExHistoryInstrumentBarsRangeCmd:
    def test_parse_bars(self) -> None:
        d1 = _zipday(2026, 9, 1)  # _parse_date: year=num//2048+2004, 月日=num%2048
        body = b"\x00" * 12 + struct.pack("<H", 1)
        body += struct.pack("<HHffffIIf", d1, 570, 100.0, 105.0, 99.0, 104.0, 500, 300, 103.5)
        bars = GetExHistoryInstrumentBarsRangeCmd(8, "X", 20260901, 20260910).parse_response(body)
        assert len(bars) == 1
        assert bars[0].year == 2026 and bars[0].month == 9 and bars[0].day == 1
        assert (bars[0].hour, bars[0].minute) == (9, 30)
        assert bars[0].amount == pytest.approx(103.5)  # settlement 在 32B 记录的 offset 28

    def test_too_short_returns_empty(self) -> None:
        assert (
            GetExHistoryInstrumentBarsRangeCmd(8, "X", 20260901, 20260910).parse_response(
                b"\x00" * 13
            )
            == []
        )


# ── GetExMinuteTimeDataCmd ───────────────────────────────────────────────


class TestGetExMinuteTimeDataCmd:
    def test_parse_records(self) -> None:
        body = struct.pack("<B9sH", 8, b"GC0001", 2)
        body += struct.pack("<HffII", 570, 100.0, 99.5, 10, 5000)
        body += struct.pack("<HffII", 571, 100.1, 99.6, 20, 5001)
        bars = GetExMinuteTimeDataCmd(8, "GC0001").parse_response(body)
        assert len(bars) == 2
        assert (bars[0].hour, bars[0].minute) == (9, 30)
        assert bars[1].price == pytest.approx(100.1)
        assert bars[0].volume == 10 and bars[0].open_interest == 5000

    def test_short_body_returns_empty(self) -> None:
        assert GetExMinuteTimeDataCmd(8, "X").parse_response(b"\x00" * 11) == []


# ── GetExTransactionDataCmd ──────────────────────────────────────────────


class TestGetExTransactionDataCmd:
    def test_parse_records(self) -> None:
        body = struct.pack("<B9s4sH", 8, b"GC0001", b"\x00" * 4, 2)
        # direction(H)=nature*10000+秒：H ≤65535 → nature≤6。60025 → nature=6, 秒=25
        body += struct.pack("<HIIiH", 570, 1000, 5, 3, 60025)
        body += struct.pack("<HIIiH", 571, 1001, 6, -1, 65535)  # 秒=5535>59 → 0
        recs = GetExTransactionDataCmd(8, "GC0001").parse_response(body)
        assert len(recs) == 2
        assert (recs[0].hour, recs[0].minute, recs[0].second) == (9, 30, 25)
        assert recs[0].nature == 6 and recs[0].zengcang == 3
        assert recs[1].second == 0  # 非法秒数归零

    def test_short_body_returns_empty(self) -> None:
        assert GetExTransactionDataCmd(8, "X").parse_response(b"\x00" * 15) == []


# ── GetExInstrumentQuoteListCmd（category 分派与错误分支） ────────────────


class TestGetExInstrumentQuoteListCmd:
    def test_unsupported_category_raises(self) -> None:
        cmd = GetExInstrumentQuoteListCmd(market=8, category=0)
        with pytest.raises(TdxCommandError, match="不支持的扩展行情类别"):
            cmd.parse_response(struct.pack("<H", 1) + b"\x00" * 10)

    def test_empty_body_returns_empty(self) -> None:
        cmd = GetExInstrumentQuoteListCmd(market=47, category=2)
        assert cmd.parse_response(b"") == []

    def test_truncated_record_returns_empty_for_that_code(self) -> None:
        cmd = GetExInstrumentQuoteListCmd(market=8, category=3)
        body = struct.pack("<H", 1) + b"\x00" * 10  # 声明 1 条但无 140B 数据
        assert cmd.parse_response(body) == []

    def _quote_list_body(self, category: int, n: int, *, interleave: bool = True) -> bytes:
        """构造 quote_list 响应体。

        wire 语义（pytdx 同款，主循环「读 10B 索引 → 解 290B 体」交错）：
        interleave=True  → n×[10B 代码索引 + 290B 数据体] 交错（真实布局）；
        interleave=False → 集中式 [2B num + n×10B 索引 + n×290B 体]（负例，
        用于证明解析器按交错布局读，集中布局会在第 2 条读歪）。
        数据体 = 140B 可解区 + 150B 填充。
        """
        body = struct.pack("<H", n)
        entries = [
            struct.pack("<B9s", 8, f"CODE{i}".encode("gbk").ljust(9, b"\x00"))
            + b"\x00" * 140
            + b"\xab" * 150
            for i in range(n)
        ]
        if interleave:
            return body + b"".join(entries)
        return body + b"".join(e[:10] for e in entries) + b"".join(e[10:] for e in entries)

    def test_futures_branch_parses_fields(self) -> None:
        body = self._quote_list_body(3, 1)
        cmd = GetExInstrumentQuoteListCmd(market=8, category=3)
        rows = cmd.parse_response(body)
        assert len(rows) == 1
        assert rows[0]["code"] == "CODE0"
        # <IfffffIIIIfIIfIf… 布局：BiShu=0, ZuoJie=0.0 …
        assert rows[0]["market"] == 8
        assert rows[0]["BiShu"] == 0

    def test_hk_branch_parses_fields(self) -> None:
        body = self._quote_list_body(2, 1)
        cmd = GetExInstrumentQuoteListCmd(market=47, category=2)
        rows = cmd.parse_response(body)
        assert len(rows) == 1
        assert rows[0]["code"] == "CODE0"
        assert rows[0]["XianJia"] == 0.0
        assert rows[0]["MaiRuJia1"] == 0.0 and rows[0]["MaiChuLiang5"] == 0

    def test_multi_code_parsing_advances_pos(self) -> None:
        """两条记录：验证 pos 前进 10+290 每条，不重叠误读。"""
        body = self._quote_list_body(3, 2)
        rows = GetExInstrumentQuoteListCmd(market=8, category=3).parse_response(body)
        assert [r["code"] for r in rows] == ["CODE0", "CODE1"]

    def test_concentrated_layout_misreads_second_code(self) -> None:
        """负例对照：集中式布局（非真实 wire）第 2 条代码必然读歪——
        证明解析器语义是「索引+体交错」，锁定 wire 理解，防回归。"""
        body = self._quote_list_body(3, 2, interleave=False)
        rows = GetExInstrumentQuoteListCmd(market=8, category=3).parse_response(body)
        assert len(rows) == 2
        assert rows[0]["code"] == "CODE0"
        assert rows[1]["code"] != "CODE1"

    def test_second_record_truncated_yields_first_only(self) -> None:
        body = self._quote_list_body(2, 2)
        body = body[: 2 + 300 + 10] + b"\x00" * 100  # 第 2 条体不足
        rows = GetExInstrumentQuoteListCmd(market=47, category=2).parse_response(body)
        assert [r["code"] for r in rows] == ["CODE0"]


# ── 全体命令 build_request 可执行（防签名回归） ──────────────────────────


def test_all_cmds_are_base_command() -> None:
    cmds: list[BaseCommand] = [
        GetExMarketsCmd(),
        GetExInstrumentCountCmd(),
        GetExInstrumentInfoCmd(0, 1),
        GetExInstrumentQuoteCmd(8, "X"),
        GetExInstrumentBarsCmd(4, 8, "X"),
        GetExHistoryInstrumentBarsRangeCmd(8, "X", 20260901, 20260910),
        GetExMinuteTimeDataCmd(8, "X"),
        GetExTransactionDataCmd(8, "X"),
        GetExInstrumentQuoteListCmd(market=8, category=3),
    ]
    for c in cmds:
        assert isinstance(c.build_request(), bytes) and len(c.build_request()) > 0
