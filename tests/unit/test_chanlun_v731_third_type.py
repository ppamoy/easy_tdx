"""V731 三类买卖点（3买/3卖）原文口径回归。

背景（scripts/audit_3rd_type_accuracy.py 实测）：
修复前教科书 3买/3卖 召回率 **0%**。根因是「离开笔」定位语义错位——
``zs.py::find_zss`` 在关闭中枢时已把关闭它的那一笔并入 ``zs.lines``
（它就是中枢末条线），而旧代码用 ``bi.start.k.k_index > zs.end.k.k_index``
在中枢**之后**找突破笔，该条件要求突破笔起点 > 离开笔自己的终点，于是
真·离开笔永远被排除，只能选中更晚的笔。

本文件锁定三类原文口径行为，每条都可被修复前的代码证伪：
1. 教科书 3买/3卖 能被识别（召回）；
2. 定位落在真回抽/反抽点上（不是后续某次无关回踩）；
3. 「假突破 → 真突破 → 真回踩」不被首个失败的回踩终止（旧代码 break 掉整轮）；
4. 回抽笔长度超过旧的硬编码 15 根窗口时仍应识别（旧代码静默丢弃约 14.5%）。
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402


def _mk(bars) -> pd.DataFrame:
    rows = []
    dt = datetime(2024, 1, 2)
    for o, c, h, ln in bars:
        rows.append({"datetime": dt, "open": o, "close": c, "high": h, "low": ln, "vol": 1e6})
        dt += timedelta(days=1)
    return pd.DataFrame(rows)


def _seg(n: int, o: float, c: float, jitter: float = 0.05):
    """生成一段从 o 线性走到 c 的 K 线（n 根）。"""
    out = []
    for i in range(n):
        t0 = o + (c - o) * (i / n)
        t1 = o + (c - o) * ((i + 1) / n)
        lo, hi = min(t0, t1), max(t0, t1)
        out.append((t0, t1, hi + jitter, lo - jitter))
    return out


def _build(pts: list[float], seg_len: int = 9) -> pd.DataFrame:
    """按拐点序列构造 K 线：相邻拐点之间走 seg_len 根。"""
    bars: list[tuple[float, float, float, float]] = []
    for a, b in zip(pts, pts[1:]):
        bars += _seg(seg_len, a, b)
    return _mk(bars)


def _run(df: pd.DataFrame, **cfg):
    cfg.setdefault("zs_from_xd", False)
    conf = ChanlunConfig(**cfg)
    return ChanlunAnalyser(code="T", frequency="daily", config=conf).process_klines(df)


def _third(res):
    return [m for m in res.mmds if m.mmd_type.value in ("3buy", "3sell")]


class TestThirdTypeRecall:
    """教科书 3买/3卖 必须被识别且定位正确。"""

    def test_3buy_textbook_detected_and_located(self) -> None:
        """箱体中枢 → 突破 ZG → 回抽不破 ZG → 续涨。"""
        # 10→12→11→12.5→11.2 构成箱体，13.5 突破，12.6 回抽不破
        res = _run(_build([10, 12, 11, 12.5, 11.2, 13.5, 12.6, 14.5]))
        hits = _third(res)
        assert hits, "教科书 3买 未被识别（召回失败）"
        assert hits[0].mmd_type.value == "3buy"
        # 定位：必须落在回抽笔（zg 之上、且不是突破笔本身）
        zg = hits[0].zs.zg
        assert hits[0].bi.low > zg, f"3买 定位错误：低点未在中枢上沿之上 ({hits[0].bi.low} <= {zg})"

    def test_3sell_textbook_detected_and_located(self) -> None:
        """箱体中枢 → 跌破 ZD → 反抽不破 ZD → 续跌。"""
        res = _run(_build([14, 12, 13, 11.5, 12.8, 10.5, 11.4, 9.5]))
        hits = _third(res)
        assert hits, "教科书 3卖 未被识别（召回失败）"
        assert hits[0].mmd_type.value == "3sell"
        zd = hits[0].zs.zd
        assert hits[0].bi.high < zd, (
            f"3卖 定位错误：高点未在中枢下沿之下 ({hits[0].bi.high} >= {zd})"
        )


class TestThirdTypeNoEarlyTermination:
    """首个回抽失败不得终止整轮搜索（旧实现用 break 导致真信号永久漏报）。"""

    def test_fake_breakout_then_real_breakout_still_detected(self) -> None:
        """假突破→回踩跌回中枢→再真突破→回踩不破。

        旧实现在首个回踩 `bi.low <= zs.zg` 时 break 掉整个中枢的搜索，
        后续真 3买 永远不会报出。本用例即该漏报场景的最小复现。
        """
        pts = [10, 12, 11, 12.5, 11.2, 12.3, 10.8, 13.2, 10.9, 14.6, 13.7, 15.5]
        res = _run(_build(pts))
        hits = _third(res)
        assert hits, "假突破后真突破的 3买 被漏报（首个失败回踩不应终止搜索）"
        assert hits[-1].mmd_type.value == "3buy"
        zg = hits[-1].zs.zg
        assert hits[-1].bi.low > zg, "定位错误：真回踩低点应在 zg 之上"


class TestThirdTypeWindow:
    """回抽笔长度：旧的硬编码 15 根窗口会静默丢弃合法信号。"""

    @pytest.mark.parametrize("seg_len", [9, 30])
    def test_long_retest_not_killed_by_bar_window(self, seg_len: int) -> None:
        """同一结构把每段 K 线数放大（回抽笔随之变长），仍应识别。

        seg_len=30 时回抽笔跨度远超旧的 15 根窗口，旧实现会 break 丢弃。
        """
        res = _run(_build([10, 12, 11, 12.5, 11.2, 13.5, 12.6, 14.5], seg_len=seg_len))
        hits = _third(res)
        assert hits, f"seg_len={seg_len} 时 3买 被窗口误杀"
        assert hits[0].mmd_type.value == "3buy"

    def test_window_configurable_and_zero_means_unlimited(self) -> None:
        """mmd_3rd_retest_max_bars 应可配置；0（默认）= 不限制。"""
        conf = ChanlunConfig(zs_from_xd=False)
        assert conf.mmd_3rd_retest_max_bars == 0, "默认应为 0（纯原文口径，不限制）"
        assert conf.to_dict()["mmd_3rd_retest_max_bars"] == 0

        df = _build([10, 12, 11, 12.5, 11.2, 13.5, 12.6, 14.5], seg_len=30)
        # 显式收紧到 5 根：长回抽应被抑制（对照侧，证明开关真的生效）
        tight = _run(df, mmd_3rd_retest_max_bars=5)
        assert not _third(tight), "收紧窗口到 5 根后长回抽仍报出，开关未生效"
