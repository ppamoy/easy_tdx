"""client.py 纯函数测试（V399d）。

覆盖 _record_signature / _page_signature / _classify_fund_flow /
_date_from_bar / _historical_fund_flow_from_records / _serialize_stocks /
_deserialize_stocks / _load_cache / _save_cache / _today_in_shanghai，
全部离线可测。
"""

from __future__ import annotations

import pytest

from easy_tdx.client import (
    _classify_fund_flow,
    _date_from_bar,
    _deserialize_stocks,
    _historical_fund_flow_from_records,
    _load_cache,
    _page_signature,
    _record_signature,
    _save_cache,
    _serialize_stocks,
    _today_in_shanghai,
)
from easy_tdx.models.bar import SecurityBar
from easy_tdx.models.enums import Market
from easy_tdx.models.security import SecurityInfo
from easy_tdx.models.timeseries import TransactionRecord


def _rec(buyorsell: int, price: float, vol: int, hour: int = 10, minute: int = 30):
    return TransactionRecord(hour=hour, minute=minute, price=price, vol=vol, buyorsell=buyorsell)


class TestSignatures:
    def test_record_signature(self) -> None:
        r = _rec(0, 10.5, 100, hour=9, minute=31)
        assert _record_signature(r) == (9, 31, 10.5, 100, 0, 0)

    def test_page_signature(self) -> None:
        first = _rec(0, 10.0, 100)
        last = _rec(1, 11.0, 200)
        sig = _page_signature([first, last])
        assert sig[0] == (10, 30, 10.0, 100, 0, 0)
        assert sig[1] == (10, 30, 11.0, 200, 1, 0)


class TestFundFlow:
    def test_classify(self) -> None:
        # 超大单买入：1000 股 * 100 元 * 100 = 1000 万元 → super_in
        # 大单卖出：2000 股 * 200 元 * 100 = 4000 万元 → super_out
        # 中单买入：500 股 * 100 元 * 100 = 500 万 → super_in
        # 小单买入：100 股 * 10 元 * 100 = 10 万 → small_in
        records = [
            _rec(0, 1000.0, 100),  # 1000 万
            _rec(1, 200.0, 2000),  # 4000 万
            _rec(0, 100.0, 500),  # 500 万
            _rec(0, 10.0, 10),  # 10 * 10 * 100 = 1 万 → small_in
            _rec(2, 999.0, 9999),  # 中性，忽略
        ]
        flow = _classify_fund_flow(records)
        assert flow.super_in == pytest.approx(1000.0 * 100 * 100 + 500 * 100 * 100)
        assert flow.super_out == pytest.approx(200.0 * 2000 * 100)
        assert flow.small_in == pytest.approx(10.0 * 10 * 100)
        assert flow.small_out == 0.0

    def test_historical(self) -> None:
        flow = _historical_fund_flow_from_records(20240315, [_rec(0, 10.0, 10)])
        assert flow.year == 2024
        assert flow.month == 3
        assert flow.day == 15
        assert flow.small_in == pytest.approx(10.0 * 10 * 100)


class TestDateFromBar:
    def test_date(self) -> None:
        bar = SecurityBar(
            open=10,
            close=11,
            high=12,
            low=9,
            vol=100,
            amount=1100,
            year=2024,
            month=2,
            day=29,
            hour=15,
            minute=0,
        )
        assert _date_from_bar(bar) == 20240229


class TestStockCache:
    def _stocks(self) -> list[SecurityInfo]:
        return [
            SecurityInfo(
                market=Market.SZ,
                code="000001",
                name="平安银行",
                volunit=100,
                decimal_point=2,
                pre_close=10.0,
            )
        ]

    def test_serialize_deserialize(self) -> None:
        stocks = self._stocks()
        data = _serialize_stocks(stocks)
        assert data[0]["code"] == "000001"
        assert "_raw" not in data[0]
        back = _deserialize_stocks(data)
        assert back[0].code == "000001"
        assert back[0].market == Market.SZ

    def test_cache_roundtrip(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr("easy_tdx.client._CACHE_DIR", tmp_path)
        stocks = self._stocks()
        _save_cache(stocks)
        loaded = _load_cache()
        assert loaded is not None
        assert loaded[0].code == "000001"

    def test_load_missing_cache(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr("easy_tdx.client._CACHE_DIR", tmp_path)
        assert _load_cache() is None


class TestToday:
    def test_today_format(self) -> None:
        v = _today_in_shanghai()
        assert 19000101 <= v <= 29991231
        assert len(str(v)) == 8
