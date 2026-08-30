"""一类买卖点趋势门控 回归测试（V83）。

覆盖修复：
- 1买/1卖 必须建立在真实趋势之上（≥2 个同向中枢，trend_strength>0）；
  纯震荡市（单中枢）不再产生 1买/1卖。
- 1买/1卖 只认趋势背驰（笔背驰/两中枢趋势背驰），不再把盘整背驰算作一买。
- _reference_zs_for_bi 返回笔所对应的同期参考中枢。
"""

from __future__ import annotations

from datetime import datetime

from easy_tdx.chanlun.mmd import _calc_zs_avg_volume, _is_strong_beichi, _reference_zs_for_bi
from easy_tdx.chanlun.types import BI, FX, ZS, CLKline, Direction, FXType


def _ck(idx: int, h: float, low: float) -> CLKline:
    return CLKline(
        k_index=idx,
        date=datetime(2025, 1, 1),
        open=(h + low) / 2,
        close=(h + low) / 2,
        high=h,
        low=low,
        amount=1.0,
        index=0,
    )


def _fx(fx_type: FXType, mid: CLKline, val: float) -> FX:
    return FX(fx_type=fx_type, k=mid, klines=[mid, mid, mid], val=val, index=0, done=True)


def _bi(index: int, direction: Direction, start_k: int, end_k: int, high: float, low: float) -> BI:
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


class TestReferenceZsForBi:
    """参考中枢应取笔发生时的同期中枢，而非数据末端最后中枢。"""

    def test_returns_contemporaneous_center(self) -> None:
        zs_a = ZS(
            lines=[_bi(0, Direction.UP, 100, 110, 22.0, 18.0)],
            zg=21.0,
            zd=19.0,
            gg=22.0,
            dd=18.0,
            index=0,
            done=True,
            start=_fx(FXType.DI, _ck(100, 22.0, 18.0), 18.0),
            end=_fx(FXType.DING, _ck(110, 22.0, 18.0), 22.0),
        )
        zs_b = ZS(
            lines=[_bi(1, Direction.UP, 200, 210, 18.0, 14.0)],
            zg=17.0,
            zd=15.0,
            gg=18.0,
            dd=14.0,
            index=1,
            done=True,
            start=_fx(FXType.DI, _ck(200, 18.0, 14.0), 14.0),
            end=_fx(FXType.DING, _ck(210, 18.0, 14.0), 18.0),
        )
        # 一笔从 150 开始（在 A 之后、B 之前）→ 应参考 A
        bi = _bi(2, Direction.DOWN, 150, 160, 20.0, 15.0)
        ref = _reference_zs_for_bi([zs_a, zs_b], bi)
        assert ref is zs_a

    def test_falls_back_to_last_center_for_final_break(self) -> None:
        """最终跌破笔（中枢尚未在其前结束）应退而取最后中枢。"""
        zs = ZS(
            lines=[_bi(0, Direction.UP, 100, 110, 20.0, 16.0)],
            zg=19.0,
            zd=17.0,
            gg=20.0,
            dd=16.0,
            index=0,
            done=False,
            start=_fx(FXType.DI, _ck(100, 20.0, 16.0), 16.0),
            end=_fx(FXType.DING, _ck(130, 20.0, 16.0), 20.0),
        )
        bi = _bi(1, Direction.DOWN, 140, 150, 18.0, 13.0)
        ref = _reference_zs_for_bi([zs], bi)
        assert ref is zs


