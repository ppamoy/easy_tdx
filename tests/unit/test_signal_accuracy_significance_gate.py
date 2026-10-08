"""V736 P0：verdict 的「显著」二字必须有统计依据，不许 n=1 就宣称显著。

为什么必须锁死这条（实测发现的严重误导，不是理论风险）
------------------------------------------------------
修复前 ``_verdict`` / ``_signal_type_verdict`` 只做 ``excess > 0.05`` 的
**裸阈值判断**：不看样本量、没有 p 值、没有置信区间。实测构造出一个
**n=1 条信号**就能让 verdict 输出：

    「买入信号 1 个；信号命中率显著高于随机入场基准」

而该字符串经 web/routers/chanlun.py、web/routers/stock_pick.py、
backtest/engine.py 三处直接显示在 UI「信号准确度」面板上，前端
ChanlunAccuracyPanel.vue 还明写「绿色 = 显著优于随机」。
用户看到「显著」合理推断是「统计上显著好于抛硬币」——这个推断当时是**错的**。

修复后「显著」必须同时过三关（缺一不可）：
  1. 效应量 > ``_EXCESS_SIGNIFICANT``
  2. 样本量 ≥ ``_MIN_N_FOR_SIGNIFICANCE``
  3. 比例 z 检验 |z| ≥ 1.96

本文件把所有关卡都钉死，任何一关被拆掉都会失败。
"""

from __future__ import annotations

import pandas as pd
import pytest

from easy_tdx.backtest.signal_accuracy import (
    _EXCESS_SIGNIFICANT,
    _MIN_N_FOR_SIGNIFICANCE,
    _is_significant,
    compute_signal_accuracy,
)


def _frame(closes: list[float]) -> pd.DataFrame:
    df = pd.DataFrame({"close": closes})
    df["datetime"] = pd.date_range("2024-01-01", periods=len(df))
    return df


def _trades(df: pd.DataFrame, indices: list[int]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "datetime": [df["datetime"].iloc[i] for i in indices],
            "direction": ["BUY"] * len(indices),
            "rejected": [False] * len(indices),
        }
    )


class TestSignificanceGate:
    """_is_significant 的三关：效应量 / 样本量 / z 检验。"""

    def test_huge_excess_with_n1_is_not_significant(self) -> None:
        """核心回归：效应量再大，n=1 也不许判显著（修复前会判）。"""
        # excess=+0.50 远超 0.05 门槛，但 n=1
        assert _is_significant(0.50, 1, 0.50) is False

    def test_small_excess_below_threshold_never_significant(self) -> None:
        """效应量不够时，样本量再大也不许判显著。"""
        assert _is_significant(_EXCESS_SIGNIFICANT - 0.001, 100_000, 0.50) is False

    def test_sample_size_below_minimum_never_significant(self) -> None:
        """样本量不足时，效应量再大也不许判显著。"""
        n = _MIN_N_FOR_SIGNIFICANCE - 1
        assert _is_significant(0.99, n, 0.50) is False

    def test_z_test_gate_tightens_with_sample_size(self) -> None:
        """同效应量下，判定必须随 n 收紧 —— 修复前完全不随 n 变。"""
        excess = _EXCESS_SIGNIFICANT + 0.01  # 刚过效应量门槛
        # n 刚达标：z 不够 → 不显著
        assert _is_significant(excess, _MIN_N_FOR_SIGNIFICANCE, 0.50) is False
        # n 很大：z 足够 → 显著
        assert _is_significant(excess, 5000, 0.50) is True

    def test_genuinely_strong_and_large_sample_is_significant(self) -> None:
        """对照组：效应量大且样本足时必须仍判显著（不要把门关死）。"""
        assert _is_significant(0.50, 100, 0.50) is True

    def test_baseline_at_extremes_does_not_crash(self) -> None:
        """基线命中率为 0 或 1 时 SE=0，不得除零崩溃。"""
        assert _is_significant(0.20, 100, 0.0) is False
        assert _is_significant(0.20, 100, 1.0) is False


class TestVerdictWording:
    """端到端：真实跑 compute_signal_accuracy，检查文案不许滥用「显著」。"""

    def test_single_signal_never_claims_significance(self) -> None:
        """n=1 信号的 verdict 不得出现「显著高于/显著优于」这类结论。

        这是本轮实测复现的原始 bug：单条信号落在低点附近就能让
        excess_hit_rate 达到 +0.4957，从而触发「显著高于随机入场基准」。
        """
        # 先跌后涨，把唯一的买入信号放在最低点附近 → 命中而随机基线约 0.5
        closes = [100 - i * 0.5 for i in range(60)] + [70 + i * 1.0 for i in range(60)]
        df = _frame(closes)
        report = compute_signal_accuracy(df, _trades(df, [59]))

        verdict = str(report.get("verdict", ""))
        assert "显著高于" not in verdict, f"n=1 不得宣称显著：{verdict}"
        assert "显著优于" not in verdict, f"n=1 不得宣称显著：{verdict}"
        # 且必须明确告知样本不足
        assert "不足以判断显著性" in verdict, f"应说明样本不足：{verdict}"

    @pytest.mark.parametrize("n", [1, 5, 15])
    def test_small_samples_never_claim_significance(self, n: int) -> None:
        """小样本一律不得宣称显著（覆盖 1/5/15）。"""
        closes = [100.0 + (i % 17) - 8 for i in range(200)]
        df = _frame(closes)
        indices = list(range(10, 10 + n))
        report = compute_signal_accuracy(df, _trades(df, indices))

        verdict = str(report.get("verdict", ""))
        assert "显著高于" not in verdict, f"n={n} 不得宣称显著：{verdict}"
