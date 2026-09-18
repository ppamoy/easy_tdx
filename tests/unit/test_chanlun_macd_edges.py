"""MACD 计算边界金标测试（V679）。

锁定 calc_macd 空序列与 calc_macd_force 区间越界回退，确保背驰力度计算稳定。
"""

from __future__ import annotations

from easy_tdx.chanlun.macd import _calc_ema, calc_macd, calc_macd_force


def test_calc_macd_empty_returns_empty_lists() -> None:
    assert calc_macd([]) == {"dif": [], "dea": [], "hist": []}
    assert _calc_ema([], 12) == []


def test_calc_macd_output_length_matches_input() -> None:
    closes = [10.0, 10.2, 10.1, 10.5, 10.4, 10.8]
    macd = calc_macd(closes)
    assert len(macd["dif"]) == len(closes)
    assert len(macd["dea"]) == len(closes)
    assert len(macd["hist"]) == len(closes)


def test_calc_macd_force_out_of_range_returns_zero() -> None:
    closes = [10.0, 10.2, 10.1, 10.5]
    force = calc_macd_force(closes, start_idx=2, end_idx=4)
    assert force == {"hist_sum": 0.0, "hist_up_sum": 0.0, "hist_down_sum": 0.0}


def test_calc_macd_force_valid_range_is_nonnegative() -> None:
    closes = [10.0, 10.2, 10.1, 10.5, 10.4, 10.8, 10.6]
    force = calc_macd_force(closes, start_idx=1, end_idx=5)
    assert force["hist_sum"] >= 0.0
    assert force["hist_up_sum"] >= 0.0
    assert force["hist_down_sum"] >= 0.0
