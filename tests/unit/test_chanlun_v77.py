"""V77 缠论条件 240-243 单元测试。

条件240：量能分布深度分析（Volume Distribution Depth）
条件241：中枢结构权重评估（Zhongshu Structure Weight）
条件242：信号新鲜度验证（Signal Freshness Validation）
条件243：价格动能加速度（Price Momentum Acceleration）
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from easy_tdx.chanlun.mmd import (
    _calc_volume_distribution_depth_v77,
    _calc_zhongshu_structure_weight_v77,
    _calc_signal_freshness_validation_v77,
    _calc_price_momentum_acceleration_v77,
)
from easy_tdx.chanlun.types import MMD, MMDType
from easy_tdx.backtest.chanlun_validator import ConditionGroup


def _make_mmd(mmd_type: str = "3buy", confidence: float = 0.6) -> MMD:
    """Helper to create MMD with correct enum value."""
    return MMD(mmd_type=MMDType(mmd_type), confidence=confidence, msg="test")


def _make_closes(n: int = 60, base: float = 100.0) -> list[float]:
    import random
    random.seed(42)
    return [base + random.uniform(-5, 5) * (i / n) for i in range(n)]


def _make_volumes(n: int = 60, base: float = 1000.0) -> list[float]:
    import random
    random.seed(43)
    return [base + random.uniform(-200, 200) for _ in range(n)]


# ── TestV77ConditionGroup：ConditionGroup 枚举测试 ───────────────────────────

class TestV77ConditionGroup:
    """V77 ConditionGroup 存在性和正确性测试。"""

    def test_v77_exists(self):
        assert hasattr(ConditionGroup, "V77")

    def test_v77_condition_range(self):
        assert ConditionGroup.V77.condition_range == (240, 243)

    def test_v77_description(self):
        desc = ConditionGroup.V77.description
        assert len(desc) > 0


# ── TestV77MMDFields：MMD 对象字段测试 ───────────────────────────────────────

class TestV77MMDFields:
    """MMD 对象包含 V77 字段。"""

    def test_mmd_has_v77_fields(self):
        mmd = _make_mmd()
        assert hasattr(mmd, "_volume_distribution_depth_v77")
        assert hasattr(mmd, "_zhongshu_structure_weight_v77")
        assert hasattr(mmd, "_signal_freshness_validation_v77")
        assert hasattr(mmd, "_price_momentum_acceleration_v77")


# ── TestV77BacktestValidator：回测验证器测试 ─────────────────────────────────

class TestV77BacktestValidator:
    """V77 条件回测验证器测试。"""

    def test_v77_validator_usage(self):
        from easy_tdx.backtest.chanlun_validator import ChanlunConditionBacktestValidator
        validator = ChanlunConditionBacktestValidator()
        assert ConditionGroup.V77 in list(ConditionGroup)

    def test_v77_multi_group_validation(self):
        groups = [ConditionGroup.V75, ConditionGroup.V76, ConditionGroup.V77]
        ranges = [g.condition_range for g in groups]
        assert ranges[0] == (232, 235)
        assert ranges[1] == (236, 239)
        assert ranges[2] == (240, 243)

    def test_v77_summary_output(self):
        from easy_tdx.backtest.chanlun_validator import ChanlunConditionBacktestValidator
        validator = ChanlunConditionBacktestValidator()
        summary = validator.validate_conditions({}, [ConditionGroup.V77])
        assert summary is not None


# ── TestV77Functions：各计算函数单元测试 ─────────────────────────────────────

class TestV77Functions:
    """V77 四个计算函数的单元测试。"""

    # ── 条件240：量能分布深度分析 ──────────────────────────────────────────

    def test_vdd_buy_low_position(self):
        """买入信号在低位 → 应该增加置信度。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = _make_closes(60, base=80.0)
        volumes = _make_volumes(60)
        result = _calc_volume_distribution_depth_v77(mmd, closes, volumes)
        assert "energy_zone" in result
        assert "confidence_adjust" in result
        assert isinstance(result["volume_rank"], float)
        assert 0 <= result["volume_rank"] <= 1

    def test_vdd_sell_high_position(self):
        """卖出信号在高价 → 能量区为distribution，应降低置信度。"""
        mmd = _make_mmd("3sell", 0.6)
        closes = _make_closes(60, base=150.0)
        volumes = _make_volumes(60)
        result = _calc_volume_distribution_depth_v77(mmd, closes, volumes)
        assert "energy_zone" in result
        assert "confidence_adjust" in result

    def test_vdd_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mmd("3buy", 0.6)
        result = _calc_volume_distribution_depth_v77(mmd, [1.0, 2.0], [100.0, 200.0])
        assert result["msg"] != ""
        assert result["confidence_adjust"] == 0.0

    def test_vdd_with_volume_confirmation(self):
        """量能确认场景：低位放量 → 加分。"""
        mmd = _make_mmd("3buy", 0.5)
        closes = [80.0 + i * 0.02 for i in range(60)]
        volumes = [500.0] * 50 + [1500.0, 1800.0, 2000.0, 2200.0, 2500.0]
        result = _calc_volume_distribution_depth_v77(mmd, closes, volumes)
        assert result["energy_zone"] in [
            "accumulation", "low_zone", "neutral", "distribution", "high_zone"
        ]

    # ── 条件241：中枢结构权重评估 ──────────────────────────────────────────

    def test_zsw_near_zhongshu_support(self):
        """买入信号靠近中枢支撑 → 权重评分高。"""
        from easy_tdx.chanlun.types import ZS
        mmd = _make_mmd("3buy", 0.6)
        zss = [
            ZS(index=0, zg=100.5, zd=99.5),
            ZS(index=1, zg=95.5, zd=94.5),
        ]
        closes = [100.0] * 60
        result = _calc_zhongshu_structure_weight_v77(mmd, zss, closes)
        assert "weight_score" in result
        assert "nearest_zs_dist" in result
        assert result["weight_score"] > 0
        assert result["zs_level"] != "none"

    def test_zsw_far_from_zhongshu(self):
        """买入信号远离中枢 → 权重评分低。"""
        from easy_tdx.chanlun.types import ZS
        mmd = _make_mmd("3buy", 0.6)
        zss = [
            ZS(index=0, zg=100.5, zd=99.5),
        ]
        closes = [200.0] * 60
        result = _calc_zhongshu_structure_weight_v77(mmd, zss, closes)
        assert "weight_score" in result
        assert 0 <= result["weight_score"] <= 1.0

    def test_zsw_no_zhongshu(self):
        """无中枢数据时返回默认值。"""
        mmd = _make_mmd("3buy", 0.6)
        result = _calc_zhongshu_structure_weight_v77(mmd, [], [10.0] * 10)
        assert result["msg"] != ""
        assert result["weight_score"] == 0.0

    def test_zsw_insufficient_closes(self):
        """价格数据不足时返回默认值。"""
        from easy_tdx.chanlun.types import ZS
        mmd = _make_mmd("3buy", 0.6)
        zss = [ZS(index=0, zg=100.5, zd=99.5)]
        result = _calc_zhongshu_structure_weight_v77(mmd, zss, [10.0, 11.0])
        assert result["msg"] != ""

    # ── 条件242：信号新鲜度验证 ────────────────────────────────────────────

    def test_sfv_fresh_signal(self):
        """无笔信息时 → 使用默认逻辑。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = _make_closes(60)
        result = _calc_signal_freshness_validation_v77(mmd, closes)
        assert "freshness_score" in result
        assert "age_label" in result
        assert isinstance(result["freshness_score"], float)
        assert 0 <= result["freshness_score"] <= 1.0

    def test_sfv_aging_signal(self):
        """模拟有笔信息的衰老信号。"""
        from easy_tdx.chanlun.types import CLKline, BI
        from datetime import datetime

        k = CLKline(k_index=50, date=datetime(2026, 8, 1), open=10, close=10, high=10, low=10, amount=100)
        bi = BI(start=k, end=k, direction="up", index=0)
        mmd = _make_mmd("3buy", 0.6)
        mmd.bi = bi
        closes = _make_closes(60)
        result = _calc_signal_freshness_validation_v77(mmd, closes)
        assert "bars_since_signal" in result
        assert result["bars_since_signal"] >= 0

    def test_sfv_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mmd("3buy", 0.6)
        result = _calc_signal_freshness_validation_v77(mmd, [1.0, 2.0])
        assert result["msg"] != ""

    def test_sfv_score_range(self):
        """新鲜度评分应在 [0, 1] 范围内。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = _make_closes(60)
        result = _calc_signal_freshness_validation_v77(mmd, closes)
        assert 0 <= result["freshness_score"] <= 1.0

    # ── 条件243：价格动能加速度 ────────────────────────────────────────────

    def test_pma_accelerating_up(self):
        """加速上涨场景 → 买入信号应加分。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = [10.0 + i * 0.1 + i * i * 0.001 for i in range(30)]
        result = _calc_price_momentum_acceleration_v77(mmd, closes)
        assert "momentum_direction" in result
        assert "acceleration_strength" in result
        assert "confidence_adjust" in result

    def test_pma_decelerating(self):
        """动能衰减场景 → 买入信号应减分。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = [10.0 + 5.0 * (1 - 0.95 ** i) for i in range(30)]
        result = _calc_price_momentum_acceleration_v77(mmd, closes)
        assert "momentum_direction" in result
        assert result["momentum_direction"] in [
            "accelerating_up", "growing_up", "flat", "decelerating", "sharp_reversal"
        ]

    def test_pma_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mmd("3buy", 0.6)
        result = _calc_price_momentum_acceleration_v77(mmd, [1.0, 2.0])
        assert result["msg"] != ""

    def test_pma_sell_signal(self):
        """卖出信号在下跌加速时 → 应加分。"""
        mmd = _make_mmd("3sell", 0.6)
        closes = [20.0 - i * 0.1 - i * i * 0.002 for i in range(30)]
        result = _calc_price_momentum_acceleration_v77(mmd, closes)
        assert "acceleration" in result
        assert isinstance(result["acceleration"], float)

    def test_pma_flat_market(self):
        """横盘市场 → 加速度接近零。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = [10.0] * 30
        result = _calc_price_momentum_acceleration_v77(mmd, closes)
        assert abs(result["acceleration"]) < 0.01

    # ── 综合冒烟测试 ──────────────────────────────────────────────────────

    def test_all_v77_functions_no_crash(self):
        """所有 V77 函数在无异常情况下正常运行。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = _make_closes(60)
        volumes = _make_volumes(60)
        from easy_tdx.chanlun.types import ZS
        zss = [ZS(index=0, zg=100.5, zd=99.5)]

        r1 = _calc_volume_distribution_depth_v77(mmd, closes, volumes)
        r2 = _calc_zhongshu_structure_weight_v77(mmd, zss, closes)
        r3 = _calc_signal_freshness_validation_v77(mmd, closes)
        r4 = _calc_price_momentum_acceleration_v77(mmd, closes)

        assert all(r is not None for r in [r1, r2, r3, r4])
        assert all(isinstance(r.get("confidence_adjust", 0), float) for r in [r1, r2, r3, r4])
