"""背驰边界条件金标测试（V654）。

锁定 _check_pz_beichi / _check_qs_beichi 的防御分支：
趋势不成立、中枢缺失 lines、离开笔越界、未创新极值等场景必须静默跳过，
不能产出错误背驰或崩溃。
"""

from __future__ import annotations

from easy_tdx.chanlun.beichi import _check_pz_beichi, _check_qs_beichi
from easy_tdx.chanlun.types import BI, FX, ZS, CLKline, Direction, FXType


def _bi(index: int, direction: str, high: float, low: float) -> BI:
    start_fx = FX(
        fx_type=FXType.DI if direction == "up" else FXType.DING,
        k=CLKline(
            k_index=index * 10,
            date=None,  # type: ignore[arg-type]
            open=low,
            close=high,
            high=high,
            low=low,
            amount=0.0,
            index=index,
        ),
        klines=[],
        val=low if direction == "up" else high,
        index=index,
        done=True,
    )
    end_fx = FX(
        fx_type=FXType.DING if direction == "up" else FXType.DI,
        k=CLKline(
            k_index=index * 10 + 5,
            date=None,  # type: ignore[arg-type]
            open=low,
            close=high,
            high=high,
            low=low,
            amount=0.0,
            index=index,
        ),
        klines=[],
        val=high if direction == "up" else low,
        index=index,
        done=True,
    )
    return BI(
        start=start_fx,
        end=end_fx,
        direction=Direction.UP if direction == "up" else Direction.DOWN,
        index=index,
        high=high,
        low=low,
    )


def _zs(index: int, lines: list[BI], zg: float, zd: float) -> ZS:
    gg = max((line.high for line in lines), default=zg)
    dd = min((line.low for line in lines), default=zd)
    return ZS(
        lines=lines,
        zg=zg,
        zd=zd,
        gg=gg,
        dd=dd,
        direction="",
        index=index,
        done=True,
    )


def test_pz_skip_when_line_count_lt_3() -> None:
    bis = [_bi(0, "up", 10.0, 8.0), _bi(1, "down", 10.0, 8.0)]
    zs = _zs(0, bis, 10.0, 8.0)
    assert _check_pz_beichi(bis, [zs], closes=None) == []


def test_pz_skip_when_no_enter_or_exit() -> None:
    # first.index <= 0：没有进入笔；last.index + 1 >= len(bis)：没有离开笔。
    bis = [_bi(0, "up", 12.0, 9.0), _bi(1, "down", 12.0, 9.0), _bi(2, "up", 12.0, 9.0)]
    zs = _zs(0, bis, 12.0, 9.0)
    assert _check_pz_beichi(bis, [zs], closes=None) == []


def test_qs_skip_when_not_trend() -> None:
    bis = [
        _bi(0, "up", 12.0, 8.0),
        _bi(1, "down", 11.0, 9.0),
        _bi(2, "up", 13.0, 10.0),
        _bi(3, "down", 12.0, 10.0),
    ]
    prev = _zs(0, [bis[0], bis[1], bis[2]], 11.0, 9.0)
    curr = _zs(1, [bis[1], bis[2], bis[3]], 12.0, 10.0)
    # 中枢不满足同向排列（既不同上、也不同下）
    assert _check_qs_beichi(bis, [prev, curr], closes=None) == []


def test_qs_skip_when_missing_lines() -> None:
    bis = [_bi(0, "up", 12.0, 8.0), _bi(1, "down", 12.0, 8.0)]
    prev = _zs(0, [], 10.0, 8.0)
    curr = _zs(1, [], 12.0, 10.0)
    assert _check_qs_beichi(bis, [prev, curr], closes=None) == []


def test_qs_skip_when_exit_out_of_range() -> None:
    # 向上趋势成立，但后一中枢最后一条线之后没有离开笔。
    bis = [_bi(0, "up", 12.0, 8.0), _bi(1, "down", 11.0, 9.0), _bi(2, "up", 13.0, 10.0)]
    prev = _zs(0, [bis[0], bis[1]], 11.0, 9.0)
    curr = _zs(1, [bis[1], bis[2]], 12.0, 10.0)
    assert _check_qs_beichi(bis, [prev, curr], closes=None) == []


def test_qs_skip_when_no_new_high() -> None:
    """向上趋势背驰必须创新高；未创新高时静默跳过。"""
    bis = [
        _bi(0, "up", 10.0, 8.0),
        _bi(1, "down", 10.0, 9.0),
        _bi(2, "up", 12.0, 9.0),
        _bi(3, "down", 12.0, 10.0),
        _bi(4, "up", 12.0, 10.0),
    ]
    prev = _zs(0, [bis[0], bis[1], bis[2]], 10.0, 9.0)
    curr = _zs(1, [bis[2], bis[3], bis[4]], 12.0, 10.0)
    assert _check_qs_beichi(bis, [prev, curr], closes=None) == []


def test_qs_skip_when_no_new_low() -> None:
    """向下趋势背驰必须创新低；未创新低时静默跳过。"""
    bis = [
        _bi(0, "down", 12.0, 10.0),
        _bi(1, "up", 12.0, 11.0),
        _bi(2, "down", 10.0, 9.0),
        _bi(3, "up", 10.0, 11.0),
        _bi(4, "down", 10.0, 9.0),
    ]
    prev = _zs(0, [bis[0], bis[1], bis[2]], 12.0, 10.0)
    curr = _zs(1, [bis[2], bis[3], bis[4]], 10.0, 9.0)
    assert _check_qs_beichi(bis, [prev, curr], closes=None) == []


def test_qs_skip_when_exit_direction_mismatch() -> None:
    """向上趋势背驰：离开段方向与趋势不符时不产出背驰（缠论原文）。"""
    bis = [
        _bi(0, "up", 12.0, 8.0),
        _bi(1, "down", 11.0, 9.0),
        _bi(2, "up", 13.0, 10.0),
        _bi(3, "up", 14.0, 11.0),  # 前一中枢离开段（向上）
        _bi(4, "up", 13.0, 11.0),
        _bi(5, "down", 12.0, 10.0),  # 后一中枢离开段方向不符（向下）
    ]
    prev = _zs(0, [bis[0], bis[1], bis[2]], 10.0, 8.0)
    curr = _zs(1, [bis[2], bis[3], bis[4]], 12.0, 10.0)
    assert _check_qs_beichi(bis, [prev, curr], closes=None) == []
