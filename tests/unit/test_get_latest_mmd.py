"""web/routers/screening.py _get_latest_mmd 测试（V429 方向判断回归）。"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from easy_tdx.web.routers.screening import _get_latest_mmd


def _mmd(mmd_type: str, low: float, high: float, index: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        mmd_type=SimpleNamespace(value=mmd_type),
        bi=SimpleNamespace(
            index=index,
            end=SimpleNamespace(k=SimpleNamespace(date=date(2024, 3, 15))),
            low=low,
            high=high,
        ),
    )


class TestGetLatestMmd:
    def test_second_buy_s_uses_low(self) -> None:
        """V429: 类二买 2buy_s 应取 low（endswith('buy') 会误判取 high）。"""
        result = SimpleNamespace(mmds=[_mmd("2buy_s", low=10.0, high=12.0)])
        out = _get_latest_mmd(result)
        assert out is not None
        assert out["type"] == "2buy_s"
        assert out["price"] == 10.0

    def test_sell_uses_high(self) -> None:
        result = SimpleNamespace(mmds=[_mmd("3sell", low=10.0, high=12.0)])
        out = _get_latest_mmd(result)
        assert out is not None
        assert out["price"] == 12.0

    def test_no_mmds_returns_none(self) -> None:
        assert _get_latest_mmd(SimpleNamespace(mmds=[])) is None
