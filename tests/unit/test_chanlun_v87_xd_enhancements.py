"""缠论v87线段计算改进测试。

测试改进内容：
1. 特征序列分型严格判定
2. 方向一致性检查
"""

from __future__ import annotations

from datetime import datetime

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import BI, FX, Direction, FXType
from easy_tdx.chanlun.xd import _feature_fx_end_segment, find_xds


def _make_bi(
    index: int,
    direction: str,
    start_val: float,
    end_val: float,
    high: float,
    low: float,
) -> BI:
    """快速构造笔。"""
    start_fx = FX(
        fx_type=FXType.DI if direction == "up" else FXType.DING,
        k=type("CLK", (), {"k_index": index * 10, "index": index, "date": datetime.now()})(),
        klines=[],
        val=start_val,
        index=0,
        done=True,
    )
    end_fx = FX(
        fx_type=FXType.DING if direction == "up" else FXType.DI,
        k=type("CLK", (), {"k_index": index * 10 + 5, "index": index, "date": datetime.now()})(),
        klines=[],
        val=end_val,
        index=0,
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


class TestFeatureFxEndSegment:
    """特征序列分型判定测试。"""

    def test_up_segment_top_fx(self):
        """向上线段：特征序列（向下笔）形成顶分型。"""
        features = [
            (0, _make_bi(0, "down", 12, 10, 12, 9)),  # left
            (1, _make_bi(1, "down", 14, 8, 14, 7)),  # mid (highest high)
            (2, _make_bi(2, "down", 10, 6, 10, 5)),  # right
        ]
        assert _feature_fx_end_segment(features, Direction.UP)

    def test_up_segment_no_top_fx(self):
        """向上线段：特征序列未形成顶分型。"""
        features = [
            (0, _make_bi(0, "down", 20, 15, 20, 14)),
            (1, _make_bi(1, "down", 15, 12, 16, 11)),  # mid not highest
            (2, _make_bi(2, "down", 12, 8, 15, 7)),
        ]
        assert not _feature_fx_end_segment(features, Direction.UP)

    def test_down_segment_bottom_fx(self):
        """向下线段：特征序列（向上笔）形成底分型。"""
        features = [
            (0, _make_bi(0, "up", 10, 15, 16, 10)),  # left
            (1, _make_bi(1, "up", 8, 18, 19, 8)),  # mid (lowest low)
            (2, _make_bi(2, "up", 15, 20, 21, 15)),  # right
        ]
        assert _feature_fx_end_segment(features, Direction.DOWN)

    def test_down_segment_no_bottom_fx(self):
        """向下线段：特征序列未形成底分型。"""
        features = [
            (0, _make_bi(0, "up", 10, 15, 16, 10)),
            (1, _make_bi(1, "up", 15, 18, 19, 14)),  # mid not lowest
            (2, _make_bi(2, "up", 18, 20, 22, 17)),
        ]
        assert not _feature_fx_end_segment(features, Direction.DOWN)

    def test_insufficient_features(self):
        """特征笔不足3个不应形成分型。"""
        features = [
            (0, _make_bi(0, "down", 20, 15, 20, 14)),
            (1, _make_bi(1, "down", 15, 10, 16, 9)),
        ]
        assert not _feature_fx_end_segment(features, Direction.UP)


class TestFindXds:
    """线段查找测试。"""

    def test_basic_segment(self):
        """基本线段：至少3笔。"""
        # 构造一个明显的向上线段（由多个向下笔构成特征序列）
        bis = [
            _make_bi(0, "up", 10, 15, 16, 9),  # 同向笔1
            _make_bi(1, "down", 15, 12, 16, 11),  # 特征1
            _make_bi(2, "down", 12, 8, 14, 7),  # 特征2 (bottom)
            _make_bi(3, "up", 8, 12, 13, 7),  # 同向笔2
        ]
        # 本用例聚焦特征序列分型的基本线段，隔离笔破坏默认开启的影响
        config = ChanlunConfig(xd_bi_pohuai=False)
        xds = find_xds(bis, config)
        assert len(xds) >= 1

    def test_segment_direction_alternates(self):
        """相邻线段方向应交替。"""
        # 构造振荡行情
        bis = []
        base = 10.0
        for i in range(10):
            if i % 2 == 0:
                bis.append(_make_bi(i, "up", base, base + 2, base + 3, base - 1))
            else:
                bis.append(_make_bi(i, "down", base + 2, base, base + 3, base - 1))
            base += 1

        config = ChanlunConfig()
        xds = find_xds(bis, config)
        for i in range(1, len(xds)):
            assert xds[i].direction != xds[i - 1].direction, f"线段 {i - 1} 和 {i} 方向相同"

    def test_fewer_than_3_bis_no_segment(self):
        """少于3笔不应有线段。"""
        bis = [
            _make_bi(0, "up", 10, 15, 16, 9),
            _make_bi(1, "down", 15, 12, 16, 11),
        ]
        config = ChanlunConfig()
        xds = find_xds(bis, config)
        assert len(xds) == 0

    def test_empty_bis_no_segment(self):
        """空笔列表无线段。"""
        assert find_xds([]) == []


class TestSegmentDirectionConsistency:
    """线段方向一致性测试。"""

    def test_up_segment_end_higher_than_start(self):
        """向上线段终点应高于起点。"""
        # 向上线段：起点10，终点15（高于起点）
        bis = [
            _make_bi(0, "up", 10, 15, 16, 9),
            _make_bi(1, "down", 15, 12, 16, 11),
            _make_bi(2, "down", 12, 8, 14, 7),
            _make_bi(3, "up", 8, 14, 15, 7),
        ]
        config = ChanlunConfig()
        xds = find_xds(bis, config)
        for xd in xds:
            if xd.direction == Direction.UP:
                assert xd.end.val > xd.start.val, (
                    f"向上线段终点({xd.end.val})应高于起点({xd.start.val})"
                )

    def test_down_segment_end_lower_than_start(self):
        """向下线段终点应低于起点。"""
        bis = [
            _make_bi(0, "down", 20, 15, 21, 14),
            _make_bi(1, "up", 15, 18, 19, 14),
            _make_bi(2, "up", 18, 22, 23, 17),
            _make_bi(3, "down", 22, 16, 24, 15),
        ]
        config = ChanlunConfig()
        xds = find_xds(bis, config)
        for xd in xds:
            if xd.direction == Direction.DOWN:
                assert xd.end.val < xd.start.val, (
                    f"向下线段终点({xd.end.val})应低于起点({xd.start.val})"
                )
