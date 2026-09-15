"""真实行情金标快照回归（V603）。

把 SZ000001 一段真实日线（2025-01-13 ~ 2025-09-08，160 根，前复权）固化为
fixture，锁定当前（已按缠论原文修正后的）缠论结构：笔/线段/中枢/买卖点/背驰
的计数与几何不变量。任何后续算法改动若改变这些金标，必须有意识地更新快照。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from easy_tdx.chanlun import ChanlunAnalyser
from easy_tdx.chanlun.types import Direction

FIXTURE = Path(__file__).parent.parent / "fixtures" / "chanlun_000001_daily.json"


def _load_df() -> pd.DataFrame:
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def result():
    df = _load_df()
    return ChanlunAnalyser(code="SZ000001", frequency="daily").process_klines(df)


def test_fixture_loads(result) -> None:
    assert len(result.klines) == 160


def test_counts_locked(result) -> None:
    assert len(result.bis) == 27
    assert len(result.xds) == 3
    assert len(result.zss) == 3
    assert len(result.mmds) == 4
    assert len(result.bcs) == 1  # V617 MACD 力度窗口用极值 bar_index 后，此段出现 1 个笔背驰


def test_bi_endpoints_on_extremes(result) -> None:
    klines = result.klines
    for bi in result.bis:
        sb = klines[bi.start.bar_index]
        eb = klines[bi.end.bar_index]
        if bi.direction == Direction.UP:
            assert bi.start.val == sb.low, f"向上笔起点未落低点 {bi}"
            assert bi.end.val == eb.high, f"向上笔终点未落高点 {bi}"
        else:
            assert bi.start.val == sb.high, f"向下笔起点未落高点 {bi}"
            assert bi.end.val == eb.low, f"向下笔终点未落低点 {bi}"


def test_zs_semantics(result) -> None:
    for zs in result.zss:
        assert zs.zg > zs.zd, f"中枢上沿应高于下沿 {zs}"
        assert zs.gg >= zs.zg, f"gg 应 >= zg {zs}"
        assert zs.dd <= zs.zd, f"dd 应 <= zd {zs}"
        if zs.lines:
            assert zs.zg == min(line.high for line in zs.lines), f"zg 应为 min(high) {zs}"
            assert zs.zd == max(line.low for line in zs.lines), f"zd 应为 max(low) {zs}"
            assert zs.gg == max(line.high for line in zs.lines), f"gg 应为 max(high) {zs}"
            assert zs.dd == min(line.low for line in zs.lines), f"dd 应为 min(low) {zs}"


def test_beichi_force_ratio_and_anchor(result) -> None:
    from easy_tdx.chanlun.mmd_conditions import _calc_bi_force

    closes = [k.close for k in result.klines]
    klines = result.klines
    for bc in result.bcs:
        curr, prev = bc.curr, bc.prev
        cf = _calc_bi_force(curr, closes, curr.index)
        pf = _calc_bi_force(prev, closes, prev.index)
        if pf > 0 and cf > 0:
            assert cf < pf * 0.8, f"背驰力度未衰减 {bc.msg}"
        anchor = bc.curr.end if bc.curr else None
        if anchor is not None:
            bar = klines[anchor.bar_index]
            assert anchor.val in (bar.high, bar.low), f"背驰锚点未落极值 {bc.msg}"


def test_mmd_structure_position(result) -> None:
    """买卖点结构位置：1买在下跌背驰创新低(低于中枢下沿)、1卖创新高(高于中枢上沿)、
    3买回踩不破中枢上沿、3卖反抽不破中枢下沿。"""
    for m in result.mmds:
        t = m.mmd_type.value
        if t == "1buy":
            assert m.bi is not None and m.zs is not None, m.msg
            assert m.bi.low < m.zs.zd, m.msg
        elif t == "1sell":
            assert m.bi is not None and m.zs is not None, m.msg
            assert m.bi.high > m.zs.zg, m.msg
        elif t == "3buy":
            assert m.bi is not None and m.zs is not None, m.msg
            assert m.bi.low > m.zs.zg * 1.005, m.msg
        elif t == "3sell":
            assert m.bi is not None and m.zs is not None, m.msg
            assert m.bi.high < m.zs.zd * 0.995, m.msg


def test_mmd_second_type_structure(result) -> None:
    """二类买卖点结构：2买/类2买 = 一买后回踩不创新低；2卖/类2卖 = 一卖后反抽不创新高。"""
    ones_buy = [m for m in result.mmds if m.mmd_type.value == "1buy" and m.bi is not None]
    ones_sell = [m for m in result.mmds if m.mmd_type.value == "1sell" and m.bi is not None]
    for m in result.mmds:
        t = m.mmd_type.value
        if t in ("2buy", "2buy_s") and m.bi is not None:
            assert any(
                o.bi.low < m.bi.low and o.bi.index < m.bi.index for o in ones_buy
            ), m.msg
        elif t in ("2sell", "2sell_s") and m.bi is not None:
            assert any(
                o.bi.high > m.bi.high and o.bi.index < m.bi.index for o in ones_sell
            ), m.msg


def test_bi_end_to_end(result) -> None:
    for i in range(len(result.bis) - 1):
        prev, nxt = result.bis[i], result.bis[i + 1]
        assert prev.end.bar_index == nxt.start.bar_index
        assert prev.end.val == nxt.start.val


def test_xd_direction_and_pivot(result) -> None:
    for xd in result.xds:
        if xd.direction == Direction.UP:
            assert xd.end.val > xd.start.val, f"向上线段终点应高于起点 {xd}"
        else:
            assert xd.end.val < xd.start.val, f"向下线段终点应低于起点 {xd}"
    for i in range(len(result.xds) - 1):
        assert result.xds[i].end.bar_index == result.xds[i + 1].start.bar_index
        assert result.xds[i].end.val == result.xds[i + 1].start.val


def test_beichi_new_extreme_gate(result) -> None:
    """每个笔/趋势背驰都必须满足缠论原文的创新高/新低门槛。"""
    for bc in result.bcs:
        bc_type = bc.bc_type.value
        if bc_type in ("bi", "qs"):
            curr, prev = bc.curr, bc.prev
            if curr.direction == Direction.UP:
                assert curr.high > prev.high, f"{bc_type} 背驰未创新高 {bc.msg}"
            else:
                assert curr.low < prev.low, f"{bc_type} 背驰未创新低 {bc.msg}"
        else:  # pz 盘整背驰：进入/离开同向
            assert bc.curr.direction == bc.prev.direction


def test_mmd_anchor_on_extreme(result) -> None:
    klines = result.klines
    for m in result.mmds:
        bi_ = m.bi
        if bi_ is None:
            continue
        idx = bi_.end.bar_index
        bar = klines[idx]
        if "buy" in m.mmd_type.value:
            assert bi_.end.val == bar.low, f"买点未锚定低点 {m.mmd_type.value}"
        else:
            assert bi_.end.val == bar.high, f"卖点未锚定高点 {m.mmd_type.value}"