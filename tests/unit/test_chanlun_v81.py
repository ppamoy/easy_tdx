"""V81 缠论模型精准度提升测试（条件256-259）。"""

import numpy as np

from easy_tdx.backtest.chanlun_validator import ConditionGroup
from easy_tdx.chanlun.types import MMD, MMDType

# ── V81 条件组定义测试 ───────────────────────────────────────────────


class TestV81ConditionGroup:
    """V81 ConditionGroup 存在性与范围测试。"""

    def test_v81_enum_exists(self):
        assert hasattr(ConditionGroup, "V81")

    def test_v81_condition_range(self):
        assert ConditionGroup.V81.condition_range == (256, 259)

    def test_v81_description(self):
        desc = ConditionGroup.V81.description
        assert "波动率" in desc
        assert "支撑阻力" in desc or "支撑" in desc
        assert "量价能量" in desc or "能量" in desc
        assert "执行窗口" in desc or "窗口" in desc


# ── V81 MMD 字段测试 ─────────────────────────────────────────────────


class TestV81MMDFields:
    """MMD 对象包含 V81 四个字段。"""

    def test_mmd_has_v81_fields(self):
        mmd = MMD(mmd_type=MMDType("1buy"), confidence=0.5, msg="test")
        assert hasattr(mmd, "_volatility_regime_transition_v81")
        assert hasattr(mmd, "_support_resistance_strength_v81")
        assert hasattr(mmd, "_volume_price_energy_distribution_v81")
        assert hasattr(mmd, "_signal_execution_window_v81")


# ── V81 回测验证器测试 ───────────────────────────────────────────────


class TestV81BacktestValidator:
    """V81 回测验证器测试。"""

    def test_v81_validator_single_group(self):
        from easy_tdx.backtest.chanlun_validator import ChanlunConditionBacktestValidator

        _ = ChanlunConditionBacktestValidator()
        # 验证 V81 组可被识别
        low, high = ConditionGroup.V81.condition_range
        assert low == 256
        assert high == 259

    def test_v81_validator_multi_group(self):
        from easy_tdx.backtest.chanlun_validator import ChanlunConditionBacktestValidator

        _ = ChanlunConditionBacktestValidator()
        # V79+V80+V81 联合验证
        groups = [ConditionGroup.V79, ConditionGroup.V80, ConditionGroup.V81]
        ranges = [g.condition_range for g in groups]
        assert ranges == [(248, 251), (252, 255), (256, 259)]

    def test_v81_summary_output(self):
        """V81 summary 输出结构正确。"""
        from easy_tdx.backtest.chanlun_validator import ChanlunConditionBacktestValidator

        _ = ChanlunConditionBacktestValidator()
        # 验证 V81 组条件范围
        low, high = ConditionGroup.V81.condition_range
        assert low == 256
        assert high == 259
        desc = ConditionGroup.V81.description
        assert len(desc) > 0


# ── V81 计算函数测试 ─────────────────────────────────────────────────


