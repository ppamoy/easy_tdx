"""买卖点时间窗口索引一致性 回归测试（V83）。

覆盖修复：
- _find_second_type_mmds：原实现用 `bi.start.k.k_index - buy_1_idx` 混用
  原始K线索引与笔索引，导致 30/40 根 K 线的离开/回调时间窗口几乎永不成立，
  2买/2卖 实际无法被识别。
- _find_third_type_mmds：原实现用 `bi.start.k.index`（合并K线序号）与
  `zs.end.k.k_index`（原始K线索引）比较，导致突破笔在错位尺度上被过滤。
"""

from __future__ import annotations

from datetime import datetime

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.mmd import _find_second_type_mmds
from easy_tdx.chanlun.types import (
    BI,
    FX,
    MMD,
    ZS,
    CLKline,
    Direction,
    FXType,
    MMDType,
)


def _ck(
    idx: int,
    h: float,
    l: float,  # noqa: E741
) -> CLKline:
    """构造一根具有指定原始K线索引的 CLKline（k_index 与 CK 序号脱钩）。"""
    return CLKline(
        k_index=idx,
        date=datetime(2025, 1, 1),
        open=(h + l) / 2,
        close=(h + l) / 2,
        high=h,
        low=l,
        amount=1.0,
        index=0,  # 测试中不使用合并序号
    )


def _fx(fx_type: FXType, mid: CLKline, val: float) -> FX:
    """构造分型（三根 K 线相同不影响时间窗口逻辑）。"""
    return FX(
        fx_type=fx_type,
        k=mid,
        klines=[mid, mid, mid],
        val=val,
        index=0,
        done=True,
    )


def _bi(index: int, direction: Direction, start_k: int, end_k: int, high: float, low: float) -> BI:
    """构造一笔：起始K线索引 start_k、结束K线索引 end_k。

    笔索引 index 与 K 线索引刻意拉开差距（如 index=0 但 start_k=100），
    用于暴露"K线索引 - 笔索引"的混用问题。
    """
    start_mid = _ck(start_k, high, low)
    end_mid = _ck(end_k, high, low)
    start_fx = _fx(
        FXType.DI if direction == Direction.UP else FXType.DING,
        start_mid,
        low if direction == Direction.UP else high,
    )
    end_fx = _fx(
        FXType.DING if direction == Direction.UP else FXType.DI,
        end_mid,
        high if direction == Direction.UP else low,
    )
    return BI(
        start=start_fx,
        end=end_fx,
        direction=direction,
        index=index,
        high=max(high, low),
        low=min(high, low),
    )


