"""web/routers/chanlun.py _build_signal_explanation 测试（V422）。"""

from __future__ import annotations

from types import SimpleNamespace

from easy_tdx.web.routers.chanlun import _build_signal_explanation


class TestBuildSignalExplanation:
    def test_with_advice(self) -> None:
        mmd = SimpleNamespace(
            mmd_type=SimpleNamespace(value="3buy"),
            confidence=0.9,
            msg="中枢突破后回踩确认",
            _decision_support={"action_recommendation": "买入"},
        )
        out = _build_signal_explanation(mmd)
        assert "3buy" in out
        assert "90%" in out
        assert "买入" in out
        assert "中枢突破后回踩确认" in out

    def test_without_advice(self) -> None:
        mmd = SimpleNamespace(
            mmd_type=SimpleNamespace(value="1sell"),
            confidence=0.55,
            msg="",
            _decision_support={},
        )
        out = _build_signal_explanation(mmd)
        assert "1sell" in out
        assert "55%" in out
