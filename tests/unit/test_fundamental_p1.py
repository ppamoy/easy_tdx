"""P1 长赢基本面选股：指标层 / 树粮菜打分 / 四季判断 / point-in-time 单元测试。"""

from __future__ import annotations

from datetime import date

import pandas as pd

from easy_tdx.fundamental.indicators import (
    indicator_values,
    pick_report,
)
from easy_tdx.fundamental.screener import (
    GRAIN,
    TREE,
    VEGETABLE,
    score_grain,
    score_tree,
    score_vegetable,
    screen_stock,
)
from easy_tdx.fundamental.season import detect_season


def _raw(**overrides):
    """构造一条原始 gpcw 字段 dict（字段名 -> 值）。"""
    base = {
        "基本每股收益": 1.5,
        "每股净资产": 8.0,
        "净资产收益率": 18.0,
        "其中：营业收入": 100.0,
        "其中：营业成本": 60.0,
        "归属于母公司所有者的净利润": 20.0,
        "所有者权益（或股东权益）合计": 80.0,
        "资产总计": 200.0,
        "负债合计": 80.0,
        "经营活动产生的现金流量净额": 25.0,
        "每股经营现金流量": 0.8,
        "营业收入增长率(%)": 12.0,
        "净利润增长率(%)": 15.0,
        "总股本": 10.0,
        "已上市流通A股": 10.0,
    }
    base.update(overrides)
    return base


def _row(**overrides) -> pd.Series:
    ind = indicator_values(_raw(**overrides))
    s = pd.Series(
        {
            "code": "600519",
            "market": "SH",
            "report_date": date(2026, 3, 31),
            "disclosure_date": date(2026, 4, 25),
            **ind,
        }
    )
    return s


class TestIndicatorValues:
    def test_derived_ratios(self):
        ind = indicator_values(_raw())
        assert abs(ind["gross_margin"] - 40.0) < 1e-6  # (100-60)/100
        assert abs(ind["net_margin"] - 20.0) < 1e-6  # 20/100
        assert abs(ind["debt_ratio"] - 40.0) < 1e-6  # 80/200
        assert ind["eps"] == 1.5
        assert ind["roe"] == 18.0

    def test_missing_values_none(self):
        ind = indicator_values(_raw(**{"其中：营业收入": None, "其中：营业成本": None}))
        assert ind["gross_margin"] is None
        assert ind["net_margin"] is None


class TestPointInTime:
    def _frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "code": "600519", "market": "SH",
                    "report_date": date(2025, 12, 31), "disclosure_date": date(2026, 4, 10),
                    "eps": 5.0,
                },
                {
                    "code": "600519", "market": "SH",
                    "report_date": date(2026, 3, 31), "disclosure_date": date(2026, 4, 25),
                    "eps": 1.5,
                },
                {
                    "code": "600519", "market": "SH",
                    "report_date": date(2026, 6, 30), "disclosure_date": date(2026, 8, 20),
                    "eps": 3.0,
                },
            ]
        )

    def test_pick_before_disclosure_uses_last_disclosed(self):
        fr = self._frame()
        # 4 月 20 日：一季报(4/25) 尚未披露 → 应选 2025 年报
        row = pick_report(fr, "600519", date(2026, 4, 20), market="SH")
        assert row is not None
        assert row["eps"] == 5.0

    def test_pick_after_disclosure_uses_newer(self):
        fr = self._frame()
        row = pick_report(fr, "600519", date(2026, 5, 1), market="SH")
        assert row is not None
        assert row["eps"] == 1.5

    def test_pick_excludes_future(self):
        fr = self._frame()
        # 未来半年报（8/20 披露）在 5 月不应出现
        row = pick_report(fr, "600519", date(2026, 5, 1), market="SH")
        assert row["eps"] != 3.0