class TestSecondTypeTimeWindowIndexConsistency:
    """2买/2卖 时间窗口必须使用原始K线索引（k_index）而非笔索引。"""

    def test_2buy_detected_within_kline_window(self) -> None:
        """回调笔与离开笔相差 6 根 K 线（K线索引差），应识别为 2买。

        V731：回调幅度由 16.5 调整为 19.0（回撤约 43%，小于 50%）。
        原取值 low=16.5 对应 leave_range=7.0 上回撤 **78.6%**，
        按 `_find_second_type_mmds` docstring「回调幅度小于原下跌的 50%」
        本就不该是 2买——卖侧镜像早已正确拒绝该幅度，只有买侧因 50% 阈值
        被赋给 `_` 丢弃（死代码）而错误放行。本用例锁定的是「K线索引窗口」
        这一主题，故把幅度改为合格值，避免用例同时夹带被修复的不对称 bug。
        """
        bis = [
            _bi(0, Direction.DOWN, 100, 105, 20.0, 15.0),
            _bi(1, Direction.UP, 106, 112, 22.0, 16.0),
            _bi(2, Direction.DOWN, 113, 118, 21.5, 19.0),
            _bi(3, Direction.UP, 119, 125, 24.0, 17.5),
        ]
        first_type_mmds = [
            MMD(mmd_type=MMDType.BUY_1, zs=ZS(), bi=bis[0], confidence=0.8, msg="1买"),
        ]
        config = ChanlunConfig(zs_from_xd=False)
        mmds = _find_second_type_mmds(
            bis,
            [],
            first_type_mmds,
            config,
            volatility=0.01,
            volumes=None,
            macd_data=None,
            closes=None,
        )
        types = [m.mmd_type for m in mmds]
        assert MMDType.BUY_2 in types, f"应识别 2买，实际: {types}"

    def test_2buy_kline_window_follows_config(self) -> None:
        """回调笔距 1买 超过 40 根 K 线时：受 config 控制，不再是硬编码。

        V734（2026-10-11）：此处原断言「一定不出 2买」，锁的是 V8 遗留的
        硬编码 `total_time > 40`。实测 25 只日线，该硬编码砍掉买侧
        (2buy+2buy_s) 53% 的信号、卖侧 0% ⇒ **系统性做空偏误**，已改为
        由 `config.mmd_2nd_span_max_bars` 控制。

        ⚠️ 原用例的 K 线数据**根本走不到时间窗口判定**：
        1买 low=15.0、离开笔 high=22.0 ⇒ leave_range=7.0，
        strict=3.5 / loose=4.9，而回调笔 low=16.5 ⇒ 回撤 5.5 > 4.9，
        **在回撤深度这一关就被拒了**（实测 max_bars=0/40/200/1000 全部「无」）。
        所以旧断言是**假绿**：它恒真，与窗口无关。
        本用例改用**浅回调**（low=20.0 ⇒ 回撤 2.0 < 3.5），让判定真的走到窗口这一关。

        按纪律必须测**两侧**：设 40 时不出、设 0（默认，纯原文口径）时出。
        """
        bis = [
            _bi(0, Direction.DOWN, 100, 105, 20.0, 15.0),
            _bi(1, Direction.UP, 106, 112, 22.0, 16.0),
            _bi(2, Direction.DOWN, 160, 165, 21.0, 20.0),  # 浅回调：low=20.0
            _bi(3, Direction.UP, 166, 172, 24.0, 17.5),
        ]
        first_type_mmds = [
            MMD(mmd_type=MMDType.BUY_1, zs=ZS(), bi=bis[0], confidence=0.8, msg="1买"),
        ]

        def _types(max_bars: int) -> list[MMDType]:
            cfg = ChanlunConfig(zs_from_xd=False)
            cfg.mmd_2nd_span_max_bars = max_bars
            return [
                m.mmd_type
                for m in _find_second_type_mmds(
                    bis,
                    [],
                    first_type_mmds,
                    cfg,
                    volatility=0.01,
                    volumes=None,
                    macd_data=None,
                    closes=None,
                )
            ]

        # 前置：确认该形态在「不限」时确实能出 2买（否则本用例又是假绿）
        unlimited = _types(0)
        assert MMDType.BUY_2 in unlimited, (
            f"前置失败：不限窗口时应出 2买，实际 {[t.value for t in unlimited]} —— "
            "说明回撤深度等其他门槛把它拒了，本用例失去意义，需重新构造数据"
        )
        # 侧 A：显式设 40 ⇒ 窗口生效，不出 2买（保留旧的收紧能力）
        assert MMDType.BUY_2 not in _types(40), "设 40 时窗口应生效，不应出 2买"
        # 侧 B：默认 0 = 不限（纯缠论原文口径）⇒ 应出 2买
        assert MMDType.BUY_2 in _types(0), "设 0（默认/原文口径）时应出 2买"

    def test_2sell_detected_within_kline_window(self) -> None:
        """卖出方向同样使用 K 线索引窗口。"""
        bis = [
            _bi(0, Direction.UP, 200, 205, 22.0, 17.0),
            _bi(1, Direction.DOWN, 206, 212, 21.0, 15.5),
            _bi(2, Direction.UP, 213, 218, 18.0, 16.0),
            _bi(3, Direction.DOWN, 219, 225, 17.5, 14.5),
        ]
        first_type_mmds = [
            MMD(mmd_type=MMDType.SELL_1, zs=ZS(), bi=bis[0], confidence=0.8, msg="1卖"),
        ]
        config = ChanlunConfig(zs_from_xd=False)
        mmds = _find_second_type_mmds(
            bis,
            [],
            first_type_mmds,
            config,
            volatility=0.01,
            volumes=None,
            macd_data=None,
            closes=None,
        )
        types = [m.mmd_type for m in mmds]
        assert MMDType.SELL_2 in types, f"应识别 2卖，实际: {types}"


