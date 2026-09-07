"""web/routers/screening.py V429 _is_buy_signal 方向判断 测试。"""

from __future__ import annotations

from easy_tdx.web.routers.screening import _is_buy_signal


class TestIsBuySignal:
    def test_buy_types(self) -> None:
        for t in ("1buy", "2buy", "3buy"):
            assert _is_buy_signal(t) is True, t

    def test_second_buy_s(self) -> None:
        # 类二买 2buy_s：endswith("buy") 会误判为 False，包含判断应识别为 buy
        assert _is_buy_signal("2buy_s") is True

    def test_sell_types(self) -> None:
        for t in ("1sell", "2sell", "2sell_s", "3sell"):
            assert _is_buy_signal(t) is False, t

    def test_unknown(self) -> None:
        assert _is_buy_signal("") is False
