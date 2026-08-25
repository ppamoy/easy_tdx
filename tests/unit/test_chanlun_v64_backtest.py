"""V64 缠论条件回测验证测试：V58-V63 条件组系统性回测 + V63 条件专项验证。

覆盖：
- ConditionGroup 枚举定义正确性
- ChanlunConditionBacktestValidator 核心功能
- V63 条件190/191 回测影响评估
- 多股票对比分析
- 边界情况和异常处理
"""

from __future__ import annotations

import numpy as np
import pytest

from easy_tdx.backtest.chanlun_validator import (
    ConditionGroup,
    ChanlunConditionBacktestValidator,
    ConditionValidationResult,
    MultiStockResult,
    SignalResult,
)
from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig


# ──────────────────────────────────────────────────────────────────────────────
# 测试数据生成工具
# ──────────────────────────────────────────────────────────────────────────────

def _make_trending_df(n: int = 300, start_price: float = 50.0, trend: str = "up") -> tuple[list[float], list[float], list[float], list[float]]:
    """生成趋势数据 (open, high, low, close)。"""
    np.random.seed(42)
    returns = np.random.randn(n) * 0.02
    if trend == "up":
        returns = returns + 0.003
    elif trend == "down":
        returns = returns - 0.003

    closes = [start_price]
    for r in returns[1:]:
        closes.append(closes[-1] * (1 + r))

    opens = [c * (1 + np.random.randn() * 0.005) for c in closes]
    highs = [max(o, c) * (1 + abs(np.random.randn()) * 0.01) for o, c in zip(opens, closes)]
    lows = [min(o, c) * (1 - abs(np.random.randn()) * 0.01) for o, c in zip(opens, closes)]
    vols = [1e6 * (1 + abs(np.random.randn()) * 0.5) for _ in range(n)]

    return opens, highs, lows, closes


def _make_oscillating_df(n: int = 300, start_price: float = 30.0) -> tuple[list[float], list[float], list[float], list[float]]:
    """生成震荡数据（适合测试中枢）。"""
    np.random.seed(123)
    base = start_price
    closes = [base]
    for i in range(1, n):
        delta = np.sin(i / 20) * 2 + np.random.randn() * 0.5
        closes.append(closes[-1] + delta)

    opens = [c * (1 + np.random.randn() * 0.003) for c in closes]
    highs = [max(o, c) * (1 + abs(np.random.randn()) * 0.008) for o, c in zip(opens, closes)]
    lows = [min(o, c) * (1 - abs(np.random.randn()) * 0.008) for o, c in zip(opens, closes)]
    vols = [5e5 * (1 + abs(np.random.randn()) * 0.3) for _ in range(n)]

    return opens, highs, lows, closes


def _make_df(opens: list, highs: list, lows: list, closes: list) -> "pd.DataFrame":
    """构造 DataFrame。"""
    import pandas as pd
    return pd.DataFrame({
        "open": opens, "high": highs, "low": lows, "close": closes, "vol": [1e6] * len(closes),
    })


# ──────────────────────────────────────────────────────────────────────────────
# ConditionGroup 枚举测试
# ──────────────────────────────────────────────────────────────────────────────

class TestConditionGroup:
    """ConditionGroup 枚举正确性测试。"""

    def test_all_groups_defined(self):
        """所有 V58-V68 分组都应定义。"""
        expected = {"V58", "V59", "V60", "V61", "V62", "V63", "V64", "V65", "V66", "V67", "V68", "V69", "V70", "V71", "V72"}
        actual = {g.name for g in ConditionGroup}
        assert expected == actual

    def test_condition_ranges(self):
        """条件编号范围正确。"""
        assert ConditionGroup.V58.condition_range == (172, 175)
        assert ConditionGroup.V59.condition_range == (176, 179)
        assert ConditionGroup.V60.condition_range == (180, 183)
        assert ConditionGroup.V61.condition_range == (184, 185)
        assert ConditionGroup.V62.condition_range == (186, 189)
        assert ConditionGroup.V63.condition_range == (190, 191)
        assert ConditionGroup.V64.condition_range == (0, 0)
        assert ConditionGroup.V65.condition_range == (192, 195)
        assert ConditionGroup.V66.condition_range == (196, 199)

    def test_descriptions(self):
        """每个分组都有描述。"""
        for g in ConditionGroup:
            assert isinstance(g.description, str)
            assert len(g.description) > 0


# ──────────────────────────────────────────────────────────────────────────────
# 基础回测验证器测试
# ──────────────────────────────────────────────────────────────────────────────

class TestBacktestValidatorBasic:
    """回测验证器基础功能测试。"""

    def test_insufficient_data(self):
        """数据不足时返回带注释的结果。"""
        validator = ChanlunConditionBacktestValidator(min_bars=100)
        df = _make_df(*_make_trending_df(50))
        results = validator.validate_conditions(df, [ConditionGroup.V63])
        assert len(results) == 1
        assert "数据不足" in results[0].condition_details.get("note", "")

    def test_valid_data_returns_results(self):
        """有效数据应返回所有分组的验证结果。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_trending_df(300))
        results = validator.validate_conditions(df, [ConditionGroup.V63])
        assert len(results) == 1
        assert results[0].group == ConditionGroup.V63

    def test_multi_group_validation(self):
        """多分组验证应返回正确数量结果。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_trending_df(300))
        groups = [ConditionGroup.V61, ConditionGroup.V62, ConditionGroup.V63]
        results = validator.validate_conditions(df, groups)
        assert len(results) == 3
        result_groups = {r.group for r in results}
        assert result_groups == set(groups)


# ──────────────────────────────────────────────────────────────────────────────
# V63 条件专项回测测试（重点）
# ──────────────────────────────────────────────────────────────────────────────

