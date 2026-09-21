"""缠论多级别递归计算。

以低级别线段（XD）作为高级别的「笔」逐级递归：第 1 级把基础线段的 XD
当作高级别「笔」计算其线段/中枢/背驰/买卖点；第 2 级再把第 1 级得到的
XD 当作更高级别「笔」继续递归，依此类推形成 `compute_recursive_levels`
的多级别递归链。

XD 与 BI 都继承自 Line，字段一致，因此每一级都能复用同一套线段/中枢/背驰/
买卖点算法（运行时鸭子类型）。端点始终锚定原始 K 线的 bar_index，因此原始
`closes` 序列在整个递归链内都是有效的力度/MACD 上下文。

为避免在 ChanlunAnalyser 中内联一大段递归逻辑，这里抽出独立函数，便于
单独做金标测试。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from easy_tdx.chanlun.beichi import check_bi_beichi
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.mmd import find_mmds_v44
from easy_tdx.chanlun.types import BC, BI, MMD, XD, ZS
from easy_tdx.chanlun.xd import find_xds
from easy_tdx.chanlun.zs import find_zss
from easy_tdx.chanlun.zsd import find_qsds, find_zsds


@dataclass
class RecursiveLevelResult:
    """递归级别计算结果。"""

    xds: list[XD] = field(default_factory=list)
    zss: list[ZS] = field(default_factory=list)
    mmds: list[MMD] = field(default_factory=list)
    bcs: list[BC] = field(default_factory=list)
    zsds: list[XD] = field(default_factory=list)
    qsds: list[XD] = field(default_factory=list)


def compute_recursive_level(
    xds: list[XD],
    closes: list[float] | None = None,
    volumes: list[float] | None = None,
    macd_data: dict[str, list[float]] | None = None,
    volatility: float | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    config: ChanlunConfig | None = None,
) -> RecursiveLevelResult:
    """以线段为高级别笔，计算第一级高级别线段/中枢/背驰/买卖点。

    等价于 `compute_recursive_levels(..., depth=1)` 的第一级结果，
    保留为单级别递归的向后兼容入口。

    Args:
        xds: 低级别线段列表（方向自然交替）。
        closes/volumes/highs/lows/macd_data/volatility: 与单级别
            find_mmds_v44 相同的指标上下文，用于高级别买卖点增强条件。
        config: 缠论配置；为 None 时使用默认配置。

    Returns:
        RecursiveLevelResult：第一级高级别线段、线段中枢、背驰、三类买卖点。
        低级别线段少于 3 根时返回空结果。
    """
    if config is None:
        config = ChanlunConfig()

    if len(xds) < 3:
        return RecursiveLevelResult()

    return _compute_one_level(
        xds,
        closes=closes,
        volumes=volumes,
        macd_data=macd_data,
        volatility=volatility,
        highs=highs,
        lows=lows,
        config=config,
    )


def compute_recursive_levels(
    xds: list[XD],
    depth: int = 1,
    closes: list[float] | None = None,
    volumes: list[float] | None = None,
    macd_data: dict[str, list[float]] | None = None,
    volatility: float | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    config: ChanlunConfig | None = None,
) -> list[RecursiveLevelResult]:
    """多级别递归：以低级别线段逐级构造更高级别线段/中枢/背驰/买卖点。

    第 1 级的「高级别笔」= 传入的低级别线段；随后每一级把上一级得到的
    线段当作更高级别的「笔」，递归计算其线段/中枢/背驰/三类买卖点，
    直到达到 `depth` 级或当前级线段不足 3 根为止。

    Args:
        xds: 基础级别线段（方向自然交替），作为第 1 级递归的「笔」。
        depth: 期望递归级别数（>=1）。实际返回级别数受数据约束，可少于 depth。
        closes/volumes/highs/lows/macd_data/volatility: 与单级别
            find_mmds_v44 相同的指标上下文。端点始终锚定原始 K 线的
            bar_index，因此原始 closes 序列对每一级都有效。
        config: 缠论配置；为 None 时使用默认配置。

    Returns:
        每级一个 RecursiveLevelResult，result[i] 对应第 i+1 级递归。
        基础线段少于 3 根时报空列表。
    """
    if config is None:
        config = ChanlunConfig()

    if depth < 1:
        depth = 1

    results: list[RecursiveLevelResult] = []
    lines: list[XD] = xds
    for _ in range(depth):
        if len(lines) < 3:
            break
        level = _compute_one_level(
            lines,
            closes=closes,
            volumes=volumes,
            macd_data=macd_data,
            volatility=volatility,
            highs=highs,
            lows=lows,
            config=config,
        )
        results.append(level)
        # 本级的线段成为下一级的「高级别笔」。
        lines = level.xds

    return results


def _compute_one_level(
    lines: list[XD],
    closes: list[float] | None,
    volumes: list[float] | None,
    macd_data: dict[str, list[float]] | None,
    volatility: float | None,
    highs: list[float] | None,
    lows: list[float] | None,
    config: ChanlunConfig,
) -> RecursiveLevelResult:
    """把线段列表当高级别「笔」，计算其所在级别的高级别线段/中枢/背驰/买卖点。

    XD 与 BI 同构，运行时按 BI 传入既有算法。方向交替由低级别线段保证。
    """
    lines_bi = cast(list[BI], lines)

    level_xds = find_xds(lines_bi, config)
    level_zss = find_zss(lines_bi, config)
    level_mmds = find_mmds_v44(
        lines_bi,
        level_zss,
        closes=closes,
        config=config,
        volumes=volumes,
        macd_data=macd_data,
        volatility=volatility,
        highs=highs,
        lows=lows,
    )
    level_bcs = check_bi_beichi(lines_bi, level_zss, closes=closes, config=config)
    level_zsds = find_zsds(level_xds, config)
    level_qsds = find_qsds(level_xds, config)

    return RecursiveLevelResult(
        xds=level_xds,
        zss=level_zss,
        mmds=level_mmds,
        bcs=level_bcs,
        zsds=level_zsds,
        qsds=level_qsds,
    )
