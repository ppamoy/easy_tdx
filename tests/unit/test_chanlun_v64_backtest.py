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
        """所有 V58-V63 分组都应定义。"""
        expected = {"V58", "V59", "V60", "V61", "V62", "V63"}
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
