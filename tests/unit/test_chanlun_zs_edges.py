"""中枢计算边界金标测试（V660）。

锁定中枢区间有效性、重叠比例、关闭条件、质量评分等纯函数边界，
防止后续重构中枢算法时破坏缠论中枢的几何约束。
"""

from __future__ import annotations

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import BI, FX, ZS, CLKline, Direction, FXType
from easy_tdx.chanlun.zs import (
    _calc_zs_quality,
    _is_valid_zs_range,
    _overlap_ratio,
    _should_close_candidate,
)


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


def _zs(lines: list[BI], zg: float, zd: float) -> ZS:
    return ZS(
        lines=lines,
        zg=zg,
        zd=zd,
        gg=max((b.high for b in lines), default=zg),
        dd=min((b.low for b in lines), default=zd),
        index=0,
        done=True,
    )


def test_overlap_ratio_bounds() -> None:
    assert _overlap_ratio(10.0, 9.0, 10.0, 9.0) == 1.0
    assert _overlap_ratio(10.0, 9.0, 12.0, 11.0) == 0.0
    assert _overlap_ratio(10.0, 9.0, 5.0, 4.0) == 0.0
    # 退化区间（high <= low）返回 0，避免除零
    assert _overlap_ratio(10.0, 9.0, 8.0, 8.0) == 0.0


def test_is_valid_zs_range() -> None:
    assert _is_valid_zs_range(10.0, 9.0, 11.0, 8.0)
    assert not _is_valid_zs_range(9.0, 10.0, 11.0, 8.0)  # zg <= zd
    assert not _is_valid_zs_range(10.0, 9.0, 9.5, 8.0)  # gg < zg
    assert not _is_valid_zs_range(10.0, 9.0, 11.0, 9.5)  # dd > zd
    # 宽度过窄（0.05% 以下）不构成有效中枢
    assert not _is_valid_zs_range(100.0, 99.99, 101.0, 98.0)


def test_should_close_candidate() -> None:
    config = ChanlunConfig(zs_min_lines=3)
    candidate = [
        _bi(0, "up", 12.0, 8.0),
        _bi(1, "down", 11.0, 9.0),
        _bi(2, "up", 12.0, 10.0),
    ]
    zg = 11.0
    zd = 10.0

    # 候选不足 min_lines 时不关闭
    assert not _should_close_candidate(candidate[:2], zg, zd, candidate[2], config)
    # 新笔与候选区间仍有重叠时不关闭
    assert not _should_close_candidate(candidate, zg, zd, _bi(3, "up", 11.0, 10.0), config)
    # 完全脱离候选区间时关闭
    assert _should_close_candidate(candidate, zg, zd, _bi(3, "up", 14.0, 13.0), config)


def test_calc_zs_quality_grades() -> None:
    strong = _zs(
        [_bi(i, "up" if i % 2 == 0 else "down", 12.0 + i * 0.1, 11.0 + i * 0.1) for i in range(7)],
        12.2,
        11.2,
    )
    quality = _calc_zs_quality(strong, strong.lines, 0)
    assert quality["grade"] == "strong"
    assert 0.0 <= quality["quality_score"] <= 1.0

    weak = _zs([_bi(0, "up", 10.0, 9.0)], 10.0, 9.0)
    weak_quality = _calc_zs_quality(weak, weak.lines, 0)
    assert weak_quality["grade"] == "weak"
    assert weak_quality["quality_score"] == 0.3
