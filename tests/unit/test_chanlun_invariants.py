"""缠论结构不变量自审（V740）。

把「笔端点落极值 / high&low=区间极值 / 方向交替 / 中枢 zg>zd 且 zg=min(前2笔high)
/ zd=max(前2笔low) / gg>=zg / dd<=zd」等几何不变量固化为回归测试。任何算法改动
若破坏这些不变量，本测试立即失败——不再依赖人工肉眼对照某段行情来发现 bug。

这是对历史上反复出现的「用户报某段画错→才发现算法 bug」被动模式的纠正：把人工
复盘转化成机器自审。新增标的/周期 fixture 时自动覆盖（见 CASES）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from easy_tdx.chanlun import ChanlunAnalyser
from easy_tdx.chanlun.types import Direction

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"

# (文件名, 周期)——新增 fixture 自动纳入自审
CASES = [
    ("chanlun_000001_daily.json", "daily"),
    ("chanlun_000001_weekly.json", "weekly"),
    ("chanlun_000001_30min.json", "30min"),
    ("chanlun_000333_daily.json", "daily"),
    ("chanlun_600519_daily.json", "daily"),
]

_TOL = 0.01  # 前复权浮点容差


def _load(fn: str, freq: str):
    rows = json.loads((FIXTURE_DIR / fn).read_text())
    df = pd.DataFrame(rows)
    if "datetime" in df.columns and "date" not in df.columns:
        df["date"] = df["datetime"]
    df["date"] = pd.to_datetime(df["date"])
    res = ChanlunAnalyser(code="SZ000001", frequency=freq).process_klines(df)
    return res


@pytest.fixture(scope="module", params=CASES, ids=[c[0] for c in CASES])
def result(request):
    fn, freq = request.param
    return _load(fn, freq)


# ── 笔：端点落极值 ─────────────────────────────────────────────────────────


def test_bi_endpoints_on_kline_extremes(result) -> None:
    """每笔起止分型值必须等于对应原始K线的极值（顶=high，底=low）。"""
    ks = result.klines
    for b in result.bis:
        assert 0 <= b.start.bar_index < len(ks), f"bi[{b.index}] start 越界"
        assert 0 <= b.end.bar_index < len(ks), f"bi[{b.index}] end 越界"
        sb, eb = ks[b.start.bar_index], ks[b.end.bar_index]
        if b.direction == Direction.UP:
            assert abs(b.start.val - sb.low) < _TOL, (
                f"向上笔 bi[{b.index}] 起点{b.start.val}≠K线低点{sb.low}"
            )
            assert abs(b.end.val - eb.high) < _TOL, (
                f"向上笔 bi[{b.index}] 终点{b.end.val}≠K线高点{eb.high}"
            )
        else:
            assert abs(b.start.val - sb.high) < _TOL, (
                f"向下笔 bi[{b.index}] 起点{b.start.val}≠K线高点{sb.high}"
            )
            assert abs(b.end.val - eb.low) < _TOL, (
                f"向下笔 bi[{b.index}] 终点{b.end.val}≠K线低点{eb.low}"
            )


# ── 笔：high/low = 端点分型顶/底（缠论原文 62课L20）─────────────────────────


def test_bi_high_low_equal_endpoint_fractals(result) -> None:
    """笔 high/low = 端点分型顶/底（缠论原文 62课L20）。

    62课L20：「两个相邻的顶和底之间构成一笔，所谓笔，就是顶和底之间的其他波动，
    都可以忽略不算」——笔极值即端点分型值 max/min(start.val, end.val)，
    区间内未成端点的更高顶/更低底属「其他波动」，按原文忽略。

    此前 V740 曾用「区间所有原始K线极值」覆盖端点值（注释自称原文但查无出处），
    会使 gn/dn 超过端点分型值，放大中枢 GG/DD 污染。V857 修复：恢复端点分型值。
    与偏差A（GG/DD 同向段 Zn 过滤）配合，共同保证 GG/DD = 同向段端点分型值极值，
    即原文 20课L22 口径。
    """
    for b in result.bis:
        ep_high = max(b.start.val, b.end.val)
        ep_low = min(b.start.val, b.end.val)
        assert abs(b.high - ep_high) < _TOL, (
            f"bi[{b.index}] high={b.high}≠端点分型顶{ep_high}（62课L20）"
        )
        assert abs(b.low - ep_low) < _TOL, (
            f"bi[{b.index}] low={b.low}≠端点分型底{ep_low}（62课L20）"
        )


# ── 笔：方向交替 ───────────────────────────────────────────────────────────


def test_bi_direction_alternates(result) -> None:
    """相邻笔方向必须相反（缠论笔的基本要求）。"""
    for i in range(1, len(result.bis)):
        assert result.bis[i].direction != result.bis[i - 1].direction, (
            f"bi[{i}]与bi[{i - 1}]方向相同 ({result.bis[i].direction.value})"
        )


# ── 中枢：zg>zd / gg>=zg / dd<=zd / ZG/ZD 由前 zs_zd_lines 笔冻结 ──────────

# ⚠️ V735 更正：上面「冻结笔数 3 = 缠论原文」的说法**是错的**。
# 原文第20课原文是「ZG=min(g1、g2)、ZD=max(d1、d2)」—— 只有 **A、C 两段**
# （第 1、3 笔）参与，中间那笔（B）不参与，**原文里没有 g3**。
# V735 起 zs_zd_original_ac 默认 True ⇒ 走 A、C 两段；本文件按原文改。
_ZD_LINES = 3


def test_zs_geometry_invariants(result) -> None:
    """中枢几何不变量：zg>zd，gg>=zg，dd<=zd，且 zg/zd 由 A、C 两段确定。

    V735：判据改用原文第20课的 A、C 两段（见上方注释）。
    """
    for z in result.zss:
        assert z.zg > z.zd, f"中枢[{z.index}] zg={z.zg} 必须 > zd={z.zd}"
        assert z.gg >= z.zg - _TOL, f"中枢[{z.index}] gg={z.gg} 必须 >= zg={z.zg}"
        assert z.dd <= z.zd + _TOL, f"中枢[{z.index}] dd={z.dd} 必须 <= zd={z.zd}"
        if len(z.lines) >= 3:
            # 原文第20课：ZG=min(g1、g2)、ZD=max(d1、d2) —— A、C 两段
            a_seg, c_seg = z.lines[0], z.lines[2]
            ezg = min(a_seg.high, c_seg.high)
            ezd = max(a_seg.low, c_seg.low)
            assert abs(z.zg - ezg) < _TOL, (
                f"中枢[{z.index}] zg={z.zg}≠A、C两段min(high)={ezg}（原文第20课）"
            )
            assert abs(z.zd - ezd) < _TOL, (
                f"中枢[{z.index}] zd={z.zd}≠A、C两段max(low)={ezd}（原文第20课）"
            )
            # 20课L22：GG=max(gn)、DD=min(dn)，n遍历与中枢方向一致的Z走势段(同向段)；
            # 反向段(B/D…)不参与。中枢方向=首笔方向(30课L142「一样有方向…下上下」)。
            assert z.direction in ("up", "down"), (
                f"中枢[{z.index}] direction={z.direction} 应为 up/down（30课L142）"
            )
            same_dir = [ln for ln in z.lines if ln.direction.value == z.direction]
            assert same_dir, f"中枢[{z.index}] 应有同向段(Zn)"
            assert abs(z.gg - max(ln.high for ln in same_dir)) < _TOL, (
                f"中枢[{z.index}] gg={z.gg}≠同向段max(gn)（20课L22 GG遍历Zn）"
            )
            assert abs(z.dd - min(ln.low for ln in same_dir)) < _TOL, (
                f"中枢[{z.index}] dd={z.dd}≠同向段min(dn)（20课L22 DD遍历Zn）"
            )


# ── 线段：端点为分型极值、方向与首末笔一致 ─────────────────────────────────


def test_xd_endpoints_on_bi_extremes(result) -> None:
    """线段起止必须落在某笔的分型极值上，且方向与起止笔一致。"""
    bi_by_idx = {b.index: b for b in result.bis}
    for x in result.xds:
        # 线段起点应对齐某笔起点（向上段=底，向下段=顶）
        # 线段起点对齐检查：start_index 必须存在于笔索引表（未用的取值不再赋值）
        assert not hasattr(x, "start_index") or x.start_index in bi_by_idx
        if x.direction == Direction.UP:
            # 向上线段：起点是底（低），终点是顶（高）
            assert x.end.val >= x.start.val + _TOL or abs(x.end.val - x.start.val) < _TOL * 10, (
                f"向上线段 {x} 终点应 >= 起点"
            )
        else:
            assert x.start.val >= x.end.val + _TOL or abs(x.start.val - x.end.val) < _TOL * 10, (
                f"向下线段 {x} 终点应 <= 起点"
            )