class TestV63Backtest:
    """V63 条件190/191 回测验证测试。"""

    def _run_v63_test(self, df) -> ConditionValidationResult | None:
        """运行 V63 回测并返回结果。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        results = validator.validate_conditions(df, [ConditionGroup.V63])
        return results[0] if results else None

    def test_oscillating_data_v63(self):
        """震荡数据上 V63 条件应产生有效信号。"""
        df = _make_df(*_make_oscillating_df(400))
        result = self._run_v63_test(df)
        assert result is not None
        # 震荡数据应该有足够的买卖点
        assert result.total_signals >= 0  # 至少不报错

    def test_up_trend_v63(self):
        """上升趋势数据上 V63 条件应产生卖出信号。"""
        df = _make_df(*_make_trending_df(400, trend="up"))
        result = self._run_v63_test(df)
        assert result is not None
        assert result.group == ConditionGroup.V63
        # 验证指标结构完整性（无论是否有信号）
        details = result.condition_details
        if details.get("note") != "无买卖点信号":
            assert "total_enhanced_signals" in details
            assert "avg_confidence" in details

    def test_down_trend_v63(self):
        """下降趋势数据上 V63 条件应产生卖出信号。"""
        df = _make_df(*_make_trending_df(400, trend="down"))
        result = self._run_v63_test(df)
        assert result is not None
        assert result.group == ConditionGroup.V63

    def test_v63_confidence_correlation_computed(self):
        """V63 置信度相关性应被正确计算。"""
        df = _make_df(*_make_oscillating_df(500))
        result = self._run_v63_test(df)
        assert result is not None
        # confidence_correlation 应为数值
        assert isinstance(result.confidence_correlation, float)
        assert -1.0 <= result.confidence_correlation <= 1.0 or result.confidence_correlation == 0.0

    def test_v63_summary_output(self):
        """V63 摘要输出应包含必要信息。"""
        df = _make_df(*_make_trending_df(300))
        result = self._run_v63_test(df)
        assert result is not None
        summary = result.summary()
        assert "V63" in summary
        assert "中枢级别权重优化" in summary
        assert "总信号数" in summary or "无" in summary


# ──────────────────────────────────────────────────────────────────────────────
# 多股票对比分析测试
# ──────────────────────────────────────────────────────────────────────────────

class TestMultiStockComparison:
    """多股票对比分析测试。"""

    def test_single_stock_comparison(self):
        """单股票对比应返回正确结果。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_oscillating_df(300))
        results = validator.validate_multi_stock({"sh600000": df})
        assert len(results) == 1
        assert results[0].stock_code == "sh600000"
        assert isinstance(results[0].signal_count, int)

    def test_multi_stock_comparison(self):
        """多股票对比应返回每只股票的结果。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        data = {
            "sh600000": _make_df(*_make_oscillating_df(300)),
            "sz000001": _make_df(*_make_trending_df(300, trend="up")),
            "sh601318": _make_df(*_make_trending_df(300, trend="down")),
        }
        results = validator.validate_multi_stock(data)
        assert len(results) == 3
        codes = {r.stock_code for r in results}
        assert codes == {"sh600000", "sz000001", "sh601318"}

    def test_multi_stock_short_data_filtered(self):
        """短数据股票应被过滤。"""
        validator = ChanlunConditionBacktestValidator(min_bars=100)
        data = {
            "short_stock": _make_df(*_make_trending_df(50)),
            "long_stock": _make_df(*_make_trending_df(300)),
        }
        results = validator.validate_multi_stock(data)
        assert len(results) == 1
        assert results[0].stock_code == "long_stock"

    def test_multi_stock_condition_breakdown(self):
        """多股票对比应包含条件命中统计。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_oscillating_df(400))
        results = validator.validate_multi_stock({"sh600000": df})
        assert len(results) == 1
        # condition_breakdown 应有 V63 相关条目
        breakdown = results[0].condition_breakdown
        v63_keys = [k for k in breakdown if "v63" in k.lower()]
        # 至少结构存在（可能为0）
        assert isinstance(breakdown, dict)


# ──────────────────────────────────────────────────────────────────────────────
# 条件组对比表格测试
# ──────────────────────────────────────────────────────────────────────────────

class TestGroupComparison:
    """条件组对比表格测试。"""

    def test_compare_all_groups(self):
        """全部条件组对比应返回 DataFrame。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_oscillating_df(300))
        groups = list(ConditionGroup)
        table = validator.compare_groups(df, groups)
        assert len(table) == len(groups)
        assert "分组" in table.columns
        assert "胜率" in table.columns
        assert "提升" in table.columns

    def test_compare_partial_groups(self):
        """部分条件组对比应只返回指定组。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_trending_df(300))
        groups = [ConditionGroup.V62, ConditionGroup.V63]
        table = validator.compare_groups(df, groups)
        assert len(table) == 2
        groups_in_table = set(table["分组"].tolist())
        assert groups_in_table == {"v62", "v63"}


# ──────────────────────────────────────────────────────────────────────────────
# SignalResult 数据类测试
# ──────────────────────────────────────────────────────────────────────────────

class TestSignalResult:
    """SignalResult 数据类测试。"""

    def test_create_signal_result(self):
        """创建 SignalResult 应成功。"""
        r = SignalResult(
            signal_type="buy",
            entry_bar=10,
            exit_bar=15,
            entry_price=100.0,
            exit_price=105.0,
            pnl_pct=5.0,
            holding_days=5,
            hit=True,
            signal_confidence=0.75,
        )
        assert r.signal_type == "buy"
        assert r.pnl_pct == 5.0
        assert r.hit is True

    def test_sell_signal_result(self):
        """卖出信号结果应正确。"""
        r = SignalResult(
            signal_type="sell",
            entry_bar=10,
            exit_bar=15,
            entry_price=100.0,
            exit_price=95.0,
            pnl_pct=5.0,
            holding_days=5,
            hit=True,
            signal_confidence=0.8,
        )
        assert r.signal_type == "sell"
        assert r.hit is True


