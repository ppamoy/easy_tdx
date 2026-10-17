"""缠论线段 65课 不变量守卫（偏差D，65课L34）。

缠论原文 65课L34：
  ①「线段的前三笔，必须有重叠的部分……只要构成有重叠部分的前三笔，那么必然会
    形成一线段」——每条线段自身的起笔前三笔区间须有公共交集。
  ②「线段破坏的充要条件，就是被另一个线段破坏」——线段间首尾相连（chaining），
    不应出现孤立笔（线段 i 的终点 = 线段 i+1 的起点）。

偏差D V857 破坏确认集成保证这两条：起点前三笔检查（不重叠则滑动，仅孤立数据最
前端）+ 破坏确认（下一线段前三笔无重叠则线段延伸，而非孤立中间笔）。

双向验证：stash 偏差D（xd.py）后，000001_30min/weekly 的 xd0 前三笔不重叠（违
①），本测试应失败（抓到回归）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "chanlun_108"

FIXTURES = [
    ("chanlun_000001_daily.json", "daily"),
    ("chanlun_000001_30min.json", "30min"),
    ("chanlun_000001_weekly.json", "weekly"),
    ("chanlun_600519_daily.json", "daily"),
]


def _load(fname: str):
    src = FIXTURE_DIR.parent / fname
    if not src.exists():
        pytest.skip(f"{fname} 不存在")
    rows = json.loads(src.read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"])
    return df


@pytest.mark.parametrize("fname,freq", FIXTURES, ids=[f[0] for f in FIXTURES])
def test_xd_first3_overlap_and_chaining(fname: str, freq: str) -> None:
    """每条线段前三笔须重叠（65课L34①），线段间首尾相连（chaining，65课L34②）。"""
    df = _load(fname)
    res = ChanlunAnalyser(
        code=fname, frequency=freq, config=ChanlunConfig(zs_from_xd=False)
    ).process_klines(df)
    bis = res.bis
    xds = res.xds
    if len(xds) < 1:
        pytest.skip("线段不足，无法校验")

    # 线段起点 → 笔序号映射
    bmap = {(b.start.bar_index, round(b.start.val, 4)): i for i, b in enumerate(bis)}

    # ① 前三笔重叠
    violations = []
    for xd in xds:
        si = bmap.get((xd.start.bar_index, round(xd.start.val, 4)))
        if si is None or si + 2 >= len(bis):
            continue
        f3 = bis[si : si + 3]
        if not (min(b.high for b in f3) > max(b.low for b in f3)):
            violations.append(xd.index)
    assert not violations, (
        f"{fname}: 线段 {violations} 前三笔无重叠（违 65课L34①）"
    )

    # ② chaining：线段 i 终点 = 线段 i+1 起点
    gaps = []
    for i in range(len(xds) - 1):
        if xds[i].end.bar_index != xds[i + 1].start.bar_index:
            gaps.append((i, xds[i].end.bar_index, xds[i + 1].start.bar_index))
    assert not gaps, (
        f"{fname}: 线段间 chaining 断裂 {gaps}（违 65课L34②「线段破坏=被另一个线段破坏」）"
    )
