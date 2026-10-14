"""V811 回归测试：3买/3卖 不得引用已被新中枢取代的旧中枢。

背景：600066 在 2026-06-29 11:00 出现了一个假 3卖，引用的是 zs#23 (ZD=29.54)，
但此时 zs#24 (ZD=26.00) 已经形成。旧代码在中枢之后无限搜索反抽笔，
不知道新中枢已形成，导致引用过期的 ZD/ZG 产生虚假信号。

修复：搜索反抽/回踩笔时，一旦进入下一个中枢的范围就停止。
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig


@pytest.fixture(scope="module")
def result_600066():
    """跑一次 600066 30min 分析（约15秒），模块内所有测试共用。"""
    fp = ROOT / "audit_data" / "kline_30min" / "sh600066_30min.json"
    if not fp.is_file():
        pytest.skip("缺少 600066 30min K线缓存")
    rows = json.loads(fp.read_text("utf-8"))
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    cfg = ChanlunConfig(zs_from_xd=False)
    analyser = ChanlunAnalyser(code="SH600066", frequency="30min", config=cfg)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return analyser.process_klines(df)


def test_no_3sell_referencing_superseded_zs(result_600066):
    """3卖不得引用已被新中枢取代的旧中枢。

    旧 bug: zs#23(ZD=29.54) 的离开笔后，zs#24(ZD=26) 已形成，
    但代码继续在 zs#24 内部搜索反抽笔，找到 high=27.96 < 29.54 → 假3卖。
    修复后: 搜索到 zs#24 首笔时停止，不产生该假信号。
    """
    zss = result_600066.zss
    mmds = result_600066.mmds

    for m in mmds:
        if m.mmd_type.value != "3sell":
            continue
        zs = m.zs
        bi = m.bi
        if zs is None or bi is None:
            continue

        next_zs = None
        for z2 in zss:
            if z2.index > zs.index and z2.lines:
                next_zs = z2
                break

        if next_zs is None:
            continue

        next_first_bi_idx = next_zs.lines[0].index
        assert bi.index <= next_first_bi_idx, (
            f"3卖 bi#{bi.index} 引用了已被取代的旧中枢 zs#{zs.index}(ZD={zs.zd:.2f})，"
            f"但 zs#{next_zs.index}(ZD={next_zs.zd:.2f}) 首笔 bi#{next_first_bi_idx} "
            f"已在该信号之前形成 → 假信号！msg={m.msg}"
        )


def test_3sell_at_2026_06_29_gone(result_600066):
    """2026-06-29 11:00 的假 3卖（引用 zs#23 ZD=29.54）应已消除。"""
    mmds = result_600066.mmds
    bad = [
        m for m in mmds
        if m.mmd_type.value == "3sell"
        and m.bi is not None
        and m.bi.end.k.k_index in range(2850, 2870)
    ]
    assert len(bad) == 0, (
        f"2026-06-29 区域不应有 3卖（旧中枢已被新中枢取代），"
        f"但找到了 {len(bad)} 个: {[(m.bi.index, m.msg[:50]) for m in bad]}"
    )


def test_1buy_at_2026_09_23_present(result_600066):
    """2026-09-23 的 1买信号不应被修复影响。"""
    mmds = result_600066.mmds
    buy1 = [
        m for m in mmds
        if m.mmd_type.value == "1buy"
        and m.bi is not None
        and m.bi.end.k.k_index == 3356
    ]
    assert len(buy1) >= 1, "2026-09-23 的 1买信号应存在"


def test_no_3buy_referencing_superseded_zs(result_600066):
    """3买同样不得引用已被新中枢取代的旧中枢。"""
    zss = result_600066.zss
    mmds = result_600066.mmds

    for m in mmds:
        if m.mmd_type.value != "3buy":
            continue
        zs = m.zs
        bi = m.bi
        if zs is None or bi is None:
            continue

        next_zs = None
        for z2 in zss:
            if z2.index > zs.index and z2.lines:
                next_zs = z2
                break

        if next_zs is None:
            continue

        next_first_bi_idx = next_zs.lines[0].index
        assert bi.index <= next_first_bi_idx, (
            f"3买 bi#{bi.index} 引用了已被取代的旧中枢 zs#{zs.index}(ZG={zs.zg:.2f})，"
            f"但 zs#{next_zs.index}(ZG={next_zs.zg:.2f}) 首笔 bi#{next_first_bi_idx} "
            f"已在该信号之前形成 → 假信号！msg={m.msg}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
