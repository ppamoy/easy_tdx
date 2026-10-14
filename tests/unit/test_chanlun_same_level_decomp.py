"""第38课「走势类型连接的同级别分解」行为级测试。

判据只有 docs/缠论108课/38.走势类型连接的同级别分解.md 原文，逐字核对：

  1. 「在这种同级别的分解中，是不需要中枢延伸或扩展的概念的」
  2. 「只要5分钟级别的三段上下上或下上下类型有价格区间的重合就构成中枢」
  3. 「如果这5分钟次级别延伸出6段，那么就当成两个30分钟盘整类型的连接，
       在这种分解中，是允许盘整+盘整情况的」
  4. 「永远只针对一个正在完成着的同级别中枢，一旦该中枢完成，
       就继续关注下一个同级别中枢」

纪律（AGENTS.md §1/§4）：断言**真实行为**，不用存在性断言冒充；
每个用例同时给正例与反例（对照组），证明分解口径真的与非同级别分解不同。
"""

from __future__ import annotations

import pytest

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.same_level import (
    _overlap,
    TrendSegment,
    decompose_same_level,
    decomposition_diff,
)
from easy_tdx.chanlun.types import BI, Direction, FX, FXType
from easy_tdx.chanlun.zs import find_zss


def _k(i: int, h: float, l: float) -> object:
    """造一个最小缠论 K 线（同级别分解只用到 date/high/low）。"""
    from datetime import datetime, timedelta

    from easy_tdx.chanlun.types import CLKline

    base = datetime(2025, 1, 1)
    return CLKline(
        k_index=i,
        date=base + timedelta(days=i),
        open=(h + l) / 2,
        close=(h + l) / 2,
        high=h,
        low=l,
        amount=0.0,
        index=i,
    )


def _fx(i: int, val: float, t: FXType) -> FX:
    k = _k(i, val + 0.01, val - 0.01)
    return FX(fx_type=t, k=k, klines=[k], val=val, index=i, done=True)


def _bi(i: int, a: float, b: float, up: bool) -> BI:
    """造一笔：up=True 时从低点 a 涨到高点 b；否则从高点 a 跌到低点 b。"""
    hi, lo = (b, a) if up else (a, b)
    return BI(
        start=_fx(i * 2, a, FXType.DI if up else FXType.DING),
        end=_fx(i * 2 + 1, b, FXType.DING if up else FXType.DI),
        direction=Direction.UP if up else Direction.DOWN,
        index=i,
        high=hi,
        low=lo,
    )


def _alt(n: int, hi: float, lo: float, first_up: bool = False) -> list[BI]:
    """交替方向笔序列，每笔都在 [lo, hi] 之间往返（保证互相重叠）。"""
    out: list[BI] = []
    for i in range(n):
        up = (i % 2 == 1) if first_up else (i % 2 == 0)
        # up 笔：lo → hi；down 笔：hi → lo
        out.append(_bi(i, lo if up else hi, hi if up else lo, up))
    return out


# ── 正例：三段重合 ⇒ 一个中枢 ─────────────────────────────────────────────


def test_three_overlapping_segments_form_one_zs() -> None:
    """原文第38课：三段上下上/下上下有价格区间的重合就构成中枢。"""
    bis = _alt(3, 11.0, 10.0, first_up=False)
    segs = decompose_same_level(bis, ChanlunConfig())

    assert len(segs) == 1
    assert segs[0].n_segments == 3
    assert len(segs[0].zss) == 1
    zs = segs[0].zss[0]
    assert zs.zd == 10.0 and zs.zg == 11.0  # 三段完全重合 ⇒ 全域
    assert segs[0].is_panzheng, "只有一个中枢 ⇒ 原文第17课的盘整"


def test_two_segments_cannot_form_zs() -> None:
    """反例：只有 2 段 ⇒ 构不成中枢（原文要求三段）。"""
    bis = _alt(2, 11.0, 10.0)
    segs = decompose_same_level(bis, ChanlunConfig())
    assert all(len(s.zss) == 0 for s in segs)
    assert segs[0].kind == "none"


