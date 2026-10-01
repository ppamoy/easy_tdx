"""valid_fractals 独立性 & 交替性金标测试。

缠论原文硬约束：**相邻分型不得共用 K 线**（至少隔 1 根独立K线），且分型序列
必须顶底严格交替。这两个性质原本由 find_bis 的 gap 规则间接保证，但该保证依赖
bi_type——legacy 的 simple 口径只要顶底交替就成笔，甚至允许一笔起止点同类，
会让笔端点分型集合退化成含大量违规的原始分型。

为此 analyser._enforce_fx_independence 在序列化前显式收紧一次。本文件锁死
「不管用哪种笔口径，valid_fractals 都必须满足这两条性质」。

背景：用户报告 000001 日线 2024-12-17(底) / 12-18(顶) / 12-19(底) 连续三天被
标成分型——这三个分型两两共用 2 根缠论K线，违反上述约束。
"""

from __future__ import annotations

import pytest

from easy_tdx.chanlun.analyser import _enforce_fx_independence
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import FX, CLKline, FXType


def _ck(index: int, high: float, low: float) -> CLKline:
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


def _fx(index: int, fx_type: FXType, val: float) -> FX:
    """构造一个占 [index-1, index, index+1] 三根缠论K线的分型。"""
    mid = _ck(index, val, val)
    return FX(
        fx_type=fx_type,
        k=mid,
        klines=[_ck(index - 1, val, val), mid, _ck(index + 1, val, val)],
        val=val,
        index=index,
        done=True,
        bar_index=index,
    )


def _indep_gaps_ok(fxs: list[FX], min_gap: int) -> bool:
    for a, b in zip(fxs, fxs[1:]):
        gap = b.klines[0].index - a.klines[-1].index + 1
        if gap < min_gap:
            return False
    return True


@pytest.mark.parametrize("bi_type", ["new", "old", "simple"])
def test_valid_fractals_alternate_and_independent(bi_type: str) -> None:
    """任何笔口径下，输出都必须顶底交替且不共用K线。

    输入刻意模拟用户报告的病态情形：底-顶-底 挤在连续三根K线上。
    """
    min_gap = 5 if bi_type == "old" else 3
    # 三个两两共用的分型（index 10/11/12，各占 ±1 根）
    dirty = [
        _fx(10, FXType.DI, 8.6),
        _fx(11, FXType.DING, 9.0),
        _fx(12, FXType.DI, 8.4),
    ]
    out = _enforce_fx_independence(dirty, ChanlunConfig(bi_type=bi_type))

    # 相邻不得同类
    assert all(a.fx_type != b.fx_type for a, b in zip(out, out[1:])), "存在相邻同类型分型"
    # 相邻不得共用K线
    assert _indep_gaps_ok(out, min_gap), "存在共用K线的相邻分型"
    assert len(out) >= 1


@pytest.mark.parametrize("bi_type", ["new", "old", "simple"])
def test_simple_bitype_does_not_degrade_to_raw_list(bi_type: str) -> None:
    """simple 口径不得让结果退化成「全部保留」（这是修复前的行为）。"""
    n = 30
    # 交替但密集：index 0,1,2,... 各占 ±1 → 相邻恒共用K线
    raw = [_fx(i, FXType.DING if i % 2 == 0 else FXType.DI, 10.0 + i) for i in range(n)]
    out = _enforce_fx_independence(raw, ChanlunConfig(bi_type=bi_type))
    min_gap = 5 if bi_type == "old" else 3
    assert _indep_gaps_ok(out, min_gap)
    # 必须真的筛掉一部分（间隔 min_gap 意味着最多保留约 n/min_gap 个）
    assert len(out) < len(raw), f"{bi_type} 口径下未过滤任何分型"


def test_missing_klines_is_rejected() -> None:
    """缺 klines 信息时无法确定间距，应视为不达标而非放行。"""
    a = _fx(10, FXType.DI, 8.0)
    b = _fx(40, FXType.DING, 9.0)
    b.klines = []  # 损坏
    out = _enforce_fx_independence([a, b], ChanlunConfig())
    assert out == [a]


@pytest.mark.parametrize("bi_type", ["new", "old"])
def test_new_and_old_bitype_keep_original_counts(bi_type: str) -> None:
    """对照组：new/old 口径下本就合规的输入必须原样保留，不被误伤。"""
    min_gap = 5 if bi_type == "old" else 3
    step = 10  # 远大于两种口径的要求
    clean = [_fx(i * step, FXType.DING if i % 2 == 0 else FXType.DI, 10.0 + i) for i in range(6)]
    out = _enforce_fx_independence(clean, ChanlunConfig(bi_type=bi_type))
    assert len(out) == len(clean), "合规输入被误删"
    assert _indep_gaps_ok(out, min_gap)


def test_extreme_value_wins_when_too_close() -> None:
    """间距不足时保留极值更强者：顶取更高、底取更低。"""
    # 两个同为 di 且共用K线 → 应保留低点更低的那个
    weak = _fx(10, FXType.DI, 8.5)
    strong = _fx(11, FXType.DI, 8.1)
    out = _enforce_fx_independence([weak, strong], ChanlunConfig())
    assert len(out) == 1
    assert out[0].val == 8.1

    # 两个同为 ding 且共用K线 → 应保留高点更高的那个
    weak_d = _fx(10, FXType.DING, 9.0)
    strong_d = _fx(11, FXType.DING, 9.4)
    out2 = _enforce_fx_independence([weak_d, strong_d], ChanlunConfig())
    assert out2[0].val == 9.4


def test_duplicate_entries_deduped() -> None:
    """重复项（同 bar_index 同类型）去重，避免图上重复绘制。"""
    a = _fx(10, FXType.DI, 8.0)
    dup = _fx(10, FXType.DI, 8.0)
    out = _enforce_fx_independence([a, dup], ChanlunConfig())
    assert len(out) == 1


def test_empty_and_single_input() -> None:
    assert _enforce_fx_independence([], ChanlunConfig()) == []
    one = _fx(5, FXType.DI, 8.0)
    assert _enforce_fx_independence([one], ChanlunConfig()) == [one]
