"""多标的/多周期真实行情金标快照回归（V604）。

对多只股票、多周期固化真实行情快照，锁定缠论结构计数与几何不变量。
任何算法改动若改变这些金标，必须有意识地更新快照。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from easy_tdx.chanlun import ChanlunAnalyser
from easy_tdx.chanlun.types import Direction

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"

# (fixture 文件名, frequency, 期望计数 bi/xd/zs/mmd/bc)
# V730：600519_daily 的 mmd 5→3——旧「趋势背驰」用中枢末笔(lines[-1])对比且不锚定
# 候选笔，把中枢延伸期的 bi6/bi14 误标为 1卖（连带 2卖）。修正为离开段口径
# （bis[lines[-1].index+1]，与 beichi._check_qs_beichi 一致）后，该段行情第二离开段
# (bi15) 超出数据末端、无有效趋势背驰，1卖/2卖 按原文正确消失。
# V730 P1-4：600519_daily 的 xd 1→2——旧实现对「向下笔低点跌破特征序列分型
# 极值」这一情况二场景以「第4特征元素分型且创新低」粗糙近似，导致 1578.34 前的
# 突破分型被漏判（欠分段，正是用户反馈的「线段画不准」）。改为按第71课真实价格
# 击穿判定（bi.low < gap_fx_extreme）后，UP 段正确止于 1578.34 并衔接 DOWN 段。
CASES = [
    ("chanlun_600519_daily.json", "daily", (15, 2, 4, 3, 1)),
    ("chanlun_000333_daily.json", "daily", (15, 4, 2, 1, 1)),
    ("chanlun_000001_weekly.json", "weekly", (15, 2, 3, 3, 2)),
    ("chanlun_000001_30min.json", "30min", (13, 1, 3, 2, 1)),
]


@pytest.fixture(scope="module", params=CASES, ids=[c[0] for c in CASES])
def case(request):
    fname, freq, counts = request.param
    rows = json.loads((FIXTURE_DIR / fname).read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    res = ChanlunAnalyser(code=fname, frequency=freq).process_klines(df)
    return res, counts


def test_counts_locked(case) -> None:
    res, counts = case
    exp_bi, exp_xd, exp_zs, exp_mmd, exp_bc = counts
    assert len(res.bis) == exp_bi
    assert len(res.xds) == exp_xd
    assert len(res.zss) == exp_zs
    assert len(res.mmds) == exp_mmd
    assert len(res.bcs) == exp_bc


def test_to_dict_serializes(case) -> None:
    """to_dict 序列化不崩溃；分钟级日期应含时分（V623 字符串日期归一化）。"""
    res, _ = case
    d = res.to_dict()
    assert "bis" in d and "mmds" in d and "bcs" in d
    if res.frequency == "30min":
        assert any(":" in bi["start_date"] for bi in d["bis"])


def test_bi_endpoints_on_extremes(case) -> None:
    res, _ = case
    klines = res.klines
    for bi in res.bis:
        sb = klines[bi.start.bar_index]
        eb = klines[bi.end.bar_index]
        if bi.direction == Direction.UP:
            assert bi.start.val == sb.low
            assert bi.end.val == eb.high
        else:
            assert bi.start.val == sb.high
            assert bi.end.val == eb.low


def test_zs_semantics(case) -> None:
    res, _ = case
    for zs in res.zss:
        assert zs.zg > zs.zd
        assert zs.gg >= zs.zg
        assert zs.dd <= zs.zd
        # V730 原文口径（第17/20课）：ZG/ZD 由前两个走势的重叠确定后冻结；
        # 第3笔起为延伸，不改变 ZG/ZD。gg/dd 为全部走势极值。
        if len(zs.lines) >= 2:
            first2 = zs.lines[:2]
            assert zs.zg == min(line.high for line in first2), f"zg 应为前两笔 min(high) {zs}"
            assert zs.zd == max(line.low for line in first2), f"zd 应为前两笔 max(low) {zs}"
        if zs.lines:
            assert zs.gg == max(line.high for line in zs.lines)
            assert zs.dd == min(line.low for line in zs.lines)


def test_beichi_force_ratio_and_anchor(case) -> None:
    from easy_tdx.chanlun.mmd_conditions import _calc_bi_force

    res, _ = case
    closes = [k.close for k in res.klines]
    klines = res.klines
    for bc in res.bcs:
        curr, prev = bc.curr, bc.prev
        cf = _calc_bi_force(curr, closes, curr.index)
        pf = _calc_bi_force(prev, closes, prev.index)
        if pf > 0 and cf > 0:
            assert cf < pf * 0.8, bc.msg
        anchor = bc.curr.end if bc.curr else None
        if anchor is not None:
            bar = klines[anchor.bar_index]
            assert anchor.val in (bar.high, bar.low), bc.msg


def test_mmd_structure_position(case) -> None:
    res, _ = case
    for m in res.mmds:
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


def test_mmd_second_type_structure(case) -> None:
    res, _ = case
    ones_buy = [m for m in res.mmds if m.mmd_type.value == "1buy" and m.bi is not None]
    ones_sell = [m for m in res.mmds if m.mmd_type.value == "1sell" and m.bi is not None]
    for m in res.mmds:
        t = m.mmd_type.value
        if t in ("2buy", "2buy_s") and m.bi is not None:
            assert any(o.bi.low < m.bi.low and o.bi.index < m.bi.index for o in ones_buy), m.msg
        elif t in ("2sell", "2sell_s") and m.bi is not None:
            assert any(o.bi.high > m.bi.high and o.bi.index < m.bi.index for o in ones_sell), m.msg


def test_bi_end_to_end(case) -> None:
    res, _ = case
    for i in range(len(res.bis) - 1):
        assert res.bis[i].end.bar_index == res.bis[i + 1].start.bar_index
        assert res.bis[i].end.val == res.bis[i + 1].start.val


def test_xd_direction_and_pivot(case) -> None:
    res, _ = case
    for xd in res.xds:
        if xd.direction == Direction.UP:
            assert xd.end.val > xd.start.val
        else:
            assert xd.end.val < xd.start.val
    for i in range(len(res.xds) - 1):
        assert res.xds[i].end.bar_index == res.xds[i + 1].start.bar_index
        assert res.xds[i].end.val == res.xds[i + 1].start.val


def test_xd_endpoints_anchor_on_fractal_extremes(case) -> None:
    """线段端点必为特征序列分型点的极值，落在 [low, high] 区间内。"""
    res, _ = case
    for xd in res.xds:
        assert xd.low <= xd.start.val <= xd.high, f"线段起点越界 {xd}"
        assert xd.low <= xd.end.val <= xd.high, f"线段终点越界 {xd}"
        # 向上线段终点高于起点、向下线段终点低于起点
        if xd.direction == Direction.UP:
            assert xd.end.val > xd.start.val
        else:
            assert xd.end.val < xd.start.val


def test_beichi_new_extreme_gate(case) -> None:
    res, _ = case
    for bc in res.bcs:
        bc_type = bc.bc_type.value
        if bc_type in ("bi", "qs"):
            curr, prev = bc.curr, bc.prev
            if curr.direction == Direction.UP:
                assert curr.high > prev.high, bc.msg
            else:
                assert curr.low < prev.low, bc.msg
        else:
            assert bc.curr.direction == bc.prev.direction


def test_mmd_anchor_on_extreme(case) -> None:
    res, _ = case
    klines = res.klines
    for m in res.mmds:
        bi_ = m.bi
        if bi_ is None:
            continue
        bar = klines[bi_.end.bar_index]
        if "buy" in m.mmd_type.value:
            assert bi_.end.val == bar.low
        else:
            assert bi_.end.val == bar.high