class TestScreener:
    def test_tree_high_roe_growth(self):
        row = _row(roe=25.0, rev_yoy=20.0, np_yoy=25.0, **{"其中：营业收入": 5000.0})
        sc, _ = score_tree(row, pool_size=1)
        assert sc >= 60

    def test_grain_low_debt_profitable(self):
        row = _row(debt_ratio=15.0, eps=2.0, np_yoy=5.0)
        sc, _ = score_grain(row, pool_size=1)
        assert sc >= 60

    def test_vegetable_high_growth(self):
        row = _row(rev_yoy=40.0, np_yoy=60.0, net_margin=12.0)
        sc, _ = score_vegetable(row, pool_size=1)
        assert sc >= 60

    def test_screen_stock_returns_category(self):
        # 高 ROE + 高增长 + 高毛利 → 最可能是 tree
        row = _row(roe=30.0, rev_yoy=25.0, np_yoy=30.0)
        res = screen_stock(row, pool_size=1)
        assert res is not None
        assert res.category in (TREE, GRAIN, VEGETABLE)
        assert res.as_dict()["label"]

    def test_screen_stock_none_for_empty(self):
        assert screen_stock(None, pool_size=1) is None


class TestSeason:
    def _make_bars(self, up: bool = True, n: int = 120) -> tuple[list, list]:
        dates = [date(2025, 1, 1) + __import__("datetime").timedelta(days=i) for i in range(n)]
        closes = []
        px = 100.0
        for i in range(n):
            px *= (1.005 if up else 0.995)
            closes.append(px)
        return dates, closes

    def test_uptrend_not_winter(self):
        dates, closes = self._make_bars(up=True)
        res = detect_season(dates, closes, date(2025, 5, 1))
        assert res.season in ("summer", "spring")

    def test_downtrend_not_summer(self):
        dates, closes = self._make_bars(up=False)
        res = detect_season(dates, closes, date(2025, 5, 1))
        assert res.season in ("autumn", "winter")

    def test_insufficient_bars_unknown(self):
        dates = [date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3)]
        closes = [100.0, 101.0, 102.0]
        res = detect_season(dates, closes, date(2025, 1, 5))
        assert res.season == "unknown"



class TestBatchVerify:
    """批量时点验证汇总逻辑（合成数据，不依赖网络）。"""

    def _period(self, results, idx=None):
        return {
            "date": "2025-01-01",
            "season": None,
            "results": results,
            "index": idx or {"ret_20d": 1.0, "ret_60d": 2.0, "ret_250d": 5.0},
        }

    def _res(self, category, r20, r60=None, r250=None):
        return {
            "category": category,
            "performance": {"ret_20d": r20, "ret_60d": r60, "ret_250d": r250},
        }

    def test_summarize_basic(self):
        from easy_tdx.fundamental.pipeline import _summarize_periods

        periods = [
            self._period(
                [self._res("tree", 5.0, 10.0), self._res("grain", -2.0, 1.0)],
                idx={"ret_20d": 1.0, "ret_60d": 2.0, "ret_250d": 5.0},
            )
        ]
        s = _summarize_periods(periods, (20, 60, 250))
        # tree: 1 sample
        assert s["by_category"]["tree"]["count"] == 1
        assert s["by_category"]["tree"]["ret_20d"]["avg"] == 5.0
        assert s["by_category"]["tree"]["ret_20d"]["hit_rate"] == 1.0
        # grain: 1 sample
        assert s["by_category"]["grain"]["ret_20d"]["avg"] == -2.0
        assert s["by_category"]["grain"]["ret_20d"]["hit_rate"] == 0.0
        # overall: 2 samples, avg (5 + -2)/2 = 1.5
        assert s["overall"]["count"] == 2
        assert abs(s["overall"]["ret_20d"]["avg"] - 1.5) < 1e-6
        # index
        assert s["index"]["ret_20d"]["avg"] == 1.0
        # beats: overall 1.5 > index 1.0
        assert s["beats_index"]["ret_20d"]["beats"] is True
        assert abs(s["beats_index"]["ret_20d"]["alpha"] - 0.5) < 1e-6

    def test_summarize_vegetable_and_empty(self):
        from easy_tdx.fundamental.pipeline import _summarize_periods

        periods = [
            self._period(
                [self._res("vegetable", 3.0, 6.0), self._res("vegetable", -1.0, 4.0)],
                idx={"ret_20d": 2.0, "ret_60d": 3.0, "ret_250d": 4.0},
            )
        ]
        s = _summarize_periods(periods, (20, 60, 250))
        assert s["by_category"]["vegetable"]["count"] == 2
        assert abs(s["by_category"]["vegetable"]["ret_20d"]["avg"] - 1.0) < 1e-6
        assert s["by_category"]["tree"]["count"] == 0
        assert s["by_category"]["tree"]["ret_20d"]["avg"] is None
        # index beats overall here (2.0 > 1.0)
        assert s["beats_index"]["ret_20d"]["beats"] is False
