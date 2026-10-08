"""翻页取数截断的「可感知性」测试。

背景（本项目 AGENTS.md 记的头号 bug 源：静默失败）：
``_fetch_portfolio_bars`` / ``_fetch_multi_strategy_bars`` 原先在翻页中途
某一页抛异常时直接 ``except Exception: break`` —— 该标的**已取到的页**照样
参与回测，于是历史少掉一段，而调用方完全不知道，回测结论建立在残缺数据上。

修复后：中途失败必须留下可见痕迹
（warning 日志 + df.attrs["bars_truncated"] + 结果里的
``data_incomplete``/``incomplete_symbols``/``warnings``）。

本文件断言的都是**行为**（真调用 fetch 函数、真跑 _run_*_backtest），
不做源码文本断言。
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import pytest

from easy_tdx.backtest.portfolio_engine import StockData
from easy_tdx.web.routers import backtest as bt

# ── 夹具 ──────────────────────────────────────────────────────────────────────


def _page(n: int, start: str, seed: int = 0) -> pd.DataFrame:
    """造一页日线（``datetime`` 列，供回测引擎直接消费）。"""
    close = 10.0 + seed + (pd.Series(range(n)) % 7) * 0.1
    return pd.DataFrame(
        {
            "datetime": pd.date_range(start, periods=n, freq="B"),
            "open": close - 0.1,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "vol": [5000.0] * n,
            "amount": close * 5000,
        }
    )


class _FlakyFetch:
    """第 ``fail_on_page`` 页抛异常的假 fetch（其余页返回数据）。"""

    def __init__(self, fail_on_page: int, pages: list[pd.DataFrame]) -> None:
        self.fail_on_page = fail_on_page
        self.pages = pages
        self.calls: list[int] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> pd.DataFrame:
        # 调用约定：fetch_qfq_klines(mac, client, market, code, category, start, count)
        page = int(args[5]) // 800
        self.calls.append(page)
        if page == self.fail_on_page:
            raise RuntimeError(f"模拟第 {page} 页取数失败")
        return self.pages[page]


# ── 问题 2：翻页中途失败必须「可感知」 ─────────────────────────────────────────


async def test_portfolio_page2_failure_is_perceivable(monkeypatch) -> None:
    """真调用 _fetch_portfolio_bars：第 2 页失败 → 结果可感知截断。"""
    fake = _FlakyFetch(
        fail_on_page=1,
        pages=[_page(800, "2021-01-01"), _page(800, "2018-01-01")],
    )
    monkeypatch.setattr("easy_tdx.web.klines.fetch_qfq_klines", fake)

    stocks = await bt._fetch_portfolio_bars(None, ["SZ:000001"], "DAY", None, None, None)

    # 已取到第 1 页 → 标的不会被整个丢弃（这正是危险所在：残缺数据会被拿去回测）
    assert len(stocks) == 1, "中途失败时已取到的页仍会返回"
    assert len(stocks[0].df) == 800, "只拿到了第 1 页的 800 根，历史少掉一段"

    # 牙齿：截断必须可感知
    assert stocks[0].df.attrs.get(bt.BARS_TRUNCATED_ATTR) is True
    assert bt._collect_incomplete_symbols(stocks) == ["SZ000001"]


async def test_portfolio_page2_failure_logs_warning(monkeypatch, caplog) -> None:
    """中途失败必须留 warning 日志（否则线上排查无从下手）。"""
    fake = _FlakyFetch(
        fail_on_page=1,
        pages=[_page(800, "2021-01-01"), _page(800, "2018-01-01")],
    )
    monkeypatch.setattr("easy_tdx.web.klines.fetch_qfq_klines", fake)

    with caplog.at_level(logging.WARNING, logger="easy_tdx.web.routers.backtest"):
        await bt._fetch_portfolio_bars(None, ["SZ:000001"], "DAY", None, None, None)

    warning_texts = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("不完整" in t for t in warning_texts), f"缺少截断 warning: {warning_texts}"


def test_run_portfolio_backtest_surfaces_incomplete(monkeypatch) -> None:
    """端到端：_run_portfolio_backtest 结果里显式标记数据不完整。"""
    df = _page(300, "2023-01-01")
    df.attrs[bt.BARS_TRUNCATED_ATTR] = True
    stocks = [StockData(code="000001", market="SZ", df=df)]

    req = _make_portfolio_req()
    result = bt._run_portfolio_backtest(stocks, req)

    assert result["data_incomplete"] is True
    assert result["incomplete_symbols"] == ["SZ000001"]
    assert any("截断" in w for w in result["warnings"])
    # 既有字段不受影响（不破坏 API 契约）
    assert "total_performance" in result
    assert "individual_results" in result


def test_run_portfolio_backtest_clean_data_has_no_flag() -> None:
    """对照组：数据完整时不打任何不完整标记（不能误报）。"""
    df = _page(300, "2023-01-01")
    stocks = [StockData(code="000001", market="SZ", df=df)]

    result = bt._run_portfolio_backtest(stocks, _make_portfolio_req())

    assert "data_incomplete" not in result
    assert "incomplete_symbols" not in result
    assert "warnings" not in result


async def test_multi_strategy_page2_failure_is_perceivable(monkeypatch) -> None:
    """多策略槽位同样：第 2 页失败必须可感知。"""
    fake = _FlakyFetch(
        fail_on_page=1,
        pages=[_page(800, "2021-01-01"), _page(800, "2018-01-01")],
    )
    monkeypatch.setattr("easy_tdx.web.klines.fetch_qfq_klines", fake)

    item = _make_slot_item()
    slots = await bt._fetch_multi_strategy_bars(None, [item], None)

    assert len(slots) == 1
    assert len(slots[0].df) == 800
    assert slots[0].df.attrs.get(bt.BARS_TRUNCATED_ATTR) is True
    assert bt._collect_incomplete_symbols(slots) == ["SH:601088"]


def test_multi_strategy_run_surfaces_incomplete() -> None:
    """多策略 _run 结果里也要能感知截断。"""
    df = _page(300, "2023-01-01")
    df.attrs[bt.BARS_TRUNCATED_ATTR] = True

    slot = _make_slot()
    slot.df = df

    result = bt._run_multi_strategy_backtest([slot], _make_multi_req())

    assert result["data_incomplete"] is True
    assert result["incomplete_symbols"] == ["SH:601088"]
    assert any("截断" in w for w in result["warnings"])
    assert "total_performance" in result


# ── 辅助构造 ──────────────────────────────────────────────────────────────────


def _make_portfolio_req() -> Any:
    from easy_tdx.web.backtest_schemas import PortfolioBacktestRequest

    return PortfolioBacktestRequest(
        strategy="ma_cross", params={"fast": 5, "slow": 20}, stocks=["SZ:000001"], cash=100000
    )


def _make_multi_req() -> Any:
    from easy_tdx.web.backtest_schemas import MultiStrategyBacktestRequest

    return MultiStrategyBacktestRequest(
        items=[
            {
                "symbol": "SH:601088",
                "strategy": "ma_cross",
                "params": {"fast": 5, "slow": 20},
            }
        ],
        cash=100000,
    )


def _make_slot_item() -> Any:
    return _make_multi_req().items[0]


def _make_slot() -> Any:
    from easy_tdx.backtest.multi_strategy_engine import StrategySlot
    from easy_tdx.backtest.strategies import get_registry

    df = _page(300, "2023-01-01")
    return StrategySlot(
        label="双均线",
        symbol="SH:601088",
        strategy=get_registry().get("ma_cross").build({"fast": 5, "slow": 20}),
        df=df,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
