"""真实行情金标快照回归（V603）。

把 SZ000001 一段真实日线（2025-01-13 ~ 2025-09-08，160 根，前复权）固化为
fixture，锁定当前（已按缠论原文修正后的）缠论结构：笔/线段/中枢/买卖点/背驰
的计数与几何不变量。任何后续算法改动若改变这些金标，必须有意识地更新快照。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from easy_tdx.chanlun import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import Direction
from easy_tdx.web.routers.stock_pick import _run_timing_one

FIXTURE = Path(__file__).parent.parent / "fixtures" / "chanlun_000001_daily.json"


def _load_df() -> pd.DataFrame:
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def result():
    df = _load_df()
    return ChanlunAnalyser(code="SZ000001", frequency="daily", config=ChanlunConfig(zs_from_xd=False)).process_klines(df)


def test_fixture_loads(result) -> None:
    assert len(result.klines) == 160


def test_counts_locked(result) -> None:
    assert len(result.bis) == 12  # V740 笔算法修正后伪拆分合并（两底间取最高顶）
    # 假破坏恢复（第71-78课）：笔破坏暂定+真破坏确认后，原 3 段合并为 2 段
    assert len(result.xds) == 2
    # V733 原文中枢口径：ZG/ZD 前三笔冻结（第17/20/35课）。
    # 中枢变窄后，原本被并入 zs0 的一段震荡不再与 [ZD,ZG] 重叠 → 中枢提前
    # 结束，故由 2 个变为 3 个（实测确认，非笔/线段变化所致：bis/xds 未变）。
    assert len(result.zss) == 3
    # V735→V851：原文口径 + 前视修复后 mmds 由 4 → **2**。
    # 消失的 2 个（实测）：
    #   1) SELL_1 @ bi3（high=11.04 > zs0.zg=10.63，顶背驰成立）
    #   2) BUY_3  @ bi10
    # 原文依据（第17课）：「缠中说禅趋势：在任何级别的任何走势中，某完成的
    #   走势类型**至少包含两个以上依次同向**的缠中说禅走势中枢」。
    # 第21课：「一个上涨趋势确定后，不可能再有第一类与第二类买点」。
    # ⇒ 1买/1卖 必须建立在已成立的趋势（≥2 个同向中枢）之上。
    # bi3 时（bar 30→38）只有 zs0 一个中枢（zs0 到 bar 53 才结束），
    # zs1/zs2 都在**未来** ⇒ 不满足「趋势确立」，SELL_1 被门控挡掉。
    # ⚠️ 这正是 V851 修掉的**前视**：旧实现 `_calc_trend_strength(zss)` 用
    #   **全部**中枢算全局强度（含未来的 zs1/zs2），于是 bi3 靠未来的中枢
    #   「凑出」趋势 → 误报 SELL_1。V851 改为 per-bi `_prior_zss`（只用截至
    #   该笔已成立的中枢），前视消失，信号随之减少。
    # bis/xds/zss 三个结构计数**均未变**（12/2/3），只有信号数变化。
    assert len(result.mmds) == 2
    # V740：笔 high/low 改为区间真实极值后，中枢 zg 上移，盘整背驰力度对比变化，
    # 1 个笔背驰（bi3 力度 < bi1）正确显现。
    # V733：中枢由 2 个变 3 个后，新增中枢[1] 的盘整背驰 → bcs 1→2（实测确认）
    assert len(result.bcs) == 2


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
        # V730 原文口径（第17/20课）：ZG/ZD 由前两个走势的重叠确定后冻结；
        # 第3笔起为延伸，不改变 ZG/ZD。gg/dd 为全部走势极值。
        if len(zs.lines) >= 2:
            first2 = zs.lines[:3]  # V733：前三笔冻结（原文口径）
            assert zs.zg == min(line.high for line in first2), f"zg 应为前三笔 min(high) {zs}"
            assert zs.zd == max(line.low for line in first2), f"zd 应为前三笔 max(low) {zs}"
        if zs.lines:
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
            assert m.bi.low > m.zs.zg, m.msg
        elif t == "3sell":
            assert m.bi is not None and m.zs is not None, m.msg
            assert m.bi.high < m.zs.zd, m.msg


def test_mmd_second_type_structure(result) -> None:
    """二类买卖点结构：2买/类2买 = 一买后回踩不创新低；2卖/类2卖 = 一卖后反抽不创新高。"""
    ones_buy = [m for m in result.mmds if m.mmd_type.value == "1buy" and m.bi is not None]
    ones_sell = [m for m in result.mmds if m.mmd_type.value == "1sell" and m.bi is not None]
    for m in result.mmds:
        t = m.mmd_type.value
        if t in ("2buy", "2buy_s") and m.bi is not None:
            assert any(o.bi.low < m.bi.low and o.bi.index < m.bi.index for o in ones_buy), m.msg
        elif t in ("2sell", "2sell_s") and m.bi is not None:
            assert any(o.bi.high > m.bi.high and o.bi.index < m.bi.index for o in ones_sell), m.msg


def test_timing_response_novice_fields() -> None:
    """择时输出必须包含 verdict / novice_advice / signal_quality 三个小白字段。"""
    df = _load_df()
    out = _run_timing_one(df, "SZ:000001", "SZ", "000001", date(2025, 9, 8))
    assert "error" not in out
    assert out["verdict"]["action"] in ("买入", "卖出", "观望")
    assert out["novice_advice"] is not None
    assert out["novice_advice"]["explanation"]
    assert out["signal_quality"]["summary"]
    # structure 计数与快照一致（V730 原文中枢口径后 zs 3→2）
    assert out["structure"]["bi_count"] == 12
    assert out["structure"]["zs_count"] == 3  # V733：中枢变窄 → 2→3
    # V851：前视修复（_calc_trend_strength 全局 → per-bi _prior_zss）后，
    # 用未来中枢「凑趋势」的 SELL_1@bi3 与 BUY_3@bi10 消失，mmd 3→2。
    # 详见 test_counts_locked 的原文依据（第17/21课）与前视说明。
    assert out["structure"]["mmd_count"] == 2
    assert out["structure"]["bc_count"] == 2  # V733：中枢变窄多出 1 个盘整背驰


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