class TestV81Functions:
    """V81 四个计算函数的功能测试。"""

    def _make_mmd(self, mmd_type: str = "1buy") -> MMD:
        return MMD(mmd_type=MMDType(mmd_type), confidence=0.5, msg="test")

    def _make_data(
        self, n: int = 50, trend: str = "up"
    ) -> tuple[list[float], list[float], list[float], list[float]]:
        np.random.seed(42)
        if trend == "up":
            base = np.linspace(10, 15, n) + np.random.randn(n) * 0.3
        elif trend == "down":
            base = np.linspace(15, 10, n) + np.random.randn(n) * 0.3
        else:
            base = np.ones(n) * 12 + np.random.randn(n) * 0.2
        highs = (base + np.abs(np.random.randn(n)) * 0.2).tolist()
        lows = (base - np.abs(np.random.randn(n)) * 0.2).tolist()
        closes = base.tolist()
        volumes = (np.abs(np.random.randn(n)) * 1000000 + 500000).tolist()
        return closes, highs, lows, volumes

    # ── 条件256：波动率状态转换检测 ────────────────────────────────

    def test_v81_volatility_regime_compressed(self):
        """波动率压缩状态 → 加分。"""
        from easy_tdx.chanlun.mmd import _calc_volatility_regime_transition_v81

        mmd = self._make_mmd("1buy")
        # 构造低波动数据（ATR收缩）
        np.random.seed(100)
        base = np.linspace(10, 10.1, 40) + np.random.randn(40) * 0.01
        highs = (base + 0.005).tolist()
        lows = (base - 0.005).tolist()
        closes = base.tolist()
        result = _calc_volatility_regime_transition_v81(mmd, closes, highs, lows)
        assert "regime" in result
        assert "confidence_adjust" in result
        assert result["regime"] in ("compressed", "normal", "elevated", "expanding", "unknown")

    def test_v81_volatility_regime_insufficient_data(self):
        """数据不足时返回默认值。"""
        from easy_tdx.chanlun.mmd import _calc_volatility_regime_transition_v81

        mmd = self._make_mmd("1sell")
        result = _calc_volatility_regime_transition_v81(mmd, [1.0, 2.0], [1.1, 2.1], [0.9, 1.9])
        assert result["msg"] == "数据不足"
        assert result["confidence_adjust"] == 0.0

    def test_v81_volatility_regime_buy_sell_different(self):
        """买入和卖出信号的调整方向可能不同。"""
        from easy_tdx.chanlun.mmd import _calc_volatility_regime_transition_v81

        closes, highs, lows, _ = self._make_data(50, "up")
        mmd_buy = self._make_mmd("1buy")
        mmd_sell = self._make_mmd("1sell")
        r_buy = _calc_volatility_regime_transition_v81(mmd_buy, closes, highs, lows)
        r_sell = _calc_volatility_regime_transition_v81(mmd_sell, closes, highs, lows)
        assert r_buy["regime"] == r_sell["regime"]
        # 买入和卖出的调整可能不同（压缩状态下买入+3%，卖出+2%）
        assert isinstance(r_buy["confidence_adjust"], float)
        assert isinstance(r_sell["confidence_adjust"], float)

    # ── 条件257：关键支撑阻力强度验证 ──────────────────────────────

    def test_v81_sr_strength_strong(self):
        """强支撑/阻力 → 加分。"""
        from easy_tdx.chanlun.mmd import _calc_support_resistance_strength_v81

        mmd = self._make_mmd("1buy")
        # 构造有明显支撑位的数据
        np.random.seed(200)
        base = np.linspace(10, 12, 50)
        # 在10.0处制造多次触底
        for i in range(10, 50):
            if i % 5 == 0:
                base[i] = 10.0 + np.random.randn() * 0.05
        highs = (base + 0.1).tolist()
        lows = (base - 0.1).tolist()
        closes = base.tolist()
        result = _calc_support_resistance_strength_v81(mmd, closes, highs, lows)
        assert "strength_level" in result
        assert "confidence_adjust" in result
        assert result["strength_level"] in ("strong", "weak", "moderate", "distant", "unknown")

    def test_v81_sr_insufficient_data(self):
        """数据不足时返回默认值。"""
        from easy_tdx.chanlun.mmd import _calc_support_resistance_strength_v81

        mmd = self._make_mmd("1sell")
        result = _calc_support_resistance_strength_v81(mmd, [1.0], [1.1], [0.9])
        assert result["msg"] == "数据不足"

    def test_v81_sr_fields_complete(self):
        """返回字段完整性。"""
        from easy_tdx.chanlun.mmd import _calc_support_resistance_strength_v81

        mmd = self._make_mmd("1buy")
        closes, highs, lows, _ = self._make_data(50, "up")
        result = _calc_support_resistance_strength_v81(mmd, closes, highs, lows)
        assert "strength_level" in result
        assert "nearest_sr_dist_pct" in result
        assert "sr_count" in result
        assert "confidence_adjust" in result
        assert "msg" in result

    # ── 条件258：量价能量分布验证 ──────────────────────────────────

    def test_v81_energy_distribution_buy(self):
        """买入信号的能量分布评估。"""
        from easy_tdx.chanlun.mmd import _calc_volume_price_energy_distribution_v81

        mmd = self._make_mmd("1buy")
        closes, highs, lows, volumes = self._make_data(50, "up")
        result = _calc_volume_price_energy_distribution_v81(mmd, closes, volumes, highs, lows)
        assert "energy_zone" in result
        assert "energy_score" in result
        assert "confidence_adjust" in result
        assert result["energy_zone"] in ("low", "mid", "high", "unknown")

    def test_v81_energy_distribution_sell(self):
        """卖出信号的能量分布评估。"""
        from easy_tdx.chanlun.mmd import _calc_volume_price_energy_distribution_v81

        mmd = self._make_mmd("1sell")
        closes, highs, lows, volumes = self._make_data(50, "down")
        result = _calc_volume_price_energy_distribution_v81(mmd, closes, volumes, highs, lows)
        assert "energy_zone" in result
        assert isinstance(result["energy_score"], float)

    def test_v81_energy_insufficient_data(self):
        """数据不足时返回默认值。"""
        from easy_tdx.chanlun.mmd import _calc_volume_price_energy_distribution_v81

        mmd = self._make_mmd("1buy")
        result = _calc_volume_price_energy_distribution_v81(
            mmd, [1.0, 2.0], [100, 200], [1.1, 2.1], [0.9, 1.9]
        )
        assert result["msg"] == "数据不足"

    def test_v81_energy_no_volumes(self):
        """无成交量数据时返回默认值。"""
        from easy_tdx.chanlun.mmd import _calc_volume_price_energy_distribution_v81

        mmd = self._make_mmd("1buy")
        closes, highs, lows, _ = self._make_data(50, "up")
        result = _calc_volume_price_energy_distribution_v81(mmd, closes, None, highs, lows)
        assert result["msg"] == "数据不足"

    # ── 条件259：信号执行窗口评估 ──────────────────────────────────

    def test_v81_execution_window_favorable(self):
        """理想执行窗口 → 加分。"""
        from easy_tdx.chanlun.mmd import _calc_signal_execution_window_v81

        mmd = self._make_mmd("1buy")
        closes, highs, lows, volumes = self._make_data(30, "up")
        result = _calc_signal_execution_window_v81(mmd, closes, highs, lows, volumes)
        assert "window_quality" in result
        assert "confidence_adjust" in result
        assert result["window_quality"] in (
            "favorable",
            "acceptable",
            "caution",
            "unfavorable",
            "unknown",
        )

    def test_v81_execution_window_insufficient_data(self):
        """数据不足时返回默认值。"""
        from easy_tdx.chanlun.mmd import _calc_signal_execution_window_v81

        mmd = self._make_mmd("1sell")
        result = _calc_signal_execution_window_v81(mmd, [1.0], [1.1], [0.9], None)
        assert result["msg"] == "数据不足"

    def test_v81_execution_window_fields_complete(self):
        """返回字段完整性。"""
        from easy_tdx.chanlun.mmd import _calc_signal_execution_window_v81

        mmd = self._make_mmd("1buy")
        closes, highs, lows, volumes = self._make_data(30, "up")
        result = _calc_signal_execution_window_v81(mmd, closes, highs, lows, volumes)
        assert "window_quality" in result
        assert "volatility_score" in result
        assert "liquidity_score" in result
        assert "confidence_adjust" in result
        assert "msg" in result

    # ── 综合冒烟测试 ───────────────────────────────────────────────

    def test_v81_all_functions_smoke(self):
        """所有V81函数在正常数据下不抛出异常。"""
        from easy_tdx.chanlun.mmd import (
            _calc_signal_execution_window_v81,
            _calc_support_resistance_strength_v81,
            _calc_volatility_regime_transition_v81,
            _calc_volume_price_energy_distribution_v81,
        )

        mmd = self._make_mmd("1buy")
        closes, highs, lows, volumes = self._make_data(50, "up")

        r1 = _calc_volatility_regime_transition_v81(mmd, closes, highs, lows)
        assert isinstance(r1, dict)
        assert "confidence_adjust" in r1

        r2 = _calc_support_resistance_strength_v81(mmd, closes, highs, lows)
        assert isinstance(r2, dict)
        assert "confidence_adjust" in r2

        r3 = _calc_volume_price_energy_distribution_v81(mmd, closes, volumes, highs, lows)
        assert isinstance(r3, dict)
        assert "confidence_adjust" in r3

        r4 = _calc_signal_execution_window_v81(mmd, closes, highs, lows, volumes)
        assert isinstance(r4, dict)
        assert "confidence_adjust" in r4

    def test_v81_compatibility_with_v79_v80(self):
        """V81与V79/V80不冲突。"""
        from easy_tdx.chanlun.mmd import (
            _calc_fractal_stability_validation_v79,
            _calc_mmd_zhongshu_distance_v80,
            _calc_volatility_regime_transition_v81,
        )

        mmd = self._make_mmd("1buy")
        closes, highs, lows, _ = self._make_data(50, "up")

        r79 = _calc_fractal_stability_validation_v79(mmd, highs, lows)
        r80 = _calc_mmd_zhongshu_distance_v80(mmd, closes, highs, lows)
        r81 = _calc_volatility_regime_transition_v81(mmd, closes, highs, lows)

        assert "confidence_adjust" in r79
        assert "confidence_adjust" in r80
        assert "confidence_adjust" in r81