# ── 核心：不定义中枢延伸 ⇒ 6 段当两个盘整连接 ────────────────────────────


def test_no_zs_extension_six_segments_become_two_panzheng() -> None:
    """原文第38课核心句：「如果这5分钟次级别延伸出6段，那么就当成两个30分钟
    盘整类型的连接，在这种分解中，是允许盘整+盘整情况的」。

    构造 6 段全部互相重叠的序列。非同级别分解（find_zss）会把它们全并成
    一个中枢（延伸）；同级别分解必须切成两个 3 段盘整。
    """
    bis = _alt(6, 11.0, 10.0, first_up=False)
    segs = decompose_same_level(bis, ChanlunConfig())

    # 6 段 / 3 段一个中枢 ⇒ 两个盘整段
    assert len(segs) == 2, f"应切成 2 段，实际 {len(segs)}: {segs}"
    for s in segs:
        assert s.n_segments == 3, f"每段应 3 段，实际 {s.n_segments}"
        assert len(s.zss) == 1
        assert s.is_panzheng, "每段只含 1 个中枢 ⇒ 盘整（原文第17课）"
    assert not segs[0].is_trend and not segs[1].is_trend

    # 「盘整 + 盘整」是原文明确允许的连接
    assert segs[0].is_panzheng and segs[1].is_panzheng

    # ── 对照组（AGENTS.md §4：必须证明与既有口径不同）──────────────────
    # 非同级别分解：允许延伸 ⇒ 一个中枢吃掉全部 6 段
    other = find_zss(bis, ChanlunConfig())
    assert len(other) == 1, f"非同级别分解应并成 1 个中枢，实际 {len(other)}"
    assert other[0].line_count == 6, f"该中枢应含 6 段，实际 {other[0].line_count}"
    # 同级别分解：每个中枢最多 3 段（原文「不需要中枢延伸」）
    assert max(len(z.lines) for s in segs for z in s.zss) == 3


