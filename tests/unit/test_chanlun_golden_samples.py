"""缠论金标样本回归（V602）。

用「手工标注正确结果」的确定性样本锁定笔/线段/背驰的关键行为，
防止后续改动把模型改坏。样本聚焦于可精确预测的纯函数与单元行为。
"""

from __future__ import annotations

from datetime import datetime

from easy_tdx.chanlun.beichi import check_bi_beichi
from easy_tdx.chanlun.bi import find_bis
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.fractal import find_fractals
from easy_tdx.chanlun.kline_merge import merge_klines
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


# ── 分型识别金标 ──────────────────────────────────────────────────────

def test_fractal_golden() -> None:
    """一段明显顶分型 + 底分型的序列，应恰好识别出 1 个顶分型 + 1 个底分型。"""
    cklines = [
        _mk_clkline(0, 10.0, 8.0),
        _mk_clkline(1, 12.0, 9.0),
        _mk_clkline(2, 14.0, 10.0),  # 顶分型中间
        _mk_clkline(3, 13.0, 9.0),
        _mk_clkline(4, 12.0, 8.0),  # 底分型中间
        _mk_clkline(5, 11.0, 9.0),
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


# ── 盘整背驰语义金标 ─────────────────────────────────────────────────

def _mk_zs(lines) -> ZS:
    return ZS(lines=lines, zg=17.0, zd=13.0, gg=18.0, dd=12.0, direction="", index=0, done=True)


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


def test_beichi_rejects_no_new_high() -> None:
    # bi2 未创新高（high=9.5 < bi0.high=10），即使力度小也不标背驰
    bis = [
        _mk_bi(0, "up", 10.0, 6.0),
        _mk_bi(1, "down", 10.0, 6.0),
        _mk_bi(2, "up", 9.5, 8.5),  # 未创新高
    ]
    bcs = check_bi_beichi(bis, [], closes=None)
    assert all(bc.bc_type != BCType.BI for bc in bcs)