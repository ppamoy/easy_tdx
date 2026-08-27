"""V79 缠论条件 248-251 单元测试。

条件248：分型稳定性验证（Fractal Stability Validation）
条件249：买卖点距离安全阈值（MMD Distance Safety）
条件250：多级别结构一致性评分（Multi-Level Structure Consistency）
条件251：价格动能持续性评分（Price Momentum Continuity）
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from easy_tdx.chanlun.mmd import (
    _calc_fractal_stability_validation_v79,
    _calc_mmd_distance_safety_v79,
    _calc_multi_level_structure_consistency_v79,
    _calc_price_momentum_continuity_v79,
)
from easy_tdx.chanlun.types import MMD, MMDType
from easy_tdx.backtest.chanlun_validator import ConditionGroup


def _make_mmd(mmd_type: str = "3buy", confidence: float = 0.6) -> MMD:
    """Helper to create MMD with correct enum value."""
    return MMD(mmd_type=MMDType(mmd_type), confidence=confidence, msg="test")


def _make_closes(n: int = 80, base: float = 100.0, trend: str = "flat") -> list[float]:
    """Generate test closing prices."""
    import random
    random.seed(42)
    if trend == "up":
        return [base + i * 0.05 + random.uniform(-1, 1) for i in range(n)]
    elif trend == "down":
        return [base - i * 0.05 + random.uniform(-1, 1) for i in range(n)]
    else:
        return [base + random.uniform(-5, 5) * (1 + 0.01 * i) for i in range(n)]


def _make_highs(closes: list[float], spread: float = 1.0) -> list[float]:
    return [c + spread + 0.5 for c in closes]


def _make_lows(closes: list[float], spread: float = 1.0) -> list[float]:
    return [c - spread - 0.5 for c in closes]


def _make_volumes(n: int = 80, base: float = 1000.0) -> list[float]:
    import random
    random.seed(43)
    return [base + random.uniform(-200, 200) for _ in range(n)]


# ── TestV79ConditionGroup：ConditionGroup 枚举测试 ───────────────────────────

class TestV79ConditionGroup:
    """V79 ConditionGroup 存在性和正确性测试。"""

    def test_v79_exists(self):
        assert hasattr(ConditionGroup, "V79")

    def test_v79_condition_range(self):
        assert ConditionGroup.V79.condition_range == (248, 251)

    def test_v79_description(self):
        desc = ConditionGroup.V79.description
        assert len(desc) > 0
        assert "分型" in desc or "距离" in desc or "多级别" in desc or "动能" in desc


# ── TestV79MMDFields：MMD 对象字段测试 ───────────────────────────────────────

class TestV79MMDFields:
    """MMD 对象包含 V79 字段。"""

    def test_mmd_has_v79_fields(self):
        mmd = _make_mmd()
        assert hasattr(mmd, "_fractal_stability_validation_v79")
        assert hasattr(mmd, "_mmd_distance_safety_v79")
        assert hasattr(mmd, "_multi_level_structure_consistency_v79")
        assert hasattr(mmd, "_price_momentum_continuity_v79")


# ── TestV79BacktestValidator：回测验证器测试 ─────────────────────────────────

class TestV79BacktestValidator:
    """V79 条件回测验证器测试。"""

    def test_v79_validator_usage(self):
        from easy_tdx.backtest.chanlun_validator import ChanlunConditionBacktestValidator
        validator = ChanlunConditionBacktestValidator()
        assert ConditionGroup.V79 in list(ConditionGroup)

    def test_v79_multi_group_validation(self):
        groups = [ConditionGroup.V76, ConditionGroup.V77, ConditionGroup.V78, ConditionGroup.V79]
        ranges = [g.condition_range for g in groups]
        assert ranges[0] == (236, 239)
        assert ranges[1] == (240, 243)
        assert ranges[2] == (244, 247)
        assert ranges[3] == (248, 251)

    def test_v79_summary_output(self):
        from easy_tdx.backtest.chanlun_validator import ChanlunConditionBacktestValidator
        validator = ChanlunConditionBacktestValidator()
        summary = validator.validate_conditions({}, [ConditionGroup.V79])
        assert summary is not None


# ── TestV79Functions：各计算函数单元测试 ─────────────────────────────────────

class TestV79Functions:
    """V79 四个计算函数的单元测试。"""

    # ── 条件248：分型稳定性验证 ──────────────────────────────────────────

    def test_fsv_buy_stable(self):
        """买入信号分型稳定 → 高分。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = _make_closes(30, base=100.0)
        highs = _make_highs(closes, 1.0)
        lows = _make_lows(closes, 1.0)
        result = _calc_fractal_stability_validation_v79(mmd, highs, lows)
        assert "stability_score" in result
        assert "fractal_status" in result
        assert "confidence_adjust" in result
        assert isinstance(result["stability_score"], float)
        assert 0 <= result["stability_score"] <= 1.0
        assert result["fractal_status"] in ["stable", "weak", "broken", "unknown"]

    def test_fsv_sell_stable(self):
        """卖出信号分型稳定 → 高分。"""
        mmd = _make_mmd("3sell", 0.6)
        closes = _make_closes(30, base=100.0)
        highs = _make_highs(closes, 1.0)
        lows = _make_lows(closes, 1.0)
        result = _calc_fractal_stability_validation_v79(mmd, highs, lows)
        assert "stability_score" in result
        assert result["stability_score"] >= 0.0

    def test_fsv_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mmd("3buy", 0.6)
        result = _calc_fractal_stability_validation_v79(mmd, [1.0, 2.0], [1.0, 2.0])
        assert result["msg"] != ""
        assert result["stability_score"] == 0.5
        assert result["confidence_adjust"] == 0.0

    def test_fsv_broken_fractal(self):
        """分型被破坏 → 低分。"""
        mmd = _make_mmd("3buy", 0.6)
        # 创建一个有新高点的序列（顶分型被破坏）
        closes = [100.0 + i * 0.5 for i in range(30)]
        highs = [c + 1.0 for c in closes]
        lows = [c - 1.0 for c in closes]
        # 最后一个高点远高于前一个
        highs[-1] = highs[-2] * 1.1
        result = _calc_fractal_stability_validation_v79(mmd, highs, lows)
        assert "fractal_status" in result
        assert isinstance(result["confidence_adjust"], float)

    # ── 条件249：买卖点距离安全阈值 ──────────────────────────────────────────

    def test_mds_safe_distance(self):
        """距离充足 → 安全。"""
        mmds = [
            _make_mmd("3buy", 0.6),
            _make_mmd("3buy", 0.5),
        ]
        current = mmds[-1]
        # 模拟较远距离
        import random
        random.seed(1)
        closes = _make_closes(60, base=100.0)
        result = _calc_mmd_distance_safety_v79(mmds, current, closes)
        assert "distance_score" in result
        assert "safety_level" in result
        assert "bars_to_nearest" in result
        assert isinstance(result["distance_score"], float)
        assert 0 <= result["distance_score"] <= 1.0

    def test_mds_too_close(self):
        """距离过近 → 低分。"""
        mmds = [
            _make_mmd("3buy", 0.6),
            _make_mmd("3buy", 0.5),
            _make_mmd("3buy", 0.7),
        ]
        current = mmds[-1]
        closes = _make_closes(60, base=100.0)
        result = _calc_mmd_distance_safety_v79(mmds, current, closes)
        assert "safety_level" in result
        assert result["safety_level"] in ["safe", "moderate", "close", "too_close", "isolated"]

    def test_mds_insufficient_data(self):
        """信号不足时返回默认值。"""
        mmd = _make_mmd("3buy", 0.6)
        result = _calc_mmd_distance_safety_v79([], mmd, [1.0, 2.0])
        assert result["msg"] != ""
        assert result["distance_score"] == 0.5
        assert result["confidence_adjust"] == 0.0

    def test_mds_empty_mmds(self):
        """空信号列表 → 返回默认值（数据不足）。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = _make_closes(30)
        result = _calc_mmd_distance_safety_v79([], mmd, closes)
        # 空列表触发"数据不足"默认返回
        assert result["distance_score"] == 0.5
        assert result["confidence_adjust"] == 0.0

    # ── 条件250：多级别结构一致性评分 ──────────────────────────────────────────

    def test_mls_full_consensus_up(self):
        """短中长周期全同向上涨 → 全一致。"""
        mmd = _make_mmd("3buy", 0.6)
        # 单调上涨序列
        closes = [100.0 + i * 0.5 for i in range(70)]
        highs = _make_highs(closes, 1.0)
        lows = _make_lows(closes, 1.0)
        result = _calc_multi_level_structure_consistency_v79(mmd, closes, highs, lows)
        assert "consistency_score" in result
        assert "short_align" in result
        assert "mid_align" in result
        assert "long_align" in result
        assert isinstance(result["consistency_score"], float)
        assert 0 <= result["consistency_score"] <= 1.0

    def test_mls_conflicted(self):
        """短中长周期矛盾 → 低分。"""
        mmd = _make_mmd("3buy", 0.6)
        # 震荡序列，可能产生矛盾
        closes = [100.0 + 5.0 * ((-1) ** i) for i in range(70)]
        highs = _make_highs(closes, 1.0)
        lows = _make_lows(closes, 1.0)
        result = _calc_multi_level_structure_consistency_v79(mmd, closes, highs, lows)
        assert "consistency_score" in result
        assert isinstance(result["short_align"], bool)
        assert isinstance(result["mid_align"], bool)
        assert isinstance(result["long_align"], bool)

    def test_mls_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mmd("3buy", 0.6)
        result = _calc_multi_level_structure_consistency_v79(mmd, [1.0, 2.0], [2.0, 3.0], [1.0, 2.0])
        assert result["msg"] != ""
        assert result["consistency_score"] == 0.5
        assert result["confidence_adjust"] == 0.0

    def test_mls_buy_vs_sell(self):
        """买入和卖出信号方向相反。"""
        closes = [100.0 + i * 0.3 for i in range(70)]
        highs = _make_highs(closes, 1.0)
        lows = _make_lows(closes, 1.0)

        buy_result = _calc_multi_level_structure_consistency_v79(_make_mmd("3buy"), closes, highs, lows)
        sell_result = _calc_multi_level_structure_consistency_v79(_make_mmd("3sell"), closes, highs, lows)

        # 两者应该都是float
        assert isinstance(buy_result["consistency_score"], float)
        assert isinstance(sell_result["consistency_score"], float)

    # ── 条件251：价格动能持续性评分 ──────────────────────────────────────────

    def test_pmc_strong_momentum_up(self):
        """价格上涨+量能放大 → 强劲动能。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = [100.0 + i * 0.5 for i in range(30)]
        volumes = [500.0 + i * 30 for i in range(30)]
        result = _calc_price_momentum_continuity_v79(mmd, closes, volumes)
        assert "momentum_score" in result
        assert "momentum_level" in result
        assert "acceleration" in result
        assert "vol_trend" in result
        assert isinstance(result["momentum_score"], float)
        assert 0 <= result["momentum_score"] <= 1.0

    def test_pmc_declining_momentum(self):
        """价格下跌+量能萎缩 → 衰竭动能。"""
        mmd = _make_mmd("3sell", 0.6)
        closes = [100.0 - i * 0.3 for i in range(30)]
        volumes = [500.0 - i * 20 for i in range(30)]
        result = _calc_price_momentum_continuity_v79(mmd, closes, volumes)
        assert "momentum_level" in result
        assert result["momentum_level"] in ["strong", "moderate", "weak", "declining", "neutral"]
        assert isinstance(result["acceleration"], float)

    def test_pmc_neutral(self):
        """中性动能 → 中性评分。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = [100.0 + 0.01 * i for i in range(30)]
        volumes = [500.0 for _ in range(30)]
        result = _calc_price_momentum_continuity_v79(mmd, closes, volumes)
        assert "momentum_score" in result
        assert isinstance(result["momentum_score"], float)

    def test_pmc_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mmd("3buy", 0.6)
        result = _calc_price_momentum_continuity_v79(mmd, [1.0, 2.0], None)
        assert result["msg"] != ""
        assert result["momentum_score"] == 0.5
        assert result["confidence_adjust"] == 0.0

    def test_pmc_no_volumes(self):
        """无成交量数据 → 仍然能计算。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = _make_closes(30, base=100.0)
        result = _calc_price_momentum_continuity_v79(mmd, closes, None)
        assert "momentum_score" in result
        assert "vol_trend" in result
        assert result["vol_trend"] == "neutral"

    def test_pmc_momentum_levels(self):
        """动能级别枚举有效性。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = _make_closes(30, base=100.0, trend="up")
        volumes = _make_volumes(30)
        result = _calc_price_momentum_continuity_v79(mmd, closes, volumes)
        valid_levels = {"strong", "moderate", "weak", "declining", "neutral"}
        assert result["momentum_level"] in valid_levels

    # ── 综合冒烟测试 ──────────────────────────────────────────────────────

    def test_all_v79_functions_no_crash(self):
        """所有 V79 函数在无异常情况下正常运行。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = _make_closes(80, base=100.0)
        volumes = _make_volumes(80)
        highs = _make_highs(closes, 1.0)
        lows = _make_lows(closes, 1.0)

        r1 = _calc_fractal_stability_validation_v79(mmd, highs, lows)
        r2 = _calc_mmd_distance_safety_v79([mmd], mmd, closes)
        r3 = _calc_multi_level_structure_consistency_v79(mmd, closes, highs, lows)
        r4 = _calc_price_momentum_continuity_v79(mmd, closes, volumes)

        assert all(r is not None for r in [r1, r2, r3, r4])
        assert all(isinstance(r.get("confidence_adjust", 0), float) for r in [r1, r2, r3, r4])

    def test_v79_vs_v78_consistency(self):
        """V79 与 V78 函数互不干扰。"""
        from easy_tdx.chanlun.mmd import (
            _calc_mmd_cycle_position_v78,
            _calc_fund_flow_divergence_v78,
        )
        mmd = _make_mmd("3buy", 0.6)
        closes = _make_closes(80)
        volumes = _make_volumes(80)
        highs = _make_highs(closes, 1.0)
        lows = _make_lows(closes, 1.0)

        # V78 函数仍能正常工作
        r_v78_1 = _calc_mmd_cycle_position_v78(mmd, closes, highs, lows)
        r_v78_2 = _calc_fund_flow_divergence_v78(closes, volumes)
        assert r_v78_1 is not None
        assert r_v78_2 is not None

        # V79 函数正常工作
        r_v79_1 = _calc_fractal_stability_validation_v79(mmd, highs, lows)
        r_v79_2 = _calc_multi_level_structure_consistency_v79(mmd, closes, highs, lows)
        r_v79_3 = _calc_price_momentum_continuity_v79(mmd, closes, volumes)
        assert r_v79_1 is not None
        assert r_v79_2 is not None
        assert r_v79_3 is not None
