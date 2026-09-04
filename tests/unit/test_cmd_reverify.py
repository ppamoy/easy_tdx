"""cli/cmd_reverify.py 重验逻辑边界测试（V398）。

cmd_reverify.py 此前覆盖率 7%。本文件 mock store 记录，覆盖 _reverify_one 的
策略未注册/单标缺 symbol/未知市场等离线错误分支，以及 _reverify_single 的
校验分支。不触网。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from easy_tdx.cli.cmd_reverify import (
    _reverify_multi,
    _reverify_one,
    _reverify_portfolio,
    _reverify_single,
)


def _rec(kind: str, strategy: str = "ma_cross", context: dict | None = None):
    return SimpleNamespace(
        kind=kind,
        strategy=strategy,
        params={},
        context=context or {},
        trade_config={"execution": "next_open"},
    )


class TestReverifyOne:
    def test_unknown_strategy_raises(self) -> None:
        with pytest.raises(ValueError, match="策略未注册"):
            _reverify_one(
                None, _rec("single", strategy="not_real"), 500, "DAILY", "NONE", 1e6, 0.0003, 0.0
            )

    def test_single_missing_symbol_raises(self) -> None:
        with pytest.raises(ValueError, match="缺少 symbol"):
            _reverify_one(None, _rec("single"), 500, "DAILY", "NONE", 1e6, 0.0003, 0.0)

    def test_single_unknown_market_raises(self) -> None:
        with pytest.raises(ValueError, match="未知市场"):
            _reverify_one(
                None,
                _rec("single", context={"symbol": "HK:00700"}),
                500,
                "DAILY",
                "NONE",
                1e6,
                0.0003,
                0.0,
            )

    def test_multi_dispatch_missing_items(self) -> None:
        with pytest.raises(ValueError, match="缺少 context.items"):
            _reverify_one(None, _rec("multi"), 500, "DAILY", "NONE", 1e6, 0.0003, 0.0)

    def test_portfolio_dispatch_missing_stocks(self) -> None:
        with pytest.raises(ValueError, match="缺少 context.stocks"):
            _reverify_one(None, _rec("portfolio"), 500, "DAILY", "NONE", 1e6, 0.0003, 0.0)


class TestReverifyPortfolio:
    def test_missing_stocks(self) -> None:
        with pytest.raises(ValueError, match="缺少 context.stocks"):
            _reverify_portfolio(
                None, {}, 500, "DAILY", "NONE", 1e6, 0.0003, 0.0, "next_open", "2024-01-01"
            )


class TestReverifyMulti:
    def test_missing_items(self) -> None:
        with pytest.raises(ValueError, match="缺少 context.items"):
            _reverify_multi(
                None, {}, 500, "DAILY", "NONE", 1e6, 0.0003, 0.0, "next_open", "2024-01-01"
            )


class TestReverifySingle:
    def test_missing_symbol(self) -> None:
        with pytest.raises(ValueError, match="缺少 symbol"):
            _reverify_single(
                None, {}, 500, "DAILY", "NONE", 1e6, 0.0003, 0.0, "next_open", "2024-01-01"
            )

    def test_unknown_market(self) -> None:
        with pytest.raises(ValueError, match="未知市场"):
            _reverify_single(
                None,
                {"symbol": "HK:00700"},
                500,
                "DAILY",
                "NONE",
                1e6,
                0.0003,
                0.0,
                "next_open",
                "2024-01-01",
            )
