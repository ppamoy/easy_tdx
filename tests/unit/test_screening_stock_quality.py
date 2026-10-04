"""web/routers/screening.py _calc_stock_quality 集成测试（V428/V437 验证）。"""

from __future__ import annotations

from types import SimpleNamespace

from easy_tdx.web.routers.screening import _calc_stock_quality


def _mmd(
    mmd_type: str, index: int, grade: str | None, strength: str, rr: float | None
) -> SimpleNamespace:
    scorecard = (
        {"overall_grade": grade, "strength": strength, "overall_score": 80.0} if grade else {}
    )
    decision = {"risk_reward_ratio": rr} if rr is not None else {}
    return SimpleNamespace(
        mmd_type=SimpleNamespace(value=mmd_type),
        bi=SimpleNamespace(index=index),
        _signal_quality_scorecard=scorecard,
        _decision_support=decision,
    )


def _result(bis=0, zss=0, mmds=None, bcs=0) -> SimpleNamespace:
    return SimpleNamespace(
        bis=[SimpleNamespace() for _ in range(bis)],
        zss=[SimpleNamespace() for _ in range(zss)],
        mmds=mmds or [],
        bcs=[SimpleNamespace() for _ in range(bcs)],
    )


class TestCalcStockQuality:
    def test_empty_structure(self) -> None:
        """无结构时仅基础分 50。"""
        assert _calc_stock_quality(_result()) == 50

    def test_full_structure_with_v102_scores_high_not_100(self) -> None:
        """完整结构 + V102 A/strong + RR 2.5 + 买入 → 仍是**高分**。

        ⚠️ V733 五之二十六：本测试原先叫 `..._clamps_100`，断言
        `_calc_stock_quality(...) == 100` —— 它锁定的正是**那个缺陷本身**：
        阶梯加分 + `min(score, 100)` 封顶，导致真实数据 95% 的股票都是 100 分，
        端点 `sort(key=quality_score)` 后再切 `top_n` **形同虚设**
        （实测质量分 vs 未来 20 日收益 ρ=+0.13 p=0.16，排不出）。

        已改为断言**连续区间**而非恰好 100：
        - 明显高于中等结构（保住"结构多 → 分高"这个原有语义）；
        - 不超过 100（封顶仍在，防止无上限）。
        系数改为**从实测分布反推**后，满分率 95% → 5%。
        """
        r = _result(
            bis=20,
            zss=5,
            mmds=[_mmd("3buy", 0, "A", "strong", 2.5)],
            bcs=3,
        )
        mid = _result(
            bis=10,
            zss=3,
            mmds=[_mmd("3buy", 0, "A", "strong", 2.5)],
            bcs=1,
        )
        full_score = _calc_stock_quality(r)
        mid_score = _calc_stock_quality(mid)
        assert mid_score < full_score, "结构更多仍应得分更高"
        assert 50 < mid_score < full_score <= 100, (
            f"应为连续分数区间，实际 {mid_score} / {full_score}"
        )

    def test_v102_bonus_increases_score(self) -> None:
        """有 V102 A 级比无 V102 分数更高。"""
        base = _result(
            bis=10,
            zss=3,
            mmds=[_mmd("3buy", 0, None, "", None)],
            bcs=0,
        )
        with_v102 = _result(
            bis=10,
            zss=3,
            mmds=[_mmd("3buy", 0, "A", "strong", 2.0)],
            bcs=0,
        )
        assert _calc_stock_quality(with_v102) > _calc_stock_quality(base)