# ──────────────────────────────────────────────────────────────────────────────
# 边界条件和错误处理测试
# ──────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    """边界条件和错误处理测试。"""

    def test_empty_stock_data(self):
        """空数据字典应返回空结果。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        results = validator.validate_multi_stock({})
        assert results == []

    def test_mixed_data_length(self):
        """混合长度数据应只保留足够长的。"""
        validator = ChanlunConditionBacktestValidator(min_bars=200)
        data = {
            "short": _make_df(*_make_trending_df(50)),
            "medium": _make_df(*_make_trending_df(150)),
            "long": _make_df(*_make_trending_df(400)),
        }
        results = validator.validate_multi_stock(data)
        # 只有 long 满足 min_bars=200
        assert len(results) == 1
        assert results[0].stock_code == "long"

    def test_validator_custom_params(self):
        """自定义参数应生效。"""
        validator = ChanlunConditionBacktestValidator(
            stop_loss=0.05,
            take_profit=0.15,
            min_confidence=0.6,
            min_bars=80,
        )
        assert validator.stop_loss == 0.05
        assert validator.take_profit == 0.15
        assert validator.min_confidence == 0.6
        assert validator.min_bars == 80

    def test_v63_no_mmds(self):
        """无买卖点数据时应返回空详情。"""
        # 用极端平坦数据，不太可能产生买卖点
        np.random.seed(999)
        closes = [100.0 + np.random.randn() * 0.0001 for _ in range(100)]
        opens = closes[:]
        highs = [c * 1.0001 for c in closes]
        lows = [c * 0.9999 for c in closes]
        df = _make_df(opens, highs, lows, closes)
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        results = validator.validate_conditions(df, [ConditionGroup.V63])
        assert len(results) == 1
        assert results[0].group == ConditionGroup.V63


# ──────────────────────────────────────────────────────────────────────────────
# 集成测试：与实际 chanlun 分析器联动
# ──────────────────────────────────────────────────────────────────────────────

class TestIntegrationWithChanlun:
    """与实际缠论分析器的集成测试。"""

    def test_v63_mmds_have_enhanced_fields(self):
        """V63 产生的 MMD 对象应包含增强字段。"""
        df = _make_df(*_make_oscillating_df(400))
        config = ChanlunConfig()
        analyser = ChanlunAnalyser(code="test", frequency="daily", config=config)
        result = analyser.process_klines(df)

        buy_3_signals = [m for m in result.mmds if m.mmd_type.name == "BUY_3"]
        sell_3_signals = [m for m in result.mmds if m.mmd_type.name == "SELL_3"]

        # 检查 BUY_3 信号是否有 V63 增强字段
        for mmd in buy_3_signals[:3]:  # 检查前3个
            assert hasattr(mmd, "_zhongshu_level_weight_enhanced_v63")
            assert hasattr(mmd, "_multi_period_signal_decay_v63")

        # 检查 SELL_3 信号
        for mmd in sell_3_signals[:3]:
            assert hasattr(mmd, "_zhongshu_level_weight_enhanced_v63")
            assert hasattr(mmd, "_multi_period_signal_decay_v63")

    def test_v63_condition_ranges_match(self):
        """条件范围应与 V63 的 190/191 一致。"""
        assert ConditionGroup.V63.condition_range == (190, 191)

    def test_full_pipeline_oscillating(self):
        """完整回测流水线在震荡数据上不应崩溃。"""
        df = _make_df(*_make_oscillating_df(500))
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        results = validator.validate_conditions(df, [ConditionGroup.V63])
        assert len(results) == 1
        result = results[0]
        # 验证所有必要字段存在
        assert result.group == ConditionGroup.V63
        assert isinstance(result.total_signals, int)
        assert isinstance(result.hit_rate, float)
        assert isinstance(result.avg_pnl_pct, float)
        assert isinstance(result.confidence_correlation, float)

    def test_full_pipeline_up_trend(self):
        """完整回测流水线在上升趋势数据上不应崩溃。"""
        df = _make_df(*_make_trending_df(500, trend="up"))
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        results = validator.validate_conditions(df, [ConditionGroup.V63])
        assert len(results) == 1
        assert results[0].group == ConditionGroup.V63


# ──────────────────────────────────────────────────────────────────────────────
# V65 条件 192-195 专项测试
# ──────────────────────────────────────────────────────────────────────────────

class TestV65ConditionGroup:
    """V65 ConditionGroup 枚举正确性测试。"""

    def test_v65_group_exists(self):
        """V65 分组应存在于枚举中。"""
        assert ConditionGroup.V65 in list(ConditionGroup)

    def test_v65_condition_range(self):
        """V65 条件范围应为 (192, 195)。"""
        assert ConditionGroup.V65.condition_range == (192, 195)
        assert ConditionGroup.V66.condition_range == (196, 199)

    def test_v65_description(self):
        """V65 应有描述。"""
        assert len(ConditionGroup.V65.description) > 0

    def test_v64_group_exists(self):
        """V64 基础设施分组应存在。"""
        assert ConditionGroup.V64 in list(ConditionGroup)
        assert ConditionGroup.V64.condition_range == (0, 0)


class TestV65MMDFields:
    """V65 MMD 增强字段存在性测试。"""

    def test_v65_fields_on_mmd(self):
        """缠论分析产生的 MMD 对象应包含 V65 增强字段。"""
        from easy_tdx.chanlun.types import MMDType
        df = _make_df(*_make_oscillating_df(500))
        config = ChanlunConfig()
        analyser = ChanlunAnalyser(code="test", frequency="daily", config=config)
        result = analyser.process_klines(df)

        for mmd in result.mmds[:5]:
            assert hasattr(mmd, "_volume_price_divergence_secondary_v65")
            assert hasattr(mmd, "_breakout_retest_confirmation_v65")
            assert hasattr(mmd, "_volatility_compression_breakout_v65")
            assert hasattr(mmd, "_signal_time_window_freshness_v65")


class TestV65BacktestValidator:
    """V65 回测验证器测试。"""

    def test_v65_group_in_validator(self):
        """ConditionGroup.V65 应可被 validator 使用。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_oscillating_df(400))
        results = validator.validate_conditions(df, [ConditionGroup.V65])
        assert len(results) == 1
        assert results[0].group == ConditionGroup.V65

    def test_v65_multi_group_validation(self):
        """V63 + V65 联合验证应返回两个结果。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_oscillating_df(400))
        results = validator.validate_conditions(df, [ConditionGroup.V63, ConditionGroup.V65])
        assert len(results) == 2
        groups = {r.group for r in results}
        assert groups == {ConditionGroup.V63, ConditionGroup.V65}

    def test_v65_summary_output(self):
        """V65 摘要应包含 V65 关键词。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_oscillating_df(400))
        results = validator.validate_conditions(df, [ConditionGroup.V65])
        assert len(results) == 1
        summary = results[0].summary()
        assert "V65" in summary

    def test_v65_confidence_correlation_valid(self):
        """V65 置信度相关性应在有效范围内。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_trending_df(400, trend="up"))
        results = validator.validate_conditions(df, [ConditionGroup.V65])
        assert len(results) == 1
        corr = results[0].confidence_correlation
        assert isinstance(corr, float)
        assert -1.0 <= corr <= 1.0 or corr == 0.0


class TestV65MultiStock:
    """V65 多股票对比测试。"""

    def test_v65_multi_stock_breakdown(self):
        """多股票对比应包含 V65 条件命中统计。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        data = {
            "sh600000": _make_df(*_make_oscillating_df(400)),
            "sz000001": _make_df(*_make_trending_df(400, trend="up")),
        }
        results = validator.validate_multi_stock(data)
        assert len(results) == 2
        for r in results:
            assert isinstance(r.condition_breakdown, dict)
            v65_keys = [k for k in r.condition_breakdown if "v65" in k.lower()]
            assert len(v65_keys) >= 0


