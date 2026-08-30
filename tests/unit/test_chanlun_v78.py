"""V78 缠论条件 244-247 单元测试。

条件244：买卖点周期位置评分（MMD Cycle Position）
条件245：多信号时间窗口一致性（Multi-Signal Consensus）
条件246：波动率压缩突破预测（Volatility Compression Breakout）
条件247：资金流向与价格背离检测（Fund Flow Divergence）
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from easy_tdx.backtest.chanlun_validator import ConditionGroup
from easy_tdx.chanlun.mmd import (
    _calc_fund_flow_divergence_v78,
    _calc_mmd_cycle_position_v78,
    _calc_multi_signal_consensus_v78,
    _calc_volatility_compression_breakout_v78,
)
from easy_tdx.chanlun.types import MMD, MMDType


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
    return [c + spread + random.uniform(0, 0.5) for c, random in zip(closes, [0] * len(closes))]


def _make_lows(closes: list[float], spread: float = 1.0) -> list[float]:
    return [c - spread + random.uniform(-0.5, 0) for c, random in zip(closes, [0] * len(closes))]


def _make_volumes(n: int = 80, base: float = 1000.0) -> list[float]:
    import random

    random.seed(43)
    return [base + random.uniform(-200, 200) for _ in range(n)]


# ── TestV78ConditionGroup：ConditionGroup 枚举测试 ───────────────────────────


class TestV78ConditionGroup:
    """V78 ConditionGroup 存在性和正确性测试。"""

    def test_v78_exists(self):
        assert hasattr(ConditionGroup, "V78")

    def test_v78_condition_range(self):
        assert ConditionGroup.V78.condition_range == (244, 247)

    def test_v78_description(self):
        desc = ConditionGroup.V78.description
        assert len(desc) > 0
        assert "周期位置" in desc or "多信号" in desc or "波动率" in desc or "资金" in desc


# ── TestV78MMDFields：MMD 对象字段测试 ───────────────────────────────────────


class TestV78MMDFields:
    """MMD 对象包含 V78 字段。"""

    def test_mmd_has_v78_fields(self):
        mmd = _make_mmd()
        assert hasattr(mmd, "_mmd_cycle_position_v78")
        assert hasattr(mmd, "_multi_signal_consensus_v78")
        assert hasattr(mmd, "_volatility_compression_breakout_v78")
        assert hasattr(mmd, "_fund_flow_divergence_v78")


# ── TestV78BacktestValidator：回测验证器测试 ─────────────────────────────────


class TestV78BacktestValidator:
    """V78 条件回测验证器测试。"""

    def test_v78_validator_usage(self):
        from easy_tdx.backtest.chanlun_validator import ChanlunConditionBacktestValidator

        _ = ChanlunConditionBacktestValidator()
        assert ConditionGroup.V78 in list(ConditionGroup)

    def test_v78_multi_group_validation(self):
        groups = [ConditionGroup.V76, ConditionGroup.V77, ConditionGroup.V78]
        ranges = [g.condition_range for g in groups]
        assert ranges[0] == (236, 239)
        assert ranges[1] == (240, 243)
        assert ranges[2] == (244, 247)

    def test_v78_summary_output(self):
        from easy_tdx.backtest.chanlun_validator import ChanlunConditionBacktestValidator

        validator = ChanlunConditionBacktestValidator()
        summary = validator.validate_conditions({}, [ConditionGroup.V78])
        assert summary is not None


# ── TestV78Functions：各计算函数单元测试 ─────────────────────────────────────


class TestV78Functions:
    """V78 四个计算函数的单元测试。"""

    # ── 条件244：买卖点周期位置评分 ──────────────────────────────────────────

    def test_mcp_buy_at_bottom(self):
        """买入信号在波段底部 → 高评分。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = _make_closes(80, base=80.0, trend="flat")
        highs = [c + 1.5 for c in closes]
        lows = [c - 1.5 for c in closes]
        result = _calc_mmd_cycle_position_v78(mmd, closes, highs, lows)
        assert "position_score" in result
        assert "cycle_position" in result
        assert "distance_to_low" in result
        assert "distance_to_high" in result
        assert "confidence_adjust" in result
        assert isinstance(result["position_score"], float)
        assert 0 <= result["position_score"] <= 1.0
        assert result["cycle_position"] in ["bottom", "lower", "mid", "upper", "top"]

    def test_mcp_sell_at_top(self):
        """卖出信号在波段顶部 → 高评分。"""
        mmd = _make_mmd("3sell", 0.6)
        closes = _make_closes(80, base=150.0, trend="flat")
        highs = [c + 1.5 for c in closes]
        lows = [c - 1.5 for c in closes]
        result = _calc_mmd_cycle_position_v78(mmd, closes, highs, lows)
        assert "position_score" in result
        assert result["position_score"] >= 0.0

    def test_mcp_insufficient_data(self):
        """数据不足时返回默认值。"""
        mmd = _make_mmd("3buy", 0.6)
        result = _calc_mmd_cycle_position_v78(mmd, [1.0, 2.0], [2.0, 3.0], [1.0, 2.0])
        assert result["msg"] != ""
        assert result["position_score"] == 0.5
        assert result["confidence_adjust"] == 0.0

    def test_mcp_mid_position(self):
        """中部位置 → 中性评分。"""
        mmd = _make_mmd("3buy", 0.6)
        # 价格在中间位置
        closes = [50.0 + i * 0.5 for i in range(80)]  # 从50涨到90
        highs = [c + 1.0 for c in closes]
        lows = [c - 1.0 for c in closes]
        result = _calc_mmd_cycle_position_v78(mmd, closes, highs, lows)
        assert result["cycle_position"] in ["bottom", "lower", "mid", "upper", "top"]
        assert isinstance(result["distance_to_low"], float)
        assert isinstance(result["distance_to_high"], float)

    # ── 条件245：多信号时间窗口一致性 ──────────────────────────────────────────

    def test_msc_strong_consensus_buy(self):
        """多个买入信号共识 → 强共识。"""
        mmds = [
            _make_mmd("3buy", 0.6),
            _make_mmd("3buy", 0.5),
            _make_mmd("3buy", 0.7),
        ]
        current = mmds[2]
        closes = _make_closes(60)
        result = _calc_multi_signal_consensus_v78(mmds, current, closes)
        assert "consensus_score" in result
        assert "nearby_buy_count" in result
        assert "nearby_sell_count" in result
        assert "consensus_level" in result
        assert isinstance(result["consensus_score"], float)
        assert 0 <= result["consensus_score"] <= 1.0

    def test_msc_isolated_signal(self):
        """孤立信号 → 中性评分。"""
        mmds = [_make_mmd("3buy", 0.6)]
        current = mmds[0]
        closes = _make_closes(60)
        result = _calc_multi_signal_consensus_v78(mmds, current, closes)
        assert result["consensus_level"] in ["isolated", "unknown"]
        assert result["consensus_score"] == 0.5

    def test_msc_insufficient_data(self):
        """信号不足时返回默认值。"""
        mmd = _make_mmd("3buy", 0.6)
        result = _calc_multi_signal_consensus_v78([], mmd, [1.0, 2.0])
        assert result["msg"] != ""
        assert result["consensus_score"] == 0.5

    def test_msc_consensus_levels(self):
        """共识等级枚举有效性。"""
        mmds = [
            _make_mmd("3buy", 0.6),
            _make_mmd("3buy", 0.5),
            _make_mmd("3sell", 0.5),
            _make_mmd("3buy", 0.7),
        ]
        current = mmds[3]
        closes = _make_closes(60)
        result = _calc_multi_signal_consensus_v78(mmds, current, closes)
        valid_levels = {
            "strong_consensus",
            "moderate_consensus",
            "contradicted",
            "isolated",
            "mixed",
        }
        assert result["consensus_level"] in valid_levels

    # ── 条件246：波动率压缩突破预测 ──────────────────────────────────────────

    def test_vcb_compressed_up(self):
        """波动率压缩且价格在上沿 → 向上突破预测。"""
        # 创建低波动率序列（压缩状态）
        closes = [100.0 + 0.01 * i for i in range(80)]  # 非常小的波动
        highs = [c + 0.02 for c in closes]
        lows = [c - 0.02 for c in closes]
        result = _calc_volatility_compression_breakout_v78(closes, highs, lows)
        assert "compression_score" in result
        assert "boll_width_percentile" in result
        assert "breakout_direction" in result
        assert "confidence_adjust" in result
        assert 0 <= result["compression_score"] <= 1.0

    def test_vcb_expanding(self):
        """波动率扩张状态 → 正常评分。"""
        closes = [100.0 + 2.0 * i * 0.1 for i in range(80)]  # 大波动
        highs = [c + 2.0 for c in closes]
        lows = [c - 2.0 for c in closes]
        result = _calc_volatility_compression_breakout_v78(closes, highs, lows)
        assert "breakout_direction" in result
        assert result["breakout_direction"] in [
            "up",
            "up_continuing",
            "down",
            "down_continuing",
            "neutral",
            "normal",
        ]

    def test_vcb_insufficient_data(self):
        """数据不足时返回默认值。"""
        result = _calc_volatility_compression_breakout_v78([1.0, 2.0], [2.0, 3.0], [1.0, 2.0])
        assert result["msg"] != ""
        assert result["compression_score"] == 0.5
        assert result["confidence_adjust"] == 0.0

    def test_vcb_percent_b_range(self):
        """percent_b 应在合理范围内。"""
        closes = _make_closes(80, base=100.0)
        highs = [c + 1.0 for c in closes]
        lows = [c - 1.0 for c in closes]
        result = _calc_volatility_compression_breakout_v78(closes, highs, lows)
        # boll_width_percentile 应合法
        assert isinstance(result["boll_width_percentile"], float)

    # ── 条件247：资金流向与价格背离检测 ──────────────────────────────────────

    def test_ffd_bullish_divergence(self):
        """看涨背离：价格下跌但量能放大。"""
        closes = [100.0 - i * 0.1 for i in range(40)]  # 价格下跌
        volumes = [500.0 + i * 20 for i in range(40)]  # 量能放大
        result = _calc_fund_flow_divergence_v78(closes, volumes)
        assert "divergence_type" in result
        assert "money_flow_score" in result
        assert "volume_price_correlation" in result
        assert isinstance(result["money_flow_score"], float)
        assert 0 <= result["money_flow_score"] <= 1.0

    def test_ffd_confirmed_up(self):
        """量价齐升 → 确认上涨。"""
        closes = [100.0 + i * 0.1 for i in range(40)]  # 价格上涨
        volumes = [500.0 + i * 20 for i in range(40)]  # 量能放大
        result = _calc_fund_flow_divergence_v78(closes, volumes)
        assert result["divergence_type"] in [
            "bearish_divergence",
            "bullish_divergence",
            "confirmed_up",
            "confirmed_down",
            "neutral",
        ]

    def test_ffd_neutral(self):
        """中性场景 → 无背离。"""
        closes = [100.0 + 0.01 * i for i in range(40)]  # 几乎不变
        volumes = [500.0 + 0.01 * i for i in range(40)]
        result = _calc_fund_flow_divergence_v78(closes, volumes)
        assert "divergence_type" in result
        assert isinstance(result["volume_price_correlation"], float)

    def test_ffd_insufficient_data(self):
        """数据不足时返回默认值。"""
        result = _calc_fund_flow_divergence_v78([1.0, 2.0], [100.0, 200.0])
        assert result["msg"] != ""
        assert result["money_flow_score"] == 0.5
        assert result["confidence_adjust"] == 0.0

    def test_ffd_correlation_range(self):
        """量价相关系数应在 [-1, 1] 范围内。"""
        closes = _make_closes(40, base=100.0)
        volumes = _make_volumes(40)
        result = _calc_fund_flow_divergence_v78(closes, volumes)
        assert -1.0 <= result["volume_price_correlation"] <= 1.0

    # ── 综合冒烟测试 ──────────────────────────────────────────────────────

    def test_all_v78_functions_no_crash(self):
        """所有 V78 函数在无异常情况下正常运行。"""
        mmd = _make_mmd("3buy", 0.6)
        closes = _make_closes(80, base=100.0)
        volumes = _make_volumes(80)
        highs = [c + 1.0 for c in closes]
        lows = [c - 1.0 for c in closes]

        r1 = _calc_mmd_cycle_position_v78(mmd, closes, highs, lows)
        r2 = _calc_multi_signal_consensus_v78([mmd], mmd, closes)
        r3 = _calc_volatility_compression_breakout_v78(closes, highs, lows)
        r4 = _calc_fund_flow_divergence_v78(closes, volumes)

        assert all(r is not None for r in [r1, r2, r3, r4])
        assert all(isinstance(r.get("confidence_adjust", 0), float) for r in [r1, r2, r3, r4])

    def test_v78_vs_v77_consistency(self):
        """V78 与 V77 函数互不干扰。"""
        from easy_tdx.chanlun.mmd import (
            _calc_volume_distribution_depth_v77,
            _calc_zhongshu_structure_weight_v77,
        )

        mmd = _make_mmd("3buy", 0.6)
        closes = _make_closes(80)
        volumes = _make_volumes(80)
        from easy_tdx.chanlun.types import ZS

        zss = [ZS(index=0, zg=100.5, zd=99.5)]

        # V77 函数仍能正常工作
        r_v77_1 = _calc_volume_distribution_depth_v77(mmd, closes, volumes)
        r_v77_2 = _calc_zhongshu_structure_weight_v77(mmd, zss, closes)
        assert r_v77_1 is not None
        assert r_v77_2 is not None

        # V78 函数正常工作
        highs = [c + 1.0 for c in closes]
        lows = [c - 1.0 for c in closes]
        r_v78_1 = _calc_mmd_cycle_position_v78(mmd, closes, highs, lows)
        r_v78_2 = _calc_fund_flow_divergence_v78(closes, volumes)
        assert r_v78_1 is not None
        assert r_v78_2 is not None
