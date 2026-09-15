"""缠论金标样本回归（V602）。

用「手工标注正确结果」的确定性样本锁定笔/线段/背驰的关键行为，
防止后续改动把模型改坏。样本聚焦于可精确预测的纯函数与单元行为。
"""

from __future__ import annotations

from datetime import datetime

from easy_tdx.chanlun.beichi import check_bi_beichi
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import BI, FX, BCType, Direction, FXType
from easy_tdx.chanlun.xd import (
    _merge_feature_sequence,
    _merged_feature_fx,
    _valid_segment_end,
    find_xds,
)


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