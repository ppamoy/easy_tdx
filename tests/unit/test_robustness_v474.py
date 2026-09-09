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
