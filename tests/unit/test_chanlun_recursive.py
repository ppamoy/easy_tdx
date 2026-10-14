"""缠论多级别递归金标测试（V651 / 深递归 V708）。

锁定「以低级别线段作为高级别笔」的递归输出：
- 手工人造线段序列 → 高级别线段/线段中枢/背驰计数与几何不变量；
- 深度多级别递归（compute_recursive_levels）：多级链逐级把上一级线段当
  更高级别「笔」递归，验证级别数、链式馈给、端点锚定与各级别几何不变量；
- 真实行情 fixture → to_dict 输出 bi/xd 两层结构且不破坏单级别序列化。
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from easy_tdx.chanlun import ChanlunAnalyser, ChanlunResult
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.recursive import (
    RecursiveLevelResult,
    compute_recursive_level,
    compute_recursive_levels,
)
from easy_tdx.chanlun.types import FX, XD, CLKline, Direction, FXType

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"

# 手工人造线段：方向交替、高低点逐步抬升/回落，使特征序列在高级别上
# 先形成向上线段顶分型、再形成向下线段底分型，保证递归输出确定。
XD_SEQ = [
    ("up", 100.0, 110.0, 112.0, 98.0),
    ("down", 110.0, 102.0, 112.0, 98.0),
    ("up", 102.0, 112.0, 114.0, 100.0),
    ("down", 112.0, 108.0, 120.0, 104.0),
    ("up", 108.0, 122.0, 124.0, 106.0),
    ("down", 122.0, 98.0, 108.0, 96.0),
    ("up", 98.0, 118.0, 120.0, 96.0),
    ("down", 118.0, 104.0, 120.0, 102.0),
    ("up", 104.0, 116.0, 118.0, 102.0),
    ("down", 116.0, 100.0, 118.0, 98.0),
]


def _k(bar_index: int) -> CLKline:
    return CLKline(
        k_index=bar_index,
        date=datetime(2020, 1, 1) + timedelta(days=bar_index),
        open=0.0,
        close=0.0,
        high=0.0,
        low=0.0,
        amount=0.0,
        index=bar_index,
    )


def _fx(fx_type: FXType, val: float, bar_index: int) -> FX:
    k = _k(bar_index)
    return FX(
        fx_type=fx_type,
        k=k,
        klines=[k],
        val=val,
        index=bar_index,
        done=True,
        bar_index=bar_index,
    )


def _make_xds() -> list[XD]:
    """构造端点共享的低级别线段序列，与真实线段划分首尾相连一致。"""
    endpoints = [seq[1] for seq in XD_SEQ] + [XD_SEQ[-1][2]]
    points: list[FX] = []
    for i, val in enumerate(endpoints):
        fx_type = FXType.DI if i % 2 == 0 else FXType.DING
        points.append(_fx(fx_type, val, i * 10))

    xds: list[XD] = []
    for i, (direction, start_val, end_val, high, low) in enumerate(XD_SEQ):
        d = Direction.UP if direction == "up" else Direction.DOWN
        xds.append(
            XD(
                start=points[i],
                end=points[i + 1],
                direction=d,
                index=i,
                high=high,
                low=low,
            )
        )
    return xds


def test_recursive_level_golden_counts() -> None:
    """人造线段序列的递归高级别输出必须与金标完全一致。"""
    result = compute_recursive_level(_make_xds(), config=ChanlunConfig(xd_bi_pohuai=False))

    assert isinstance(result, RecursiveLevelResult)
    # 高级别线段：先向上 100→112，再向下 112→98
    assert len(result.xds) == 2
    assert result.xds[0].direction == Direction.UP
    assert result.xds[0].start.val == 100.0
    assert result.xds[0].end.val == 112.0
    assert result.xds[1].direction == Direction.DOWN
    # V725（收尾不换取端点）：高级别收尾段终点取最后一个同向线段端点 100.0
    # （旧实现 max/min 换出到早已越过的 98.0 低点，违反原文收尾语义）。
    assert result.xds[1].end.val == 100.0

    # 高级别线段中枢：ZG/ZD 由前 zs_zd_lines 笔冻结（V733 默认 3）。
    # 实测（V733）：ZG=112.0（前三笔 min(high) 仍为 112，与两笔口径一致），
    # ZD=100.0（前三笔 max(low)=100 > 两笔口径的 98 —— 第3笔抬高了下沿，
    # 中枢因此变窄，符合「多求一次交集必然不宽」）。
    # V851：zs_no_hard_close 默认改为 False（9 段硬关闭，第33课上限 3+6），
    # 同时 zs_merge_overlap 默认改为 False（关闭同级别合并；依据见
    # config.py V851 注释 + 第20课 line 4「产生一个更大级别的走势中枢」）。
    # ⇒ 中枢 line_count = 9（恰好等于原文上限）。
    # 旧值 10 是 V735「不硬关闭 + 合并」下的产物，已超第33课 9 段上限。
    assert len(result.zss) == 1
    assert result.zss[0].zg == 112.0
    assert result.zss[0].zd == 100.0
    assert result.zss[0].line_count == 9

    # 高级别背驰：向下线段力度衰竭
    assert len(result.bcs) == 1
    assert result.bcs[0].bc is True

    # 该人造序列不触发三类买卖点，但结果必须是可序列化的列表
    assert result.mmds == []


def test_recursive_level_geometry_invariants() -> None:
    """递归线段端点首尾相连、方向交替；中枢区间满足 ZG>ZD。"""
    result = compute_recursive_level(_make_xds(), config=ChanlunConfig(xd_bi_pohuai=False))

    for xd in result.xds:
        if xd.direction == Direction.UP:
            assert xd.end.val > xd.start.val
        else:
            assert xd.end.val < xd.start.val
        assert xd.low <= xd.start.val <= xd.high
        assert xd.low <= xd.end.val <= xd.high

    for i in range(len(result.xds) - 1):
        assert result.xds[i].end.bar_index == result.xds[i + 1].start.bar_index
        assert result.xds[i].end.val == result.xds[i + 1].start.val
        assert result.xds[i].direction != result.xds[i + 1].direction

    for zs in result.zss:
        assert zs.zg > zs.zd
        assert zs.gg >= zs.zg
        assert zs.dd <= zs.zd


def test_recursive_level_insufficient_lines_returns_empty() -> None:
    """少于 3 根低级别线段时返回空结果，不抛异常。"""
    result = compute_recursive_level([], config=ChanlunConfig(xd_bi_pohuai=False))
    assert result.xds == [] and result.zss == [] and result.mmds == [] and result.bcs == []
    assert result.zsds == [] and result.qsds == []

    result = compute_recursive_level(_make_xds()[:2], config=ChanlunConfig(xd_bi_pohuai=False))
    assert result.xds == [] and result.zss == [] and result.mmds == [] and result.bcs == []
    assert result.zsds == [] and result.qsds == []


def test_to_dict_outputs_two_levels() -> None:
    """to_dict 输出 bi/xd 两层结构，且与单级别顶层数组一致。"""
    rows = json.loads((FIXTURE_DIR / "chanlun_000001_daily.json").read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    result = ChanlunAnalyser(
        code="000001", frequency="daily", config=ChanlunConfig(xd_bi_pohuai=False)
    ).process_klines(df)
    d = result.to_dict()

    assert set(d["levels"].keys()) == {"bi", "xd"}

    bi_level = d["levels"]["bi"]
    assert bi_level["name"] == "笔级别"
    assert bi_level["bi_count"] == d["bi_count"]
    assert bi_level["xd_count"] == d["xd_count"]
    assert bi_level["zs_count"] == d["zs_count"]
    assert bi_level["mmd_count"] == d["mmd_count"]
    assert bi_level["bc_count"] == d["bc_count"]
    assert bi_level["zsd_count"] == d["zsd_count"]
    assert bi_level["qsd_count"] == d["qsd_count"]
    assert len(bi_level["bis"]) == d["bi_count"]
    assert len(bi_level["xds"]) == d["xd_count"]

    xd_level = d["levels"]["xd"]
    assert xd_level["name"] == "线段级别"
    # 高级别「笔」= 本级别线段；fixture 只有 2 根线段，不足以递归出更高级别线段
    assert xd_level["bi_count"] == d["xd_count"]
    assert xd_level["xd_count"] == 0
    assert xd_level["zsd_count"] == 0
    assert xd_level["qsd_count"] == 0
    assert xd_level["zss"] == []
    assert xd_level["mmds"] == []
    assert xd_level["bcs"] == []


def test_recursive_module_exported_from_package() -> None:
    """递归 API 通过 chanlun 包对外导出。"""
    from easy_tdx.chanlun import RecursiveLevelResult as ExportedResult
    from easy_tdx.chanlun import compute_recursive_level as exported_compute

    assert ExportedResult is RecursiveLevelResult
    assert exported_compute is compute_recursive_level


def _craft_multiscale_xds(n: int = 1200) -> list[XD]:
    """构造多层嵌套正弦端点路径的底层线段序列。

    端点 = 300 + 90·sin(i/140) + 70·sin(i/34) + 20·sin(i/7)，方向交替，
    相邻线段端点共享，保证高阶特征序列能逐级收敛出 3 个递归级别。
    """
    es = [
        round(300 + 90 * math.sin(i / 140) + 70 * math.sin(i / 34) + 20 * math.sin(i / 7), 2)
        for i in range(n)
    ]
    points = [_fx(FXType.DI if i % 2 == 0 else FXType.DING, v, i * 10) for i, v in enumerate(es)]
    xds: list[XD] = []
    for i in range(len(points) - 1):
        d = Direction.UP if i % 2 == 0 else Direction.DOWN
        hi = max(points[i].val, points[i + 1].val) + 2
        lo = min(points[i].val, points[i + 1].val) - 2
        xds.append(
            XD(
                start=points[i],
                end=points[i + 1],
                direction=d,
                index=i,
                high=hi,
                low=lo,
            )
        )
    return xds


def _cfg() -> ChanlunConfig:
    return ChanlunConfig(xd_bi_pohuai=False)


def test_compute_recursive_levels_deep_three_levels() -> None:
    """深度递归：多级正弦端点 → 3 个递归级别，级别线段数逐级收敛。"""
    xds = _craft_multiscale_xds()
    res = compute_recursive_levels(xds, depth=5, config=_cfg())

    assert len(res) == 3
    # 级别线段数逐级收敛：基础级 → 56 → 8 → 1（数据决定的确定性金标）。
    # V730 P1-4：level2 6→8——旧实现对缺口后「第4特征元素创新低/新高」的粗糙
    # 近似漏判了部分线段终点（欠分段）；按第71课真实价格击穿判定后，158.36 段
    # 正确止于 390.81 处的特征序列分型并衔接 DOWN 段，末段同理，4 段变 8 段。
    assert [len(rl.xds) for rl in res] == [56, 8, 1]

    # 每级几何不变量：端点首尾相连、方向交替、区间合理。
    for rl in res:
        for xd in rl.xds:
            if xd.direction == Direction.UP:
                assert xd.end.val > xd.start.val
            else:
                assert xd.end.val < xd.start.val
            assert xd.low <= xd.start.val <= xd.high
            assert xd.low <= xd.end.val <= xd.high
        for i in range(len(rl.xds) - 1):
            assert rl.xds[i].end.bar_index == rl.xds[i + 1].start.bar_index
            assert rl.xds[i].end.val == rl.xds[i + 1].start.val
            assert rl.xds[i].direction != rl.xds[i + 1].direction
        for zs in rl.zss:
            assert zs.zg > zs.zd


def test_compute_recursive_levels_backward_compat_level1() -> None:
    """compute_recursive_level(单级) == compute_recursive_levels(depth=1)[0]。"""
    xds = _craft_multiscale_xds()
    one = compute_recursive_level(xds, config=_cfg())
    deep = compute_recursive_levels(xds, depth=1, config=_cfg())
    assert len(deep) == 1
    assert one.xds == deep[0].xds
    assert one.zss == deep[0].zss
    assert one.bcs == deep[0].bcs


def test_compute_recursive_levels_chain_feed() -> None:
    """第 N 级复用第 N-1 级线段作为「高级别笔」：链式馈给一致。"""
    xds = _craft_multiscale_xds()
    res = compute_recursive_levels(xds, depth=2, config=_cfg())
    assert len(res) == 2

    # 第 2 级 = 以第 1 级线段为「笔」再递归的结果。
    independent = compute_recursive_level(res[0].xds, config=_cfg())
    assert len(independent.xds) == len(res[1].xds)
    assert [(xd.index, xd.start.val, xd.end.val) for xd in independent.xds] == [
        (xd.index, xd.start.val, xd.end.val) for xd in res[1].xds
    ]


def test_compute_recursive_levels_depth_semantics() -> None:
    """depth<1 归一为 1；线段不足时提前终止、返回更少级别。"""
    xds = _craft_multiscale_xds()
    assert len(compute_recursive_levels(xds, depth=0, config=_cfg())) == 1
    assert len(compute_recursive_levels(xds, depth=1, config=_cfg())) == 1

    # 基础线段不足 3 根 → 空链，不抛异常。
    assert compute_recursive_levels([], config=_cfg()) == []
    assert compute_recursive_levels(_make_xds()[:2], config=_cfg()) == []


def test_compute_recursive_levels_exported_from_package() -> None:
    """compute_recursive_levels 通过 chanlun 包对外导出。"""
    from easy_tdx.chanlun import compute_recursive_levels as exported

    assert exported is compute_recursive_levels


def test_to_dict_emits_deep_recursion_levels() -> None:
    """to_dict 输出 levels.bi / xd / xd_l2 / xd_l3：高级别链逐级序列化。

    每级「笔」= 上一级线段（Level 1 的「笔」= result.xds，此处未填充为空），
    本级的线段 = 该级递归得到的 XD。
    """
    xds = _craft_multiscale_xds()
    res = compute_recursive_levels(xds, depth=3, config=_cfg())
    assert len(res) == 3

    result = ChanlunResult(code="000001", frequency="daily")
    result.recursive_levels = res
    d = result.to_dict()

    assert set(d["levels"].keys()) == {"bi", "xd", "xd_l2", "xd_l3"}
    assert d["levels"]["xd"]["name"] == "线段级别"
    assert d["levels"]["xd"]["xd_count"] == len(res[0].xds)
    # 第 2 级：笔 = 第 1 级线段，线段 = res[1]
    assert d["levels"]["xd_l2"]["name"] == "递归2级"
    assert d["levels"]["xd_l2"]["bi_count"] == len(res[0].xds)
    assert d["levels"]["xd_l2"]["xd_count"] == len(res[1].xds)
    # 第 3 级：笔 = 第 2 级线段，线段 = res[2]
    assert d["levels"]["xd_l3"]["name"] == "递归3级"
    assert d["levels"]["xd_l3"]["bi_count"] == len(res[1].xds)
    assert d["levels"]["xd_l3"]["xd_count"] == len(res[2].xds)


# ── V730 跨级别端点共享（缠论原文：相邻级别必须共享转折点）────────────


def _endpoint_identities(xds: list[XD]) -> set[int]:
    """某级别所有线段的端点分型对象身份集合（start/end 都算）。"""
    ids: set[int] = set()
    for xd in xds:
        ids.add(id(xd.start))
        ids.add(id(xd.end))
    return ids


def test_recursive_levels_share_turning_points_across_levels() -> None:
    """V730：高级别线段端点 MUST 是低级别线段的端点（跨级别共享转折点）。

    缠论递归的本质是「低级别线段 → 高级别笔」，因此高级别线段的起止点
    必须落在低级别的转折点（线段端点分型）上，不得悬空在低级别线段中间。

    这里用**对象身份**（id）断言而非仅比值：recursive._compute_one_level 把
    上一级 XD 原样当作 BI 传入 find_xds，端点 FX 必须是同一个对象，而不只是
    数值相同的新对象——数值相同可能掩盖「重建端点」的隐患。
    """
    xds = _craft_multiscale_xds()
    res = compute_recursive_levels(xds, depth=3, config=_cfg())
    assert len(res) == 3

    # 基础级（传入的低级别线段）端点集合
    base_ids = _endpoint_identities(xds)

    # Level-2 端点必须来自 Level-1 线段的端点
    for xd in res[1].xds:
        assert id(xd.start) in base_ids, f"L2 起点未共享基础级端点: {xd.start.val}"
        assert id(xd.end) in base_ids, f"L2 终点未共享基础级端点: {xd.end.val}"

    # Level-3 端点必须来自 Level-2 线段的端点（逐级递进，而非都指向基础级）
    l2_ids = _endpoint_identities(res[1].xds)
    for xd in res[2].xds:
        assert id(xd.start) in l2_ids, f"L3 起点未共享 L2 端点: {xd.start.val}"
        assert id(xd.end) in l2_ids, f"L3 终点未共享 L2 端点: {xd.end.val}"


def test_recursive_levels_high_endpoint_values_subset_of_low() -> None:
    """V730：高级别端点 (val, bar_index) 是低级别端点集合的子集。

    对象身份之外再锁定数值与锚定索引：序列化到前端后前端只能按
    (val, bar_index) 定位，因此这两者也必须严格落在低级别端点上，
    否则图上高级别线段会与低级别转折点错位。
    """

    def pts(xds: list[XD]) -> set[tuple[float, int]]:
        out: set[tuple[float, int]] = set()
        for xd in xds:
            out.add((round(float(xd.start.val), 4), int(xd.start.bar_index)))
            out.add((round(float(xd.end.val), 4), int(xd.end.bar_index)))
        return out

    xds = _craft_multiscale_xds()
    res = compute_recursive_levels(xds, depth=3, config=_cfg())

    base_pts = pts(xds)
    for xd in res[1].xds:
        assert (round(float(xd.start.val), 4), int(xd.start.bar_index)) in base_pts
        assert (round(float(xd.end.val), 4), int(xd.end.bar_index)) in base_pts

    l2_pts = pts(res[1].xds)
    for xd in res[2].xds:
        assert (round(float(xd.start.val), 4), int(xd.start.bar_index)) in l2_pts
        assert (round(float(xd.end.val), 4), int(xd.end.bar_index)) in l2_pts
