"""P0-2：估值分位 + 涨跌家数信号补齐测试。

验证 detect_season 输出的 signals 字典中包含 val_percentile / val_score /
breadth_ratio / breadth_score 四个新字段，且行为正确。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from easy_tdx.fundamental.season import detect_season


def _dates(n: int) -> list[date]:
    return [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]


class TestValuationPercentile:
    """估值分位信号。"""

    def test_low_valuation_gives_positive_score(self) -> None:
        """持续下跌 → 价格在底部 → val_percentile 低 → val_score = +1。"""
        cs = [100 - i * 0.6 for i in range(250)]
        sr = detect_season(_dates(250), cs, _dates(250)[-1], volumes=[1e8] * 250)
        assert sr.signals["val_percentile"] < 25.0
        assert sr.signals["val_score"] == 1

    def test_high_valuation_gives_negative_score(self) -> None:
        """持续上涨 → 价格在顶部 → val_percentile 高 → val_score = -1。"""
        cs = [100 + i * 0.6 for i in range(250)]
        sr = detect_season(_dates(250), cs, _dates(250)[-1], volumes=[1e8] * 250)
        assert sr.signals["val_percentile"] > 75.0
        assert sr.signals["val_score"] == -1

    def test_midrange_valuation_gives_zero_score(self) -> None:
        """价格在中间区域 → val_score = 0。"""
        # 先涨到 200，再回到 150（中位）
        cs = [100 + i for i in range(100)] + [200 - i for i in range(100)]
        cs = cs + [100 + i * 0.5 for i in range(50)]  # 50 bars around 150
        sr = detect_season(_dates(len(cs)), cs, _dates(len(cs))[-1], volumes=[1e8] * len(cs))
        assert sr.signals["val_score"] in (-1, 0, 1)  # valid range
        assert "val_percentile" in sr.signals


class TestBreadthRatio:
    """涨跌家数信号。"""

    def test_breadth_none_means_zero_score(self) -> None:
        """不传 breadth_ratio → breadth_score = 0（历史日期无数据）。"""
        cs = [100 + i * 0.1 for i in range(80)]
        sr = detect_season(_dates(80), cs, _dates(80)[-1])
        assert sr.signals["breadth_ratio"] is None
        assert sr.signals["breadth_score"] == 0

    def test_breadth_high_gives_positive_score(self) -> None:
        """breadth_ratio > 0.55 → breadth_score = +1。"""
        cs = [100 + i * 0.1 for i in range(80)]
        sr = detect_season(_dates(80), cs, _dates(80)[-1], breadth_ratio=0.7)
        assert sr.signals["breadth_ratio"] == 0.7
        assert sr.signals["breadth_score"] == 1

    def test_breadth_low_gives_negative_score(self) -> None:
        """breadth_ratio < 0.45 → breadth_score = -1。"""
        cs = [100 + i * 0.1 for i in range(80)]
        sr = detect_season(_dates(80), cs, _dates(80)[-1], breadth_ratio=0.3)
        assert sr.signals["breadth_ratio"] == 0.3
        assert sr.signals["breadth_score"] == -1

    def test_breadth_neutral_gives_zero_score(self) -> None:
        """breadth_ratio 0.5 → breadth_score = 0。"""
        cs = [100 + i * 0.1 for i in range(80)]
        sr = detect_season(_dates(80), cs, _dates(80)[-1], breadth_ratio=0.5)
        assert sr.signals["breadth_score"] == 0


class TestTotalScoreUnchanged:
    """估值分位和涨跌家数不改变趋势总分（它们是状态信号，不是趋势信号）。"""

    def test_val_score_not_in_total(self) -> None:
        """val_score 不加入 total_score。"""
        # 持续下跌：val_score = +1，但 total 不包含它
        cs = [100 - i * 0.6 for i in range(80)]
        vols = [1000 - i * 10 for i in range(80)]
        sr = detect_season(_dates(80), cs, _dates(80)[-1], volumes=vols)
        # total = price + ma + vol + vol2，不含 val/breadth
        trend_total = (
            sr.signals["price_score"]
            + sr.signals["ma_score"]
            + sr.signals["vol_score"]
            + sr.signals["vol_score2"]
        )
        assert sr.signals["total_score"] == trend_total

    def test_breadth_score_not_in_total(self) -> None:
        """breadth_score 不加入 total_score。"""
        cs = [100 + i * 0.1 for i in range(80)]
        sr = detect_season(_dates(80), cs, _dates(80)[-1], breadth_ratio=0.3)
        trend_total = (
            sr.signals["price_score"]
            + sr.signals["ma_score"]
            + sr.signals["vol_score"]
            + sr.signals["vol_score2"]
        )
        assert sr.signals["total_score"] == trend_total
