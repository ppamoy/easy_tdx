"""第20课定理二「升级为更大级别中枢」行为级测试。

判据只有 docs/缠论108课/ 原文，逐字核对：

  第20课「缠中说禅走势中枢中心定理二」：
    「后ZG < 前ZD 且后GG >= 前DD，或 后ZD > 前ZG 且 后DD =< 前GG，
      则等价于形成**高级别的走势中枢**。」
  第33课：
    「中枢的延伸不能超过5段，也就是一旦出现6段的延伸，加上形成中枢本身
      那三段，就构成**更大级别的中枢**了。」

纪律（AGENTS.md §1/§4）：断言真实行为；每个开关测两侧 + 对照组；
证明"升级"标记**不**偷偷改区间/段数（否则就是 V851 修掉的同级别合并错误）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import BI, CLKline, Direction, FX, FXType, ZS
from easy_tdx.chanlun.zs import mark_upgraded_zss


# ── 构造工具 ──────────────────────────────────────────────────────────────


def _k(i: int, h: float, l: float) -> CLKline:
    from datetime import datetime, timedelta

    return CLKline(
        k_index=i,
        date=datetime(2025, 1, 1) + timedelta(days=i),
        open=(h + l) / 2,
        close=(h + l) / 2,
        high=h,
        low=l,
        amount=0.0,
        index=i,
    )


def _fx(i: int, v: float, t: FXType) -> FX:
    k = _k(i, v + 0.01, v - 0.01)
    return FX(fx_type=t, k=k, klines=[k], val=v, index=i, done=True)


def _bi(i: int, hi: float, lo: float, up: bool) -> BI:
    return BI(
        start=_fx(i * 2, lo if up else hi, FXType.DI if up else FXType.DING),
        end=_fx(i * 2 + 1, hi if up else lo, FXType.DING if up else FXType.DI),
        direction=Direction.UP if up else Direction.DOWN,
        index=i,
        high=hi,
        low=lo,
    )


def _zs(idx: int, zd: float, zg: float, dd: float, gg: float) -> ZS:
    return ZS(zg=zg, zd=zd, gg=gg, dd=dd, index=idx, done=True)


# ── 定理二分支一：后ZG < 前ZD 且 后GG >= 前DD ────────────────────────────


def test_theorem2_branch_a_marks_upgrade() -> None:
    """第20课定理二分支一：后ZG < 前ZD 且 后GG >= 前DD ⇒ 形成高级别中枢。"""
    # 前中枢 [10, 12]（ZD=10, ZG=12），后中枢 ZG=9 < 10 且 GG=9.5 >= DD=8
    prev = _zs(0, zd=10.0, zg=12.0, dd=9.0, gg=13.0)
    cur = _zs(1, zd=8.0, zg=9.0, dd=8.0, gg=9.5)
    n = mark_upgraded_zss([prev, cur])
    assert n == 1
    assert cur.upgraded is True
    assert cur.level == prev.level + 1
    assert 0 in cur.upgrade_from


def test_theorem2_branch_b_marks_upgrade() -> None:
    """第20课定理二分支二：后ZD > 前ZG 且 后DD <= 前GG ⇒ 形成高级别中枢。"""
    # 前中枢 [10, 12]，后中枢 ZD=13 > 12 且 DD=11.5 <= GG=13
    prev = _zs(0, zd=10.0, zg=12.0, dd=9.0, gg=13.0)
    cur = _zs(1, zd=13.0, zg=15.0, dd=11.5, gg=15.0)
    n = mark_upgraded_zss([prev, cur])
    assert n == 1
    assert cur.upgraded is True
    assert cur.level == 2


# ── 反例：不满足定理二 ⇒ 不标记 ──────────────────────────────────────────


def test_pure_trend_continuation_not_marked() -> None:
    """第20课定理二另两支是「趋势延续」而非升级：
    后GG < 前DD ⇒ 下跌延续；后DD > 前GG ⇒ 上涨延续。
    ⇒ 不得标记 upgraded。
    """
    # 后GG(8) < 前DD(9) ⇒ 下跌延续，不是升级
    prev = _zs(0, zd=10.0, zg=12.0, dd=9.0, gg=13.0)
    cur = _zs(1, zd=6.0, zg=8.0, dd=6.0, gg=8.0)
    assert mark_upgraded_zss([prev, cur]) == 0
    assert cur.upgraded is False
    assert cur.level == 1
    assert cur.upgrade_from == []

    # 后DD(15) > 前GG(13) ⇒ 上涨延续，不是升级
    prev2 = _zs(0, zd=10.0, zg=12.0, dd=9.0, gg=13.0)
    cur2 = _zs(1, zd=15.0, zg=17.0, dd=15.0, gg=17.0)
    assert mark_upgraded_zss([prev2, cur2]) == 0
    assert cur2.upgraded is False


def test_disjoint_centers_not_marked() -> None:
    """两中枢区间完全不挨边（后 ZG 远高于前 GG）⇒ 只是两个独立中枢。"""
    prev = _zs(0, zd=10.0, zg=12.0, dd=9.0, gg=13.0)
    cur = _zs(1, zd=20.0, zg=22.0, dd=20.0, gg=22.0)
    assert mark_upgraded_zss([prev, cur]) == 0


# ── 关键纪律：升级是「标记」，不是「合并段数」────────────────────────────


def test_upgrade_does_not_merge_segments() -> None:
    """⚠️ 本测试锁死 V851 修掉的错误：升级**不得**合并段数。

    旧实现 `_merge_overlapping_zss` 做 `prev.lines.extend(zs.lines)`，
    把两个同级别中枢的段数相加，既违反第33课 9 段上限，也不是原文的
    "升级为更大级别"。mark_upgraded_zss 必须一个段都不动。
    """
    bis = [_bi(i, 11.0, 10.0, i % 2 == 0) for i in range(6)]
    prev = ZS(
        lines=bis[:3], zg=11.0, zd=10.0, gg=11.0, dd=10.0, index=0, done=True
    )
    cur = ZS(
        lines=bis[3:], zg=11.0, zd=10.0, gg=11.0, dd=10.0, index=1, done=True
    )
    before = (len(prev.lines), len(cur.lines), prev.zg, prev.zd, cur.zg, cur.zd)
    mark_upgraded_zss([prev, cur])
    after = (len(prev.lines), len(cur.lines), prev.zg, prev.zd, cur.zg, cur.zd)
    assert before == after, "升级标记不得改动任何中枢的段数或区间"


def test_upgrade_does_not_change_counts_on_real_fixture() -> None:
    """真实 fixture：开关两侧的 bis/zss/mmds 计数必须完全一致。

    这证明"升级"是纯标记语义，不会像同级别合并那样改变分析结果。
    """
    import pandas as pd

    from easy_tdx.chanlun.analyser import ChanlunAnalyser

    fx_path = Path(__file__).parents[1] / "fixtures" / "chanlun_000001_daily.json"
    rows = json.loads(fx_path.read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])

    on = ChanlunAnalyser(
        code="SZ000001", frequency="daily", config=ChanlunConfig(zs_mark_upgrade=True)
    ).process_klines(df)
    off = ChanlunAnalyser(
        code="SZ000001", frequency="daily", config=ChanlunConfig(zs_mark_upgrade=False)
    ).process_klines(df)

    assert (len(on.bis), len(on.xds), len(on.zss), len(on.mmds), len(on.bcs)) == (
        len(off.bis),
        len(off.xds),
        len(off.zss),
        len(off.mmds),
        len(off.bcs),
    ), "升级标记不得改变任何结构/信号计数"

    # 但升级标记本身必须真的产生了差异（否则测试没有牙齿）
    n_up_on = sum(1 for z in on.zss if z.upgraded)
    n_up_off = sum(1 for z in off.zss if z.upgraded)
    assert n_up_on > 0, "对照组失效：开启时应有中枢被标记为升级"
    assert n_up_off == 0


def test_default_is_mark_upgrade_on() -> None:
    """默认开启（纯标记，对既有计数零影响）。"""
    assert ChanlunConfig().zs_mark_upgrade is True


def test_upgrade_level_is_transitive() -> None:
    """连续三段都满足定理二 ⇒ level 递增，来源记录传递。"""
    a = _zs(0, zd=10.0, zg=12.0, dd=9.0, gg=13.0)
    b = _zs(1, zd=13.0, zg=15.0, dd=11.5, gg=15.0)
    c = _zs(2, zd=16.0, zg=18.0, dd=14.5, gg=18.0)
    mark_upgraded_zss([a, b, c])
    assert b.upgraded and c.upgraded
    assert c.level == 3, "连续升级应逐级进"
    assert 0 in c.upgrade_from, "来源应传递记录"


def test_empty_and_single() -> None:
    """边界：空列表与单中枢。"""
    assert mark_upgraded_zss([]) == 0
    z = _zs(0, zd=10.0, zg=12.0, dd=9.0, gg=13.0)
    assert mark_upgraded_zss([z]) == 0
    assert z.upgraded is False
