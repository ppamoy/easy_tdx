"""组合级模型可信度评分（V103）的单元测试。"""

from __future__ import annotations

import pytest

from easy_tdx.backtest.model_trust import compute_portfolio_trust


def _summary(
    symbols: int,
    with_acc: int,
    avg_excess: float,
    avg_ret: float,
    avg_win: float,
    positive: int,
    hit_above: int,
) -> dict:
    return {
        "portfolio": {
            "symbols": symbols,
            "symbols_with_accuracy": with_acc,
            "avg_hit_rate": 0.5 + avg_excess,
            "avg_excess_hit_rate": avg_excess,
            "avg_win_rate": avg_win,
            "avg_total_return": avg_ret,
            "avg_sharpe": 0.8,
            "positive_symbols": positive,
            "hit_above_baseline": hit_above,
        },
        "symbols": [],
    }


class TestComputePortfolioTrust:
    def test_good_portfolio_high(self) -> None:
        rep = compute_portfolio_trust(_summary(3, 3, 0.12, 0.2, 0.58, 2, 2))
        assert rep["score"] >= 70
        assert rep["grade"] == "高"
        assert set(rep["components"].keys()) == {"accuracy", "robustness", "performance"}
        assert "组合可信度" in rep["verdict"]

    def test_bad_portfolio_low(self) -> None:
        rep = compute_portfolio_trust(_summary(3, 3, -0.08, -0.15, 0.3, 0, 0))
        assert rep["score"] <= 40
        assert rep["grade"] == "低"

    def test_empty(self) -> None:
        rep = compute_portfolio_trust(None)
        assert rep["score"] == pytest.approx(37.0)
        assert rep["grade"] == "低"

    def test_no_symbols(self) -> None:
        rep = compute_portfolio_trust({"portfolio": {"symbols": 0}})
        assert rep["grade"] == "低"

    def test_score_range(self) -> None:
        cases = [
            _summary(5, 5, 0.1, 0.3, 0.6, 4, 4),
            _summary(4, 2, 0.0, 0.0, 0.5, 2, 1),
            _summary(4, 4, -0.15, -0.3, 0.2, 0, 0),
        ]
        for s in cases:
            rep = compute_portfolio_trust(s)
            assert 0 <= rep["score"] <= 100
            assert rep["grade"] in ("高", "中", "低")
