"""web/routers/screening.py V437 V102 风险回报比选股加分 测试。"""

from __future__ import annotations

from types import SimpleNamespace

from easy_tdx.web.routers.screening import _v102_rr_bonus


def _mmd(rr: float | None) -> SimpleNamespace:
    decision = {"risk_reward_ratio": rr} if rr is not None else {}
    return SimpleNamespace(_decision_support=decision)


class TestV102RrBonus:
    def test_excellent(self) -> None:
        bonus, reason = _v102_rr_bonus(_mmd(2.5))
        assert bonus == 10
        assert "RR=2.5" in reason

    def test_good(self) -> None:
        assert _v102_rr_bonus(_mmd(1.6))[0] == 7

    def test_acceptable(self) -> None:
        assert _v102_rr_bonus(_mmd(1.2))[0] == 3

    def test_poor(self) -> None:
        assert _v102_rr_bonus(_mmd(0.5))[0] == 0

    def test_missing(self) -> None:
        bonus, reason = _v102_rr_bonus(_mmd(None))
        assert bonus == 0
        assert reason == ""
