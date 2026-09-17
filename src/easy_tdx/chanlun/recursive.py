"""缠论多级别递归计算。

以低级别线段（XD）作为高级别的「笔」，递归计算高级别线段、线段中枢、
背驰与三类买卖点。

XD 与 BI 都是 Line 子类，字段一致，因此可复用同一套线段/中枢/背驰/买卖点
算法（运行时鸭子类型）。为避免在 ChanlunAnalyser 中内联一大段递归逻辑，
这里抽出独立函数，便于单独做金标测试。
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


@dataclass
class RecursiveLevelResult:
    """递归级别计算结果。"""

    xds: list[XD] = field(default_factory=list)
    zss: list[ZS] = field(default_factory=list)
    mmds: list[MMD] = field(default_factory=list)
    bcs: list[BC] = field(default_factory=list)


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
    """以线段为高级别笔，计算高级别线段/中枢/背驰/买卖点。

    Args:
        xds: 低级别线段列表（方向自然交替）。
        closes: 原始 K 线收盘价序列。计算力度时使用线段端点的原始 K 线
            bar_index 从该序列取 MACD 面积，因此长度需覆盖所有端点。
            为 None 时退化为振幅力度。
        volumes/highs/lows/macd_data/volatility: 与单级别 find_mmds_v44 相同的
            指标上下文，用于高级别买卖点增强条件。
        config: 缠论配置；为 None 时使用默认配置。

    Returns:
        RecursiveLevelResult：高级别线段、线段中枢、背驰、三类买卖点。
        低级别线段少于 3 根时返回空结果。
    """
    if config is None:
        config = ChanlunConfig()

    if len(xds) < 3:
        return RecursiveLevelResult()

    # XD 与 BI 同构，运行时按 BI 传入既有算法。方向交替由低级别线段保证。
    lines = cast(list[BI], xds)

    level_xds = find_xds(lines, config)
    level_zss = find_zss(lines, config)
    level_mmds = find_mmds_v44(
        lines,
        level_zss,
        closes=closes,
        config=config,
        volumes=volumes,
        macd_data=macd_data,
        volatility=volatility,
        highs=highs,
        lows=lows,
    )
    level_bcs = check_bi_beichi(lines, level_zss, closes=closes, config=config)

    return RecursiveLevelResult(
        xds=level_xds,
        zss=level_zss,
        mmds=level_mmds,
        bcs=level_bcs,
    )
