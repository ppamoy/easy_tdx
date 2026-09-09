"""backtest/robustness.py 纯函数测试（V474）。"""

from __future__ import annotations

from types import SimpleNamespace

from easy_tdx.backtest.robustness import _seg_hit_rate


def _seg(h5: dict | None = None, h3: dict | None = None) -> SimpleNamespace:
    horizons: dict = {}
    if h5 is not None:
        horizons["5"] = h5
    if h3 is not None:
        horizons["3"] = h3
    sa = {"buy": {"horizons": horizons}}
    return SimpleNamespace(signal_accuracy=sa)


class TestSegHitRate:
    def test_prefers_5(self) -> None:
        seg = _seg(h5={"count": 10, "hit_rate": 0.7}, h3={"count": 10, "hit_rate": 0.6})
        assert _seg_hit_rate(seg) == 0.7

    def test_fallback_to_3(self) -> None:
        seg = _seg(h5={"count": 0, "hit_rate": 0.0}, h3={"count": 8, "hit_rate": 0.5})
        assert _seg_hit_rate(seg) == 0.5

    def test_no_accuracy_returns_none(self) -> None:
        assert _seg_hit_rate(SimpleNamespace()) is None

    def test_no_buy_returns_none(self) -> None:
        seg = SimpleNamespace(signal_accuracy={})
        assert _seg_hit_rate(seg) is None


class TestSegmentLabels:
    def test_best_segment_label(self) -> None:
        import numpy as np

        from easy_tdx.backtest.robustness import _best_segment_label

        valid = [{"label": "A"}, {"label": "B"}, {"label": "C"}]
        rets = np.array([0.1, 0.3, 0.2])
        assert _best_segment_label(valid, rets) == "B"

    def test_worst_segment_label(self) -> None:
        import numpy as np

        from easy_tdx.backtest.robustness import _worst_segment_label

        valid = [{"label": "A"}, {"label": "B"}, {"label": "C"}]
        rets = np.array([0.1, 0.3, 0.2])
        assert _worst_segment_label(valid, rets) == "A"

    def test_labels_empty(self) -> None:
        import numpy as np

        from easy_tdx.backtest.robustness import _best_segment_label, _worst_segment_label

        assert _best_segment_label([], np.array([])) == ""
        assert _worst_segment_label([], np.array([])) == ""


class TestBuildVerdict:
    def test_overfit_verdict(self) -> None:
        from easy_tdx.backtest.robustness import _build_verdict

        v = _build_verdict([{"label": "A"}], 0.5, 0.4, 0.1, overfit=True)
        assert "过拟合" in v

    def test_robust_verdict(self) -> None:
        from easy_tdx.backtest.robustness import _build_verdict

        v = _build_verdict([{"label": "A"}], 0.5, 0.4, 0.1, overfit=False)
        assert "稳健性尚可" in v

