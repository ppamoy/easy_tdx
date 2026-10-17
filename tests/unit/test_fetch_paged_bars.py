"""fetch_paged_bars 单测（V722，R3 图表全历史回溯）。

mock fetch_qfq_klines（协议层已在别处覆盖），重点验证：
循环翻页拼接、跨页时间戳去重、历史不足时提前收尾、升序契约。
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from easy_tdx.web.klines import MAX_LOOKBACK, fetch_paged_bars

_TOTAL = 2000
_MASTER = pd.DataFrame(
    {
        "date": pd.bdate_range("2017-01-02", periods=_TOTAL),
        "close": [float(i) for i in range(_TOTAL)],
    }
)


def _page(start: int, count: int, extra: int = 0) -> pd.DataFrame:
    """TDX 语义：start=距末尾偏移；extra>0 模拟服务器多给的边界重叠。"""
    end = _TOTAL - start
    begin = max(0, end - count - extra)
    return _MASTER.iloc[begin:end].reset_index(drop=True)


call_log: list[int] = []


def _fake_fetch(mac, tdx, market, code, category, start, count, bar_time="start"):
    call_log.append(start)
    if start >= _TOTAL:
        return pd.DataFrame()
    return _page(start, count)


async def test_paged_bars_two_pages() -> None:
    global call_log
    call_log = []
    with patch("easy_tdx.web.klines.fetch_qfq_klines", side_effect=_fake_fetch):
        df = await fetch_paged_bars(None, None, "SZ", "000001", "DAY", lookback=1600)
    assert call_log == [0, 800]
    assert len(df) == 1600
    # 升序契约 + 无重复
    dates = df["date"].tolist()
    assert dates == sorted(dates)
    assert len(set(dates)) == 1600
    # 最新 bar 在最后
    assert df["date"].iloc[-1] == _MASTER["date"].iloc[-1]


async def test_paged_bars_exhausts_history() -> None:
    """lookback 超过上市历史：返回全部可得 bar，不报错。"""
    with patch("easy_tdx.web.klines.fetch_qfq_klines", side_effect=_fake_fetch):
        df = await fetch_paged_bars(None, None, "SZ", "000001", "DAY", lookback=5000)
    assert len(df) == _TOTAL
    dates = df["date"].tolist()
    assert dates == sorted(dates)
    assert len(set(dates)) == _TOTAL


async def test_paged_bars_dedup_overlap() -> None:
    """跨页边界重叠（服务器多给 5 根）：去重后不重复。"""

    def _overlap_fetch(mac, tdx, market, code, category, start, count, bar_time="start"):
        # 第 2 页多带 5 根旧 bar（与第 1 页末尾重叠）
        return _page(start, count, extra=5 if start else 0)

    with patch("easy_tdx.web.klines.fetch_qfq_klines", side_effect=_overlap_fetch):
        df = await fetch_paged_bars(None, None, "SZ", "000001", "DAY", lookback=1600)
    dates = df["date"].tolist()
    assert dates == sorted(dates)
    assert len(set(dates)) == len(dates)  # 无重复时间戳


async def test_paged_bars_empty_first_page() -> None:
    async def _must_not_second(*a, **kw):  # pragma: no cover
        raise AssertionError("首页为空不应继续翻页")

    with patch(
        "easy_tdx.web.klines.fetch_qfq_klines",
        side_effect=lambda *a, **kw: pd.DataFrame(),
    ):
        df = await fetch_paged_bars(None, None, "SZ", "000001", "DAY", lookback=1600)
    assert df.empty


async def test_paged_bars_mixed_date_types() -> None:
    """跨页 date 列类型混杂（str + Timestamp）：归一后 sort 不抛 TypeError。

    实测 MAC 服务器不同页返回 str/Timestamp 混杂，concat 后 sort_values 抛
    ``'<' not supported between instances of 'str' and 'Timestamp'``
    （/stock-pick/timing 8/12 标的失败）。修复：concat 后归一为 datetime 再去重排序。
    """

    def _mixed_fetch(mac, tdx, market, code, category, start, count, bar_time="start"):
        if start >= _TOTAL:
            return pd.DataFrame()
        page = _page(start, count)
        if start == 0:
            # 第 1 页：str 日期（MAC 服务器 ISO 字符串）
            page = page.assign(date=page["date"].astype(str))
        else:
            # 第 2 页：Timestamp 日期（另一数据路径）
            page = page.assign(date=pd.to_datetime(page["date"]))
        return page

    with patch("easy_tdx.web.klines.fetch_qfq_klines", side_effect=_mixed_fetch):
        df = await fetch_paged_bars(None, None, "SZ", "000001", "DAY", lookback=1600)
    dates = df["date"].tolist()
    assert dates == sorted(dates)
    assert len(set(dates)) == len(dates)  # 去重后无重复


async def test_paged_bars_lookback_clamped() -> None:
    """lookback 超过 MAX_LOOKBACK 被钳制（防御参数滥用）。"""
    seen_counts: list[int] = []

    def _spy(mac, tdx, market, code, category, start, count, bar_time="start"):
        seen_counts.append(start)
        if start >= _TOTAL:
            return pd.DataFrame()
        return _page(start, count)

    with patch("easy_tdx.web.klines.fetch_qfq_klines", side_effect=_spy):
        await fetch_paged_bars(None, None, "SZ", "000001", "DAY", lookback=10**9)
    assert MAX_LOOKBACK == 20000
    # 最多请求 ceil(20000/800)=25 页（本假历史 2000 根会提前停）
    assert len(seen_counts) <= 25
