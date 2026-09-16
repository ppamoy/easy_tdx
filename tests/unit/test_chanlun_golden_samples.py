"""缠论金标样本回归（V602）。

用「手工标注正确结果」的确定性样本锁定笔/线段/背驰的关键行为，
防止后续改动把模型改坏。样本聚焦于可精确预测的纯函数与单元行为。
"""

from __future__ import annotations

from datetime import datetime

from easy_tdx.chanlun.beichi import _check_pz_beichi, check_bi_beichi
from easy_tdx.chanlun.bi import find_bis
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.fractal import find_fractals
from easy_tdx.chanlun.kline_merge import merge_klines
from easy_tdx.chanlun.mmd import (
    _has_meaningful_pullback,
    _has_meaningful_rebound,
    _reference_zs_for_bi,
)
from easy_tdx.chanlun.mmd_conditions import _calc_trend_strength
from easy_tdx.chanlun.types import BI, FX, ZS, BCType, CLKline, Direction, FXType, Kline
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
        lines=[], zg=zg, zd=zd, gg=zg + 1.0, dd=zd - 1.0, direction="",
        index=0, done=True, start=None, end=None,
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
        lines=[], zg=10.0, zd=5.0, gg=11.0, dd=4.0, direction="",
        index=0, done=True, start=None, end=_mk_fx_ref(10),
    )
    zs1 = ZS(
        lines=[], zg=9.0, zd=4.0, gg=10.0, dd=3.0, direction="",
        index=1, done=True, start=None, end=_mk_fx_ref(20),
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
    """四笔重叠形成中枢、离开笔关闭中枢：应得到 1 个中枢，zg=11 zd=9 gg=12 dd=8。"""
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
    assert zs.zg == 11.0  # min(high) = 上沿
    assert zs.zd == 9.0  # max(low) = 下沿
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
    """特征序列有缺口但第4元素不跌破 → 线段继续（1 段收尾）。"""
    xds = find_xds(_gap_bis(12.0), ChanlunConfig())
    assert len(xds) == 1
    assert xds[0].direction == Direction.UP
    assert xds[0].end.val == 15.0


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
    assert zs.zg == 13.0
    assert zs.zd == 8.0


def test_find_zss_extension_keeps_zg_zd() -> None:
    """缠论原文：中枢区间由前三个走势确定，第4笔延伸不改变 zg/zd，只更新 gg/dd。"""
    bis = [
        _mk_bi(0, "up", 12.0, 8.0),
        _mk_bi(1, "down", 11.0, 9.0),
        _mk_bi(2, "up", 12.0, 8.0),
        _mk_bi(3, "down", 11.5, 9.5),  # 第4笔延伸，旧逻辑会把 zd 抬到 9.5
        _mk_bi(4, "up", 20.0, 15.0),
    ]
    zss = find_zss(bis, ChanlunConfig())
    assert len(zss) == 1
    zs = zss[0]
    assert zs.zg == 11.0  # 前三个走势确定，延伸不改变
    assert zs.zd == 9.0
    assert zs.gg == 12.0
    assert zs.dd == 8.0
    assert zs.line_count == 4


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