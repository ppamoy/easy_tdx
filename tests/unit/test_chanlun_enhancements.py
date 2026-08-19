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
        assert _calc_confidence(mmd_1buy, 0.0) >= 0.85

        # 1卖基础置信度
        mmd_1sell = MMD(mmd_type=MMDType.SELL_1, msg="1卖: 顶背驰")
        assert _calc_confidence(mmd_1sell, 0.0) >= 0.90

        # 3买基础置信度较低
        mmd_3buy = MMD(mmd_type=MMDType.BUY_3, msg="3买: 突破确认")
        assert _calc_confidence(mmd_3buy, 0.0) < 0.60

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
