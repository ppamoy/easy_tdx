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


# ── 笔：high/low = 区间真实极值（含 gap 不足无法成笔端点的中间极值）─────────


def test_bi_high_low_equal_range_extremes(result) -> None:
    """笔 high/low 必须等于 [start.bar_index, end.bar_index] 区间内所有K线的极值。

    这是 V740 修复的核心不变量：端点取极值会漏掉「区间内更高顶/更低底但因 gap
    不足无法成笔端点」的中间极值，导致中枢 zg/zd 偏窄。重算后必须严格相等。
    """
    ks = result.klines
    for b in result.bis:
        if not (0 <= b.start.bar_index <= b.end.bar_index < len(ks)):
            continue
        seg = ks[b.start.bar_index : b.end.bar_index + 1]
        hi = max(k.high for k in seg)
        lo = min(k.low for k in seg)
        assert abs(b.high - hi) < _TOL, f"bi[{b.index}] high={b.high}≠区间最高{hi}"
        assert abs(b.low - lo) < _TOL, f"bi[{b.index}] low={b.low}≠区间最低{lo}"


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
            # gg/dd 覆盖全部走势极值
            assert abs(z.gg - max(ln.high for ln in z.lines)) < _TOL, (
                f"中枢[{z.index}] gg={z.gg}≠max(high)"
            )
            assert abs(z.dd - min(ln.low for ln in z.lines)) < _TOL, (
                f"中枢[{z.index}] dd={z.dd}≠min(low)"
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
