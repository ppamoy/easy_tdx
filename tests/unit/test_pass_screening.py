"""web/routers/screening.py _pass_screening 测试（选股门槛）。"""

from __future__ import annotations

from easy_tdx.web.routers.screening import _pass_screening


class TestPassScreening:
    def test_no_signal_fails(self) -> None:
        r = {"buy_1_count": 0, "sell_1_count": 0, "quality_score": 80}
        assert _pass_screening(r, "all", True) is False

    def test_low_quality_fails(self) -> None:
        r = {"buy_1_count": 1, "sell_1_count": 0, "quality_score": 40}
        assert _pass_screening(r, "all", True) is False

    def test_signal_and_quality_passes(self) -> None:
        r = {"buy_1_count": 1, "sell_1_count": 0, "quality_score": 75}
        assert _pass_screening(r, "all", True) is True

    def test_sell_signal_passes(self) -> None:
        r = {"buy_1_count": 0, "sell_1_count": 2, "quality_score": 65}
        assert _pass_screening(r, "all", True) is True
