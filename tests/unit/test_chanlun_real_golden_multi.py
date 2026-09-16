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
CASES = [
    ("chanlun_600519_daily.json", "daily", (15, 1, 4, 2, 1)),
    ("chanlun_000333_daily.json", "daily", (15, 1, 2, 0, 1)),
    ("chanlun_000001_weekly.json", "weekly", (15, 2, 3, 2, 2)),
    ("chanlun_000001_30min.json", "30min", (13, 1, 3, 0, 1)),
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
        if zs.lines:
            assert zs.zg == min(line.high for line in zs.lines)
            assert zs.zd == max(line.low for line in zs.lines)
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
            assert m.bi.low > m.zs.zg * 1.005, m.msg
        elif t == "3sell":
            assert m.bi is not None and m.zs is not None, m.msg
            assert m.bi.high < m.zs.zd * 0.995, m.msg


def test_mmd_second_type_structure(case) -> None:
    res, _ = case
    ones_buy = [m for m in res.mmds if m.mmd_type.value == "1buy" and m.bi is not None]
    ones_sell = [m for m in res.mmds if m.mmd_type.value == "1sell" and m.bi is not None]
    for m in res.mmds:
        t = m.mmd_type.value
        if t in ("2buy", "2buy_s") and m.bi is not None:
            assert any(
                o.bi.low < m.bi.low and o.bi.index < m.bi.index for o in ones_buy
            ), m.msg
        elif t in ("2sell", "2sell_s") and m.bi is not None:
            assert any(
                o.bi.high > m.bi.high and o.bi.index < m.bi.index for o in ones_sell
            ), m.msg


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