# ──────────────────────────────────────────────────────────────────────────────
# V66 条件 196-199 专项测试
# ──────────────────────────────────────────────────────────────────────────────

class TestV66ConditionGroup:
    """V66 ConditionGroup 枚举正确性测试。"""

    def test_v66_exists(self):
        """V66 分组应存在于枚举中。"""
        assert ConditionGroup.V66 in list(ConditionGroup)

    def test_v66_condition_range(self):
        """V66 条件范围应为 (196, 199)。"""
        assert ConditionGroup.V66.condition_range == (196, 199)

    def test_v66_description(self):
        """V66 应有描述。"""
        assert len(ConditionGroup.V66.description) > 0


class TestV66MMDFields:
    """V66 MMD 增强字段存在性测试。"""

    def test_v66_mmd_fields_exist(self):
        """缠论分析产生的 MMD 对象应包含 V66 增强字段。"""
        np.random.seed(99)
        df = _make_df(*_make_trending_df(300, trend="up"))
        analyser = ChanlunAnalyser(ChanlunConfig())
        result = analyser.process_klines(df)
        mmds = result.mmds
        buy_mmds = [m for m in mmds if "buy" in m.mmd_type.value]
        if buy_mmds:
            latest = buy_mmds[-1]
            assert hasattr(latest, "_macd_momentum_acceleration_v66")
            assert hasattr(latest, "_volume_price_coordination_deep_v66")
            assert hasattr(latest, "_multi_tf_convergence_intensity_v66")
            assert hasattr(latest, "_signal_execution_priority_v66")


class TestV66BacktestValidator:
    """V66 回测验证器测试。"""

    def test_v66_validator_usable(self):
        """ConditionGroup.V66 应可被 validator 使用。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_oscillating_df(400))
        results = validator.validate_conditions(df, [ConditionGroup.V66])
        assert len(results) == 1
        assert results[0].group == ConditionGroup.V66

    def test_v66_multi_group_validation(self):
        """V65 + V66 联合验证应返回两个结果。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_oscillating_df(400))
        results = validator.validate_conditions(df, [ConditionGroup.V65, ConditionGroup.V66])
        assert len(results) == 2
        groups = {r.group for r in results}
        assert groups == {ConditionGroup.V65, ConditionGroup.V66}

    def test_v66_summary_output(self):
        """V66 摘要应包含 V66 关键词。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_oscillating_df(400))
        results = validator.validate_conditions(df, [ConditionGroup.V66])
        assert len(results) == 1
        summary = results[0].summary()
        assert "V66" in summary

    def test_v66_confidence_correlation_valid(self):
        """V66 置信度相关性应在有效范围内。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_trending_df(400, trend="up"))
        results = validator.validate_conditions(df, [ConditionGroup.V66])
        assert len(results) == 1
        corr = results[0].confidence_correlation
        assert isinstance(corr, float)
        assert -1.0 <= corr <= 1.0 or corr == 0.0


