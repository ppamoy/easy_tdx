"""缠论v86笔计算改进测试。

测试改进内容：
1. 端点方向一致性校验
2. 弱笔检测
3. 分型陷阱回归
"""

from __future__ import annotations

from datetime import datetime

from easy_tdx.chanlun.bi import _is_weak_bi, find_bis
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.fractal import find_fractals
from easy_tdx.chanlun.kline_merge import merge_klines
from easy_tdx.chanlun.types import CLKline, Direction, FXType, Kline


def _k(idx: int, dt: str, o: float, c: float, h: float, lo: float) -> Kline:
    return Kline(
        index=idx,
        date=datetime.strptime(dt, "%Y-%m-%d"),
        open=o,
        close=c,
        high=h,
        low=lo,
        amount=0.0,
    )


def _ck(idx: int, dt: str, o: float, c: float, h: float, lo: float) -> CLKline:
    return CLKline(
        k_index=idx,
        date=datetime.strptime(dt, "%Y-%m-%d"),
        open=o,
        close=c,
        high=h,
        low=lo,
        amount=0.0,
        index=0,
        merged_count=1,
        direction="",
    )


class TestBiEndpointConsistency:
    """笔端点方向一致性测试。"""

    def test_up_bi_endpoints(self):
        """向上笔：起点底分型，终点顶分型。"""
        cks = [
            _ck(0, "2025-01-02", 10, 8, 11, 8),  # 下降
            _ck(1, "2025-01-03", 9, 15, 16, 9),  # 顶分型
            _ck(2, "2025-01-06", 14, 11, 14, 10),  # 下降
            _ck(3, "2025-01-07", 10, 7, 11, 7),  # 底分型
            _ck(4, "2025-01-08", 8, 13, 14, 8),  # 上升 → 向上笔
        ]
        fxs = find_fractals(cks)
        assert len(fxs) >= 2
        bis = find_bis(fxs)
        for bi in bis:
            if bi.direction == Direction.UP:
                assert bi.start.fx_type == FXType.DI
                assert bi.end.fx_type == FXType.DING

    def test_down_bi_endpoints(self):
        """向下笔：起点顶分型，终点底分型。"""
        cks = [
            _ck(0, "2025-01-02", 10, 12, 12, 10),  # 上升
            _ck(1, "2025-01-03", 12, 15, 15, 11),  # 顶分型
            _ck(2, "2025-01-06", 14, 11, 14, 10),  # 下降
            _ck(3, "2025-01-07", 10, 8, 11, 8),  # 底分型
            _ck(4, "2025-01-08", 9, 13, 16, 9),  # 上升 → 顶分型
        ]
        fxs = find_fractals(cks)
        assert len(fxs) >= 2
        bis = find_bis(fxs)
        for bi in bis:
            if bi.direction == Direction.DOWN:
                assert bi.start.fx_type == FXType.DING
                assert bi.end.fx_type == FXType.DI


class TestWeakBiDetection:
    """弱笔检测测试。"""

    def test_weak_bi_detection(self):
        """价格变动 < 0.1% 的笔应被识别为弱笔。"""
        # 构造一个几乎水平的笔（价格变动 < 0.1%）
        start_val = 100.0
        end_val = 100.05  # 0.05% 变动
        assert _is_weak_bi(
            type("FX", (), {"val": start_val, "fx_type": FXType.DI})(),
            type("FX", (), {"val": end_val, "fx_type": FXType.DING})(),
        )
        # 正常变动不应是弱笔
        end_val2 = 101.0  # 1% 变动
        assert not _is_weak_bi(
            type("FX", (), {"val": start_val, "fx_type": FXType.DI})(),
            type("FX", (), {"val": end_val2, "fx_type": FXType.DING})(),
        )


