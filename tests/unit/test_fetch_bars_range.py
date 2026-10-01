"""fetch_bars_range 单测（V723，任意历史区间取数）。

mock fetch_qfq_klines（协议层已在别处覆盖），重点验证：
翻页直到覆盖 start_date、闭区间切片语义、end_date 缺省到最新、
历史耗尽（start_date 早于上市日）提前收尾、空区间契约。
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from easy_tdx.web.klines import fetch_bars_range

_TOTAL = 2000
_MASTER = pd.DataFrame(
    {
        "date": pd.bdate_range("2017-01-02", periods=_TOTAL),
        "close": [float(i) for i in range(_TOTAL)],
    }
)

call_log: list[int] = []


def _page(start: int, count: int) -> pd.DataFrame:
    """TDX 语义：start=距末尾偏移，end=_TOTAL-start。"""
    end = _TOTAL - start
    begin = max(0, end - count)
    return _MASTER.iloc[begin:end].reset_index(drop=True)


def _fake_fetch(mac, tdx, market, code, category, start, count, bar_time="start"):
    call_log.append(start)
    if start >= _TOTAL:
        return pd.DataFrame()
    return _page(start, count)


async def test_range_within_single_page() -> None:
    """区间落在最新 800 根内：只翻一页，闭区间切片正确。"""
    global call_log
    call_log = []
    with patch("easy_tdx.web.klines.fetch_qfq_klines", side_effect=_fake_fetch):
        df = await fetch_bars_range(None, None, "SZ", "000001", "DAY", "2024-05-06", "2024-05-20")
    assert call_log == [0]
    # 2017-01-02 + 2000 个工作日 → 最后一根 = 2024-10-11 附近；切片应为闭区间
    assert len(df) > 0
    assert df["date"].iloc[0] >= pd.Timestamp("2024-05-06")
    assert df["date"].iloc[-1] <= pd.Timestamp("2024-05-20")
    # 闭区间：恰好等于边界的 bar 应包含在内
    assert (df["date"] == pd.Timestamp("2024-05-06")).sum() == 1
    assert (df["date"] == pd.Timestamp("2024-05-20")).sum() == 1


async def test_range_spans_multiple_pages() -> None:
    """start_date 在第 2 页内：翻页到覆盖 start_date 为止。"""
    global call_log
    call_log = []
    target = _MASTER["date"].iloc[800]
    with patch("easy_tdx.web.klines.fetch_qfq_klines", side_effect=_fake_fetch):
        df = await fetch_bars_range(None, None, "SZ", "000001", "DAY", target.strftime("%Y-%m-%d"))
    assert 800 in call_log  # 翻到了第 2 页
    assert 1600 not in call_log  # 覆盖 start_date 后停
    assert len(df) == _TOTAL - 800  # end_date 缺省 → 到最新一根
    assert df["date"].iloc[0] == target


async def test_range_earlier_than_ipo_returns_all() -> None:
    """start_date 早于上市日：翻到历史尽头（短页）收尾，返回上市以来全部。"""
    global call_log
    call_log = []
    with patch("easy_tdx.web.klines.fetch_qfq_klines", side_effect=_fake_fetch):
        df = await fetch_bars_range(None, None, "SZ", "000001", "DAY", "2010-01-01")
    # 2000 根 = 3 页（0/800/1600，第 3 页短页 400 根触发收尾）
    assert call_log == [0, 800, 1600]
    assert len(df) == _TOTAL
    assert df["date"].iloc[0] == _MASTER["date"].iloc[0]


async def test_range_future_returns_empty() -> None:
    """区间完全晚于最新 bar：一页即覆盖，切片为空。"""
    global call_log
    call_log = []
    with patch("easy_tdx.web.klines.fetch_qfq_klines", side_effect=_fake_fetch):
        df = await fetch_bars_range(None, None, "SZ", "000001", "DAY", "2030-01-01")
    assert call_log == [0]
    assert df.empty


async def test_range_invalid_start_date_returns_empty() -> None:
    """非法日期字符串：不抛异常，返回空 DataFrame。"""
    df = await fetch_bars_range(None, None, "SZ", "000001", "DAY", "not-a-date")
    assert df.empty


async def test_range_end_date_inclusive() -> None:
    """end_date 当天的 bar 包含在内（闭区间语义，次日 00:00 前均有效）。"""
    global call_log
    call_log = []
    with patch("easy_tdx.web.klines.fetch_qfq_klines", side_effect=_fake_fetch):
        df = await fetch_bars_range(None, None, "SZ", "000001", "DAY", "2024-05-06", "2024-05-06")
    assert len(df) == 1
    assert df["date"].iloc[0] == pd.Timestamp("2024-05-06")


async def test_range_minute_datetime_column() -> None:
    """分钟线 datetime 列（含时分秒）同样支持区间切片。"""
    global call_log
    call_log = []
    minutes = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-05-06 09:30", periods=2000, freq="5min"),
            "close": [float(i) for i in range(2000)],
        }
    )

    def _fake_min(mac, tdx, market, code, category, start, count, bar_time="start"):
        call_log.append(start)
        end = 2000 - start
        begin = max(0, end - count)
        return minutes.iloc[begin:end].reset_index(drop=True)

    with patch("easy_tdx.web.klines.fetch_qfq_klines", side_effect=_fake_min):
        df = await fetch_bars_range(None, None, "SZ", "000001", "MIN_5", "2024-05-06", "2024-05-06")
    # 闭区间含 5/6 全天（次日 00:00 前）
    assert len(df) == int((24 * 60 - 9.5 * 60) / 5)  # 09:30 → 23:55
    assert df["datetime"].iloc[0] == pd.Timestamp("2024-05-06 09:30")
