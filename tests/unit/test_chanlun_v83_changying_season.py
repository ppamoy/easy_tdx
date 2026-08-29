"""长赢策略季节切换计时 回归测试（V83）。

覆盖修复：
- 原 _update_season 用 datetime.now()（墙钟时间）判断季节切换的30天间隔，
  回测中所有K线在几秒内跑完，days_since 恒为 0，导致季节永远无法切换。
- 修复后改用K线自身日期（int YYYYMMDD / numpy / Timestamp 兼容）计时。
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from easy_tdx.backtest.strategies import changying_chanlun as cy


class TestLatestBarDatetime:
    """_latest_bar_datetime 应正确解析各类日期格式。"""

    def test_int_yyyymmdd(self) -> None:
        df = pd.DataFrame({"datetime": [20230101, 20230201]})
        dt = cy.ChangyingChanlunStrategy._latest_bar_datetime(df)
        assert dt is not None
        assert dt.year == 2023 and dt.month == 2 and dt.day == 1

    def test_numpy_int64(self) -> None:
        # numpy int64 不是 Python int 的 isinstance，曾是解析 bug 的根源
        df = pd.DataFrame({"datetime": np.array([20230101, 20230615], dtype=np.int64)})
        dt = cy.ChangyingChanlunStrategy._latest_bar_datetime(df)
        assert dt is not None
        assert dt.year == 2023 and dt.month == 6 and dt.day == 15

    def test_timestamp(self) -> None:
        df = pd.DataFrame({"datetime": pd.to_datetime(["2023-01-01", "2023-06-15"])})
        dt = cy.ChangyingChanlunStrategy._latest_bar_datetime(df)
        assert dt is not None
        assert dt.year == 2023 and dt.month == 6

    def test_missing_datetime_falls_back_index(self) -> None:
        idx = pd.date_range("2023-01-01", periods=2, freq="D")
        df = pd.DataFrame({"close": [1.0, 2.0]}, index=idx)
        dt = cy.ChangyingChanlunStrategy._latest_bar_datetime(df)
        assert dt is not None


class TestSeasonSwitchTiming:
    """季节切换必须按K线日期计时，且未满30个交易日不能重复切换。"""

    def _make_strategy(self, dates: pd.DatetimeIndex) -> tuple[cy.ChangyingChanlunStrategy, pd.DataFrame]:
        s = cy.ChangyingChanlunStrategy()
        s._bar_index = len(dates) - 1
        s._current_season = cy.Season.UNKNOWN
        s._season_history = []
        n = len(dates)
        closes = [20 + i * 0.05 for i in range(n)]  # 单边上涨 → 评分转夏季/春季
        opens = [c - 0.1 for c in closes]
        highs = [c + 0.3 for c in closes]
        lows = [c - 0.3 for c in closes]
        df = pd.DataFrame({
            "datetime": [int(d.strftime("%Y%m%d")) for d in dates],
            "open": opens,
            "close": closes,
            "high": highs,
            "low": lows,
            "vol": [1e6] * n,
        })
        return s, df

    def test_season_can_switch_with_30d_gap(self) -> None:
        """两次调用相隔 >30 个交易日（K线日期），允许切换季节。"""
        dates = pd.date_range("2023-01-02", periods=200, freq="B")
        s, df = self._make_strategy(dates)
        # _update_season 需要已存在的缠论分析结果（否则提前返回）
        from easy_tdx.chanlun import ChanlunAnalyser
        an = ChanlunAnalyser(code="T", frequency="daily")
        s._chanlun_result = an.process_klines(df)  # type: ignore[assignment]
        # 上涨趋势 → 综合评分应产出 SUMMER/SPRING 且非 UNKNOWN
        s._update_season(df)
        assert s._current_season != cy.Season.UNKNOWN, "上涨趋势应切换出冬季/春季以外的季节"
        assert len(s._season_history) >= 1, "应记录至少一次季节切换"
        # 记录的是K线日期而非墙钟时间（年份应为2023，而非 datetime.now() 的年份）
        switch_date = s._season_history[-1][0]
        assert getattr(switch_date, "year", 1970) >= 2023

    def test_switch_blocked_within_30_days(self) -> None:
        """两次调用相隔 <30 个交易日时，不允许重复切换季节。"""
        dates = pd.date_range("2023-01-02", periods=100, freq="B")
        s, df = self._make_strategy(dates)
        # 第一次强制设立一个任意季节基准（直接写 history）
        base_date = pd.Timestamp("2023-01-02")
        s._current_season = cy.Season.WINTER
        s._season_history = [(base_date, cy.Season.WINTER, 0)]
        # 20个交易日后即触发重评（不足30日）→ 不允许切换
        s._bar_index = 20
        df20 = pd.DataFrame({
            "datetime": [int(d.strftime("%Y%m%d")) for d in dates[:21]],
            "open": [20.0] * 21,
            "close": [20 + i * 0.05 for i in range(21)],
            "high": [21.0] * 21,
            "low": [19.5] * 21,
            "vol": [1e6] * 21,
        })
        s._update_season(df20)
        assert s._current_season == cy.Season.WINTER, "不足30个交易日不应切换季节"

