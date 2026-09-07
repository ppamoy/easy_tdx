"""web/routers/screening.py V428 V102 信号质量选股加分 测试。"""

from __future__ import annotations

from types import SimpleNamespace

from easy_tdx.web.routers.screening import _v102_quality_bonus


def _mmd(grade: str, strength: str, overall: float, mmd_type: str = "3buy") -> SimpleNamespace:
    return SimpleNamespace(
        mmd_type=SimpleNamespace(value=mmd_type),
        _signal_quality_scorecard={
            "overall_grade": grade,
            "strength": strength,
            "overall_score": overall,
        },
    )


class TestV102QualityBonus:
    def test_grade_a_strong(self) -> None:
        bonus, reason = _v102_quality_bonus(_mmd("A", "strong", 85.0))
        assert bonus == 20  # 15 + 5
        assert "A" in reason and "strong" in reason

    def test_grade_b_medium(self) -> None:
        bonus, _ = _v102_quality_bonus(_mmd("B", "medium", 70.0))
        assert bonus == 12  # 10 + 2

    def test_grade_c_weak(self) -> None:
        bonus, _ = _v102_quality_bonus(_mmd("C", "weak", 30.0))
        assert bonus == 5  # 仅 C 级

    def test_no_scorecard(self) -> None:
        mmd = SimpleNamespace(mmd_type=SimpleNamespace(value="1buy"))
        bonus, reason = _v102_quality_bonus(mmd)
        assert bonus == 0
        assert reason == ""
