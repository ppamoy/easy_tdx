"""缠论 K 线包含合并：首组方向锁定守卫（偏差G，62课L22）。

缠论原文 62课L22：K 线包含处理时「向上取高高，向下取低低」。一个合并组的方向
应在组合并期间保持一致——若首组（len(result)<2，无 result[-2] 可比较）每次
merge 都按「最后一根 K 线的阴阳」重算方向，且 prev.open/close 被覆写为末根值，
则同一组会前半取高高、后半取低低，合并 high/low 既非高高也非低低。

本测试用合成 K 线复现该缺陷：k0 阳线(10→12)、k1 阴线被包含、k2 阴线被包含。
- 修复前（偏差G bug）：merge#1 up 取高高 H=12；merge#2 因 prev.close 被覆写为
  k1 值、按末根阴阳重算得 down，取低低 H 回吐到 10.8 → 方向翻转、H≠真区间高 12。
- 修复后（V857）：首组方向在第一次 merge 时锁定（up），后续沿用，H 保持 12。

双向验证：把方向锁定改回「每 merge 重算」即应失败（H<12），证明本测试能抓到回归。
"""

from __future__ import annotations

import datetime

import pytest

from easy_tdx.chanlun.kline_merge import merge_klines
from easy_tdx.chanlun.types import Kline


def _k(o: float, c: float, h: float, l: float, i: int) -> Kline:
    return Kline(
        index=i,
        date=datetime.datetime(2025, 1, 1 + i, 9, 30),
        open=o,
        close=c,
        high=h,
        low=l,
        amount=100 * c,
    )


def test_first_group_direction_locked_no_flip() -> None:
    """首组方向锁定：k0 阳(10→12)、k1/k2 阴被包含，方向应锁定 up、H 保持 12。"""
    ks = [
        _k(10, 12, 12, 10, 0),   # 阳线，区间 [10,12]
        _k(11, 10.5, 11, 10.2, 1),  # 阴线被包含
        _k(11, 10.8, 10.8, 10.2, 2),  # 阴线被包含
    ]
    out = merge_klines(ks)
    assert len(out) == 1, f"应合并为 1 根缠论K线，实际 {len(out)}"
    ck = out[0]
    # 方向锁定为 up（k0 阳线），不应翻转为 down
    assert ck.direction == "up", (
        f"首组方向应锁定 up（k0 阳线），实际 {ck.direction}（偏差G：方向翻转）"
    )
    # H 应保持 12.0（取高高），不应因翻转取低低回吐
    assert ck.high == pytest.approx(12.0), (
        f"首组 H 应=12.0（真区间高，向上取高高），实际 {ck.high}（偏差G：翻转取低低回吐）"
    )
    assert ck.merged_count == 3
