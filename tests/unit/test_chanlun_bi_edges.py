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


def test_simple_emits_legacy_warning_and_default_is_silent(caplog, monkeypatch) -> None:
    """bi-type-convergence spec：显式 simple 发 legacy 告警；默认 new 无告警。"""
    import logging

    from easy_tdx.chanlun import bi as bi_mod

    start = _fx(FXType.DI, 9.0, [_k(0)])
    end = _fx(FXType.DING, 10.0, [_k(2)])

    # 告警是进程级一次性（_warned_simple_legacy 锁），重置后才能在本测试观测到
    monkeypatch.setattr(bi_mod, "_warned_simple_legacy", False)

    # Scenario「legacy 标注」：显式 simple 仍可用，但发 legacy 告警
    with caplog.at_level(logging.WARNING, logger="easy_tdx.chanlun.bi"):
        assert _can_form_bi(start, end, ChanlunConfig(bi_type="simple")) is True
        assert any("legacy" in r.message for r in caplog.records)

    # Scenario「默认不含简化口径」：默认 new 不进 simple 分支、无告警
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="easy_tdx.chanlun.bi"):
        assert _can_form_bi(start, end, ChanlunConfig(bi_type="new")) is True
        assert not caplog.records


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


def test_pending_opposite_more_extreme_same_type_replaces_start() -> None:
    """pending_opposite 期间出现更极端同型分型应替换起点（V740 回归）。

    场景：底(8.0)→顶(10.0)成笔后，底(9.0)因 gap 不足 pending；此时出现更
    高的顶(11.0)。缠论「相邻同型取更极端」——两底之间的最高顶才是笔端点，
    故上一笔应延伸到 11.0，而非停在较低的 10.0（旧实现因 pending 保护跳过了
    更极端顶，导致笔端点取低顶、伪拆分）。
    """
    from easy_tdx.chanlun.bi import find_bis

    fxs = [
        _fx(FXType.DI, 8.0, [_k(0), _k(1), _k(2)]),
        _fx(FXType.DING, 10.0, [_k(5), _k(6), _k(7)]),  # gap(底,顶)=4 ≥3 → 成笔
        _fx(FXType.DI, 9.0, [_k(8), _k(9), _k(10)]),  # gap(顶,底)=2 <3 → pending
        _fx(FXType.DING, 11.0, [_k(11), _k(12), _k(13)]),  # 更高顶，应替换起点+清 pending
        _fx(FXType.DI, 9.5, [_k(20), _k(21), _k(22)]),  # gap(新顶,底)=8 ≥3 → 成笔
    ]
    bis = find_bis(fxs, ChanlunConfig(bi_type="new"))
    assert len(bis) == 2, f"应为 2 笔（上+下），实际 {len(bis)}"
    # 第一笔（上）终点必须落在更高的顶 11.0，而非较低的 10.0
    assert bis[0].end.val == 11.0, f"向上笔终点应取最高顶 11.0，实际 {bis[0].end.val}"
    assert bis[0].direction == Direction.UP
    # 第二笔（下）从 11.0 起
    assert bis[1].start.val == 11.0
    assert bis[1].direction == Direction.DOWN


def test_pending_opposite_non_extreme_same_type_keeps_start() -> None:
    """pending_opposite 期间出现不更极端的同型分型应保留旧起点（不误替换）。"""
    from easy_tdx.chanlun.bi import find_bis

    fxs = [
        _fx(FXType.DI, 8.0, [_k(0), _k(1), _k(2)]),
        _fx(FXType.DING, 12.0, [_k(5), _k(6), _k(7)]),  # 成笔
        _fx(FXType.DI, 9.0, [_k(8), _k(9), _k(10)]),  # gap 不足 → pending
        _fx(FXType.DING, 10.0, [_k(11), _k(12), _k(13)]),  # 较低顶，不更极端 → 保留旧顶
        _fx(FXType.DI, 9.5, [_k(20), _k(21), _k(22)]),  # 与旧顶(12.0) gap 够 → 成笔
    ]
    bis = find_bis(fxs, ChanlunConfig(bi_type="new"))
    assert len(bis) == 2
    # 第一笔终点保留在较高的旧顶 12.0，未被较低顶 10.0 替换
    assert bis[0].end.val == 12.0
    assert bis[1].start.val == 12.0
