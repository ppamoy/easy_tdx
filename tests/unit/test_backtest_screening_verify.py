"""选股结果前瞻收益验证的单元测试。"""

from __future__ import annotations

import pandas as pd
import pytest

from easy_tdx.backtest.screening_verify import (
    _find_selection_index,
    _symbol_forward_returns,
    compute_screening_verify,
)


def _bars(closes: list[float], start: str = "2024-01-01") -> dict[str, list]:
    """构造 {datetime, close} bars，交易日为连续自然日。"""
    dates = pd.date_range(start, periods=len(closes), freq="D")
    return {
        "datetime": [d.strftime("%Y-%m-%d") for d in dates],
        "close": closes,
    }


class TestFindSelectionIndex:
    def test_exact_match(self) -> None:
        dates = ["2024-01-01", "2024-01-02", "2024-01-03"]
        assert _find_selection_index(dates, "2024-01-02") == 1

    def test_nearest_future(self) -> None:
        dates = ["2024-01-01", "2024-01-03", "2024-01-05"]
        # 选股日 01-02 无数据 → 取 01-03
        assert _find_selection_index(dates, "2024-01-02") == 1

    def test_all_before_target(self) -> None:
        dates = ["2024-01-01", "2024-01-02"]
        assert _find_selection_index(dates, "2024-01-03") is None

    def test_empty(self) -> None:
        assert _find_selection_index([], "2024-01-01") is None


class TestSymbolForwardReturns:
    def test_basic_horizons(self) -> None:
        closes = [100, 101, 102, 104, 108, 110]
        fwd = _symbol_forward_returns(
            ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-06"],
            closes,
            "2024-01-01",
            (1, 6),
        )
        # idx=0: +1 -> 101/100-1=0.01; +6 -> 越界 None
        assert fwd[1] == pytest.approx(0.01)
        assert fwd[6] is None

    def test_out_of_range_none(self) -> None:
        closes = [100, 101, 102]
        dates = ["2024-01-01", "2024-01-02", "2024-01-03"]
        fwd = _symbol_forward_returns(dates, closes, "2024-01-03", (5,))
        assert fwd[5] is None


class TestComputeScreeningVerify:
    def test_selected_outperforms_pool(self) -> None:
        # 选中的 2 只后续大涨，未选中的 2 只下跌 → 超额为正
        bars = {
            "SZ:000001": _bars([100, 101, 103, 106, 110, 115]),
            "SZ:000002": _bars([100, 102, 105, 109, 114, 120]),
            "SZ:000003": _bars([100, 99, 98, 97, 96, 95]),
            "SZ:000004": _bars([100, 98, 97, 96, 95, 94]),
        }
        report = compute_screening_verify(
            bars, ["SZ:000001", "SZ:000002"], "2024-01-01", horizons=(5,)
        )
        h5 = report["horizons"]["5"]
        assert h5["selected_n"] == 2
        assert h5["pool_n"] == 4
        assert h5["selected_avg_return"] > h5["pool_avg_return"]
        assert h5["excess_return"] > 0
        assert h5["excess_hit_rate"] > 0
        assert "跑赢" in report["verdict"]
        assert report["selected_size"] == 2
        assert report["pool_size"] == 4

    def test_selected_underperforms_pool(self) -> None:
        bars = {
            "SZ:000001": _bars([100, 99, 98, 97, 96, 95]),
            "SZ:000002": _bars([100, 98, 97, 96, 95, 94]),
            "SZ:000003": _bars([100, 101, 103, 106, 110, 115]),
            "SZ:000004": _bars([100, 102, 105, 109, 114, 120]),
        }
        report = compute_screening_verify(
            bars, ["SZ:000001"], "2024-01-01", horizons=(5,)
        )
        h5 = report["horizons"]["5"]
        assert h5["excess_return"] < 0
        assert "跑输" in report["verdict"]

    def test_insufficient_forward_data(self) -> None:
        # 选股日在末端，无足够前瞻数据 → 无样本
        bars = {"SZ:000001": _bars([100, 101, 102])}
        report = compute_screening_verify(bars, ["SZ:000001"], "2024-01-03", horizons=(5,))
        h5 = report["horizons"]["5"]
        assert h5["selected_n"] == 0
        assert "无法验证" in report["verdict"] or "无足够" in report["verdict"]

    def test_verdict_present_and_deterministic(self) -> None:
        bars = {
            "SZ:000001": _bars([100, 101, 102, 103, 104, 105]),
            "SZ:000002": _bars([100, 100, 100, 100, 100, 100]),
        }
        report = compute_screening_verify(bars, ["SZ:000001"], "2024-01-01", horizons=(1, 5))
        assert isinstance(report["verdict"], str)
        assert len(report["verdict"]) > 0
        assert set(report["horizons"].keys()) == {"1", "5"}
        # per_symbol 含 selected 标记
        ps = {p["symbol"]: p for p in report["per_symbol"]}
        assert ps["SZ:000001"]["selected"] is True
        assert ps["SZ:000002"]["selected"] is False