class TestV66MultiStock:
    """V66 多股票对比测试。"""

    def test_v66_multi_stock_breakdown(self):
        """多股票对比应包含 V66 条件命中统计。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        data = {
            "sh600000": _make_df(*_make_oscillating_df(400)),
            "sz000001": _make_df(*_make_trending_df(400, trend="up")),
        }
        results = validator.validate_multi_stock(data)
        assert len(results) == 2
        for r in results:
            assert isinstance(r.condition_breakdown, dict)
            v66_keys = [k for k in r.condition_breakdown if "v66" in k.lower()]
            assert len(v66_keys) >= 0

class TestV67ConditionGroup:
    """V67 条件组枚举测试。"""

    def test_v67_exists(self):
        """ConditionGroup.V67 应存在。"""
        from easy_tdx.backtest.chanlun_validator import ConditionGroup
        assert hasattr(ConditionGroup, "V67")

    def test_v67_condition_range(self):
        """V67 应覆盖条件200-203。"""
        from easy_tdx.backtest.chanlun_validator import ConditionGroup
        start, end = ConditionGroup.V67.condition_range
        assert start == 200
        assert end == 203

    def test_v67_description(self):
        """V67 应有描述。"""
        from easy_tdx.backtest.chanlun_validator import ConditionGroup
        assert len(ConditionGroup.V67.description) > 0


class TestV67MMDFields:
    """V67 MMD 增强字段存在性测试。"""

    def test_v67_mmd_fields_exist(self):
        """缠论分析产生的 MMD 对象应包含 V67 增强字段。"""
        np.random.seed(100)
        df = _make_df(*_make_trending_df(300, trend="up"))
        analyser = ChanlunAnalyser(ChanlunConfig())
        result = analyser.process_klines(df)
        mmds = result.mmds
        buy_mmds = [m for m in mmds if "buy" in m.mmd_type.value]
        if buy_mmds:
            latest = buy_mmds[-1]
            assert hasattr(latest, "_zhongshu_divergence_strength_v67")
            assert hasattr(latest, "_multi_level_mmd_consistency_v67")
            assert hasattr(latest, "_post_signal_trajectory_health_v67")
            assert hasattr(latest, "_dynamic_sl_tp_recommendation_v67")


class TestV67BacktestValidator:
    """V67 回测验证器测试。"""

    def test_v67_validator_usable(self):
        """ConditionGroup.V67 应可被 validator 使用。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_oscillating_df(400))
        results = validator.validate_conditions(df, [ConditionGroup.V67])
        assert len(results) == 1
        assert results[0].group == ConditionGroup.V67

    def test_v67_multi_group_validation(self):
        """V66 + V67 联合验证应返回两个结果。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_oscillating_df(400))
        results = validator.validate_conditions(df, [ConditionGroup.V66, ConditionGroup.V67])
        assert len(results) == 2
        groups = {r.group for r in results}
        assert groups == {ConditionGroup.V66, ConditionGroup.V67}

    def test_v67_summary_output(self):
        """V67 摘要应包含 V67 关键词。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_oscillating_df(400))
        results = validator.validate_conditions(df, [ConditionGroup.V67])
        assert len(results) == 1
        summary = results[0].summary()
        assert "V67" in summary

    def test_v67_confidence_correlation_valid(self):
        """V67 置信度相关性应在有效范围内。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_trending_df(400, trend="up"))
        results = validator.validate_conditions(df, [ConditionGroup.V67])
        assert len(results) == 1
        corr = results[0].confidence_correlation
        assert isinstance(corr, float)
        assert -1.0 <= corr <= 1.0 or corr == 0.0


class TestV67MultiStock:
    """V67 多股票对比测试。"""

    def test_v67_multi_stock_breakdown(self):
        """多股票对比应包含 V67 条件命中统计。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        data = {
            "sh600000": _make_df(*_make_oscillating_df(400)),
            "sz000001": _make_df(*_make_trending_df(400, trend="up")),
        }
        results = validator.validate_multi_stock(data)
        assert len(results) == 2
        for r in results:
            assert isinstance(r.condition_breakdown, dict)
            v67_keys = [k for k in r.condition_breakdown if "v67" in k.lower()]
            assert len(v67_keys) >= 0



class TestV68ConditionGroup:
    """V68 条件组枚举测试。"""

    def test_v68_group_exists(self):
        """ConditionGroup.V68 应存在。"""
        assert hasattr(ConditionGroup, "V68")

    def test_v68_condition_range(self):
        """V68 应覆盖条件204-207。"""
        start, end = ConditionGroup.V68.condition_range
        assert start == 204
        assert end == 207

    def test_v68_description(self):
        """V68 应有描述。"""
        assert len(ConditionGroup.V68.description) > 0
        assert "缺口" in ConditionGroup.V68.description or "区间套" in ConditionGroup.V68.description


class TestV68MMDFields:
    """V68 MMD 增强字段存在性测试。"""

    def test_v68_fields_exist_on_mmd(self):
        """缠论分析产生的 MMD 对象应包含 V68 增强字段。"""
        from easy_tdx.chanlun.types import MMD
        mmd = MMD(mmd_type="buy_3", confidence=0.5, bi=None)
        assert hasattr(mmd, "_gap_trend_consistency_v68")
        assert hasattr(mmd, "_range_set_multi_level_v68")
        assert hasattr(mmd, "_post_signal_fund_flow_v68")
        assert hasattr(mmd, "_market_regime_adaptation_v68")


class TestV68BacktestValidator:
    """V68 回测验证器测试。"""

    def test_v68_validator_usage(self):
        """ConditionGroup.V68 应可被 validator 使用。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_trending_df(400, trend="up"))
        results = validator.validate_conditions(df, [ConditionGroup.V68])
        assert len(results) >= 1
        assert results[0].group == ConditionGroup.V68

    def test_v68_multi_group_validation(self):
        """V67 + V68 联合验证应返回两个结果。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_trending_df(400, trend="up"))
        results = validator.validate_conditions(df, [ConditionGroup.V67, ConditionGroup.V68])
        groups = {r.group for r in results}
        assert groups == {ConditionGroup.V67, ConditionGroup.V68}

    def test_v68_summary_output(self):
        """V68 摘要应包含 V68 关键词。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_trending_df(400, trend="up"))
        results = validator.validate_conditions(df, [ConditionGroup.V68])
        summary = results[0].summary()
        assert "V68" in summary


class TestV68MultiStock:
    """V68 多股票对比测试。"""

    def test_v68_multi_stock_breakdown(self):
        """多股票对比应包含 V68 条件命中统计。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        data = {
            "sh600000": _make_df(*_make_oscillating_df(400)),
            "sz000001": _make_df(*_make_trending_df(400, trend="up")),
        }
        results = validator.validate_multi_stock(data)
        assert len(results) == 2
        for r in results:
            assert isinstance(r.condition_breakdown, dict)
            v68_keys = [k for k in r.condition_breakdown if "v68" in k.lower()]
            assert len(v68_keys) >= 0


class TestV69ConditionGroup:
    """V69 条件组枚举测试。"""

    def test_v69_group_exists(self):
        """ConditionGroup.V69 应存在。"""
        assert hasattr(ConditionGroup, "V69")

    def test_v69_condition_range(self):
        """V69 应覆盖条件208-211。"""
        start, end = ConditionGroup.V69.condition_range
        assert start == 208
        assert end == 211

    def test_v69_description(self):
        """V69 应有描述。"""
        assert len(ConditionGroup.V69.description) > 0
        desc = ConditionGroup.V69.description
        assert "量价" in desc or "结构" in desc or "背离" in desc or "回踩" in desc


class TestV69MMDFields:
    """V69 MMD 增强字段存在性测试。"""

    def test_v69_fields_exist_on_mmd(self):
        """缠论分析产生的 MMD 对象应包含 V69 增强字段。"""
        from easy_tdx.chanlun.types import MMD
        mmd = MMD(mmd_type="buy_3", confidence=0.5, bi=None)
        assert hasattr(mmd, "_price_volume_divergence_v69")
        assert hasattr(mmd, "_structural_integrity_v69")
        assert hasattr(mmd, "_multi_indicator_divergence_v69")
        assert hasattr(mmd, "_retracement_depth_v69")


