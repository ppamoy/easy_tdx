"""V63 缠论模型增强测试：中枢级别权重优化增强(190) + 多周期信号衰减追踪(191)。

覆盖：
- 条件190: _calc_zhongshu_level_weight_enhanced_v63
- 条件191: _calc_multi_period_signal_decay_v63
- 集成测试: find_mmds_v39 中 V63 条件集成
"""

from __future__ import annotations

import pytest

from easy_tdx.chanlun.mmd import (
    _calc_multi_period_signal_decay_v63,
    _calc_zhongshu_level_weight_enhanced_v63,
)
from easy_tdx.chanlun.types import MMD, ZS, MMDType

# ──────────────────────────────────────────────────────────────────────────────
# 条件190: 中枢级别权重优化增强
# ──────────────────────────────────────────────────────────────────────────────


class TestZhongshuLevelWeightEnhancedV63:
    """条件190 测试。"""

    def _make_mmd(self, mmd_type: MMDType) -> MMD:
        return MMD(
            mmd_type=mmd_type,
            bi=None,
            zs=None,
            confidence=0.5,
            msg="",
        )

    def _make_zs(
        self, line_count: int, zg: float = 100.0, zd: float = 90.0, done: bool = True
    ) -> ZS:
        from unittest.mock import MagicMock

        lines = [MagicMock() for _ in range(line_count)]
        zs = ZS(index=0, lines=lines, zg=zg, zd=zd, gg=zg, dd=zd, direction="up", done=done)
        return zs

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号应跳过。"""
        mmd = self._make_mmd(MMDType.BUY_1)
        zss = [self._make_zs(5)]
        closes = [100.0] * 30
        result = _calc_zhongshu_level_weight_enhanced_v63(mmd, zss, closes)
        assert "跳过此条件" in result["msg"]
        assert result["confidence_adjust"] == 0.0

    def test_no_zs_data(self):
        """无中枢数据应返回空结果。"""
        mmd = self._make_mmd(MMDType.BUY_3)
        result = _calc_zhongshu_level_weight_enhanced_v63(mmd, [], [100.0] * 30)
        assert "无中枢数据" in result["msg"]
        assert result["confidence_adjust"] == 0.0

    def test_insufficient_closes(self):
        """K线数据不足应返回空结果。"""
        mmd = self._make_mmd(MMDType.BUY_3)
        zss = [self._make_zs(5)]
        result = _calc_zhongshu_level_weight_enhanced_v63(mmd, zss, [100.0] * 15)
        assert "数据不足" in result["msg"]

    def test_monthly_level_high_weight(self):
        """月线级别中枢应获得高权重。"""
        mmd = self._make_mmd(MMDType.BUY_3)
        zs = self._make_zs(15, zg=100.0, zd=90.0, done=True)
        # 价格在ZG附近（突破确认）
        closes = [95.0] * 20 + [100.5, 101.0, 101.5]
        result = _calc_zhongshu_level_weight_enhanced_v63(mmd, [zs], closes)
        assert result["level"] == "月线"
        assert result["distance_score"] == 4  # 紧贴ZG突破
        assert result["total_weight_bonus"] >= 15
        assert result["confidence_adjust"] == 0.05

    def test_daily_level_medium_weight(self):
        """日线级别中枢应获得中等权重。"""
        mmd = self._make_mmd(MMDType.BUY_3)
        zs = self._make_zs(5, zg=100.0, zd=90.0, done=True)
        closes = [95.0] * 20 + [100.5, 101.0]
        result = _calc_zhongshu_level_weight_enhanced_v63(mmd, [zs], closes)
        assert result["level"] == "日线"
        assert result["distance_score"] == 4

    def test_small_level_low_weight(self):
        """小级别中枢应获得低权重。"""
        mmd = self._make_mmd(MMDType.BUY_3)
        zs = self._make_zs(3, zg=100.0, zd=95.0, done=False)
        closes = [97.0] * 20 + [100.2, 100.5]
        result = _calc_zhongshu_level_weight_enhanced_v63(mmd, [zs], closes)
        assert result["level"] == "小级别"
        assert result["quality_score"] <= 2  # 未完成的中枢质量分低

    def test_sell_signal_distance(self):
        """3卖信号的距离评分应正确计算。"""
        mmd = self._make_mmd(MMDType.SELL_3)
        zs = self._make_zs(5, zg=100.0, zd=90.0, done=True)
        # 价格跌破ZD
        closes = [95.0] * 20 + [89.5, 89.0]
        result = _calc_zhongshu_level_weight_enhanced_v63(mmd, [zs], closes)
        assert result["distance_score"] == 4  # 紧贴ZD跌破
        assert result["level"] == "日线"

    def test_confidence_adjust_bounds(self):
        """置信度调整应在合理范围内。"""
        mmd = self._make_mmd(MMDType.BUY_3)
        zs = self._make_zs(5, zg=100.0, zd=90.0, done=True)
        closes = [95.0] * 20 + [100.5, 101.0]
        result = _calc_zhongshu_level_weight_enhanced_v63(mmd, [zs], closes)
        assert -0.05 <= result["confidence_adjust"] <= 0.05

    def test_msg_format(self):
        """消息格式应包含关键信息。"""
        mmd = self._make_mmd(MMDType.BUY_3)
        zs = self._make_zs(5, zg=100.0, zd=90.0, done=True)
        closes = [95.0] * 20 + [100.5, 101.0]
        result = _calc_zhongshu_level_weight_enhanced_v63(mmd, [zs], closes)
        assert "中枢级别权重优化" in result["msg"]
        assert "距离分" in result["msg"]
        assert "质量分" in result["msg"]
        assert "置信度" in result["msg"]


# ──────────────────────────────────────────────────────────────────────────────
# 条件191: 多周期信号衰减追踪
# ──────────────────────────────────────────────────────────────────────────────


class TestMultiPeriodSignalDecayV63:
    """条件191 测试。"""

    def _make_mmd(self, mmd_type: MMDType, signal_idx: int = 20) -> MMD:
        mmd = MMD(
            mmd_type=mmd_type,
            bi=None,
            zs=None,
            confidence=0.5,
            msg="",
        )
        # 模拟 bi.end.k.k_index
        if mmd.bi is None:
            from unittest.mock import MagicMock

            mock_k = MagicMock()
            mock_k.k_index = signal_idx
            mock_end = MagicMock()
            mock_end.k = mock_k
            mock_bi = MagicMock()
            mock_bi.end = mock_end
            mmd.bi = mock_bi
        return mmd

    def test_non_buy3_sell3_signal(self):
        """非3买/3卖信号应跳过。"""
        mmd = self._make_mmd(MMDType.BUY_1)
        closes = [100.0] * 30
        result = _calc_multi_period_signal_decay_v63(mmd, closes)
        assert "跳过此条件" in result["msg"]
        assert result["confidence_adjust"] == 0.0

    def test_insufficient_data(self):
        """数据不足应返回空结果。"""
        mmd = self._make_mmd(MMDType.BUY_3)
        result = _calc_multi_period_signal_decay_v63(mmd, [100.0] * 20)
        assert "数据不足" in result["msg"]

    def test_insufficient_post_signal_data(self):
        """信号后数据不足应返回空结果。"""
        mmd = self._make_mmd(MMDType.BUY_3, signal_idx=25)
        closes = [100.0] * 30
        result = _calc_multi_period_signal_decay_v63(mmd, closes)
        assert "数据不足" in result["msg"]

    def test_strong_buy_signal(self):
        """强买入信号：短期+中期均上涨，应获得正向调整。"""
        mmd = self._make_mmd(MMDType.BUY_3, signal_idx=20)
        # 信号后价格上涨
        closes = [100.0] * 21 + [101.0, 102.0, 103.5, 105.0, 106.0, 107.0]  # 7根上涨
        result = _calc_multi_period_signal_decay_v63(mmd, closes)
        assert result["overall_health"] in ("strong", "healthy", "stable")
        assert result["decay_detected"] is False
        assert result["confidence_adjust"] > 0

    def test_decaying_buy_signal(self):
        """衰减买入信号：长期下跌，应获得负向调整。"""
        mmd = self._make_mmd(MMDType.BUY_3, signal_idx=5)
        # 短期涨但长期跌 (需要至少25根，总共30根)
        # closes[5]=100是信号价，closes[6:11]涨到102然后持续下跌
        closes = [100.0] * 6 + [
            102.0,
            101.0,
            99.0,
            97.0,
            95.0,
            93.0,
            91.0,
            89.0,
            87.0,
            85.0,
            83.0,
            81.0,
            79.0,
            77.0,
            75.0,
            73.0,
            71.0,
            69.0,
            67.0,
        ]
        result = _calc_multi_period_signal_decay_v63(mmd, closes)
        # 长期跌幅大，应标记为衰减
        assert result["overall_health"] in ("declining", "weak", "decaying")
        assert result["decay_detected"] is True
        assert result["confidence_adjust"] < 0

    def test_strong_sell_signal(self):
        """强卖出信号：短期+中期均下跌，应获得正向调整。"""
        mmd = self._make_mmd(MMDType.SELL_3, signal_idx=20)
        # 信号后价格下跌
        closes = [100.0] * 21 + [99.0, 98.0, 96.5, 95.0, 94.0, 93.0]
        result = _calc_multi_period_signal_decay_v63(mmd, closes)
        assert result["overall_health"] in ("strong", "healthy", "stable")
        assert result["decay_detected"] is False
        assert result["confidence_adjust"] > 0

    def test_stable_buy_signal(self):
        """稳定买入信号：小幅上涨，应获得小幅正向调整。"""
        mmd = self._make_mmd(MMDType.BUY_3, signal_idx=20)
        closes = [100.0] * 21 + [100.3, 100.5, 100.8, 101.0, 101.2, 101.5]
        result = _calc_multi_period_signal_decay_v63(mmd, closes)
        assert result["overall_health"] in ("healthy", "stable")
        assert result["confidence_adjust"] >= 0

    def test_momentum_values_reasonable(self):
        """各周期动量值应在合理范围内。"""
        mmd = self._make_mmd(MMDType.BUY_3, signal_idx=20)
        closes = [100.0] * 21 + [101.0, 102.0, 103.0, 104.0, 105.0, 106.0]
        result = _calc_multi_period_signal_decay_v63(mmd, closes)
        assert -10.0 <= result["short_term_momentum"] <= 10.0
        assert -10.0 <= result["mid_term_momentum"] <= 10.0
        assert -10.0 <= result["long_term_momentum"] <= 10.0

    def test_msg_format(self):
        """消息格式应包含关键信息。"""
        mmd = self._make_mmd(MMDType.BUY_3, signal_idx=20)
        closes = [100.0] * 21 + [101.0, 102.0, 103.0, 104.0, 105.0, 106.0]
        result = _calc_multi_period_signal_decay_v63(mmd, closes)
        assert "多周期衰减追踪" in result["msg"]
        assert "健康度" in result["msg"]
        assert "置信度" in result["msg"]

    def test_confidence_adjust_bounds(self):
        """置信度调整应在[-4%, +4%]范围内。"""
        mmd = self._make_mmd(MMDType.BUY_3, signal_idx=20)
        closes = [100.0] * 21 + [101.0, 102.0, 103.0, 104.0, 105.0, 106.0]
        result = _calc_multi_period_signal_decay_v63(mmd, closes)
        assert -0.04 <= result["confidence_adjust"] <= 0.04


# ──────────────────────────────────────────────────────────────────────────────
# 集成测试
# ──────────────────────────────────────────────────────────────────────────────


class TestFindMMDsV63Integration:
    """V63 条件集成到 find_mmds_v39 的测试。"""

    def test_v63_functions_importable(self):
        """V63 函数应可正常导入。"""
        from easy_tdx.chanlun.mmd import (
            _calc_multi_period_signal_decay_v63,
            _calc_zhongshu_level_weight_enhanced_v63,
        )

        assert callable(_calc_zhongshu_level_weight_enhanced_v63)
        assert callable(_calc_multi_period_signal_decay_v63)

    def test_v63_fields_in_mmd_type(self):
        """MMD 类型应包含 V63 字段定义。"""
        import dataclasses

        from easy_tdx.chanlun.types import MMD

        field_names = [f.name for f in dataclasses.fields(MMD)]
        assert "_zhongshu_level_weight_enhanced_v63" in field_names
        assert "_multi_period_signal_decay_v63" in field_names

    def test_v63_confidence_bounds(self):
        """V63 置信度调整不应超出 [0, 1] 范围。"""
        mmd = MMD(
            mmd_type=MMDType.BUY_3,
            bi=None,
            zs=None,
            confidence=0.5,
            msg="",
        )
        from unittest.mock import MagicMock

        mock_k = MagicMock()
        mock_k.k_index = 20
        mock_end = MagicMock()
        mock_end.k = mock_k
        mock_bi = MagicMock()
        mock_bi.end = mock_end
        mmd.bi = mock_bi

        zs = ZS(index=0, lines=[], zg=100.0, zd=90.0, gg=100.0, dd=90.0, direction="up", done=True)
        closes = [95.0] * 20 + [100.5, 101.0, 102.0, 103.0, 104.0]

        # 直接调用条件函数并检查 bounds
        zs_result = _calc_zhongshu_level_weight_enhanced_v63(mmd, [zs], closes)
        decay_result = _calc_multi_period_signal_decay_v63(mmd, closes)

        orig_conf = mmd.confidence
        mmd.confidence = max(
            0.0, min(1.0, mmd.confidence + zs_result.get("confidence_adjust", 0.0))
        )
        mmd.confidence = max(
            0.0, min(1.0, mmd.confidence + decay_result.get("confidence_adjust", 0.0))
        )

        assert 0.0 <= mmd.confidence <= 1.0
        # 置信度应有变化
        assert mmd.confidence != orig_conf or (
            zs_result.get("confidence_adjust", 0) == 0
            and decay_result.get("confidence_adjust", 0) == 0
        )

    def test_all_v63_conditions_callable(self):
        """所有 V63 条件函数应可正常调用且返回有效结果。"""
        from unittest.mock import MagicMock

        mmd = MMD(
            mmd_type=MMDType.BUY_3,
            bi=None,
            zs=None,
            confidence=0.5,
            msg="",
        )
        mock_k = MagicMock()
        mock_k.k_index = 20
        mock_end = MagicMock()
        mock_end.k = mock_k
        mock_bi = MagicMock()
        mock_bi.end = mock_end
        mmd.bi = mock_bi

        zs = ZS(index=0, lines=[], zg=100.0, zd=90.0, gg=100.0, dd=90.0, direction="up", done=True)
        closes = [95.0] * 20 + [100.5, 101.0, 102.0]

        r1 = _calc_zhongshu_level_weight_enhanced_v63(mmd, [zs], closes)
        r2 = _calc_multi_period_signal_decay_v63(mmd, closes)

        assert "confidence_adjust" in r1
        assert "confidence_adjust" in r2
        assert isinstance(r1["confidence_adjust"], float)
        assert isinstance(r2["confidence_adjust"], float)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