class TestFractalTrapRegression:
    """分型陷阱回归测试。"""

    def test_fractal_trap_not_stuck(self):
        """密集交替分型不应卡死笔算法。"""
        # 下跌锯齿形：分型在连续CKline位置交替
        cks = [
            _ck(0, "2025-01-02", 145, 145, 150, 140),
            _ck(1, "2025-01-03", 130, 130, 135, 125),  # di
            _ck(2, "2025-01-06", 140, 140, 145, 135),  # ding
            _ck(3, "2025-01-07", 125, 125, 130, 120),  # di
            _ck(4, "2025-01-08", 133, 133, 138, 128),  # ding
            _ck(5, "2025-01-09", 120, 120, 125, 115),  # di
            _ck(6, "2025-01-10", 127, 127, 132, 122),  # ding
            _ck(7, "2025-01-13", 113, 113, 118, 108),  # di
            _ck(8, "2025-01-14", 121, 121, 126, 116),  # ding
            _ck(9, "2025-01-15", 107, 107, 112, 102),  # di
        ]
        fxs = find_fractals(cks)
        assert len(fxs) >= 6, f"应产生至少6个分型，实际 {len(fxs)}"

        bis = find_bis(fxs, ChanlunConfig(bi_type="simple"))
        assert len(bis) >= 2, f"密集交替分型场景应产出至少2笔，实际只有 {len(bis)} 笔"

        # 验证方向交替
        for i in range(1, len(bis)):
            assert bis[i].direction != bis[i - 1].direction, (
                f"笔 {i - 1} 和笔 {i} 方向相同 ({bis[i].direction.value})"
            )


class TestFullPipeline:
    """完整管道测试。"""

    def test_full_pipeline_produces_valid_structure(self):
        """从原始K线到笔的完整管道应产出有效结构。"""
        klines = [
            _k(0, "2025-01-02", 10, 8, 11, 8),
            _k(1, "2025-01-03", 8, 12, 13, 7),
            _k(2, "2025-01-06", 12, 16, 17, 11),
            _k(3, "2025-01-07", 16, 14, 18, 13),
            _k(4, "2025-01-08", 14, 10, 15, 9),
            _k(5, "2025-01-09", 10, 6, 11, 5),
            _k(6, "2025-01-10", 7, 12, 13, 6),
            _k(7, "2025-01-13", 12, 9, 14, 8),
        ]
        merged = merge_klines(klines)
        fxs = find_fractals(merged)
        bis = find_bis(fxs, ChanlunConfig(bi_type="simple"))
        assert len(bis) >= 1, "应产出至少1笔"

        # 验证笔方向交替
        for i in range(1, len(bis)):
            assert bis[i].direction != bis[i - 1].direction

    def test_empty_input(self):
        """空输入返回空列表。"""
        assert find_bis([]) == []

    def test_single_fractal(self):
        """单分型无法成笔。"""
        cks = [
            _ck(0, "2025-01-02", 10, 12, 12, 10),
            _ck(1, "2025-01-03", 12, 15, 15, 11),
            _ck(2, "2025-01-06", 14, 11, 14, 10),
        ]
        fxs = find_fractals(cks)
        bis = find_bis(fxs)
        assert len(bis) == 0  # 1个分型无法成笔


class TestNewBiRuleGap:
    """新笔规则间距测试。"""

    def test_new_bi_rule_needs_gap(self):
        """新笔规则：分型之间至少1根独立K线。"""
        # 只有3根K线，产生1个分型，不足以成笔
        cks = [
            _ck(0, "2025-01-02", 10, 12, 12, 10),
            _ck(1, "2025-01-03", 12, 15, 15, 11),
            _ck(2, "2025-01-06", 14, 11, 14, 10),
        ]
        fxs = find_fractals(cks)
        bis = find_bis(fxs)
        assert len(bis) == 0

    def test_old_bi_rule_needs_more_gap(self):
        """老笔规则：分型之间至少3根独立K线。"""
        config = ChanlunConfig(bi_type="old")
        # 4根K线可能只够new规则，不够old规则
        cks = [
            _ck(0, "2025-01-02", 10, 12, 12, 10),
            _ck(1, "2025-01-03", 12, 15, 15, 11),
            _ck(2, "2025-01-06", 14, 11, 14, 10),
            _ck(3, "2025-01-07", 10, 8, 11, 8),
        ]
        fxs = find_fractals(cks)
        bis = find_bis(fxs, config)
        # old规则需要更多间距，可能无笔
        assert len(bis) <= len(find_bis(fxs))  # old规则笔数 <= new规则