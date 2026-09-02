"""V102 测试：多信号相关性、质量评分卡、决策支持和历史模式匹配。"""

from unittest.mock import MagicMock

import pytest

from easy_tdx.chanlun.mmd import (
    _calc_decision_support_enhanced,
    _calc_historical_pattern_matching,
    _calc_multi_signal_correlation,
    _calc_signal_quality_scorecard,
)
from easy_tdx.chanlun.types import BI, MMD, MMDType


def create_mock_kline(index: int, price: float = 100.0) -> MagicMock:
    """创建模拟 K 线对象。"""
    kline = MagicMock()
    kline.k_index = index
    return kline


def create_mock_bi(end_index: int = 10, direction: str = "up") -> BI:
    """创建模拟笔对象。"""
    bi = MagicMock(spec=BI)
    bi.end = MagicMock()
    bi.end.k = create_mock_kline(end_index)
    bi.low = 98.0
    bi.high = 102.0
    return bi


def create_mock_mmd(mmd_type: MMDType = MMDType.BUY_3, bi_end_index: int = 10) -> MMD:
    """创建模拟买卖点对象。"""
    mmd = MagicMock(spec=MMD)
    mmd.mmd_type = mmd_type
    mmd.bi = create_mock_bi(bi_end_index, "up" if mmd_type == MMDType.BUY_3 else "down")
    mmd.zs = None
    mmd.confidence = 0.6
    mmd.msg = "测试信号"
    return mmd


class TestMultiSignalCorrelation:
    """测试多信号相关性分析（条件264）。"""

    def test_single_signal(self):
        """单个信号时不应有调整。"""
        mmd = create_mock_mmd()
        all_mmds = [mmd]
        closes = list(range(20, 50))  # 30 根 K 线

        result = _calc_multi_signal_correlation(mmd, all_mmds, closes)

        assert result["nearby_signals"] == 0
        assert result["signal_density"] == "low"
        assert result["confidence_adjust"] == 0.02

    def test_dense_signals(self):
        """密集信号时应降低置信度。"""
        mmd = create_mock_mmd()
        mmd2 = create_mock_mmd()
        mmd2.bi.end.k = create_mock_kline(12)  # 相邻位置
        mmd3 = create_mock_mmd()
        mmd3.bi.end.k = create_mock_kline(15)  # 较近位置
        mmd4 = create_mock_mmd()
        mmd4.bi.end.k = create_mock_kline(18)  # 较近位置
        all_mmds = [mmd, mmd2, mmd3, mmd4]
        closes = list(range(20, 50))

        result = _calc_multi_signal_correlation(mmd, all_mmds, closes)

        assert result["nearby_signals"] >= 3
        assert result["signal_density"] == "high"
        assert result["confidence_adjust"] == -0.03

    def test_non_buy_sell_signal(self):
        """非 3 买/3 卖信号应跳过。"""
        mmd = MagicMock(spec=MMD)
        mmd.mmd_type = MMDType.BUY_1  # 非 3 买
        mmd.bi = create_mock_bi()
        all_mmds = [mmd]
        closes = list(range(20, 50))

        result = _calc_multi_signal_correlation(mmd, all_mmds, closes)

        assert "非3买/3卖信号" in result.get("msg", "")


class TestSignalQualityScorecard:
    """测试信号质量评分卡（条件265）。"""

    def test_strong_buy_signal(self):
        """强买入信号应获得高分。"""
        mmd = create_mock_mmd(MMDType.BUY_3, 20)
        closes = [100 + i * 0.2 for i in range(60)]  # 60 根 K 线上升趋势 (ma5>ma20>ma60)
        volumes = [1000] * 55 + [1500] * 5  # 近期放量 >1.2 倍
        macd_data = {
            "dif": [0.2, 0.2, 0.3, 0.3, 0.5],
            "dea": [0.2, 0.2, 0.25, 0.35, 0.4],  # 最后一根金叉
            "hist": [0.01, 0.01, 0.02, 0.03, 0.05],  # 柱状持续放大
        }

        result = _calc_signal_quality_scorecard(mmd, closes, volumes, macd_data, 0.01)

        assert result["overall_grade"] in ["A", "B"]
        assert result["overall_score"] >= 3.0

    def test_weak_signal(self):
        """弱信号应获得低分。"""
        mmd = create_mock_mmd(MMDType.BUY_3, 20)
        closes = [100] * 30  # 无趋势
        volumes = None
        macd_data = None

        result = _calc_signal_quality_scorecard(mmd, closes, volumes, macd_data, None)

        assert result["overall_grade"] in ["C", "D"]
        assert result["overall_score"] < 3.0

    def test_non_buy_sell_signal(self):
        """非 3 买/3 卖信号应返回特殊消息。"""
        mmd = MagicMock(spec=MMD)
        mmd.mmd_type = MMDType.BUY_1
        result = _calc_signal_quality_scorecard(mmd, [], None, None, None)

        assert "非3买/3卖信号" in result.get("msg", "")