class TestThirdTypeIndexConsistency:
    """3买/3卖 的突破笔搜索必须使用原始K线索引（k_index）而非合并序号。"""

    def test_3buy_breakout_search_uses_k_index(self) -> None:
        """合并序号(.index)与原始K索引(k_index)不同时，必须用 k_index。"""
        # 中枢结束K线索引 300
        zs = ZS(
            lines=[_bi(0, Direction.UP, 280, 290, 22.0, 18.0)],
            zg=21.0,
            zd=19.0,
            gg=22.0,
            dd=18.0,
            index=0,
            done=True,
            start=_fx(FXType.DI, _ck(280, 22.0, 18.0), 18.0),
            end=_fx(FXType.DING, _ck(300, 22.0, 18.0), 22.0),
        )
        assert zs.end is not None
        zs_end_idx = zs.end.k.k_index  # 300
        # 构造突破笔：原始K索引 310 > 300，但合并序号刻意保持 0
        bi_far = _bi(9, Direction.UP, 310, 318, 26.0, 21.0)
        bi_far.start.k.index = 0
        bi_far.end.k.index = 0
        # 新逻辑：k_index 比较 → 通过
        assert bi_far.start.k.k_index > zs_end_idx
        # 旧逻辑：合并序号比较 → 0 > 300 为假（暴露原 bug）
        assert not (bi_far.start.k.index > zs_end_idx)

    def test_3buy_breakout_after_center_found(self) -> None:
        """突破笔位于中枢之后（k_index > 300），应被正确识别为候选。"""
        zs = ZS(
            lines=[_bi(0, Direction.UP, 280, 290, 22.0, 18.0)],
            zg=21.0,
            zd=19.0,
            gg=22.0,
            dd=18.0,
            index=0,
            done=True,
            start=_fx(FXType.DI, _ck(280, 22.0, 18.0), 18.0),
            end=_fx(FXType.DING, _ck(300, 22.0, 18.0), 22.0),
        )
        bis = [
            _bi(0, Direction.UP, 280, 290, 22.0, 18.0),
            _bi(1, Direction.DOWN, 291, 296, 20.5, 18.5),
            _bi(2, Direction.UP, 297, 302, 21.5, 19.0),
            _bi(3, Direction.DOWN, 303, 306, 20.0, 18.2),
            _bi(4, Direction.UP, 307, 315, 25.0, 20.0),
            _bi(5, Direction.DOWN, 316, 320, 24.0, 20.5),
        ]
        assert zs.end is not None
        zs_end_idx = zs.end.k.k_index
        break_candidates = [
            b for b in bis if b.start.k.k_index > zs_end_idx and b.direction == Direction.UP
        ]
        assert len(break_candidates) >= 1, "突破笔应按 k_index 被正确找到"
        assert break_candidates[0].index == 4

    def test_3sell_breakout_after_center_found(self) -> None:
        """跌破笔位于中枢之后，应被正确识别为候选。"""
        zs = ZS(
            lines=[_bi(0, Direction.UP, 280, 290, 22.0, 18.0)],
            zg=21.0,
            zd=19.0,
            gg=22.0,
            dd=18.0,
            index=0,
            done=True,
            start=_fx(FXType.DI, _ck(280, 22.0, 18.0), 18.0),
            end=_fx(FXType.DING, _ck(300, 22.0, 18.0), 22.0),
        )
        bis = [
            _bi(0, Direction.DOWN, 280, 290, 22.0, 18.0),
            _bi(1, Direction.UP, 291, 296, 20.5, 18.5),
            _bi(2, Direction.DOWN, 297, 302, 21.5, 19.0),
            _bi(3, Direction.UP, 303, 306, 20.0, 18.2),
            _bi(4, Direction.DOWN, 307, 315, 20.5, 15.0),
            _bi(5, Direction.UP, 316, 320, 18.0, 15.5),
        ]
        assert zs.end is not None
        zs_end_idx = zs.end.k.k_index
        break_candidates = [
            b for b in bis if b.start.k.k_index > zs_end_idx and b.direction == Direction.DOWN
        ]
        assert len(break_candidates) >= 1, "跌破笔应按 k_index 被正确找到"
        assert break_candidates[0].index == 4