def test_extension_free_decomposition_never_exceeds_three_segments() -> None:
    """原文「不需要中枢延伸或扩展的概念」⇒ 任何中枢都不超过 3 段。

    用真实日线 fixture 跑 12 笔：非同级别分解最长 5 段，同级别分解必须全部 3 段。
    """
    import json
    from pathlib import Path

    import pandas as pd

    from easy_tdx.chanlun.analyser import ChanlunAnalyser

    fx_path = Path(__file__).parents[1] / "fixtures" / "chanlun_000001_daily.json"
    rows = json.loads(fx_path.read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    res = ChanlunAnalyser(code="SZ000001", frequency="daily").process_klines(df)

    segs = decompose_same_level(res.bis, ChanlunConfig())
    assert segs, "至少应分解出若干段"
    for s in segs:
        for z in s.zss:
            assert len(z.lines) <= 3, (
                f"同级别分解下中枢不应超过 3 段（原文第38课不需要延伸），"
                f"实际 {len(z.lines)} 段: {z}"
            )

    # 对照组：非同级别分解在同一序列上确实有 >3 段的中枢
    other = find_zss(res.bis, ChanlunConfig())
    assert any(z.line_count > 3 for z in other), (
        "对照组失效：非同级别分解应出现 >3 段的中枢，否则无法证明口径差异"
    )


def test_decomposition_covers_every_line_exactly_once() -> None:
    """原文要求「分解具有唯一性」⇒ 不漏不重、顺序连续。"""
    bis = _alt(9, 11.0, 10.0, first_up=False)
    segs = decompose_same_level(bis, ChanlunConfig())

    covered = [b.index for s in segs for b in s.lines]
    assert covered == [b.index for b in bis], "分解必须首尾相接且顺序一致"
    assert len(set(covered)) == len(covered), "同一笔不得被两个段同时包含"


def test_non_overlapping_segments_do_not_form_zs() -> None:
    """反例：三段互不重叠 ⇒ 不构成中枢，各自独立成段。

    构造：
      bi0 down: high=12.0 low=10.0   （区间 [10,12]）
      bi1 up  : high=20.0 low=18.0   （区间 [18,20]，与上一段无重合）
      bi2 down: high=30.0 low=28.0   （区间 [28,30]，与上一段无重合）
    任取相邻两段的高低区间都不相交 ⇒ 原文「有价格区间的重合」不成立。
    """
    bis = [
        _bi(0, 12.0, 10.0, up=False),
        _bi(1, 18.0, 20.0, up=True),
        _bi(2, 30.0, 28.0, up=False),
    ]
    # 自证构造有效：相邻两段确实不重叠
    for a, b in zip(bis, bis[1:]):
        assert _overlap(a, b) <= 0, "对照组失效：构造出的相邻段竟然有重合"

    segs = decompose_same_level(bis, ChanlunConfig())
    assert all(len(s.zss) == 0 for s in segs), "无价格重合 ⇒ 无中枢"
    assert len(segs) == 3


# ── 「一旦该中枢完成，就继续关注下一个同级别中枢」──────────────────────


def test_after_zs_completes_next_zs_starts_fresh() -> None:
    """原文：「永远只针对一个正在完成着的同级别中枢，一旦该中枢完成，
    就继续关注下一个同级别中枢」。

    两组三段各自成中枢 ⇒ 两个段，且第二段的中枢不是第一段的延伸。
    """
    bis = _alt(6, 11.0, 10.0, first_up=False)
    segs = decompose_same_level(bis, ChanlunConfig())
    assert len(segs) == 2
    z0, z1 = segs[0].zss[0], segs[1].zss[0]
    # 两中枢的构成笔完全不同（不是同一中枢的延伸）
    assert not (set(id(x) for x in z0.lines) & set(id(x) for x in z1.lines))
    assert z0.index != z1.index


# ── 进入段/离开段（原文第20课）───────────────────────────────────────────


def test_zs_records_enter_and_exit_segments() -> None:
    """中枢应记录进入段与离开段（原文第20课：中枢 = 进入段 + 3段重叠 + 离开段）。"""
    bis = _alt(5, 11.0, 10.0, first_up=False)
    segs = decompose_same_level(bis, ChanlunConfig())
    zs = segs[0].zss[0]
    assert zs.enter_bi is None, "序列第一段之前没有进入段"
    assert zs.exit_bi is not None, "中枢之后应有离开段"


# ── 分解口径差异指标（供守门脚本复用）────────────────────────────────────


def test_diff_metrics_show_real_difference() -> None:
    """对照指标必须真的体现两种口径的差异，不能恒等（防"看起来测了"）。"""
    bis = _alt(6, 11.0, 10.0, first_up=False)
    d = decomposition_diff(bis, ChanlunConfig())
    sl, nsl = d["same_level"], d["non_same_level"]
    assert sl["max_zs_segments"] == 3
    assert nsl["max_zs_segments"] == 6, "非同级别分解应延伸成 6 段"
    assert sl["panzheng_plus_panzheng"] == 1
    assert nsl["panzheng_plus_panzheng"] == 0, "非同级别分解不产出盘整+盘整连接"
    assert sl["n_segments"] > 0 and nsl["n_segments"] == 0


def test_empty_and_short_inputs() -> None:
    """边界：空序列与不足 3 段。"""
    assert decompose_same_level([], ChanlunConfig()) == []
    for n in (1, 2):
        segs = decompose_same_level(_alt(n, 11.0, 10.0), ChanlunConfig())
        assert segs and all(len(s.zss) == 0 for s in segs)


def test_trend_segment_helpers() -> None:
    """TrendSegment 的盘整/趋势判定对应原文第17课定义。"""
    bis = _alt(6, 11.0, 10.0, first_up=False)
    segs = decompose_same_level(bis, ChanlunConfig())
    for s in segs:
        assert isinstance(s, TrendSegment)
        assert s.has_zs
        assert s.is_panzheng and not s.is_trend, "单中枢 ⇒ 盘整，不是趋势"
    empty = TrendSegment(lines=[], zss=[])
    assert empty.end_val == 0.0 and empty.n_segments == 0