class TestDecisionSupportEnhanced:
    """测试决策支持输出（条件266）。"""

    def test_buy_signal_with_good_rrr(self):
        """买入信号应有合理的风险收益比。"""
        mmd = create_mock_mmd(MMDType.BUY_3, 20)
        mmd.zs = MagicMock()
        mmd.zs.zg = 105.0
        mmd.zs.zd = 95.0
        closes = [100.0] * 30
        highs = [101.0] * 30
        lows = [99.0] * 30

        result = _calc_decision_support_enhanced(mmd, closes, highs, lows, None, None)

        assert result["entry_price"] > 0
        assert result["stop_loss"] < result["entry_price"]
        assert result["take_profit_1"] > result["entry_price"]
        assert "买入" in result["action_recommendation"]

    def test_sell_signal_with_good_rrr(self):
        """卖出信号应有合理的风险收益比。"""
        mmd = create_mock_mmd(MMDType.SELL_3, 20)
        mmd.zs = MagicMock()
        mmd.zs.zg = 105.0
        mmd.zs.zd = 95.0
        closes = [100.0] * 30
        highs = [101.0] * 30
        lows = [99.0] * 30

        result = _calc_decision_support_enhanced(mmd, closes, highs, lows, None, None)

        assert result["entry_price"] > 0
        assert result["stop_loss"] > result["entry_price"]
        assert result["take_profit_1"] < result["entry_price"]
        assert "卖出" in result["action_recommendation"]

    def test_non_buy_sell_signal(self):
        """非 3 买/3 卖信号应返回空操作建议。"""
        mmd = MagicMock(spec=MMD)
        mmd.mmd_type = MMDType.BUY_1
        result = _calc_decision_support_enhanced(mmd, [], None, None, None, None)

        assert "非3买/3卖信号" in result.get("action_recommendation", "")


class TestHistoricalPatternMatching:
    """测试历史模式匹配（条件267）。"""

    def test_sufficient_history(self):
        """历史数据充足时应找到相似模式。"""
        mmd = create_mock_mmd(MMDType.BUY_3, 50)
        # 创建 100 根 K 线，包含上升趋势后下跌的模式
        closes = []
        for i in range(100):
            if i < 50:
                closes.append(100 + i * 0.5)  # 上升趋势
            else:
                closes.append(125 - (i - 50) * 0.3)  # 回调

        result = _calc_historical_pattern_matching(mmd, closes, None)

        assert result["similar_patterns_found"] > 0
        assert "win_rate" in result

    def test_insufficient_history(self):
        """历史数据不足时应返回提示信息。"""
        mmd = create_mock_mmd(MMDType.BUY_3, 10)
        closes = list(range(10, 30))  # 只有 20 根 K 线

        result = _calc_historical_pattern_matching(mmd, closes, None)

        assert "历史数据不足" in result.get("msg", "") or result["similar_patterns_found"] == 0

    def test_non_buy_sell_signal(self):
        """非 3 买/3 卖信号应跳过模式匹配。"""
        mmd = MagicMock(spec=MMD)
        mmd.mmd_type = MMDType.BUY_1
        result = _calc_historical_pattern_matching(mmd, list(range(100)), None)

        assert "非3买/3卖信号" in result.get("msg", "")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
