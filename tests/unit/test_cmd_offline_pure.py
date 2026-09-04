"""cmd_offline.py 纯函数测试（V399f）。

覆盖 _df_to_bars / _is_index_code / _watch_signal_row / _is_within_since_days /
_fmt_opt_price / _render_watch_report / _advice_batch_one，离线可测。
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pandas as pd

from easy_tdx.cli.cmd_offline import (
    _advice_batch_one,
    _df_to_bars,
    _fmt_opt_price,
    _is_index_code,
    _is_within_since_days,
    _render_watch_report,
    _watch_signal_row,
)


class TestDfToBars:
    def test_convert(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "date": pd.Timestamp("2024-01-02"),
                    "open": 10,
                    "close": 11,
                    "high": 12,
                    "low": 9,
                    "vol": 100,
                    "amount": 1100,
                },
                {
                    "date": pd.Timestamp("2024-01-01"),
                    "open": 10,
                    "close": 10.5,
                    "high": 11,
                    "low": 9.5,
                    "vol": 90,
                    "amount": 1000,
                },
            ]
        )
        bars = _df_to_bars(df)
        assert len(bars) == 2
        # 按日期升序
        assert bars[0].year == 2024 and bars[0].month == 1 and bars[0].day == 1


class TestIsIndexCode:
    def test_index_prefixes(self) -> None:
        assert _is_index_code("sh", "000001") is True
        assert _is_index_code("sz", "399001") is True
        assert _is_index_code("sh", "600000") is False
        assert _is_index_code("sz", "000001") is False  # 深市非39开头不是指数


class TestWatchSignalRow:
    def test_row(self) -> None:
        mmd = SimpleNamespace(
            mmd_type=SimpleNamespace(value="3buy"),
            confidence=0.88,
            _signal_quality_scorecard={"overall_grade": "A"},
            _decision_support={
                "action_recommendation": "买入",
                "entry_price": 10.5,
                "stop_loss": 9.8,
                "take_profit_1": 12.0,
            },
        )
        row = _watch_signal_row("SZ000001", mmd, "2024-01-05")
        assert row["symbol"] == "SZ000001"
        assert row["type"] == "3buy"
        assert row["v102_grade"] == "A"
        assert row["entry_price"] == 10.5


class TestIsWithinSinceDays:
    def test_no_filter(self) -> None:
        assert _is_within_since_days("2020-01-01", 0) is True

    def test_recent(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        assert _is_within_since_days(today, 7) is True

    def test_old(self) -> None:
        assert _is_within_since_days("2020-01-01", 7) is False

    def test_bad_date(self) -> None:
        assert _is_within_since_days("not-a-date", 7) is False


class TestFmtOptPrice:
    def test_fmt(self) -> None:
        assert _fmt_opt_price(None) == "-"
        assert _fmt_opt_price(10.5) == "10.50"
        assert _fmt_opt_price(10) == "10.00"
        assert _fmt_opt_price("x") == "x"


class TestRenderWatchReport:
    def test_render(self) -> None:
        rows = [
            {
                "symbol": "SZ000001",
                "type": "3buy",
                "date": "2024-01-05",
                "confidence": 0.88,
                "v102_grade": "A",
                "advice": "买入",
                "entry_price": 10.5,
                "stop_loss": 9.8,
                "take_profit_1": 12.0,
            }
        ]
        text = _render_watch_report(rows)
        assert "离线 V102 信号监控报告" in text
        assert "SZ000001" in text
        assert "10.50" in text


class TestAdviceBatchOne:
    def test_missing_file(self, tmp_path) -> None:
        report, row = _advice_batch_one(tmp_path / "nonexistent.day", 0, 10)
        assert report is None
        assert "error" in row
