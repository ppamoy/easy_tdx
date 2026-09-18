"""笔计算边界金标测试（V659）。

锁定 _can_form_bi / 弱笔 / 端点一致性 / 价格方向 / 分型稳定性等纯函数
在关键边界上的行为，防止后续重构把笔规则改坏。
"""

from __future__ import annotations

from easy_tdx.chanlun.bi import (
    _can_form_bi,
    _check_bi_endpoint_consistency,
    _check_fractal_stability,
    _is_weak_bi,
    _validate_bi_price_direction,
)
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import FX, CLKline, Direction, FXType


def _k(index: int, high: float = 10.0, low: float = 9.0) -> CLKline:
    return CLKline(
        k_index=index,
        date=None,  # type: ignore[arg-type]
        open=low,
        close=high,
        high=high,
        low=low,
        amount=0.0,
        index=index,
    )


def _fx(fx_type: FXType, val: float, klines: list[CLKline]) -> FX:
    return FX(
        fx_type=fx_type,
        k=klines[-1] if klines else _k(0),
        klines=klines,
        val=val,
        index=0,
        done=True,
    )


def test_can_form_bi_rejects_same_fx_type() -> None:
    start = _fx(FXType.DING, 10.0, [_k(0)])
    end = _fx(FXType.DING, 11.0, [_k(2)])
    assert _can_form_bi(start, end, ChanlunConfig()) is False


def test_can_form_bi_requires_klines() -> None:
    start = _fx(FXType.DI, 9.0, [])
    end = _fx(FXType.DING, 10.0, [])
    assert _can_form_bi(start, end, ChanlunConfig()) is False


def test_can_form_bi_new_and_old_gap() -> None:
    # 新笔 gap = end_left - start_right + 1 >= 3
    start = _fx(FXType.DI, 9.0, [_k(0)])
    new_ok = _fx(FXType.DING, 10.0, [_k(2)])
    new_bad = _fx(FXType.DING, 10.0, [_k(1)])
    assert _can_form_bi(start, new_ok, ChanlunConfig(bi_type="new")) is True
    assert _can_form_bi(start, new_bad, ChanlunConfig(bi_type="new")) is False

    # 老笔 gap >= 5
    old_ok = _fx(FXType.DING, 10.0, [_k(4)])
    old_bad = _fx(FXType.DING, 10.0, [_k(3)])
    assert _can_form_bi(start, old_ok, ChanlunConfig(bi_type="old")) is True
    assert _can_form_bi(start, old_bad, ChanlunConfig(bi_type="old")) is False

    # simple 只要求顶底交替
    assert _can_form_bi(start, new_bad, ChanlunConfig(bi_type="simple")) is True


def test_is_weak_bi_threshold() -> None:
    assert _is_weak_bi(_fx(FXType.DI, 100.0, [_k(0)]), _fx(FXType.DING, 100.05, [_k(2)]))
    assert not _is_weak_bi(_fx(FXType.DI, 100.0, [_k(0)]), _fx(FXType.DING, 101.0, [_k(2)]))
    # 非正价格不判弱笔，避免除零/异常
    assert not _is_weak_bi(_fx(FXType.DI, 0.0, [_k(0)]), _fx(FXType.DING, 10.0, [_k(2)]))


def test_bi_endpoint_consistency() -> None:
    di = _fx(FXType.DI, 9.0, [_k(0)])
    ding = _fx(FXType.DING, 10.0, [_k(2)])
    assert _check_bi_endpoint_consistency(di, ding, Direction.UP)
    assert not _check_bi_endpoint_consistency(ding, di, Direction.UP)
    assert _check_bi_endpoint_consistency(ding, di, Direction.DOWN)
    assert not _check_bi_endpoint_consistency(di, ding, Direction.DOWN)


def test_validate_bi_price_direction() -> None:
    assert _validate_bi_price_direction(
        _fx(FXType.DI, 9.0, [_k(0)]), _fx(FXType.DING, 10.0, [_k(2)]), Direction.UP
    )
    assert not _validate_bi_price_direction(
        _fx(FXType.DI, 11.0, [_k(0)]), _fx(FXType.DING, 10.0, [_k(2)]), Direction.UP
    )
    assert _validate_bi_price_direction(
        _fx(FXType.DING, 11.0, [_k(0)]), _fx(FXType.DI, 10.0, [_k(2)]), Direction.DOWN
    )


def test_fractal_stability_confirmation() -> None:
    # 顶分型之后出现更低低点 → 确认；未出现 → 不确认
    cklines = [_k(i, high=10.0, low=9.0) for i in range(6)]
    cklines[4] = _k(4, high=10.0, low=8.5)
    top = _fx(FXType.DING, 10.0, [_k(1), _k(2), _k(3)])
    assert _check_fractal_stability(top, cklines, Direction.UP)

    flat_cklines = [_k(i, high=10.0, low=9.0) for i in range(6)]
    assert not _check_fractal_stability(top, flat_cklines, Direction.UP)