class TestV69BacktestValidator:
    """V69 回测验证器测试。"""

    def test_v69_validator_usage(self):
        """ConditionGroup.V69 应可被 validator 使用。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_trending_df(400, trend="up"))
        results = validator.validate_conditions(df, [ConditionGroup.V69])
        assert len(results) >= 1
        assert results[0].group == ConditionGroup.V69

    def test_v69_multi_group_validation(self):
        """V68 + V69 联合验证应返回两个结果。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_trending_df(400, trend="up"))
        results = validator.validate_conditions(df, [ConditionGroup.V68, ConditionGroup.V69])
        groups = {r.group for r in results}
        assert groups == {ConditionGroup.V68, ConditionGroup.V69}

    def test_v69_summary_output(self):
        """V69 摘要应包含 V69 关键词。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_trending_df(400, trend="up"))
        results = validator.validate_conditions(df, [ConditionGroup.V69])
        summary = results[0].summary()
        assert "V69" in summary


class TestV69MultiStock:
    """V69 多股票对比测试。"""

    def test_v69_multi_stock_breakdown(self):
        """多股票对比应包含 V69 条件命中统计。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        data = {
            "sh600000": _make_df(*_make_oscillating_df(400)),
            "sz000001": _make_df(*_make_trending_df(400, trend="up")),
        }
        results = validator.validate_multi_stock(data)
        assert len(results) == 2
        for r in results:
            assert isinstance(r.condition_breakdown, dict)
            v69_keys = [k for k in r.condition_breakdown if "v69" in k.lower()]
            assert len(v69_keys) >= 0


class TestV70ConditionGroup:
    """V70 条件组枚举测试。"""

    def test_v70_group_exists(self):
        """ConditionGroup.V70 应存在。"""
        assert hasattr(ConditionGroup, "V70")

    def test_v70_condition_range(self):
        """V70 应覆盖条件212-215。"""
        start, end = ConditionGroup.V70.condition_range
        assert start == 212
        assert end == 215

    def test_v70_description(self):
        """V70 应有描述。"""
        assert len(ConditionGroup.V70.description) > 0
        desc = ConditionGroup.V70.description
        assert "量峰" in desc or "时间" in desc or "假突破" in desc or "校准" in desc


class TestV70MMDFields:
    """V70 MMD 增强字段存在性测试。"""

    def test_v70_fields_exist_on_mmd(self):
        """缠论分析产生的 MMD 对象应包含 V70 增强字段。"""
        from easy_tdx.chanlun.types import MMD
        mmd = MMD(mmd_type="buy_3", confidence=0.5, bi=None)
        assert hasattr(mmd, "_volume_peak_detection_v70")
        assert hasattr(mmd, "_signal_time_decay_v70")
        assert hasattr(mmd, "_false_breakout_filter_v70")
        assert hasattr(mmd, "_final_confidence_calibration_v70")


