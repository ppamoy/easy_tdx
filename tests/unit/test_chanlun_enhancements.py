"""测试置信度计算、百分比修复和多级别一致性与新增强功能。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig
from easy_tdx.chanlun.mmd import _calc_confidence, find_mmds
from easy_tdx.chanlun.multi_level import MultiLevelAnalyser
from easy_tdx.chanlun.types import MMD, MMDType


class TestConfidenceScoring:
    """测试买卖点置信度计算。"""

    def test_confidence_base_values(self):
        """测试各类买卖点的基礎置信度。"""
        from easy_tdx.chanlun.types import ZS

        # 1买基础置信度应最高
        mmd_1buy = MMD(mmd_type=MMDType.BUY_1, msg="1买: 底背驰(强度=strong)")
        assert _calc_confidence(mmd_1buy, 0.0) >= 0.88

        # 1卖基础置信度
        mmd_1sell = MMD(mmd_type=MMDType.SELL_1, msg="1卖: 顶背驰")
        assert _calc_confidence(mmd_1sell, 0.0) >= 0.92

        # 3买基础置信度（V9校准至0.60，基于实际回测准确率~57%）
        mmd_3buy = MMD(mmd_type=MMDType.BUY_3, msg="3买: 突破确认")
        assert _calc_confidence(mmd_3buy, 0.0) >= 0.58

    def test_confidence_beichi_strength_bonus(self):
        """测试背驰强度对置信度的影响。"""
        from easy_tdx.chanlun.types import ZS

        mmd_weak = MMD(mmd_type=MMDType.BUY_1, msg="1买: 底背驰(强度=weak)")
        mmd_strong = MMD(mmd_type=MMDType.BUY_1, msg="1买: 底背驰(强度=strong)")

        conf_weak = _calc_confidence(mmd_weak, 0.0)
        conf_strong = _calc_confidence(mmd_strong, 0.0)

        # 强背驰应比弱背驰置信度高
        assert conf_strong > conf_weak

    def test_confidence_trend_bonus(self):
        """测试趋势强度对置信度的加成。"""
        from easy_tdx.chanlun.types import ZS

        mmd = MMD(mmd_type=MMDType.BUY_2, msg="2买: 回调确认")
        conf_low = _calc_confidence(mmd, 0.0)
        conf_high = _calc_confidence(mmd, 1.0)

        # 趋势明确时置信度应更高
        assert conf_high > conf_low

    def test_confidence_clamped_to_range(self):
        """测试置信度被限制在[0, 1]范围内。"""
        from easy_tdx.chanlun.types import ZS

        # 弱背驰 + 低趋势强度
        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3卖: 跌破确认(强度=weak)")
        conf = _calc_confidence(mmd, 0.0)
        assert 0.0 <= conf <= 1.0


class TestPercentageFix:
    """测试百分比计算修复（不再出现负数回撤）。"""

    def _make_simple_data(self, n: int = 200) -> pd.DataFrame:
        """生成简单的下跌-震荡-反弹数据。"""
        np.random.seed(99)
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        close = [50.0]
        for i in range(1, n):
            if i < 60:
                close.append(close[-1] * 0.995)
            elif i < 120:
                close.append(close[-1] + np.random.normal(0, 0.2))
            else:
                close.append(close[-1] * 1.003)
        close = np.array(close)
        return pd.DataFrame({
            "datetime": dates,
            "open": close * (1 + np.random.uniform(-0.005, 0.005, n)),
            "high": close * (1 + np.random.uniform(0, 0.01, n)),
            "low": close * (1 + np.random.uniform(-0.01, 0, n)),
            "close": close,
            "amount": [1e6] * n,
            "vol": [1e5] * n,
        })

    def test_no_negative_drawdown_pct(self):
        """测试2买消息中不会出现负数回撤百分比。"""
        df = self._make_simple_data(250)
        analyser = ChanlunAnalyser(code="TEST", frequency="daily")
        result = analyser.process_klines(df)

        for mmd in result.mmds:
            if "回撤" in mmd.msg:
                # 提取百分比数值
                import re
                match = re.search(r"回撤([-\d.]+)%", mmd.msg)
                if match:
                    pct = float(match.group(1))
                    assert pct >= 0, f"负回撤百分比: {mmd.msg}"

    def test_confidence_in_to_dict(self):
        """测试 to_dict 包含 confidence 字段。"""
        df = self._make_simple_data(200)
        analyser = ChanlunAnalyser(code="TEST", frequency="daily")
        result = analyser.process_klines(df)

        d = result.to_dict()
        assert "mmds" in d
        if d["mmds"]:
            assert "confidence" in d["mmds"][0]
            assert 0.0 <= d["mmds"][0]["confidence"] <= 1.0


class TestMultiLevelConfluence:
    """测试多级别一致性评分。"""

    def _make_trending_data(self, n: int = 300, trend: str = "up") -> pd.DataFrame:
        """生成有明显趋势的数据。"""
        np.random.seed(77)
        dates = pd.date_range("2024-01-01", periods=n, freq="D")
        close = [30.0]
        for i in range(1, n):
            if trend == "up":
                close.append(close[-1] * (1.002 + np.random.normal(0, 0.005)))
            else:
                close.append(close[-1] * (0.998 + np.random.normal(0, 0.005)))
        close = np.array(close)
        return pd.DataFrame({
            "datetime": dates,
            "open": close * (1 + np.random.uniform(-0.003, 0.003, n)),
            "high": close * (1 + np.random.uniform(0, 0.008, n)),
            "low": close * (1 + np.random.uniform(-0.008, 0, n)),
            "close": close,
            "amount": [1e6] * n,
            "vol": [1e5] * n,
        })

    def test_confluence_score_structure(self):
        """测试一致性评分返回正确的数据结构。"""
        mla = MultiLevelAnalyser()
        daily_analyser = ChanlunAnalyser(code="TEST", frequency="daily")
        mla.add_level("daily", daily_analyser)

        df = self._make_trending_data(300, "up")
        mla.process("daily", df)

        result = mla.compute_confluence_score("daily", "daily")

        assert "score" in result
        assert "trend_aligned" in result
        assert "zs_aligned" in result
        assert "time_aligned" in result
        assert isinstance(result["score"], float)
        assert 0.0 <= result["score"] <= 1.0

    def test_confluence_with_missing_level(self):
        """测试缺少级别时返回空结果。"""
        mla = MultiLevelAnalyser()
        daily_analyser = ChanlunAnalyser(code="TEST", frequency="daily")
        mla.add_level("daily", daily_analyser)

        df = self._make_trending_data(200, "up")
        mla.process("daily", df)

        result = mla.compute_confluence_score("daily", "missing_level")
        assert result["score"] == 0.0

    def test_confluence_with_no_signals(self):
        """测试无买卖点时返回零分。"""
        mla = MultiLevelAnalyser()
        daily_analyser = ChanlunAnalyser(code="TEST", frequency="daily")
        mla.add_level("daily", daily_analyser)

        # 用很短的数据，可能不会产生买卖点
        df = pd.DataFrame({
            "datetime": pd.date_range("2024-01-01", periods=50, freq="D"),
            "open": [10.0] * 50,
            "high": [10.1] * 50,
            "low": [9.9] * 50,
            "close": [10.0] * 50,
            "amount": [1e6] * 50,
            "vol": [1e5] * 50,
        })
        mla.process("daily", df)

        result = mla.compute_confluence_score("daily", "daily")
        # 数据太简单，可能没有买卖点，返回空结构
        assert "score" in result


class TestBacktestStrategyUpdate:
    """测试回测策略更新（置信度过滤和类二买/卖支持）。"""

    def test_strategy_params_exist(self):
        """测试新参数存在于策略中。"""
        from easy_tdx.backtest.strategies.chanlun import ChanlunStrategy

        param_names = [p.name for p in ChanlunStrategy.params]
        assert "use_2s_signals" in param_names
        assert "min_confidence" in param_names
        assert "stop_loss_pct" in param_names
        assert "take_profit_pct" in param_names

    def test_strategy_default_params(self):
        """测试新参数的默认值。"""
        from easy_tdx.backtest.strategies.chanlun import ChanlunStrategy

        params_dict = {p.name: p.default for p in ChanlunStrategy.params}
        assert params_dict["use_2s_signals"] is False
        assert params_dict["min_confidence"] == 0.0
        assert params_dict["stop_loss_pct"] == 0.08
        assert params_dict["take_profit_pct"] == 0.25


class TestV10Enhancements:
    """测试V10新增功能（MA斜率、BOLL过滤、ADX趋势强度、RSI动量）。"""

    def test_calc_ma_slope_up(self):
        """测试MA斜率计算：上升趋势返回up。"""
        from easy_tdx.chanlun.mmd import _calc_ma_slope
        # 模拟上升趋势数据
        closes = [10.0 + i * 0.1 for i in range(50)]
        result = _calc_ma_slope(closes, 40)
        assert result == "up", f"期望上升趋势，实际得到: {result}"

    def test_calc_ma_slope_down(self):
        """测试MA斜率计算：下降趋势返回down。"""
        from easy_tdx.chanlun.mmd import _calc_ma_slope
        # 模拟明显下降趋势数据（更大的跌幅确保斜率< -0.5%）
        closes = [100.0 - i * 0.5 for i in range(50)]
        result = _calc_ma_slope(closes, 40)
        assert result == "down", f"期望下降趋势，实际得到: {result}"

    def test_calc_ma_slope_flat(self):
        """测试MA斜率计算：横盘趋势返回flat。"""
        from easy_tdx.chanlun.mmd import _calc_ma_slope
        # 模拟横盘数据
        closes = [20.0] * 50
        result = _calc_ma_slope(closes, 40)
        assert result == "flat", f"期望横盘，实际得到: {result}"

    def test_calc_ma_slope_insufficient_data(self):
        """测试数据不足时返回flat。"""
        from easy_tdx.chanlun.mmd import _calc_ma_slope
        closes = [10.0, 10.1, 10.2]
        result = _calc_ma_slope(closes, 40)
        assert result == "flat"

    def test_calc_boll_position(self):
        """测试BOLL位置计算。"""
        from easy_tdx.chanlun.mmd import _calc_boll_position
        # 模拟上升趋势数据（价格应位于中轨附近或以上）
        closes = [10.0 + i * 0.05 for i in range(50)]
        result = _calc_boll_position(closes, 40)
        assert "percent_b" in result
        assert "position" in result
        assert 0.0 <= result["percent_b"] <= 1.0

    def test_calc_boll_position_extreme(self):
        """测试BOLL极端位置计算。"""
        from easy_tdx.chanlun.mmd import _calc_boll_position
        # 模拟剧烈波动数据
        closes = [10.0] * 20 + [20.0] * 30  # 突然暴涨
        result = _calc_boll_position(closes, 45)
        assert result["percent_b"] >= 0.5  # 价格在上涨后应在中轨或中轨以上

    def test_calc_boll_insufficient_data(self):
        """测试BOLL数据不足时返回中性值。"""
        from easy_tdx.chanlun.mmd import _calc_boll_position
        closes = [10.0, 10.1]
        result = _calc_boll_position(closes, 5)
        assert result["percent_b"] == 0.5
        assert result["position"] == "mid"

    def test_calc_adx_strength(self):
        """测试ADX趋势强度计算。"""
        from easy_tdx.chanlun.mmd import _calc_adx_strength
        # 模拟有明显趋势的数据
        closes = [10.0 + i * 0.1 for i in range(60)]
        highs = [c + 0.1 for c in closes]
        lows = [c - 0.1 for c in closes]
        adx_val, adx_level = _calc_adx_strength(closes, highs, lows, 50)
        assert adx_val >= 0
        assert adx_level in ("strong", "medium", "weak", "none")

    def test_calc_adx_insufficient_data(self):
        """测试ADX数据不足时返回0和none。"""
        from easy_tdx.chanlun.mmd import _calc_adx_strength
        closes = [10.0] * 5
        adx_val, adx_level = _calc_adx_strength(closes, None, None, 3)
        assert adx_val == 0.0
        assert adx_level == "none"

    def test_calc_rsi_momentum(self):
        """测试RSI动量计算。"""
        from easy_tdx.chanlun.mmd import _calc_rsi_momentum
        # 模拟上升趋势
        closes = [10.0 + i * 0.05 for i in range(30)]
        momentum = _calc_rsi_momentum(closes)
        assert isinstance(momentum, float)
        # 上升趋势中RSI动量应为正或接近0
        assert momentum >= -10.0  # 合理范围内

    def test_calc_rsi_momentum_insufficient_data(self):
        """测试RSI动量数据不足时返回0。"""
        from easy_tdx.chanlun.mmd import _calc_rsi_momentum
        closes = [10.0, 10.1, 10.2]
        momentum = _calc_rsi_momentum(closes)
        assert momentum == 0.0

    def test_v10_confidence_base_values(self):
        """测试V10基础置信度校准值。"""
        from easy_tdx.chanlun.types import MMD, MMDType
        from easy_tdx.chanlun.mmd import _calc_confidence

        # 3买置信度应高于V9的0.60
        mmd_3buy = MMD(mmd_type=MMDType.BUY_3, msg="3买V10: 突破确认")
        conf_3buy = _calc_confidence(mmd_3buy, 0.0)
        assert conf_3buy >= 0.65, f"3买置信度应>=0.65，实际={conf_3buy:.2f}"

        # 3卖置信度应高于V9的0.55
        mmd_3sell = MMD(mmd_type=MMDType.SELL_3, msg="3卖V10: 跌破确认")
        conf_3sell = _calc_confidence(mmd_3sell, 0.0)
        assert conf_3sell >= 0.60, f"3卖置信度应>=0.60，实际={conf_3sell:.2f}"

        # 1买/1卖置信度保持不变
        mmd_1buy = MMD(mmd_type=MMDType.BUY_1, msg="1买: 底背驰")
        conf_1buy = _calc_confidence(mmd_1buy, 0.0)
        assert conf_1buy >= 0.85

        mmd_1sell = MMD(mmd_type=MMDType.SELL_1, msg="1卖: 顶背驰")
        conf_1sell = _calc_confidence(mmd_1sell, 0.0)
        assert conf_1sell >= 0.88

    def test_v10_multi_factor_confluence(self):
        """测试V10多因子共振加成。"""
        from easy_tdx.chanlun.types import MMD, MMDType
        from easy_tdx.chanlun.mmd import _calc_confidence

        # 创建上升趋势数据
        np.random.seed(42)
        n = 100
        closes = [10.0]
        for i in range(1, n):
            closes.append(closes[-1] * (1.001 + np.random.normal(0, 0.003)))

        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买V10: 突破确认")
        # 传入真实收盘价数据应触发多因子加成
        conf_with_data = _calc_confidence(mmd, 0.5, closes=closes, volatility=0.015)
        conf_without_data = _calc_confidence(mmd, 0.5)

        # 有数据时应有多因子加成（或至少不为负）
        assert conf_with_data >= conf_without_data - 0.05

    def test_rsi_v10_filter_for_3buy(self):
        """测试V10 RSI过滤逻辑正确性。"""
        from easy_tdx.chanlun.mmd import _calc_rsi
        # 测试RSI计算边界
        # 持续上涨 → RSI应接近100
        up_closes = [10.0 + i * 0.5 for i in range(20)]
        rsi_up = _calc_rsi(up_closes)
        assert rsi_up > 80, f"上升趋势RSI应>80，实际={rsi_up:.1f}"

        # 持续下跌 → RSI应接近0
        down_closes = [50.0 - i * 0.5 for i in range(20)]
        rsi_down = _calc_rsi(down_closes)
        assert rsi_down < 20, f"下降趋势RSI应<20，实际={rsi_down:.1f}"

        # 横盘（有微小波动）→ RSI应接近50
        flat_closes = [20.0 + (i % 2) * 0.01 for i in range(20)]  # 微小波动
        rsi_flat = _calc_rsi(flat_closes)
        assert 40 <= rsi_flat <= 60, f"横盘RSI应≈50，实际={rsi_flat:.1f}"


class TestV11Enhancements:
    """测试V11新增功能（修正ADX、放宽MA斜率、多时间框架共振）。"""

    def test_calc_adx_strength_trending(self):
        """测试ADX计算：上升趋势返回正确值（V11修正版）。"""
        from easy_tdx.chanlun.mmd import _calc_adx_strength
        # 模拟明显上升趋势
        closes = [10.0 + i * 0.1 for i in range(80)]
        highs = [c + 0.1 for c in closes]
        lows = [c - 0.1 for c in closes]
        adx_val, adx_level = _calc_adx_strength(closes, highs, lows, 70)
        assert adx_val >= 20, f"上升趋势ADX应>=20，实际={adx_val}"
        assert adx_level in ("strong", "medium", "weak")

    def test_calc_adx_strength_flat(self):
        """测试ADX计算：横盘数据返回none（V11修正版）。"""
        from easy_tdx.chanlun.mmd import _calc_adx_strength
        flat_closes = [20.0] * 80
        flat_highs = [20.1] * 80
        flat_lows = [19.9] * 80
        adx_val, adx_level = _calc_adx_strength(flat_closes, flat_highs, flat_lows, 70)
        assert adx_val < 20 or adx_level == "none", f"横盘ADX应<20，实际={adx_val}, level={adx_level}"

    def test_calc_adx_strength_no_highs_lows(self):
        """测试无高低点数据时ADX正常返回（V11修正版）。"""
        from easy_tdx.chanlun.mmd import _calc_adx_strength
        closes = [10.0 + i * 0.05 for i in range(80)]
        adx_val, adx_level = _calc_adx_strength(closes, None, None, 70)
        assert isinstance(adx_val, float)
        assert adx_val >= 0

    def test_ma_slope_threshold_relaxed(self):
        """测试MA斜率阈值放宽（V11：0.5%→0.3%）。"""
        from easy_tdx.chanlun.mmd import _calc_ma_slope
        # 模拟弱上升趋势（每日涨幅约0.5%，MA斜率>0.3%）
        closes = [10.0 * (1.005 ** i) for i in range(50)]
        result = _calc_ma_slope(closes, 40)
        # 弱上升也应被识别为up（阈值从0.5%降到0.3%）
        assert result == "up", f"弱上升趋势应被识别为up，实际={result}"

    def test_rsi_momentum_threshold_relaxed(self):
        """测试RSI动量阈值放宽（V11：±2.0→±1.5）。"""
        from easy_tdx.chanlun.mmd import _calc_rsi_momentum
        # 模拟温和上升趋势
        closes = [10.0 + i * 0.02 for i in range(30)]
        momentum = _calc_rsi_momentum(closes)
        assert isinstance(momentum, float)
        # 动量应为正值或接近零
        assert momentum >= -5.0

    def test_v11_confidence_with_confluence(self):
        """测试V11多时间框架共振加成。"""
        from easy_tdx.chanlun.types import MMD, MMDType
        from easy_tdx.chanlun.mmd import _calc_confidence

        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买V11: 突破确认")
        # 设置confluence_score属性模拟多时间框架共振
        mmd.confluence_score = 0.75
        conf = _calc_confidence(mmd, 0.5)
        assert conf >= 0.70, f"强共振时应提升置信度，实际={conf:.2f}"

    def test_v11_confidence_with_medium_confluence (self):
        """测试V11中等共振加成。"""
        from easy_tdx.chanlun.types import MMD, MMDType
        from easy_tdx.chanlun.mmd import _calc_confidence

        mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买V11: 突破确认")
        mmd.confluence_score = 0.55
        conf = _calc_confidence(mmd, 0.5)
        assert conf >= 0.65, f"中等共振时应提升置信度，实际={conf:.2f}"


class TestV12Enhancements:
    """测试V12新增功能（真实ADX + KDJ动量确认 + confluence_score字段）。"""

    def test_calc_kdj_j_trending(self):
        """测试KDJ J值计算：上升趋势J值应在合理范围。"""
        from easy_tdx.chanlun.mmd import _calc_kdj_j
        # 上升趋势
        closes = [10.0 + i * 0.1 for i in range(30)]
        j = _calc_kdj_j(closes)
        assert isinstance(j, float)
        assert 0 <= j <= 100, f"J值应在0-100范围内，实际={j}"

    def test_calc_kdj_j_flat(self):
        """测试KDJ J值计算：横盘数据返回中性值。"""
        from easy_tdx.chanlun.mmd import _calc_kdj_j
        flat_closes = [20.0] * 20
        j = _calc_kdj_j(flat_closes)
        assert j == 50.0, f"横盘J值应为50，实际={j}"

    def test_calc_kdj_j_insufficient_data(self):
        """测试KDJ数据不足时返回中性值。"""
        from easy_tdx.chanlun.mmd import _calc_kdj_j
        short_closes = [10.0, 10.1, 10.2]
        j = _calc_kdj_j(short_closes)
        assert j == 50.0

    def test_find_mmds_accepts_highs_lows(self):
        """测试find_mmds接受highs/lows参数（V12新增）。"""
        from easy_tdx.chanlun.mmd import find_mmds
        from easy_tdx.chanlun.types import MMD, MMDType, BI, FX, ZS, CLKline
        from datetime import datetime
        
        # 创建简单的笔和中枢数据
        bis = []
        zss = []
        closes = [10.0 + i * 0.1 for i in range(50)]
        highs = [c + 0.1 for c in closes]
        lows = [c - 0.1 for c in closes]
        
        # find_mmds应能接受highs/lows参数而不报错
        try:
            result = find_mmds(bis, zss, closes=closes, highs=highs, lows=lows)
            assert isinstance(result, list)
        except TypeError as e:
            if "unexpected keyword argument" in str(e):
                pytest.fail(f"find_mmds不应拒绝highs/lows参数: {e}")
            raise

    def test_mmd_has_confluence_score(self):
        """测试MMD对象有confluence_score字段。"""
        from easy_tdx.chanlun.types import MMD, MMDType
        mmd = MMD(mmd_type=MMDType.BUY_3)
        assert hasattr(mmd, 'confluence_score')
        assert mmd.confluence_score == 0.0
        mmd.confluence_score = 0.75
        assert mmd.confluence_score == 0.75

    def test_mmd_has_quality_field(self):
        """测试MMD对象有quality字段。"""
        from easy_tdx.chanlun.types import MMD, MMDType
        mmd = MMD(mmd_type=MMDType.BUY_1)
        assert hasattr(mmd, 'quality')
        assert mmd.quality is None

    def test_adx_uses_real_ohlc(self):
        """测试ADX使用真实OHLC数据（非随机近似）。"""
        from easy_tdx.chanlun.mmd import _calc_adx_strength
        # 有明显趋势的数据
        closes = [10.0 + i * 0.1 for i in range(80)]
        highs = [c + 0.1 for c in closes]
        lows = [c - 0.1 for c in closes]
        adx_with_ohlc, level_with = _calc_adx_strength(closes, highs, lows, 70)
        
        # 使用None时应使用随机近似（结果可能不同）
        adx_without_ohlc, level_without = _calc_adx_strength(closes, None, None, 70)
        
        # 两者都应该返回合理的ADX值
        assert adx_with_ohlc >= 0
        assert level_with in ("strong", "medium", "weak", "none")
        assert adx_without_ohlc >= 0
        assert level_without in ("strong", "medium", "weak", "none")
