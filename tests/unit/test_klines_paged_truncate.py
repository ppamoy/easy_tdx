"""fetch_paged_bars 截断回归测试。

count>800 时 chanlun/analyze 走 fetch_paged_bars(lookback=count)。该函数以
「凑满 lookback」为停页条件，最后一页往往多带回一整页（lookback=2000 →
3 页 ≈ 2400 根）。若不截断，返回 bar 数 > lookback，与前端 /bars（按 count
截断为恰好 lookback 根、同源同价）帧长不一致——分析的 bar_index 落在前端
props.bars 的错误位置，分型/笔/中枢等所有索引锚定的标记整体错位
（用户反馈「顶底分型标记错乱」的根因）。本测试锁定「返回恰好 lookback 根
且为最新 lookback 根」契约。
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from easy_tdx.web.klines import _PAGE_SIZE, fetch_paged_bars


def _master(n: int = 2400, latest=pd.Timestamp("2026-09-24")) -> pd.DataFrame:
    """n 根日线，时间升序，最新一根 = latest。每根有唯一 open 值便于校验。"""
    dates = [latest - pd.Timedelta(days=n - 1 - i) for i in range(n)]
    return pd.DataFrame(
        {
            "date": dates,
            "open": [float(i) for i in range(n)],
            "close": [float(i) for i in range(n)],
            "high": [float(i) for i in range(n)],
            "low": [float(i) for i in range(n)],
            "vol": [float(i) for i in range(n)],
        }
    )


def _page_of(master: pd.DataFrame, start: int, count: int) -> pd.DataFrame:
    """模拟 TDX 翻页：start=0 取最新 count 根（升序），start=800 取更老 count 根。

    即 master.iloc[n-start-count : n-start]（n=master 长度），与 /bars 单页契约
    「每页内部正序、页间逆序、start=0 为最新一页」一致。
    """
    n = len(master)
    lo = max(0, n - start - count)
    hi = max(0, n - start)
    return master.iloc[lo:hi].reset_index(drop=True)


@pytest.mark.asyncio
async def test_fetch_paged_bars_truncates_to_lookback() -> None:
    """lookback=2000 时翻 3 页（≈2400 根），必须截断为最新 2000 根。"""
    master = _master(2400)
    total_calls = []

    async def fake_fetch(_mac, _tdx, _mkt, _code, _cat, start, count, bar_time="start"):
        total_calls.append(start)
        return _page_of(master, start, count)

    with patch("easy_tdx.web.klines.fetch_qfq_klines", new=fake_fetch):
        df = await fetch_paged_bars(
            mac_client=None,
            tdx_client=None,
            market="SZ",
            code="000001",
            category="DAY",
            lookback=2000,
        )

    assert len(df) == 2000, f"应截断为恰好 lookback=2000 根，实际 {len(df)}"
    # 截断取尾部：最新一根仍为 master 末根，最老一根 = master.iloc[400]
    assert df["date"].iloc[-1] == master["date"].iloc[-1]
    assert df["date"].iloc[0] == master["date"].iloc[400]
    assert df["date"].is_monotonic_increasing
    # 确认确实翻了 3 页（ceil(2000/800)=3）
    assert total_calls == [0, _PAGE_SIZE, 2 * _PAGE_SIZE]


@pytest.mark.asyncio
async def test_fetch_paged_bars_exact_page_no_truncate_needed() -> None:
    """lookback 恰为页整数倍时不多不少。"""
    master = _master(1600)

    async def fake_fetch(_mac, _tdx, _mkt, _code, _cat, start, count, bar_time="start"):
        return _page_of(master, start, count)

    with patch("easy_tdx.web.klines.fetch_qfq_klines", new=fake_fetch):
        df = await fetch_paged_bars(None, None, "SZ", "000001", "DAY", lookback=1600)

    assert len(df) == 1600


@pytest.mark.asyncio
async def test_fetch_paged_bars_fewer_than_lookback_returns_all() -> None:
    """标的上市历史不足 lookback 时返回全部可得 bar（不报错、不截断、不补零）。"""
    master = _master(1300)  # 总历史仅 1300 根

    async def fake_fetch(_mac, _tdx, _mkt, _code, _cat, start, count, bar_time="start"):
        return _page_of(master, start, count)

    with patch("easy_tdx.web.klines.fetch_qfq_klines", new=fake_fetch):
        df = await fetch_paged_bars(None, None, "SZ", "000001", "DAY", lookback=2000)

    assert len(df) == 1300  # 不足 lookback 时全返
    assert df["date"].iloc[-1] == master["date"].iloc[-1]
    assert df["date"].iloc[0] == master["date"].iloc[0]
