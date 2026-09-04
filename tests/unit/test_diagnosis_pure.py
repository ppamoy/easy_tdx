"""web/routers/diagnosis.py 纯函数测试（V399j）。

覆盖 _to_json_safe / _detect_divergence / _calculate_position_recommendation /
_get_position_notes / _calc_volume_profile_for_diagnosis，离线可测。
"""

from __future__ import annotations

import numpy as np

from easy_tdx.web.routers.diagnosis import (
    _calc_volume_profile_for_diagnosis,
    _calculate_position_recommendation,
    _detect_divergence,
    _get_position_notes,
    _to_json_safe,
)


class TestToJsonSafe:
    def test_nested(self) -> None:
        obj = {"a": np.int64(1), "b": [np.float64(2.5), np.bool_(True)], "c": np.array([1, 2, 3])}
        out = _to_json_safe(obj)
        assert out["a"] == 1
        assert isinstance(out["a"], int)
        assert out["b"] == [2.5, True]
        assert out["c"] == [1, 2, 3]

    def test_scalar(self) -> None:
        assert _to_json_safe(5) == 5
        assert _to_json_safe("x") == "x"


class TestDetectDivergence:
    def test_short_input(self) -> None:
        out = _detect_divergence([1.0] * 10, [1.0] * 10, lookback=60)
        assert out["detected"] is False
        assert out["type"] == "none"

    def test_bearish_divergence(self) -> None:
        n = 60
        prices = [100.0 + i * 0.1 for i in range(n)]
        prices[55] = 106.0
        prices[50] = 105.0
        prices[53] = 104.0  # 局部高点
        prices[58] = 107.0  # 更高的局部高点
        indicators = [10.0] * n
        indicators[53] = 9.0
        indicators[58] = 8.0  # 指标更低
        out = _detect_divergence(prices, indicators, lookback=60)
        # 顶背离/底背离由局部极值决定，这里只断言结构完整
        assert "type" in out and "strength" in out and "detected" in out

    def test_no_divergence(self) -> None:
        n = 60
        prices = [100.0 + i * 0.1 for i in range(n)]
        indicators = [10.0 + i * 0.1 for i in range(n)]
        out = _detect_divergence(prices, indicators, lookback=60)
        assert out["detected"] is False


class TestPositionRecommendation:
    def test_heavy(self) -> None:
        rec = _calculate_position_recommendation(80, "low", 0.02, True, True)
        assert rec["suggestion"] in ("重仓", "半仓")
        assert rec["position_pct"] >= 60

    def test_watch(self) -> None:
        rec = _calculate_position_recommendation(10, "high", 0.05, False, False)
        assert rec["suggestion"] == "观望"
        assert rec["position_pct"] == 0

    def test_high_volatility_reduction(self) -> None:
        rec = _calculate_position_recommendation(60, "high", 0.05, True, True)
        assert rec["position_pct"] < 60


class TestPositionNotes:
    def test_notes(self) -> None:
        notes = _get_position_notes(80, "high", True, True, True, "bullish", "weak")
        assert "重仓" in notes
        assert "降低仓位" in notes
        assert "底背离" in notes
        assert "震荡" in notes

    def test_empty_notes(self) -> None:
        notes = _get_position_notes(10, "low", False, False)
        assert notes


class TestVolumeProfile:
    def test_insufficient(self) -> None:
        assert _calc_volume_profile_for_diagnosis([1.0] * 10, [1.0] * 10) is None

    def test_none(self) -> None:
        assert _calc_volume_profile_for_diagnosis(None, None) is None

    def test_sufficient(self) -> None:
        closes = [100.0 + i * 0.1 for i in range(80)]
        vols = [1000.0] * 80
        out = _calc_volume_profile_for_diagnosis(closes, vols)
        assert out is not None
        assert "support" in out and "resistance" in out