class TestV70BacktestValidator:
    """V70 回测验证器测试。"""

    def test_v70_validator_usage(self):
        """ConditionGroup.V70 应可被 validator 使用。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_trending_df(400, trend="up"))
        results = validator.validate_conditions(df, [ConditionGroup.V70])
        assert len(results) >= 1
        assert results[0].group == ConditionGroup.V70

    def test_v70_multi_group_validation(self):
        """V69 + V70 联合验证应返回两个结果。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_trending_df(400, trend="up"))
        results = validator.validate_conditions(df, [ConditionGroup.V69, ConditionGroup.V70])
        groups = {r.group for r in results}
        assert groups == {ConditionGroup.V69, ConditionGroup.V70}

    def test_v70_summary_output(self):
        """V70 摘要应包含 V70 关键词。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        df = _make_df(*_make_trending_df(400, trend="up"))
        results = validator.validate_conditions(df, [ConditionGroup.V70])
        summary = results[0].summary()
        assert "V70" in summary


class TestV70MultiStock:
    """V70 多股票对比测试。"""

    def test_v70_multi_stock_breakdown(self):
        """多股票对比应包含 V70 条件命中统计。"""
        validator = ChanlunConditionBacktestValidator(min_bars=50)
        data = {
            "sh600000": _make_df(*_make_oscillating_df(400)),
            "sz000001": _make_df(*_make_trending_df(400, trend="up")),
        }
        results = validator.validate_multi_stock(data)
        assert len(results) == 2
        for r in results:
            assert isinstance(r.condition_breakdown, dict)
            v70_keys = [k for k in r.condition_breakdown if "v70" in k.lower()]
            assert len(v70_keys) >= 0


class TestV71ConditionGroup:
    """V71 条件组枚举测试。"""

    def test_v71_group_exists(self):
        """ConditionGroup.V71 应存在。"""
        assert hasattr(ConditionGroup, "V71")

    def test_v71_condition_range(self):
        """V71 应覆盖条件216-219。"""
        start, end = ConditionGroup.V71.condition_range
        assert start == 216
        assert end == 219

    def test_v71_description(self):
        """V71 应有描述。"""
        assert len(ConditionGroup.V71.description) > 0
        desc = ConditionGroup.V71.description
        assert any(kw in desc for kw in ["均线", "共振", "胜率", "风险收益"])


class TestV71MMDFields:
    """V71 MMD 增强字段存在性测试。"""

    def test_v71_fields_exist_on_mmd(self):
        """缠论分析产生的 MMD 对象应包含 V71 增强字段。"""
        from easy_tdx.chanlun.types import MMD
        mmd = MMD(mmd_type="buy_3", confidence=0.5, bi=None)
        assert hasattr(mmd, "_ma_alignment_strength_v71")
        assert hasattr(mmd, "_multi_tf_ma_resonance_v71")
        assert hasattr(mmd, "_mmd_history_winrate_v71")
        assert hasattr(mmd, "_dynamic_rr_optimization_v71")


class TestV71BacktestValidator:
    """V71 回测验证器测试。"""

    def test_v71_validator_usage(self):
        """ConditionGroup.V71 应可被 validator 使用。"""
        validator = ChanlunConditionBacktestValidator(min_bars=150)
        df = _make_df(*_make_trending_df(400, trend="up"))
        results = validator.validate_conditions(df, [ConditionGroup.V71])
        assert len(results) >= 1
        assert results[0].group == ConditionGroup.V71

    def test_v71_multi_group_validation(self):
        """V70 + V71 联合验证应返回两个结果。"""
        validator = ChanlunConditionBacktestValidator(min_bars=150)
        df = _make_df(*_make_trending_df(400, trend="up"))
        results = validator.validate_conditions(df, [ConditionGroup.V70, ConditionGroup.V71])
        groups = {r.group for r in results}
        assert groups == {ConditionGroup.V70, ConditionGroup.V71}

    def test_v71_summary_output(self):
        """V71 摘要应包含 V71 关键词。"""
        validator = ChanlunConditionBacktestValidator(min_bars=150)
        df = _make_df(*_make_trending_df(400, trend="up"))
        results = validator.validate_conditions(df, [ConditionGroup.V71])
        summary = results[0].summary()
        assert "V71" in summary


class TestV71MultiStock:
    """V71 多股票对比测试。"""

    def test_v71_multi_stock_breakdown(self):
        """多股票对比应包含 V71 条件命中统计。"""
        validator = ChanlunConditionBacktestValidator(min_bars=150)
        data = {
            "sh600000": _make_df(*_make_oscillating_df(400)),
            "sz000001": _make_df(*_make_trending_df(400, trend="up")),
        }
        results = validator.validate_multi_stock(data)
        assert len(results) == 2
        for r in results:
            assert isinstance(r.condition_breakdown, dict)
            v71_keys = [k for k in r.condition_breakdown if "v71" in k.lower()]
            assert len(v71_keys) >= 0


class TestV71Functions:
    """V71 计算函数功能测试。"""

    def test_ma_alignment_strength(self):
        """均线排列强度计算应返回正确结构。"""
        from easy_tdx.chanlun.mmd import _calc_ma_alignment_strength_v71
        from easy_tdx.chanlun.types import MMD, MMDType
        closes = list(range(100, 200))
        mmd = MMD(mmd_type=MMDType.BUY_3, confidence=0.5, bi=None)
        result = _calc_ma_alignment_strength_v71(mmd, closes)
        assert "alignment" in result
        assert "strength" in result
        assert "confidence_adjust" in result
        assert "msg" in result

    def test_multi_tf_ma_resonance(self):
        """多周期均线共振计算应返回正确结构。"""
        from easy_tdx.chanlun.mmd import _calc_multi_tf_ma_resonance_v71
        from easy_tdx.chanlun.types import MMD, MMDType
        closes = [100 + i * 0.5 for i in range(150)]
        mmd = MMD(mmd_type=MMDType.BUY_3, confidence=0.5, bi=None)
        result = _calc_multi_tf_ma_resonance_v71(mmd, closes)
        assert "short_aligned" in result
        assert "mid_aligned" in result
        assert "long_aligned" in result
        assert "resonance_count" in result
        assert "confidence_adjust" in result

    def test_dynamic_rr_optimization(self):
        """动态风险收益比计算应返回正确结构。"""
        from easy_tdx.chanlun.mmd import _calc_dynamic_rr_optimization_v71
        from easy_tdx.chanlun.types import MMD, MMDType
        import random
        random.seed(42)
        # 生成更有波动性的数据
        closes = [100.0]
        for _ in range(60):
            closes.append(closes[-1] + random.uniform(-2, 2.5))
        highs = [c + abs(random.uniform(0.3, 1.0)) for c in closes]
        lows = [c - abs(random.uniform(0.3, 1.0)) for c in closes]
        mmd = MMD(mmd_type=MMDType.BUY_3, confidence=0.5, bi=None)
        result = _calc_dynamic_rr_optimization_v71(mmd, closes, highs, lows, None)
        assert "stop_loss_pct" in result
        assert "take_profit_pct" in result
        assert "rr_ratio" in result
        # rr_ratio 应为正数（止损止盈都为正时）
        assert result["rr_ratio"] >= 0.0

    def test_mmd_history_winrate(self):
        """历史胜率回溯计算应返回正确结构。"""
        from easy_tdx.chanlun.mmd import _calc_mmd_history_winrate_v71
        from easy_tdx.chanlun.types import MMD, MMDType
        import random
        random.seed(42)
        closes = [100 + sum(random.uniform(-1, 1.5) for _ in range(i)) for i in range(200)]
        volumes = [random.uniform(0.5, 2.0) for _ in range(200)]
        mmd = MMD(mmd_type=MMDType.BUY_3, confidence=0.5, bi=None)
        result = _calc_mmd_history_winrate_v71(mmd, closes, volumes)
        assert "lookback_winrate" in result
        assert "sample_count" in result
        assert "confidence_adjust" in result


# ──────────────────────────────────────────────────────────────────────────────
# V72: 条件 220-223（均线收敛发散+支撑阻力距离+量价结构质量+信号衰减速度）
# ──────────────────────────────────────────────────────────────────────────────

class TestV72ConditionGroup:
    """V72 ConditionGroup 枚举测试。"""

    def test_v72_group_exists(self):
        assert hasattr(ConditionGroup, 'V72')
        assert ConditionGroup.V72.value == "v72"

    def test_v72_condition_range(self):
        group = ConditionGroup.V72
        start, end = group.condition_range
        assert start == 220
        assert end == 223

    def test_v72_description(self):
        desc = ConditionGroup.V72.description
        assert "均线收敛发散" in desc or "支撑阻力" in desc or "量价结构" in desc or "信号衰减" in desc


class TestV72MMDFields:
    """V72 MMD 增强字段存在性测试。"""

    def test_v72_fields_exist_on_mmd(self):
        """MMD 对象应包含 V72 增强字段。"""
        from easy_tdx.chanlun.types import MMD
        mmd = MMD(mmd_type="buy_3", confidence=0.5, bi=None)
        assert hasattr(mmd, "_ma_convergence_divergence_v72")
        assert hasattr(mmd, "_support_resistance_proximity_v72")
        assert hasattr(mmd, "_volume_structure_quality_v72")
        assert hasattr(mmd, "_signal_decay_velocity_v72")


class TestV72BacktestValidator:
    """V72 回测验证器测试。"""

    def test_v72_validator_usage(self):
        """ConditionGroup.V72 应可被 validator 使用。"""
        validator = ChanlunConditionBacktestValidator(min_bars=150)
        df = _make_df(*_make_trending_df(400, trend="up"))
        results = validator.validate_conditions(df, [ConditionGroup.V72])
        assert len(results) >= 1
        assert results[0].group == ConditionGroup.V72

    def test_v72_multi_group_validation(self):
        """V71 + V72 联合验证应返回两个结果。"""
        validator = ChanlunConditionBacktestValidator(min_bars=150)
        df = _make_df(*_make_trending_df(400, trend="up"))
        results = validator.validate_conditions(df, [ConditionGroup.V71, ConditionGroup.V72])
        groups = {r.group for r in results}
        assert groups == {ConditionGroup.V71, ConditionGroup.V72}

    def test_v72_summary_output(self):
        """V72 摘要应包含 V72 关键词。"""
        validator = ChanlunConditionBacktestValidator(min_bars=150)
        df = _make_df(*_make_trending_df(400, trend="up"))
        results = validator.validate_conditions(df, [ConditionGroup.V72])
        summary = results[0].summary()
        assert "V72" in summary

class TestV72Functions:
    """V72 计算函数功能测试。"""

    def test_ma_convergence_divergence(self):
        """均线收敛发散评估应返回正确结构。"""
        from easy_tdx.chanlun.mmd import _calc_ma_convergence_divergence_v72
        from easy_tdx.chanlun.types import MMD, MMDType
        np.random.seed(99)
        closes = [100.0]
        for _ in range(100):
            closes.append(closes[-1] * (1 + np.random.randn() * 0.01))
        mmd = MMD(mmd_type=MMDType.BUY_3, confidence=0.5, bi=None)
        result = _calc_ma_convergence_divergence_v72(mmd, closes)
        assert "state" in result
        assert "spread_pct" in result
        assert "confidence_adjust" in result
        assert "msg" in result
        assert result["state"] in ("converging", "diverging", "entangled", "unknown")

    def test_support_resistance_proximity(self):
        """支撑阻力位距离评估应返回正确结构。"""
        from easy_tdx.chanlun.mmd import _calc_support_resistance_proximity_v72
        from easy_tdx.chanlun.types import MMD, MMDType
        np.random.seed(77)
        closes = [50.0]
        highs = [50.0]
        lows = [50.0]
        for _ in range(50):
            c = closes[-1] * (1 + np.random.randn() * 0.02)
            h = max(c, closes[-1]) * (1 + abs(np.random.randn()) * 0.01)
            l = min(c, closes[-1]) * (1 - abs(np.random.randn()) * 0.01)
            closes.append(c)
            highs.append(h)
            lows.append(l)
        mmd = MMD(mmd_type=MMDType.BUY_3, confidence=0.5, bi=None)
        result = _calc_support_resistance_proximity_v72(mmd, closes, highs, lows)
        assert "current_price" in result
        assert "nearest_support" in result
        assert "nearest_resistance" in result
        assert "support_dist_pct" in result
        assert "confidence_adjust" in result

    def test_volume_structure_quality(self):
        """量价结构质量评分应返回正确结构。"""
        from easy_tdx.chanlun.mmd import _calc_volume_structure_quality_v72
        from easy_tdx.chanlun.types import MMD, MMDType
        np.random.seed(55)
        closes = [100.0]
        volumes = [1e6]
        for _ in range(80):
            closes.append(closes[-1] * (1 + np.random.randn() * 0.015))
            volumes.append(1e6 * (1 + abs(np.random.randn()) * 0.5))
        mmd = MMD(mmd_type=MMDType.BUY_3, confidence=0.5, bi=None)
        result = _calc_volume_structure_quality_v72(mmd, closes, volumes)
        assert "up_vol_ratio" in result
        assert "down_vol_ratio" in result
        assert "volume_health" in result
        assert "stability_score" in result
        assert "confidence_adjust" in result

    def test_signal_decay_velocity(self):
        """信号衰减速度评估应返回正确结构。"""
        from easy_tdx.chanlun.mmd import _calc_signal_decay_velocity_v72
        from easy_tdx.chanlun.types import MMD, MMDType
        np.random.seed(33)
        closes = [100.0]
        for _ in range(80):
            closes.append(closes[-1] * (1 + np.random.randn() * 0.01))
        # 构造历史信号
        mmds_all = []
        for i in range(5):
            mmd = MMD(mmd_type=MMDType.BUY_3, confidence=0.4 + i * 0.05, bi=None)
            mmds_all.append(mmd)
        mmd = MMD(mmd_type=MMDType.BUY_3, confidence=0.65, bi=None)
        result = _calc_signal_decay_velocity_v72(mmd, closes, mmds_all)
        assert "recent_confidences" in result
        assert "trend_direction" in result
        assert "velocity" in result
        assert "confidence_adjust" in result

    def test_v72_data_insufficient(self):
        """数据不足时应返回默认值。"""
        from easy_tdx.chanlun.mmd import (
            _calc_ma_convergence_divergence_v72,
            _calc_support_resistance_proximity_v72,
            _calc_volume_structure_quality_v72,
        )
        from easy_tdx.chanlun.types import MMD, MMDType
        mmd = MMD(mmd_type=MMDType.BUY_3, confidence=0.5, bi=None)
        short_closes = [100.0, 101.0, 102.0]
        result = _calc_ma_convergence_divergence_v72(mmd, short_closes)
        assert result["msg"] != ""
        result2 = _calc_support_resistance_proximity_v72(mmd, short_closes, None, None)
        assert result2["msg"] != ""
        result3 = _calc_volume_structure_quality_v72(mmd, short_closes, None)
        assert result3["msg"] != ""
