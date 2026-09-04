"""fundamental/indicators.py 纯函数测试（V399）。

覆盖 _period_from_filename / _to_date / _dt / _f / _market_from_code /
indicator_values / pick_report 七个纯函数，离线可测。
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from easy_tdx.fundamental.indicators import (
    _dt,
    _f,
    _market_from_code,
    _period_from_filename,
    _to_date,
    indicator_values,
    pick_report,
)


class TestParsers:
    def test_period_from_filename(self) -> None:
        assert _period_from_filename("gpcw20240331.zip") == 20240331
        assert _period_from_filename("foo.zip") == 0

    def test_to_date(self) -> None:
        assert _to_date(20240331) == date(2024, 3, 31)
        assert _to_date(240331) == date(2024, 3, 31)
        assert _to_date(0) is None
        assert _to_date(None) is None
        assert _to_date("abc") is None

    def test_dt(self) -> None:
        assert _dt(20240101) == date(2024, 1, 1)
        assert _dt(0) is None
        assert _dt(None) is None

    def test_f(self) -> None:
        assert _f(1.5) == 1.5
        assert _f("2.5") == 2.5
        assert _f(None) is None
        assert _f("x") is None

    def test_market_from_code(self) -> None:
        assert _market_from_code("600000") == "SH"
        assert _market_from_code("830000") == "BJ"
        assert _market_from_code("000001") == "SZ"


class TestIndicatorValues:
    def test_derived_metrics(self) -> None:
        v = {
            "其中：营业收入": 100.0,
            "其中：营业成本": 60.0,
            "归属于母公司所有者的净利润": 20.0,
            "资产总计": 200.0,
            "负债合计": 100.0,
            "经营活动产生的现金流量净额": 30.0,
            "基本每股收益": 1.2,
            "每股净资产": 8.0,
            "净资产收益率": 15.0,
        }
        out = indicator_values(v)
        assert out["gross_margin"] == 40.0
        assert out["net_margin"] == 20.0
        assert out["debt_ratio"] == 50.0
        assert out["eps"] == 1.2

    def test_empty_revenue(self) -> None:
        out = indicator_values({"其中：营业收入": None, "其中：营业成本": 60.0})
        assert out["gross_margin"] is None


class TestPickReport:
    def _frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"code": "000001", "market": "SZ", "report_date": date(2024, 3, 31),
                 "disclosure_date": date(2024, 4, 25)},
                {"code": "000001", "market": "SZ", "report_date": date(2023, 12, 31),
                 "disclosure_date": date(2024, 1, 20)},
            ]
        )

    def test_pick_latest_disclosed(self) -> None:
        row = pick_report(self._frame(), "000001", date(2024, 5, 1))
        assert row is not None
        assert row["report_date"] == date(2024, 3, 31)

    def test_pick_none_when_after_target(self) -> None:
        assert pick_report(self._frame(), "000001", date(2023, 12, 1)) is None

    def test_pick_none_for_unknown_code(self) -> None:
        assert pick_report(self._frame(), "999999", date(2024, 5, 1)) is None
