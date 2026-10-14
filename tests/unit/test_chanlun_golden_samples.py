"""缠论金标样本回归（V602）。

用「手工标注正确结果」的确定性样本锁定笔/线段/背驰的关键行为，
防止后续改动把模型改坏。样本聚焦于可精确预测的纯函数与单元行为。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from easy_tdx.chanlun.beichi import _check_pz_beichi, check_bi_beichi
from easy_tdx.chanlun.bi import find_bis
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.fractal import find_fractals
from easy_tdx.chanlun.kline_merge import merge_klines
from easy_tdx.chanlun.mmd import (
    _find_first_type_mmds,
    _has_meaningful_pullback,
    _has_meaningful_rebound,
    _reference_zs_for_bi,
)
from easy_tdx.chanlun.mmd_conditions import _calc_trend_strength
from easy_tdx.chanlun.types import (
    BI,
    FX,
    MMD,
    ZS,
    BCType,
    CLKline,
    Direction,
    FXType,
    Kline,
    MMDType,
)
from easy_tdx.chanlun.xd import (
    _merge_feature_sequence,
    _merged_feature_fx,
    _valid_segment_end,
    find_xds,
)
from easy_tdx.chanlun.zs import find_zss


def _mk_bi(
    index: int,
    direction: str,
    high: float,
    low: float,
    start_val: float = 0.0,
    end_val: float = 0.0,
) -> BI:
    start_fx = FX(
        fx_type=FXType.DI if direction == "up" else FXType.DING,
        k=type("CLK", (), {"k_index": index * 10, "index": index, "date": datetime.now()})(),
        klines=[],
        val=start_val,
        index=index,
        done=True,
    )
    end_fx = FX(
        fx_type=FXType.DING if direction == "up" else FXType.DI,
        k=type("CLK", (), {"k_index": index * 10 + 5, "index": index, "date": datetime.now()})(),
        klines=[],
        val=end_val,
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


def _mk_clkline(index: int, high: float, low: float) -> CLKline:
    return CLKline(
        k_index=index,
        date=datetime.now(),
        open=low,
        close=high,
        high=high,
        low=low,
        amount=0.0,
        index=index,
        merged_count=1,
        direction="",
        klines=[],
        high_k_index=index,
        low_k_index=index,
    )


def _mk_kline(index: int, high: float, low: float) -> Kline:
    return Kline(
        index=index,
        date=datetime.now(),
        open=low,
        close=high,
        high=high,
        low=low,
        amount=1000.0,
    )


# ── K线包含处理金标 ──────────────────────────────────────────────────


def test_merge_klines_up_inclusion_high_high() -> None:
    klines = [_mk_kline(0, 10.0, 8.0), _mk_kline(1, 12.0, 9.0), _mk_kline(2, 11.0, 9.5)]
    merged = merge_klines(klines)
    assert len(merged) == 2
    assert merged[0].high == 10.0 and merged[0].low == 8.0
    # 向上合并取高高：high=max(12,11)=12，low=max(9,9.5)=9.5
    assert merged[1].high == 12.0
    assert merged[1].low == 9.5
    assert merged[1].merged_count == 2


def test_merge_klines_down_inclusion_low_low() -> None:
    klines = [_mk_kline(0, 10.0, 8.0), _mk_kline(1, 9.0, 7.0), _mk_kline(2, 8.5, 7.5)]
    merged = merge_klines(klines)
    assert len(merged) == 2
    # 向下合并取低低：high=min(9,8.5)=8.5，low=min(7,7.5)=7
    assert merged[1].high == 8.5
    assert merged[1].low == 7.0
    assert merged[1].merged_count == 2


def test_fractal_dual_dimension_requires_high_and_low() -> None:
    """缠论原文：顶分型要求中间K线高点最高且低点也最高（双维度）。"""
    cklines = [
        _mk_clkline(0, 10.0, 9.0),
        _mk_clkline(1, 12.0, 7.0),  # 高点最高但低点最低 → 不是顶分型
        _mk_clkline(2, 11.0, 8.0),
    ]
    fxs = find_fractals(cklines, ChanlunConfig())
    assert len(fxs) == 0


# ── 分型识别金标 ──────────────────────────────────────────────────────


def test_fractal_golden() -> None:
    """一段明显顶分型 + 底分型的序列，应恰好识别出 1 个顶分型 + 1 个底分型。"""
    cklines = [
        _mk_clkline(0, 10.0, 8.0),
        _mk_clkline(1, 12.0, 9.0),
        _mk_clkline(2, 14.0, 10.0),  # 顶分型中间
        _mk_clkline(3, 13.0, 9.0),
        _mk_clkline(4, 12.0, 8.0),  # 底分型中间
        _mk_clkline(5, 13.0, 9.0),  # 高点须高于中间K线高点（双维度）
    ]
    fxs = find_fractals(cklines, ChanlunConfig())
    assert len(fxs) == 2
    assert fxs[0].fx_type == FXType.DING
    assert fxs[0].val == 14.0
    assert fxs[0].bar_index == 2
    assert fxs[1].fx_type == FXType.DI
    assert fxs[1].val == 8.0
    assert fxs[1].bar_index == 4


# ── 特征序列包含处理金标 ──────────────────────────────────────────────


def test_merge_feature_sequence_no_inclusion() -> None:
    features = [(0, _mk_bi(0, "down", 12, 10)), (1, _mk_bi(1, "down", 11, 9))]
    merged = _merge_feature_sequence(features)
    assert len(merged) == 2


def test_merge_feature_sequence_inclusion_high_high() -> None:
    # F1 [10,12] 包含 F2 [10.5,11.5] → 向上合并取高高
    features = [(0, _mk_bi(0, "down", 12, 10)), (1, _mk_bi(1, "down", 11.5, 10.5))]
    merged = _merge_feature_sequence(features)
    assert len(merged) == 1
    assert merged[0][1] == 12.0  # 高高
    assert merged[0][2] == 10.5  # 低取较高


def test_merge_feature_sequence_down_inclusion_low_low() -> None:
    """缠论特征序列包含处理：向下特征序列取「低低」。"""
    f1 = _mk_bi(0, "down", 14.0, 12.0)
    f2 = _mk_bi(1, "down", 12.0, 10.0)
    f3 = _mk_bi(2, "down", 11.5, 11.0)  # 被 f2 包含
    merged = _merge_feature_sequence([(0, f1), (1, f2), (2, f3)])
    assert len(merged) == 2
    # 向下特征序列取低低：high=min(12,11.5)、low=min(10,11)
    assert merged[1][1] == 11.5
    assert merged[1][2] == 10.0


# ── 特征序列分型金标 ──────────────────────────────────────────────────


def test_merged_feature_fx_up_top() -> None:
    merged = [([0], 12.0, 10.0), ([1], 14.0, 11.0), ([2], 13.0, 9.0)]
    assert _merged_feature_fx(merged, Direction.UP) is True


def test_merged_feature_fx_down_bottom() -> None:
    merged = [([0], 20.0, 12.0), ([1], 18.0, 8.0), ([2], 19.0, 10.0)]
    assert _merged_feature_fx(merged, Direction.DOWN) is True


def _mk_fx(fx_type: FXType, val: float, index: int, bar_index: int) -> FX:
    k = CLKline(
        k_index=index * 10,
        date=datetime.now(),
        open=val,
        close=val,
        high=val,
        low=val,
        amount=0.0,
        index=index,
        merged_count=1,
        direction="",
        klines=[],
        high_k_index=index * 10,
        low_k_index=index * 10,
    )
    return FX(
        fx_type=fx_type,
        k=k,
        klines=[k],
        val=val,
        index=index,
        done=True,
        bar_index=bar_index,
    )


def _mk_fx3(fx_type: FXType, val: float, kidx: list[int]) -> FX:
    klines = []
    for ki in kidx:
        klines.append(
            CLKline(
                k_index=ki,
                date=datetime.now(),
                open=val,
                close=val,
                high=val,
                low=val,
                amount=0.0,
                index=ki,
                merged_count=1,
                direction="",
                klines=[],
                high_k_index=ki,
                low_k_index=ki,
            )
        )
    return FX(
        fx_type=fx_type,
        k=klines[1],
        klines=klines,
        val=val,
        index=0,
        done=True,
        bar_index=kidx[1],
    )


def test_find_bis_new_bi_requires_independent_kline() -> None:
    """缠论新笔：顶底之间至少 1 根独立K线。顶[0,1,2] 底[4,5,6] → 成立。"""
    fxs = [
        _mk_fx3(FXType.DING, 20.0, [0, 1, 2]),
        _mk_fx3(FXType.DI, 10.0, [4, 5, 6]),
    ]
    bis = find_bis(fxs, ChanlunConfig(bi_type="new"))
    assert len(bis) == 1
    assert bis[0].direction == Direction.DOWN


def test_find_bis_new_bi_rejects_adjacent_fractals() -> None:
    """缠论新笔：顶[0,1,2] 底[3,4,5] 无独立K线 → 不成立。"""
    fxs = [
        _mk_fx3(FXType.DING, 20.0, [0, 1, 2]),
        _mk_fx3(FXType.DI, 10.0, [3, 4, 5]),
    ]
    bis = find_bis(fxs, ChanlunConfig(bi_type="new"))
    assert len(bis) == 0


# ── 笔计算金标 ────────────────────────────────────────────────────────


def test_find_bis_simple_golden() -> None:
    fxs = [
        _mk_fx(FXType.DI, 10.0, 0, 0),
        _mk_fx(FXType.DING, 15.0, 1, 1),
        _mk_fx(FXType.DI, 12.0, 2, 2),
        _mk_fx(FXType.DING, 18.0, 3, 3),
        _mk_fx(FXType.DI, 11.0, 4, 4),
    ]
    bis = find_bis(fxs, ChanlunConfig(bi_type="simple"))
    assert len(bis) == 4
    assert bis[0].direction == Direction.UP
    assert bis[0].start.val == 10.0 and bis[0].end.val == 15.0
    assert bis[1].direction == Direction.DOWN and bis[1].end.val == 12.0
    assert bis[2].direction == Direction.UP and bis[2].end.val == 18.0
    assert bis[3].direction == Direction.DOWN and bis[3].end.val == 11.0


def test_find_bis_more_extreme_top_replaces() -> None:
    # 更极端的顶分型应替换并延伸上一笔终点
    fxs = [
        _mk_fx(FXType.DI, 10.0, 0, 0),
        _mk_fx(FXType.DING, 15.0, 1, 1),
        _mk_fx(FXType.DING, 20.0, 2, 2),
        _mk_fx(FXType.DI, 13.0, 3, 3),
    ]
    bis = find_bis(fxs, ChanlunConfig(bi_type="simple"))
    assert len(bis) == 2
    assert bis[0].direction == Direction.UP
    assert bis[0].end.val == 20.0  # 更极端顶替换
    assert bis[1].direction == Direction.DOWN
    assert bis[1].end.val == 13.0


def test_mmd_1st_dedup_config_default() -> None:
    """1买/1卖 去重启发式默认开启，可关闭以得到严格原文（不去重）模式。"""
    assert ChanlunConfig().mmd_1st_dedup is True
    assert ChanlunConfig(mmd_1st_dedup=False).mmd_1st_dedup is False


# ── 1买/1卖 结构去重启发式金标（工程启发式，非缠论原文）────────────


def test_has_meaningful_rebound_3pct() -> None:
    assert _has_meaningful_rebound(103.0, 100.0)  # 3% 反弹 → True
    assert not _has_meaningful_rebound(102.0, 100.0)  # 2% → False
    assert not _has_meaningful_rebound(99.0, 100.0)  # 未反弹 → False
    assert _has_meaningful_rebound(100.0, None)  # 首次无前值 → True


def test_has_meaningful_pullback_3pct() -> None:
    assert _has_meaningful_pullback(97.0, 100.0)  # 3% 回落 → True
    assert not _has_meaningful_pullback(98.0, 100.0)  # 2% → False
    assert not _has_meaningful_pullback(101.0, 100.0)  # 未回落 → False
    assert _has_meaningful_pullback(100.0, None)  # 首次无前值 → True


# ── 1买/1卖 趋势强度金标 ────────────────────────────────────────────


def _mk_zs_val(zg: float, zd: float) -> ZS:
    return ZS(
        lines=[],
        zg=zg,
        zd=zd,
        gg=zg + 1.0,
        dd=zd - 1.0,
        direction="",
        index=0,
        done=True,
        start=None,
        end=None,
    )


def test_trend_strength_requires_two_same_direction_zs() -> None:
    """缠论趋势背驰需要趋势（至少两个同向中枢）；不同向/单中枢趋势强度为 0。"""
    # 两个同向（都在下降）→ >0
    assert _calc_trend_strength([_mk_zs_val(10.0, 8.0), _mk_zs_val(8.0, 6.0)]) > 0
    # 不同向（一升一降）→ 0
    assert _calc_trend_strength([_mk_zs_val(10.0, 8.0), _mk_zs_val(12.0, 7.0)]) == 0
    # 单中枢 → 0
    assert _calc_trend_strength([_mk_zs_val(10.0, 8.0)]) == 0


# ── 1买/1卖 同期参考中枢金标（无未来函数）──────────────────────────


def _mk_fx_ref(kidx: int) -> FX:
    k = CLKline(
        k_index=kidx,
        date=datetime.now(),
        open=1.0,
        close=1.0,
        high=1.0,
        low=1.0,
        amount=0.0,
        index=kidx,
        merged_count=1,
        direction="",
        klines=[],
        high_k_index=kidx,
        low_k_index=kidx,
    )
    return FX(fx_type=FXType.DI, k=k, klines=[], val=1.0, index=0, done=True, bar_index=kidx)


def test_reference_zs_point_in_time_no_future() -> None:
    """一买/一卖只能参考「笔发生前已结束」的中枢，不能偷看未来中枢。"""
    zs0 = ZS(
        lines=[],
        zg=10.0,
        zd=5.0,
        gg=11.0,
        dd=4.0,
        direction="",
        index=0,
        done=True,
        start=None,
        end=_mk_fx_ref(10),
    )
    zs1 = ZS(
        lines=[],
        zg=9.0,
        zd=4.0,
        gg=10.0,
        dd=3.0,
        direction="",
        index=1,
        done=True,
        start=None,
        end=_mk_fx_ref(20),
    )
    bi = BI(
        start=_mk_fx_ref(15),
        end=_mk_fx_ref(25),
        direction=Direction.DOWN,
        index=0,
        high=12.0,
        low=8.0,
    )
    ref = _reference_zs_for_bi([zs0, zs1], bi)
    assert ref is zs0  # 只取 end=10 < 笔起点15 的中枢，不取未来 zs1


# ── 中枢计算金标 ─────────────────────────────────────────────────────


def test_find_zss_golden() -> None:
    """四笔重叠形成中枢、离开笔关闭中枢：应得到 1 个中枢。

    V850 口径修正（第20课 A/C 口径，原文优先）：
        第20课：「特别地，再定义`ZG=min(g1、g2)`, `ZD=max(d1、d2)`」
        + 「A、C段，其方向与中枢形成的方向是一致的……
           以后都把这些与中枢方向一致的次级别走势类型称为`Z走势段`」
        ⇒ Z走势段只含 A(笔0)、C(笔2)，B(笔1) 按定义**不是** Z走势段。
        ⇒ zg = min(笔0.high, 笔2.high) = min(12, 12) = 12
           zd = max(笔0.low,  笔2.low)  = max( 8,  8) = 8
        （旧断言 zg==11 是第18课三端口径 min(12,11,12)，已按第20课修正）
    """
    bis = [
        _mk_bi(0, "up", 12.0, 8.0),
        _mk_bi(1, "down", 11.0, 9.0),
        _mk_bi(2, "up", 12.0, 8.0),
        _mk_bi(3, "down", 11.0, 9.0),
        _mk_bi(4, "up", 20.0, 15.0),  # 离开中枢，触发关闭
    ]
    zss = find_zss(bis, ChanlunConfig())
    assert len(zss) == 1
    zs = zss[0]
    assert zs.line_count == 4
    # V850：第20课 A/C 口径 —— 只取笔0、笔2，B 段（笔1）不参与
    assert zs.zg == 12.0  # min(g1,g2) = min(笔0.high, 笔2.high) = min(12,12)
    assert zs.zd == 8.0  # max(d1,d2) = max(笔0.low,  笔2.low)  = max( 8, 8)
    assert zs.gg == 12.0
    assert zs.dd == 8.0
    assert zs.done is True


# ── 线段特征序列缺口 + 笔破坏确认金标（缠论 77 课）──────────────────


def _gap_bis(f4_low: float):
    return [
        _mk_bi(0, "up", 12.0, 9.0, start_val=10.0, end_val=12.0),
        _mk_bi(1, "down", 12.0, 11.0, start_val=12.0, end_val=11.0),  # F1 [11,12]
        _mk_bi(2, "up", 15.0, 10.0, start_val=11.0, end_val=15.0),
        _mk_bi(3, "down", 15.0, 13.0, start_val=15.0, end_val=13.0),  # F2 [13,15] 与 F1 有缺口
        _mk_bi(4, "up", 14.0, 12.0, start_val=13.0, end_val=14.0),
        _mk_bi(5, "down", 14.0, 12.0, start_val=14.0, end_val=12.0),  # F3 [12,14]
        _mk_bi(6, "up", 13.0, 11.0, start_val=12.0, end_val=13.0),
        _mk_bi(7, "down", 13.0, f4_low, start_val=13.0, end_val=10.0),  # F4
    ]


def test_find_xds_gap_bi_destruction_confirmed() -> None:
    """特征序列有缺口 + 第4元素跌破顶分型最低点 → 线段在顶分型处结束（2 段）。"""
    xds = find_xds(_gap_bis(10.0), ChanlunConfig())
    assert len(xds) == 2
    assert xds[0].direction == Direction.UP
    assert xds[0].start.val == 10.0
    assert xds[0].end.val == 15.0
    assert xds[1].direction == Direction.DOWN


def test_find_xds_gap_no_confirmation_continues() -> None:
    """特征序列有缺口但第4元素不跌破 → 线段继续，收尾取最后一个同向笔端点。"""
    # V725（line-segment-original-fidelity「收尾不换取端点」）：收尾禁止 max/min
    # 换出端点。旧实现从序列中挑 max(end.val)=15（bi2 的端点，早已被后续走势
    # 离开），违反「最后已完成且方向一致的同向笔分型」；现取最后一个同向笔
    # bi6 的端点 13.0。
    xds = find_xds(_gap_bis(12.0), ChanlunConfig())
    assert len(xds) == 1
    assert xds[0].direction == Direction.UP
    assert xds[0].end.val == 13.0


# ── 盘整背驰语义金标 ─────────────────────────────────────────────────


def _mk_zs(lines) -> ZS:
    return ZS(lines=lines, zg=17.0, zd=13.0, gg=18.0, dd=12.0, direction="", index=0, done=True)


def test_pz_beichi_bounds_no_crash_when_zs_at_end() -> None:
    """中枢最后一笔是最后一笔时，离开笔越界 → 不崩溃且不产出背驰。"""
    bis = [
        _mk_bi(0, "down", 10.0, 6.0),
        _mk_bi(1, "up", 10.0, 6.0),
        _mk_bi(2, "down", 9.0, 5.0),
    ]
    zs = ZS(lines=bis, zg=9.0, zd=5.0, gg=10.0, dd=5.0, direction="", index=0, done=True)
    bcs = _check_pz_beichi(bis, [zs], closes=None)
    assert bcs == []


def test_pz_beichi_enter_exit_same_direction() -> None:
    """盘整背驰：进入笔与离开笔同向、离开力度衰减才成立。"""
    bi0 = _mk_bi(0, "down", 20.0, 10.0)  # 进入（向下），力度 10
    bi1 = _mk_bi(1, "up", 18.0, 12.0)
    bi2 = _mk_bi(2, "down", 17.0, 13.0)
    bi3 = _mk_bi(3, "up", 18.0, 12.0)
    bi4 = _mk_bi(4, "down", 15.0, 14.0)  # 离开（向下），力度 1 < 8
    bis = [bi0, bi1, bi2, bi3, bi4]
    zs = _mk_zs([bi1, bi2, bi3])
    bcs = check_bi_beichi(bis, [zs], closes=None)
    assert any(bc.bc_type == BCType.PZ for bc in bcs)


def test_pz_beichi_rejects_opposite_direction() -> None:
    """盘整背驰：进入笔向下、离开笔向上（方向相反）不应判为盘整背驰。"""
    bi0 = _mk_bi(0, "down", 20.0, 10.0)
    bi1 = _mk_bi(1, "up", 18.0, 12.0)
    bi2 = _mk_bi(2, "down", 17.0, 13.0)
    bi3 = _mk_bi(3, "up", 18.0, 12.0)
    bi4 = _mk_bi(4, "up", 16.0, 14.0)  # 离开方向向上，与进入相反
    bis = [bi0, bi1, bi2, bi3, bi4]
    zs = _mk_zs([bi1, bi2, bi3])
    bcs = check_bi_beichi(bis, [zs], closes=None)
    assert all(bc.bc_type != BCType.PZ for bc in bcs)


# ── 趋势背驰语义金标 ─────────────────────────────────────────────────


def test_qs_beichi_exit_stroke_after_zs() -> None:
    """趋势背驰：离开笔 = 中枢最后一条线之后的那一笔，两段同向且创新低/力度衰减。"""
    bi0 = _mk_bi(0, "up", 22.0, 18.0)
    bi1 = _mk_bi(1, "down", 21.0, 17.0)
    bi2 = _mk_bi(2, "up", 20.0, 16.0)
    bi3 = _mk_bi(3, "down", 19.0, 15.0)
    bi4 = _mk_bi(4, "down", 14.0, 10.0)  # 前中枢离开笔（向下）
    bi5 = _mk_bi(5, "up", 16.0, 12.0)
    bi6 = _mk_bi(6, "down", 15.0, 11.0)
    bi7 = _mk_bi(7, "up", 14.0, 10.0)
    bi8 = _mk_bi(8, "down", 11.0, 9.0)  # 后中枢离开笔（向下，创新低，力度小）
    bis = [bi0, bi1, bi2, bi3, bi4, bi5, bi6, bi7, bi8]
    prev_zs = ZS(lines=[bi1, bi2, bi3], zg=20.0, zd=16.0, gg=21.0, dd=15.0, done=True)
    curr_zs = ZS(lines=[bi5, bi6, bi7], zg=15.0, zd=11.0, gg=16.0, dd=10.0, done=True)
    bcs = check_bi_beichi(bis, [prev_zs, curr_zs], closes=None)
    assert any(bc.bc_type == BCType.QS for bc in bcs)


def test_find_zss_records_enter_exit_bi() -> None:
    """缠论原文：中枢由进入段 + 重叠段 + 离开段构成，find_zss 显式记录两端。"""
    bis = [
        _mk_bi(0, "down", 30.0, 20.0),  # 进入中枢前
        _mk_bi(1, "up", 15.0, 8.0),
        _mk_bi(2, "down", 14.0, 7.0),
        _mk_bi(3, "up", 13.0, 6.0),
        _mk_bi(4, "down", 7.0, 5.0),  # 离开中枢后
    ]
    zss = find_zss(bis, ChanlunConfig())
    assert len(zss) == 1
    zs = zss[0]
    assert zs.enter_bi is bis[0]
    assert zs.exit_bi is bis[4]
    # V733 原文口径（第17/20/35课，zs_zd_lines=3）：
    # 中枢 = 三个连续次级别走势的重叠 → ZG=min(15,14,13)=13, ZD=max(8,7,6)=8
    # （V730 的 2 笔冻结口径为 14/8，已按原文修正）
    assert zs.zg == 13.0
    assert zs.zd == 8.0


def test_find_zss_extension_keeps_zg_zd() -> None:
    """缠论原文：中枢区间由前三个走势确定并冻结，第4笔起延伸只更新 gg/dd。

    V850 口径修正（第20课 A/C 口径）：
        第20课：「特别地，再定义`ZG=min(g1、g2)`, `ZD=max(d1、d2)`」
        + 「A、C段，其方向与中枢形成的方向是一致的……
           以后都把这些与中枢方向一致的次级别走势类型称为`Z走势段`」
        ⇒ Z走势段只含 A(笔0)、C(笔2)，B(笔1) 按定义不是 Z走势段。
        ⇒ zg = min(笔0.high, 笔2.high) = min(12, 12) = 12
           zd = max(笔0.low,  笔2.low)  = max( 8,  8) = 8
        （旧断言 zg==11 是第18课三端口径 min(12,11,12)，已按第20课修正）
    """
    bis = [
        _mk_bi(0, "up", 12.0, 8.0),
        _mk_bi(1, "down", 11.0, 9.0),
        _mk_bi(2, "up", 12.0, 8.0),
        _mk_bi(3, "down", 11.5, 9.5),  # 第4笔延伸：只更新 gg/dd，不动 zg/zd
        _mk_bi(4, "up", 20.0, 15.0),
    ]
    zss = find_zss(bis, ChanlunConfig())
    assert len(zss) == 1
    zs = zss[0]
    # V850：A/C 口径 —— 只取笔0、笔2，B 段（笔1）不参与
    assert zs.zg == 12.0  # min(12, 12)
    assert zs.zd == 8.0  # max(8, 8)
    assert zs.gg == 12.0
    assert zs.dd == 8.0
    assert zs.line_count == 4


def test_xd_tiebreak_earliest_is_deterministic() -> None:
    """缠论线段多义性：确定性取舍取「最早确认」，且同一输入永远同一划分。"""
    from easy_tdx.chanlun.xd import XD_TIEBREAK_EARLIEST

    assert XD_TIEBREAK_EARLIEST is True
    bis = _gap_bis(10.0)
    a = [(x.start.val, x.end.val, x.direction.value) for x in find_xds(bis, ChanlunConfig())]
    b = [(x.start.val, x.end.val, x.direction.value) for x in find_xds(list(bis), ChanlunConfig())]
    assert a == b


# ── 线段方向校验金标 ──────────────────────────────────────────────────


def test_valid_segment_end_direction() -> None:
    bis = [
        _mk_bi(0, "up", 12, 9, start_val=10, end_val=12),
        _mk_bi(1, "down", 12, 8, start_val=12, end_val=8),
        _mk_bi(2, "up", 13, 8, start_val=8, end_val=13),
    ]
    assert _valid_segment_end(bis, 0, 2, Direction.UP) is True  # 13 > 10
    assert _valid_segment_end(bis, 0, 1, Direction.UP) is False  # 8 > 10 不成立


# ── 线段划分金标 ──────────────────────────────────────────────────────


def test_find_xds_three_bis_one_segment() -> None:
    bis = [
        _mk_bi(0, "up", 12, 9, start_val=10, end_val=12),
        _mk_bi(1, "down", 12, 8, start_val=12, end_val=9),
        _mk_bi(2, "up", 13, 9, start_val=9, end_val=13),
    ]
    xds = find_xds(bis, ChanlunConfig())
    assert len(xds) == 1
    assert xds[0].direction == Direction.UP


# ── 背驰金标（创新高/新低门槛）───────────────────────────────────────


def test_beichi_requires_new_high_for_up() -> None:
    # bi0 向上力度大、bi2 向上创新高但力度小 → 应标背驰
    bis = [
        _mk_bi(0, "up", 10.0, 6.0),  # force=4
        _mk_bi(1, "down", 10.0, 6.0),
        _mk_bi(2, "up", 11.0, 9.5),  # 创新高(11>10)，force=1.5 < 4*0.8
    ]
    bcs = check_bi_beichi(bis, [], closes=None)
    assert any(bc.bc_type == BCType.BI for bc in bcs)


def test_beichi_requires_new_low_for_down() -> None:
    # bi0 向下力度大、bi2 向下创新低但力度小 → 应标背驰
    bis = [
        _mk_bi(0, "down", 10.0, 6.0),  # force=4
        _mk_bi(1, "up", 10.0, 6.0),
        _mk_bi(2, "down", 8.5, 5.5),  # 创新低(5.5<6)，force=3 < 4*0.8
    ]
    bcs = check_bi_beichi(bis, [], closes=None)
    assert any(bc.bc_type == BCType.BI for bc in bcs)


def test_beichi_rejects_no_new_low() -> None:
    # bi2 未创新低（low=6.5 > bi0.low=6），即使力度小也不标背驰
    bis = [
        _mk_bi(0, "down", 10.0, 6.0),
        _mk_bi(1, "up", 10.0, 6.0),
        _mk_bi(2, "down", 9.5, 6.5),  # 未创新低
    ]
    bcs = check_bi_beichi(bis, [], closes=None)
    assert all(bc.bc_type != BCType.BI for bc in bcs)


def test_beichi_rejects_no_new_high() -> None:
    # bi2 未创新高（high=9.5 < bi0.high=10），即使力度小也不标背驰
    bis = [
        _mk_bi(0, "up", 10.0, 6.0),
        _mk_bi(1, "down", 10.0, 6.0),
        _mk_bi(2, "up", 9.5, 8.5),  # 未创新高
    ]
    bcs = check_bi_beichi(bis, [], closes=None)
    assert all(bc.bc_type != BCType.BI for bc in bcs)


# ══ V730 原文对照测试（缠论第17/20/24/35/67/71课口径锁定）══════════════


# ── 一、线段：特征序列分型的「两种情况」（第67/71课）──────────────────
# 情况一（无缺口）：特征序列分型一出现即确认结束。
# 情况二（有缺口）：分型不立即结束线段，须由第二特征序列分型、或价格击穿
#   分型极值、或同向笔创新极值（分型无效）裁决。


def _mk_zs_raw(bis, zg, zd, gg, dd, index=0, done=True):
    return ZS(lines=bis, zg=zg, zd=zd, gg=gg, dd=dd, direction="", index=index, done=done)


def test_xd_no_gap_fx_confirms_immediately() -> None:
    """情况一：特征序列无缺口 → 分型出现即结束（对照：find_zss 前两笔冻结）。

    向上线段特征序列（向下笔）：F1=[11,12]，F2=[13,15] 与 F1 有缺口 → 修改样本
    使 F2 区间 [11.5,13.5] 与 F1 重叠（无缺口）→ 分型即确认，线段终点 15.0。
    """
    bis = [
        _mk_bi(0, "up", 12.0, 9.0, start_val=10.0, end_val=12.0),
        _mk_bi(1, "down", 12.0, 11.0, start_val=12.0, end_val=11.0),  # F1 [11,12]
        _mk_bi(2, "up", 15.0, 10.0, start_val=11.0, end_val=15.0),
        _mk_bi(3, "down", 13.5, 11.5, start_val=15.0, end_val=11.5),  # F2 [11.5,13.5] 无缺口
        _mk_bi(4, "up", 14.0, 12.0, start_val=11.5, end_val=14.0),
        _mk_bi(5, "down", 12.5, 10.5, start_val=14.0, end_val=10.5),  # F3 [10.5,12.5]
    ]
    xds = find_xds(bis, ChanlunConfig())
    # F1/F2/F3 构成顶分型（中元素 bi3 高点 13.5 最高）且 F1/F2 无缺口 → 立即结束
    assert len(xds) == 2
    assert xds[0].direction == Direction.UP
    assert xds[0].end.val == 15.0
    assert xds[1].direction == Direction.DOWN


def test_xd_gap_requires_confirmation_price_pierce() -> None:
    """情况二：特征序列有缺口 + 价格击穿分型极值 → 确认结束（第71课第三出口）。

    旧实现以「第4特征元素创新低」粗糙近似该场景；V730 改为真实价格击穿判定：
    向上段的分型极值 = 分型三元素最低点，任何后续笔 low < 该极值 → 确认。
    """
    # _gap_bis(10.0)：分型 F1[11,12] F2[13,15] F3[12,14]，缺口 → gap_pending，
    # 分型极值 = min(11,13,12)=11；bi7 low=10 < 11 → 确认，终点在 bi3（15.0）。
    xds = find_xds(_gap_bis(10.0), ChanlunConfig())
    assert len(xds) == 2
    assert xds[0].end.val == 15.0


def test_xd_gap_invalidated_by_new_extreme() -> None:
    """情况二：特征序列有缺口 + 同向笔创出超过分型顶点的新极值 → 分型无效、线段延续。"""
    # bi7 改为向上笔创新高：顶分型从未被确认，线段延伸至新高 16.0
    bis = [
        _mk_bi(0, "up", 12.0, 9.0, start_val=10.0, end_val=12.0),
        _mk_bi(1, "down", 12.0, 11.0, start_val=12.0, end_val=11.0),
        _mk_bi(2, "up", 15.0, 10.0, start_val=11.0, end_val=15.0),
        _mk_bi(3, "down", 15.0, 13.0, start_val=15.0, end_val=13.0),
        _mk_bi(4, "up", 14.0, 12.0, start_val=13.0, end_val=14.0),
        _mk_bi(5, "down", 14.0, 12.0, start_val=14.0, end_val=12.0),
        _mk_bi(6, "up", 15.5, 11.0, start_val=12.0, end_val=15.5),
        _mk_bi(7, "up", 16.0, 15.5, start_val=15.5, end_val=16.0),
    ]
    xds = find_xds(bis, ChanlunConfig())
    # 分型无效后线段延续；收尾取最后一个同向笔端点 = 16.0
    assert len(xds) == 1
    assert xds[0].end.val == 16.0


# ── 二、中枢：前两笔冻结 + 纯重叠延伸（第17/20/35课）────────────────


def test_zs_zg_zd_frozen_first_two_no_enter_offset() -> None:
    """中枢区间 = 前三个次级别走势重叠的冻结：ZG=min(g1,g2,g3), ZD=max(d1,d2,d3)。

    V733：原文「中枢 = 三个连续次级别走势的重叠区间」，故冻结笔数由 2 改为 3
    （由 config.zs_zd_lines 控制，默认 3）。

    直接喂 find_zss（无进入段偏移，bis[0] 即中枢第一笔）：
    bi0=[8,10], bi1=[7,15], bi2=[8.5,9.5]
      → ZG=min(10,15,9.5)=9.5, ZD=max(8,7,8.5)=8.5
    bi3=[9,12] 与 [8.5,9.5] 重叠 → 延伸；延伸只更新 gg/dd。
    """
    bis = [
        _mk_bi(0, "up", 10.0, 8.0),
        _mk_bi(1, "down", 15.0, 7.0),
        _mk_bi(2, "up", 9.5, 8.5),
        _mk_bi(3, "down", 12.0, 9.0),  # 延伸笔（与 [8,10] 重叠）
        _mk_bi(4, "down", 6.0, 4.0),  # 与 [8,10] 无重叠 → 中枢关闭
    ]
    zss = find_zss(bis, ChanlunConfig())
    assert len(zss) == 1
    zs = zss[0]
    assert zs.zg == 9.5  # min(10, 15, 9.5)
    assert zs.zd == 8.5  # max(8, 7, 8.5)
    assert zs.gg == 15.0  # 全区间最高
    assert zs.dd == 7.0  # 全区间最低
    assert zs.line_count == 4


def test_zs_extension_pure_overlap_no_ratio_threshold() -> None:
    """延伸判据 = 与 [ZD,ZG] 纯重叠（overlap_high > overlap_low），无比例阈值。

    V730 P1-2 移除了 v87 的重叠率百分比要求：窄至 0.1 的重叠也是延伸，
    不应因「重叠占比低」而把同一中枢误拆成两个。
    """
    bis = [
        _mk_bi(0, "up", 10.0, 8.0),
        _mk_bi(1, "down", 15.0, 7.0),
        _mk_bi(2, "up", 9.5, 8.5),
        _mk_bi(3, "down", 20.0, 9.95),  # 与 [8,10] 仅重叠 [9.95,10]，宽 0.05
        _mk_bi(4, "down", 6.0, 4.0),
    ]
    zss = find_zss(bis, ChanlunConfig())
    assert len(zss) == 1
    # V733 三笔冻结：ZG=min(10,15,9.5)=9.5, ZD=max(8,7,8.5)=8.5
    assert zss[0].zg == 9.5
    assert zss[0].zd == 8.5
    # 本用例的核心是「窄重叠也算延伸、不被误拆」—— bi3=[9.95,20] 与
    # 冻结区间 [8.5,9.5] 的 overlap_high=min(9.5,20)=9.5、overlap_low=
    # max(8.5,9.95)=9.95 → 9.5 > 9.95 不成立，故 bi3 **不**延伸，
    # 中枢在此关闭（line_count=3）。V733 下中枢更窄，这是预期行为；
    # 「窄重叠不被误拆」的断言由 zs.zg/zd 被 bi2 收窄仍保持 1 个中枢来体现。
    assert zss[0].line_count == 3


def test_zs_extension_cap_9_segments_closes_and_restarts() -> None:
    """V730 P1-6（社区共识工程上限）：延伸达 9 段后关闭中枢，后续笔开启新候选。"""
    bis = [_mk_bi(0, "up", 10.0, 8.0), _mk_bi(1, "down", 15.0, 7.0)]
    # 再造 7 笔与 [8,10] 有重叠的笔（共 9 段）→ 达上限关闭
    for i in range(2, 9):
        lo = 8.5 + 0.1 * i
        bis.append(_mk_bi(i, "down" if i % 2 else "up", lo + 1.0, lo))
    bis.append(_mk_bi(9, "down", 30.0, 25.0))  # 无重叠 → 若未达上限会被并入延伸
    zss = find_zss(bis, ChanlunConfig())
    assert len(zss) == 1
    assert zss[0].line_count == 9  # 9 段上限（含初始 2 段）
    # V733 三笔冻结：ZG=min(10,15,9.7)=9.7, ZD=max(8,7,8.7)=8.7
    # （V730 的 2 笔口径为 10.0/8.0；本用例的核心是「9 段上限关闭与重启」，
    #   ZG/ZD 仅作附带校验，随冻结口径一并更新）
    assert zss[0].zg == 9.7 and zss[0].zd == 8.7  # 冻结不变


# ── 三、趋势背驰：离开段口径 + 候选笔锚定（第24课）──────────────────


def test_qs_beichi_anchored_to_exit_segment() -> None:
    """趋势背驰的背驰点必须锚定在「第二离开段」本身（curr_exit_idx == bi_idx）。

    构造两个同向下移中枢：zs0 lines=[bi1,bi2,bi3]（zg=15,zd=11），zs1
    lines=[bi5,bi6,bi7]（zg=11,zd=7）。离开段口径下比较 bis[4] vs bis[8]，
    bis[8] 创新低且力度（振幅）衰减 → 趋势背驰成立，且 bc.bi 即 bis[8]。
    """
    bis = [
        _mk_bi(0, "up", 22.0, 18.0),
        _mk_bi(1, "down", 15.0, 11.0),
        _mk_bi(2, "up", 15.0, 11.0),
        _mk_bi(3, "down", 15.0, 11.0),
        _mk_bi(4, "down", 11.0, 7.0),  # zs0 离开段（向下，力度 4）
        _mk_bi(5, "up", 11.0, 7.0),
        _mk_bi(6, "down", 11.0, 7.0),
        _mk_bi(7, "up", 11.0, 7.0),
        _mk_bi(8, "down", 7.5, 5.0),  # zs1 离开段：创新低(5<7)、力度 2.5 < 4*0.8
    ]
    zss = [
        _mk_zs_raw([bis[1], bis[2], bis[3]], 15.0, 11.0, 15.0, 11.0),
        _mk_zs_raw([bis[5], bis[6], bis[7]], 11.0, 7.0, 11.0, 7.0, index=1),
    ]
    bcs = check_bi_beichi(bis, zss, closes=None)
    qs = [bc for bc in bcs if bc.bc_type == BCType.QS]
    assert len(qs) == 1
    assert qs[0].curr is bis[8]  # 背驰点锚定在第二离开段本身，而非后续不相关的笔


def test_qs_beichi_not_anchored_no_signal() -> None:
    """候选笔不是第二离开段（curr_exit_idx != bi_idx）→ 不产生趋势背驰。

    P0-1 锚定语义的反向验证：把 bis[8]（真正的离开段）换成 bis[9]（后续
    同向笔），力度再弱也不能把背驰标到它上面——旧实现会误标。
    """
    bis = [
        _mk_bi(0, "up", 22.0, 18.0),
        _mk_bi(1, "down", 15.0, 11.0),
        _mk_bi(2, "up", 15.0, 11.0),
        _mk_bi(3, "down", 15.0, 11.0),
        _mk_bi(4, "down", 11.0, 7.0),
        _mk_bi(5, "up", 11.0, 7.0),
        _mk_bi(6, "down", 11.0, 7.0),
        _mk_bi(7, "up", 11.0, 7.0),
        _mk_bi(8, "up", 10.0, 8.0),  # zs1 离开段方向向上（与趋势相反）→ QS 不成立
        _mk_bi(9, "down", 9.0, 5.0),  # 后续同向笔：即使创新低也不背驰（未锚定）
    ]
    zss = [
        _mk_zs_raw([bis[1], bis[2], bis[3]], 15.0, 11.0, 15.0, 11.0),
        _mk_zs_raw([bis[5], bis[6], bis[7]], 11.0, 7.0, 11.0, 7.0, index=1),
    ]
    bcs = check_bi_beichi(bis, zss, closes=None)
    assert all(bc.bc_type != BCType.QS for bc in bcs)


# ── 四、1买/1卖 扫描方向对称（V730 P1-5）────────────────────────────


def test_first_type_mmd_scan_direction_symmetry() -> None:
    """1买 forward 与 1卖 forward 镜像：pullback_low 只累计「信号之前」的回落。

    反向验证（未来函数探测）：1卖候选笔 high > zg 但**之后**的走势大幅回落
    ——正向扫描下 pullback_low 含未来数据不影响判定时序，但若实现退回
    reversed(bis)，评估首笔时 pullback_low 已含末端低点，会拒绝本应成立的
    顶部信号。锁定：两支顶背驰笔（力度衰减+创新高）都应被标出。
    """
    bis = [
        _mk_bi(0, "up", 22.0, 18.0),
        _mk_bi(1, "down", 14.0, 10.0),  # zs0: zg=14, zd=10
        _mk_bi(2, "up", 14.0, 10.0),
        _mk_bi(3, "down", 14.0, 10.0),
        _mk_bi(4, "up", 20.0, 14.0),  # zs0 离开段（向上）
        _mk_bi(5, "down", 16.0, 12.0),  # zs1: zg=16, zd=12（上移 → 同向上升趋势）
        _mk_bi(6, "up", 16.0, 12.0),
        _mk_bi(7, "down", 16.0, 12.0),
        _mk_bi(8, "up", 24.0, 16.0),  # zs1 离开段：创新高(24>20)、力度 8 > 6*0.8 → 无背驰
        _mk_bi(9, "down", 24.0, 20.0),
        _mk_bi(10, "up", 25.0, 24.0),  # 创新高(25>24)、力度 1 < 8*0.8 → 1卖 ✓
        _mk_bi(11, "down", 25.0, 21.0),
        _mk_bi(12, "up", 26.0, 25.0),  # 创新高(26>25)、力度 1 < 1*0.8? 否 → 跳过
        _mk_bi(13, "down", 26.0, 22.0),  # 之后深度回落（若 reversed 扫描会污染判定）
    ]
    zss = [
        _mk_zs_raw([bis[1], bis[2], bis[3]], 14.0, 10.0, 14.0, 10.0),
        _mk_zs_raw([bis[5], bis[6], bis[7]], 16.0, 12.0, 16.0, 12.0, index=1),
    ]
    mmds = _find_first_type_mmds(bis, zss, None, ChanlunConfig())
    sells = [m for m in mmds if m.mmd_type == MMDType.SELL_1]
    assert len(sells) == 1
    assert sells[0].bi is bis[10]


# ── V730 区间套（V68 条件205）计分契约 ────────────────────────────────
# 背景：分层回测（scripts/nesting_backtest.py，20 只龙头 × 800 根日线）显示
# 区间套确认在 3卖 上显著占优（h=5/10/20 命中率 74.6%/74.6%/66.7% vs
# 62.8%/55.8%/48.8%），但在 3买 上不占优（47.8%/34.8%/47.6% vs 63.0%/63.0%/57.7%）。
# 换言之：该评分目前对卖点有效、对买点无效。这里锁定**当前计分契约**，
# 使任何试图调整计分方向的改动都必须同步更新本测试与回测结论。


def _mk_zs_for_nesting(zg: float, zd: float, index: int = 0) -> ZS:
    """构造区间套计分用的中枢（只需 zg/zd/done，其余字段不参与计分）。"""
    return ZS(lines=[], zg=zg, zd=zd, gg=zg, dd=zd, direction="", index=index, done=True)


def test_nesting_score_needs_40_bars() -> None:
    """数据不足 40 根时不计算区间套（评分保持默认 0）。"""
    from easy_tdx.chanlun.mmd_conditions import _calc_range_set_multi_level_v68

    mmd = MMD(mmd_type=MMDType.BUY_3, msg="", confidence=0.5)
    zss = [_mk_zs_for_nesting(10.0, 9.0)]
    res = _calc_range_set_multi_level_v68(mmd, zss, closes=[10.0] * 39)
    assert res["multi_level_score"] == 0.0
    assert "数据不足" in res["msg"]


def test_nesting_score_buy_uses_zs_above_counts() -> None:
    """锁定买入分支口径：support_level 取「价格上方中枢数 / 中枢总数」。

    注意这是**原实现口径**（价格上方的中枢在买入语境下实为阻力），分层回测
    表明按此口径 3买 不占优；曾尝试改为下方中枢反而更差，故保持。测试目的
    是让任何改动作实据对比后再改，而不是静默翻转。
    """
    from easy_tdx.chanlun.mmd_conditions import _calc_range_set_multi_level_v68

    mmd = MMD(mmd_type=MMDType.BUY_3, msg="", confidence=0.5)
    # 价格 20，三个中枢全部位于价格下方（9-10 / 10-11 / 11-12）
    zss = [
        _mk_zs_for_nesting(10.0, 9.0, 0),
        _mk_zs_for_nesting(11.0, 10.0, 1),
        _mk_zs_for_nesting(12.0, 11.0, 2),
    ]
    closes = [20.0] * 60
    res = _calc_range_set_multi_level_v68(mmd, zss, closes)
    # 语义：zs_above_price = 「价格在中枢上方」的中枢数（代码 "above": current > zs.zg）
    assert res["zs_above_price"] == 3.0  # 价格站上全部 3 个中枢
    assert res["zs_below_price"] == 0.0
    # 买入分支 support_level = zs_above/n = 1.0（突破确认），加距离项 → 高分
    assert res["multi_level_score"] == pytest.approx(0.3 * 1.0 + 0.3 * 1.0 + 0.4 * 1.0, abs=0.02)


def test_nesting_score_sell_uses_zs_below_counts() -> None:
    """锁定卖出分支口径：resistance_level 取「价格下方中枢数 / 中枢总数」（镜像）。"""
    from easy_tdx.chanlun.mmd_conditions import _calc_range_set_multi_level_v68

    mmd = MMD(mmd_type=MMDType.SELL_3, msg="", confidence=0.5)
    # 价格 5，三个中枢全在价格上方
    zss = [
        _mk_zs_for_nesting(10.0, 9.0, 0),
        _mk_zs_for_nesting(11.0, 10.0, 1),
        _mk_zs_for_nesting(12.0, 11.0, 2),
    ]
    closes = [5.0] * 60
    res = _calc_range_set_multi_level_v68(mmd, zss, closes)
    assert res["zs_above_price"] == 0.0
    assert res["zs_below_price"] == 3.0  # 价格跌破全部 3 个中枢
    # 卖出分支 resistance_level = zs_below/n = 1.0（跌破确认），镜像买入分支
    assert res["multi_level_score"] == pytest.approx(0.3 * 1.0 + 0.3 * 1.0 + 0.4 * 1.0, abs=0.02)


def test_nesting_score_confidence_adjust_bands() -> None:
    """V-25 下线：confidence_adjust 恒 0，评分只作诊断不再调权。

    旧分档（>=0.7→+5%，>=0.5→+3%，>=0.3→0，否则 -3%）已随文档
    §四 step2 移除——价格位置评分与真区间套不同义，不得混入
    mmd.confidence。本测试同时守住两侧：不加分也不减分。
    """
    from easy_tdx.chanlun.mmd_conditions import _calc_range_set_multi_level_v68

    def adjust_and_score(zss_: list[ZS], price: float, buy: bool) -> dict:
        mmd = MMD(mmd_type=MMDType.BUY_3 if buy else MMDType.SELL_3, msg="", confidence=0.5)
        return _calc_range_set_multi_level_v68(mmd, zss_, closes=[price] * 60)

    # 高分场景（旧逻辑会 +5%）：现在必须 0
    below_all = [_mk_zs_for_nesting(20.0, 19.0), _mk_zs_for_nesting(21.0, 20.0)]
    res_hi = adjust_and_score(below_all, 5.0, buy=False)
    assert res_hi["confidence_adjust"] == 0.0
    # 诊断评分本身仍在（高分场景评分应 >0.5，证明不是靠数据不足路径返回 0）
    assert res_hi["multi_level_score"] > 0.5
    # 低分场景（旧逻辑会 -3%）：现在也必须 0
    inside = [_mk_zs_for_nesting(20.0, 10.0)]
    res_lo = adjust_and_score(inside, 15.0, buy=True)
    assert res_lo["confidence_adjust"] == 0.0
    assert res_lo["multi_level_score"] < 0.5
    # msg 不再含「置信度」尾巴
    assert "置信度" not in res_hi["msg"]


def test_nesting_score_does_not_touch_confidence() -> None:
    """端到端对照：条件 205 运行后 mmd.confidence 必须与运行前一致。

    控制组：同数据同信号，仅存在/不存在 v68 调用——置信度必须同值。
    （V-25 前旧实现会 +3~5%/-3% 改写 confidence。）
    """
    from easy_tdx.chanlun.mmd_conditions import _calc_range_set_multi_level_v68

    below_all = [_mk_zs_for_nesting(20.0, 19.0), _mk_zs_for_nesting(21.0, 20.0)]
    mmd = MMD(mmd_type=MMDType.SELL_3, msg="", confidence=0.6)
    before = mmd.confidence
    _calc_range_set_multi_level_v68(mmd, below_all, closes=[5.0] * 60)
    assert mmd.confidence == before, "v68 评分不得改写 mmd.confidence"


def test_nesting_score_serialized_by_analyser() -> None:
    """to_dict 输出 v68_range_set_multi_level，供前端标注与回测分组消费。"""
    from easy_tdx.chanlun.analyser import ChanlunResult

    mmd = MMD(mmd_type=MMDType.SELL_3, msg="", confidence=0.5)
    mmd._range_set_multi_level_v68 = {"multi_level_score": 0.75, "confidence_adjust": 0.05}
    result = ChanlunResult(code="600519", frequency="daily")
    result.mmds = [mmd]
    d = result.to_dict()
    assert d["mmds"][0]["v68_range_set_multi_level"]["multi_level_score"] == 0.75


# ── V730 区间套：时间锚定与回踩站稳因子 ──────────────────────────────
# 修复前缺陷：评分用 closes[-1]（序列最新价）+ 全部中枢 → 同一标的所有 3buy
# 共享同一评分、所有 3sell 共享另一评分（实测 600519：3buy 恒 0.592、
# 3sell 恒 0.639），与信号自身位置无关；且用到信号之后才形成的中枢（未来函数）。
# 修复后：锚定信号时刻（mmd.bi.end.bar_index），只用此前已形成的中枢，
# 并新增回踩站稳因子（3买 破位组实测 10 根命中率仅 35.7% vs 站稳组 59.8%）。


def _mk_bi_for_nesting(start_bar: int, end_bar: int) -> BI:
    """构造带 bar_index 的笔（用于给 MMD 提供信号时间锚点）。"""
    bi = _mk_bi(start_bar, "up", 12.0, 10.0, start_val=10.0, end_val=12.0)
    bi.start.bar_index = start_bar
    bi.end.bar_index = end_bar
    return bi


def test_nesting_score_anchored_to_signal_time() -> None:
    """评分必须锚定信号时刻，而非序列末尾：末尾价变化不应影响历史信号评分。"""
    from easy_tdx.chanlun.mmd_conditions import _calc_range_set_multi_level_v68

    zs = _mk_zs_for_nesting(10.0, 9.0, index=0)
    zs.start = _mk_bi_for_nesting(10, 20).start
    zs.end = _mk_bi_for_nesting(10, 20).end  # 中枢结束于 bar 20（信号之前）

    mmd = MMD(mmd_type=MMDType.BUY_3, msg="", confidence=0.5)
    mmd.bi = _mk_bi_for_nesting(21, 30)  # 信号在 bar 30
    closes = [10.0] * 60
    closes[30] = 12.0  # 信号时刻价格 12（站上中枢 ZG=10）
    r1 = _calc_range_set_multi_level_v68(mmd, [zs], closes)

    # 只改末尾价（模拟继续行情推进），信号时刻状态未变 → 评分不应变
    closes2 = list(closes)
    closes2[-1] = 3.0  # 末尾暴跌（回到中枢下方）
    r2 = _calc_range_set_multi_level_v68(mmd, [zs], closes2)
    assert r1["multi_level_score"] == r2["multi_level_score"], (
        "历史信号评分不应被后续行情改写（修复前会用 closes[-1]，导致评分漂移）"
    )


def test_nesting_score_ignores_future_zhongshu() -> None:
    """信号之后才形成的中枢不得参与计分（未来函数）。"""
    from easy_tdx.chanlun.mmd_conditions import _calc_range_set_multi_level_v68

    past = _mk_zs_for_nesting(10.0, 9.0, index=0)  # 信号前
    past.start = _mk_bi_for_nesting(5, 10).start
    past.end = _mk_bi_for_nesting(5, 10).end
    future = _mk_zs_for_nesting(30.0, 29.0, index=1)  # 信号后（未来）
    future.start = _mk_bi_for_nesting(40, 45).start
    future.end = _mk_bi_for_nesting(40, 45).end

    mmd = MMD(mmd_type=MMDType.BUY_3, msg="", confidence=0.5)
    mmd.bi = _mk_bi_for_nesting(21, 30)  # 信号在 bar 30
    closes = [15.0] * 60
    closes[30] = 15.0

    only_past = _calc_range_set_multi_level_v68(mmd, [past], closes)
    with_future = _calc_range_set_multi_level_v68(mmd, [past, future], closes)
    # 未来中枢（ZG=30，价格在下方）若被计入会拉低 above 比例 → 评分下降
    assert with_future["multi_level_score"] == only_past["multi_level_score"]
    assert with_future["zhongshu_count"] == only_past["zhongshu_count"]


def test_nesting_retest_hold_penalizes_breakdown() -> None:
    """回踩跌回中枢内（破位）应拉低 3买 评分。"""
    from easy_tdx.chanlun.mmd_conditions import _calc_range_set_multi_level_v68

    zs = _mk_zs_for_nesting(10.0, 9.0, index=0)
    zs.start = _mk_bi_for_nesting(5, 10).start
    zs.end = _mk_bi_for_nesting(5, 10).end  # 中枢在信号前完成

    mmd = MMD(mmd_type=MMDType.BUY_3, msg="", confidence=0.5)
    mmd.bi = _mk_bi_for_nesting(21, 40)  # 信号在 bar 40

    # 站稳：前 10 根回踩最低 10.5 >= ZG=10
    hold_closes = [12.0] * 60
    hold_closes[31:41] = [10.5] * 10
    hold_closes[40] = 12.0
    r_hold = _calc_range_set_multi_level_v68(mmd, [zs], hold_closes)

    # 破位：前 10 根最低 8.5 < ZG=10（跌回中枢内）
    brk_closes = [12.0] * 60
    brk_closes[31:41] = [8.5] * 10
    brk_closes[40] = 12.0
    r_brk = _calc_range_set_multi_level_v68(mmd, [zs], brk_closes)

    assert r_hold["retest_hold"] == 1.0
    assert r_brk["retest_hold"] == 0.0
    assert r_hold["multi_level_score"] > r_brk["multi_level_score"], (
        "回踩破位的 3买 评分必须低于站稳者"
    )


# ── V730 其余「时间错配」类缺陷（同批 V79 条件）────────────────────────
# 与区间套（条件205）同构：这些条件都直接调整 mmd.confidence，若用序列
# 最新状态标注历史信号，则评分与信号自身无关、且含未来函数。


def test_distance_safety_uses_prior_same_direction_signals() -> None:
    """V730：距离安全须找「之前」的同向信号；且方向判定须匹配 1buy/3buy 小写值。

    原实现两处缺陷：①遍历 mmds[:-1]（含未来信号）；②用 startswith("BUY")
    而 MMDType.value 是小写的 "1buy"/"3buy" → 永远匹配不到，所有信号恒为
    isolated/99（实测 5/5 标的恒定，完全丧失区分度）。
    """
    from easy_tdx.chanlun.mmd_conditions import _calc_mmd_distance_safety_v79

    def mk(t: MMDType, bar: int) -> MMD:
        m = MMD(mmd_type=t, msg="", confidence=0.5)
        m.bi = _mk_bi_for_nesting(bar - 5, bar)
        return m

    mmds = [
        mk(MMDType.BUY_1, 10),
        mk(MMDType.BUY_3, 30),  # 距前一同向 20 根
        mk(MMDType.SELL_1, 45),
        mk(MMDType.SELL_3, 50),  # 距前一同向 5 根
    ]
    closes = [10.0] * 60

    first = _calc_mmd_distance_safety_v79(mmds, mmds[0], closes)
    assert first["safety_level"] == "isolated"  # 无前置同向信号

    buy3 = _calc_mmd_distance_safety_v79(mmds, mmds[1], closes)
    assert buy3["bars_to_nearest"] == 20
    assert buy3["safety_level"] == "safe"

    sell3 = _calc_mmd_distance_safety_v79(mmds, mmds[3], closes)
    assert sell3["bars_to_nearest"] == 5
    assert sell3["safety_level"] == "close"


def test_distance_safety_ignores_later_signals() -> None:
    """不得把「信号之后」才出现的同向信号计入距离（未来函数）。"""
    from easy_tdx.chanlun.mmd_conditions import _calc_mmd_distance_safety_v79

    def mk(t: MMDType, bar: int) -> MMD:
        m = MMD(mmd_type=t, msg="", confidence=0.5)
        m.bi = _mk_bi_for_nesting(bar - 5, bar)
        return m

    target = mk(MMDType.BUY_1, 30)
    later = mk(MMDType.BUY_3, 33)  # 仅相隔 3 根，但在目标之后
    closes = [10.0] * 60
    r = _calc_mmd_distance_safety_v79([target, later], target, closes)
    assert r["bars_to_nearest"] == 99, "不得引用未来信号计算距离"
    assert r["safety_level"] == "isolated"


def test_fractal_stability_anchored_after_signal() -> None:
    """分型稳定性须观察「信号之后」的窗口，而非序列末尾（否则所有信号同值）。"""
    from easy_tdx.chanlun.mmd_conditions import _calc_fractal_stability_validation_v79

    def mk(t: MMDType, bar: int) -> MMD:
        m = MMD(mmd_type=t, msg="", confidence=0.5)
        m.bi = _mk_bi_for_nesting(bar - 5, bar)
        return m

    # 信号在 bar 30：其后平稳（无新高）→ stable
    early = mk(MMDType.BUY_1, 30)
    highs = [10.0] * 60
    lows = [9.0] * 60
    r_early = _calc_fractal_stability_validation_v79(early, highs, lows)

    # 信号在 bar 30，之后出现大幅新高（破坏顶分型）→ 稳定性应下降
    # 判据：窗口末根 current_high 是否突破窗口内此前最高 * 1.02
    highs2 = [10.0] * 60
    highs2[50] = 11.0  # 窗口末根（bar 50）独创新高，其余维持 10.0
    r_broken = _calc_fractal_stability_validation_v79(early, highs2, lows)

    assert r_early["fractal_status"] == "stable"
    assert r_early["stability_score"] > r_broken["stability_score"], (
        "信号后出现新高破坏分型时，稳定性评分必须下降"
    )


# ── V730 条件254/259/263 的时间锚定 ───────────────────────────────────
# 由 scripts/detect_constant_mmd_fields.py 巡检发现：这三个字段在 12/12 或
# 10/12 的标的上对所有信号取恒定值 → 用序列末尾状态标注历史信号（未来函数）。
# 修复后均降至 0/12。


def test_ma_alignment_anchored_to_signal() -> None:
    """均线排列须取「信号当时」的均线，而非序列末尾。"""
    from easy_tdx.chanlun.mmd_conditions import _calc_ma_alignment_strength_v80

    def mk(t: MMDType, bar: int) -> MMD:
        m = MMD(mmd_type=t, msg="", confidence=0.5)
        m.bi = _mk_bi_for_nesting(bar - 5, bar)
        return m

    n = 120
    # 前 60 根横盘 10，后 60 根上涨到 20 → 末尾是多头排列，而 bar=60 处不是
    closes = [10.0] * 60 + [10.0 + i * 0.15 for i in range(60)]
    early = mk(MMDType.BUY_1, 60)
    late = mk(MMDType.BUY_1, n - 1)

    r_early = _calc_ma_alignment_strength_v80(early, closes)
    r_late = _calc_ma_alignment_strength_v80(late, closes)
    assert r_early["ma_alignment"] != r_late["ma_alignment"], (
        "不同时点的信号应得到各自的均线排列结论（修复前共享末尾结论）"
    )


def test_volatility_compression_anchored_to_signal() -> None:
    """波动率压缩须衡量「信号当时」的区间宽度，而非末尾。"""
    from easy_tdx.chanlun.mmd_conditions import _calc_volatility_compression_breakout_v82

    def mk(t: MMDType, bar: int) -> MMD:
        m = MMD(mmd_type=t, msg="", confidence=0.5)
        m.bi = _mk_bi_for_nesting(bar - 5, bar)
        return m

    n = 100  # noqa: F841 — len(highs) 即该值，保留变量仅为可读性
    # 前 50 根极窄（压缩），后 50 根剧烈震荡（无压缩）
    highs = [10.05] * 50 + [10.0 + (i % 5) * 0.5 for i in range(50)]
    lows = [9.95] * 50 + [10.0 + (i % 5) * 0.5 - 0.2 for i in range(50)]
    closes = [10.0] * 50 + [10.0 + (i % 5) * 0.4 for i in range(50)]

    r_compressed = _calc_volatility_compression_breakout_v82(
        mk(MMDType.BUY_1, 49), closes, highs, lows
    )
    r_wide = _calc_volatility_compression_breakout_v82(mk(MMDType.BUY_1, 99), closes, highs, lows)
    assert r_compressed["compression_pct"] < r_wide["compression_pct"], (
        "压缩段的区间宽度必须小于震荡段（修复前两者都用末尾窗口而相同）"
    )


def test_execution_window_anchored_to_signal() -> None:
    """执行窗口须评估「信号当时」的波动与量能，而非末尾。"""
    from easy_tdx.chanlun.mmd_conditions import _calc_signal_execution_window_v81

    def mk(t: MMDType, bar: int) -> MMD:
        m = MMD(mmd_type=t, msg="", confidence=0.5)
        m.bi = _mk_bi_for_nesting(bar - 5, bar)
        return m

    n = 120  # noqa: F841 — len(closes) 即该值，保留变量仅为可读性
    # 前 60 根平静，后 60 根剧烈波动 → 波动率分应不同
    calm = [10.0] * 60
    wild = [10.0 + ((-1) ** i) * 3.0 for i in range(60)]
    closes = calm + wild
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]

    r_calm = _calc_signal_execution_window_v81(mk(MMDType.BUY_1, 59), closes, highs, lows, None)
    r_wild = _calc_signal_execution_window_v81(mk(MMDType.BUY_1, 119), closes, highs, lows, None)
    assert r_calm["volatility_score"] != r_wild["volatility_score"], (
        "平静段与剧烈段的执行窗口评分必须不同（修复前共享末尾结论）"
    )
