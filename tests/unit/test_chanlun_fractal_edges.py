"""分型识别边界金标测试（V678）。

锁定 find_fractals 的严格/非严格模式、十字星跳过、bar_index 回退等行为。
"""

from __future__ import annotations

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.fractal import find_fractals
from easy_tdx.chanlun.types import CLKline, FXType


def _k(index: int, high: float, low: float) -> CLKline:
    return CLKline(
        k_index=index,
        date=None,  # type: ignore[arg-type]
        open=low,
        close=high,
        high=high,
        low=low,
        amount=0.0,
        index=index,
        merged_count=1,
    )


def test_insufficient_cklines_returns_empty() -> None:
    assert find_fractals([_k(0, 10.0, 9.0)], ChanlunConfig()) == []


def test_strict_ding_requires_both_high_and_low_highest() -> None:
    cklines = [
        _k(0, 10.0, 8.0),
        _k(1, 12.0, 9.0),
        _k(2, 11.0, 8.5),
    ]
    fxs = find_fractals(cklines, ChanlunConfig(fx_strict=True))
    assert len(fxs) == 1
    assert fxs[0].fx_type == FXType.DING


def test_non_strict_allows_equal_highs() -> None:
    cklines = [
        _k(0, 10.0, 8.0),
        _k(1, 12.0, 9.0),
        _k(2, 12.0, 8.5),
    ]
    strict = find_fractals(cklines, ChanlunConfig(fx_strict=True))
    non_strict = find_fractals(cklines, ChanlunConfig(fx_strict=False))
    assert strict == []
    assert len(non_strict) == 1
    assert non_strict[0].fx_type == FXType.DING


def test_doji_is_skipped() -> None:
    cklines = [_k(0, 10.0, 10.0), _k(1, 10.0, 10.0), _k(2, 10.0, 10.0)]
    assert find_fractals(cklines, ChanlunConfig(fx_strict=True)) == []
    assert find_fractals(cklines, ChanlunConfig(fx_strict=False)) == []


def test_bar_index_fallback_to_k_index() -> None:
    cklines = [
        _k(0, 10.0, 8.0),
        _k(5, 12.0, 9.0),
        _k(9, 11.0, 8.5),
    ]
    fxs = find_fractals(cklines, ChanlunConfig())
    assert fxs[0].bar_index == 5
