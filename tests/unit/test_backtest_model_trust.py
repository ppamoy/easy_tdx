"""模型可信度综合评分（V101）的单元测试。"""

from __future__ import annotations

import pytest

from easy_tdx.backtest.model_trust import (
    _accuracy_score,
    _performance_score,
    _robustness_score,
    compute_model_trust,
)


def _good_sa() -> dict:
    return {
        "buy": {
            "horizons": {
                "5": {
                    "count": 30,
                    "hit_rate": 0.7,
                    "baseline_hit_rate": 0.5,
                    "excess_hit_rate": 0.2,
                }
            }
        },
        "benchmark": {"alpha": 0.15, "buy_hold_return": 0.2, "strategy_return": 0.35},
    }


def _bad_sa() -> dict:
    return {
        "buy": {
            "horizons": {
                "5": {
                    "count": 20,
                    "hit_rate": 0.4,
                    "baseline_hit_rate": 0.5,
                    "excess_hit_rate": -0.1,
                }
            }
        },
        "benchmark": {"alpha": -0.15},
    }


def _good_rob() -> dict:
    return {
        "overfit_likely": False,
        "consistency": {
            "segments_analyzed": 3,
            "positive_segment_ratio": 0.67,
            "beats_buy_hold_ratio": 0.67,
        },
    }


def _bad_rob() -> dict:
    return {
        "overfit_likely": True,
        "consistency": {
            "segments_analyzed": 3,
            "positive_segment_ratio": 0.33,
            "beats_buy_hold_ratio": 0.0,
        },
    }


class TestAccuracyScore:
    def test_above_baseline(self) -> None:
        score, comp = _accuracy_score(_good_sa())
        assert 0.0 <= score <= 1.0
        assert score > 0.7
        assert comp["excess_hit_rate"] == pytest.approx(0.2)

    def test_below_baseline(self) -> None:
        score, _ = _accuracy_score(_bad_sa())
        assert score < 0.3

    def test_missing(self) -> None:
        score, comp = _accuracy_score(None)
        assert score == pytest.approx(0.3)
        assert "note" in comp

    def test_low_pf_discounts(self) -> None:
        """V433: 命中率优但 PF<1（赢小亏大）时准确度分打折。"""
        sa = _good_sa()
        sa["buy"]["horizons"]["5"]["profit_factor"] = 0.6
        score, comp = _accuracy_score(sa)
        assert comp["profit_factor"] == pytest.approx(0.6)
        assert score == pytest.approx(0.8)  # 1.0 * 0.8


class TestRobustnessScore:
    def test_overfit_drags(self) -> None:
        score, comp = _robustness_score(_bad_rob())
        assert comp["overfit_likely"] is True
        assert score == pytest.approx(0.2)

    def test_consistent(self) -> None:
        score, _ = _robustness_score(_good_rob())
        assert score > 0.6

    def test_missing(self) -> None:
        score, comp = _robustness_score(None)
        assert score == pytest.approx(0.5)


class TestPerformanceScore:
    def test_good_performance(self) -> None:
        score, comp = _performance_score({"total_return": 0.35, "win_rate": 0.62}, _good_sa())
        assert score > 0.7
        assert comp["alpha"] == pytest.approx(0.15)

    def test_missing(self) -> None:
        score, comp = _performance_score(None, None)
        assert score == pytest.approx(0.3)


class TestComputeModelTrust:
    def test_good_model_high(self) -> None:
        rep = compute_model_trust({"total_return": 0.35, "win_rate": 0.62}, _good_sa(), _good_rob())
        assert rep["score"] >= 70
        assert rep["grade"] == "高"
        assert set(rep["components"].keys()) == {"accuracy", "robustness", "performance"}
        assert "综合可信度" in rep["verdict"]

    def test_bad_model_low(self) -> None:
        rep = compute_model_trust({"total_return": -0.1, "win_rate": 0.3}, _bad_sa(), _bad_rob())
        assert rep["score"] <= 40
        assert rep["grade"] == "低"

    def test_empty_conservative(self) -> None:
        rep = compute_model_trust({}, None, None)
        # 无数据时保守低分
        assert rep["score"] < 50
        assert rep["grade"] == "低"
        assert rep["score"] == pytest.approx(37.0)

    def test_score_range(self) -> None:
        for perf, sa, rob in [
            ({"total_return": 0.5, "win_rate": 0.7}, _good_sa(), _good_rob()),
            ({"total_return": 0.0, "win_rate": 0.5}, None, None),
            ({"total_return": -0.5, "win_rate": 0.1}, _bad_sa(), _bad_rob()),
        ]:
            rep = compute_model_trust(perf, sa, rob)
            assert 0 <= rep["score"] <= 100
            assert rep["grade"] in ("高", "中", "低")
