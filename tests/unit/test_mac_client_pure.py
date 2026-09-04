"""mac/client.py 纯函数测试（V399e）。

覆盖 _convert_board_code / _flatten_quote_fields / _quotes_to_df /
_flatten_tick_chart / _flatten_multi_tick_chart，离线可测。
"""

from __future__ import annotations

from datetime import date

from easy_tdx.mac.client import (
    _convert_board_code,
    _flatten_multi_tick_chart,
    _flatten_quote_fields,
    _flatten_tick_chart,
    _quotes_to_df,
)
from easy_tdx.mac.models import (
    MacMultiTickChart,
    MacMultiTickDay,
    MacQuoteField,
    MacTick,
    MacTickChart,
)


class TestConvertBoardCode:
    def test_us(self) -> None:
        assert _convert_board_code("US0401") == 30401

    def test_hk(self) -> None:
        assert _convert_board_code("HK0283") == 20283

    def test_six_digit_prefixes(self) -> None:
        assert _convert_board_code("000686") == 31686
        assert _convert_board_code("399372") == 30372
        assert _convert_board_code("899050") == 32050
        assert _convert_board_code("880686") == 20686

    def test_other_int(self) -> None:
        assert _convert_board_code("601001") == 601001


class TestFlattenQuotes:
    def test_flatten(self) -> None:
        q = MacQuoteField(market=0, code="000001", name="平安银行", fields={"price": 10.5})
        rows = _flatten_quote_fields([q])
        assert rows[0]["code"] == "000001"
        assert rows[0]["price"] == 10.5

    def test_to_df(self) -> None:
        q = MacQuoteField(market=0, code="000001", name="平安银行", fields={})
        df = _quotes_to_df([q])
        assert df.iloc[0]["name"] == "平安银行"


class TestFlattenTick:
    def test_single(self) -> None:
        tick = MacTick(time="09:30", price=10.0, avg=9.95, vol=100)
        chart = MacTickChart(
            market=0,
            code="000001",
            name="平安银行",
            pre_close=9.9,
            open=10.0,
            high=10.5,
            low=9.8,
            close=10.4,
            vol=100,
            amount=1000.0,
            charts=[tick],
        )
        rows = _flatten_tick_chart(chart)
        assert rows[0]["time"] == "09:30"

    def test_multi(self) -> None:
        tick = MacTick(time="09:30", price=10.0, avg=9.95, vol=100)
        day = MacMultiTickDay(date=date(2024, 1, 2), pre_close=9.9, ticks=[tick])
        chart = MacMultiTickChart(
            market=0,
            code="000001",
            name="平安银行",
            pre_close=9.9,
            open=10.0,
            high=10.5,
            low=9.8,
            close=10.4,
            vol=100,
            amount=1000.0,
            charts=[day],
        )
        rows = _flatten_multi_tick_chart(chart)
        assert rows[0]["date"] == date(2024, 1, 2)
        assert rows[0]["pre_close"] == 9.9
