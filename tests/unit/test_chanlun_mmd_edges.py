"""买卖点力度计算边界金标测试（V667）。

锁定 _calc_bi_force 在无收盘价、端点越界、上下方向等场景下稳定回退，
避免 MACD 力度计算异常影响背驰/买卖点判断。
"""

from __future__ import annotations

from easy_tdx.chanlun.mmd_conditions import _calc_bi_force
from easy_tdx.chanlun.types import BI, FX, CLKline, Direction, FXType


def _bi(index: int, direction: str, high: float, low: float, start_idx: int, end_idx: int) -> BI:
    start_fx = FX(
        fx_type=FXType.DI if direction == "up" else FXType.DING,
        k=CLKline(
            k_index=start_idx,
            date=None,  # type: ignore[arg-type]
            open=low,
            close=high,
            high=high,
            low=low,
            amount=0.0,
            index=start_idx,
        ),
        klines=[],
        val=low if direction == "up" else high,
        index=index,
        done=True,
        bar_index=start_idx,
    )
    end_fx = FX(
        fx_type=FXType.DING if direction == "up" else FXType.DI,
        k=CLKline(
            k_index=end_idx,
            date=None,  # type: ignore[arg-type]
            open=low,
            close=high,
            high=high,
            low=low,
            amount=0.0,
            index=end_idx,
        ),
        klines=[],
        val=high if direction == "up" else low,
        index=index,
        done=True,
        bar_index=end_idx,
    )
    return BI(
        start=start_fx,
        end=end_fx,
        direction=Direction.UP if direction == "up" else Direction.DOWN,
        index=index,
        high=high,
        low=low,
    )


def test_calc_bi_force_no_closes_falls_back_to_amplitude() -> None:
    bi = _bi(0, "up", high=12.0, low=8.0, start_idx=0, end_idx=5)
    assert _calc_bi_force(bi, None, bi.index) == 4.0


def test_calc_bi_force_out_of_range_falls_back_to_amplitude() -> None:
    bi = _bi(0, "down", high=12.0, low=8.0, start_idx=80, end_idx=90)
    closes = [10.0] * 20
    assert _calc_bi_force(bi, closes, bi.index) == 4.0


def test_calc_bi_force_valid_closes_is_nonnegative() -> None:
    bi = _bi(0, "up", high=12.0, low=8.0, start_idx=2, end_idx=6)
    closes = [10.0, 10.2, 10.1, 10.5, 10.4, 10.8, 10.6, 11.0]
    force = _calc_bi_force(bi, closes, bi.index)
    assert isinstance(force, float)
    assert force >= 0.0