class TestTrendBeichiExcludesConsolidation:
    """1买/1卖 只认趋势背驰，盘整背驰不再触发。"""

    def test_consolidation_divergence_alone_not_trend_beichi(self) -> None:
        """单中枢内末笔力度衰减（盘整背驰）不应判定为趋势背驰。"""
        # 中枢内三笔，末笔力度弱于首笔——纯盘整背驰场景
        zs = ZS(
            lines=[
                _bi(0, Direction.DOWN, 100, 108, 20.0, 16.0),
                _bi(1, Direction.UP, 109, 115, 19.5, 16.5),
                _bi(2, Direction.DOWN, 116, 122, 19.0, 16.8),
            ],
            zg=19.5,
            zd=16.8,
            gg=20.0,
            dd=16.0,
            index=0,
            done=True,
            start=_fx(FXType.DING, _ck(100, 20.0, 16.0), 20.0),
            end=_fx(FXType.DI, _ck(122, 19.0, 16.8), 16.8),
        )
        # 末笔（index 2）力度 < 首笔（index 0）：盘整背驰条件成立
        # 但末笔没有创新低（16.8 > 16.0）→ 不是趋势背驰
        bis_list: list[BI] = list(zs.lines)  # type: ignore[arg-type]
        result = _is_strong_beichi(bis_list[-1], bis_list, [zs], None, 0.8, "down")
        assert result is False

    def test_new_low_with_force_decay_is_trend_beichi(self) -> None:
        """创出新低且力度衰减 → 趋势背驰成立。"""
        # 前笔低点 16.0，末笔低点 15.0（创新低）
        bis = [
            _bi(0, Direction.DOWN, 100, 108, 20.0, 16.0),
            _bi(1, Direction.UP, 109, 115, 19.5, 16.5),
            _bi(2, Direction.DOWN, 116, 122, 18.0, 15.0),  # 创新低 15.0
        ]
        # 用幅度作为力度代理：末笔幅度(18-15=3) < 首笔幅度(20-16=4)*0.8
        result = _is_strong_beichi(bis[2], bis, [], None, 0.8, "down")
        assert result is True


class TestZsAvgVolume:
    """中枢盘整期均量：作为突破/跌破量能比较基准。"""

    def test_center_span_average(self) -> None:
        """中枢均量 = 构成笔覆盖K线区间的平均成交量。"""
        zs = ZS(
            lines=[
                _bi(0, Direction.UP, 100, 110, 20.0, 16.0),
                _bi(1, Direction.DOWN, 111, 120, 19.5, 16.5),
                _bi(2, Direction.UP, 121, 130, 19.8, 16.8),
            ],
            zg=19.5,
            zd=16.8,
            gg=20.0,
            dd=16.0,
            index=0,
            done=True,
            start=_fx(FXType.DING, _ck(100, 20.0, 16.0), 20.0),
            end=_fx(FXType.DI, _ck(130, 19.8, 16.8), 16.8),
        )
        # K线 100-130 的成交量：区间内前10根 1000，后21根 2000（volumes 索引与 k_index 对齐）
        volumes = [0.0] * 131  # 索引 0-130
        for i in range(100, 131):
            volumes[i] = 1000.0 if i < 110 else 2000.0
        avg = _calc_zs_avg_volume(volumes, zs)
        # 区间 [100, 130] 共 31 根：10*1000 + 21*2000 = 52000 / 31
        assert abs(avg - 52000 / 31) < 1e-6, f"应取中枢覆盖区间均量, got {avg}"

    def test_empty_volumes_returns_zero(self) -> None:
        zs = ZS(lines=[_bi(0, Direction.UP, 100, 110, 20.0, 16.0)], zg=19.0, zd=17.0, index=0)
        assert _calc_zs_avg_volume(None, zs) == 0.0

    def test_out_of_range_clamped(self) -> None:
        """K线索引超出成交量长度时应收敛到有效区间，不崩溃。"""
        zs = ZS(
            lines=[_bi(0, Direction.UP, 95, 200, 20.0, 16.0)],
            zg=19.0,
            zd=17.0,
            index=0,
            start=_fx(FXType.DI, _ck(95, 20.0, 16.0), 16.0),
            end=_fx(FXType.DING, _ck(200, 20.0, 16.0), 20.0),
        )
        volumes = [1.0] * 10  # 只有10根（索引0-9）
        avg = _calc_zs_avg_volume(volumes, zs)
        # 区间被钳制到 [0, 9]，均量为 1.0
        assert avg == 1.0
