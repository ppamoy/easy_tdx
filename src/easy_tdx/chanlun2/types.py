"""chanlun2 类型定义——严格对照108课原文。

核心原文依据：
- 第17课：中枢=次级别走势类型重叠；盘整=1中枢；趋势=≥2依次同向中枢。
- 第20课：中枢区间 [ZD,ZG]=前两 Z 走势段重叠；GG/G/D/DD 四指标；
  中枢延伸=任意[dn,gn]与[ZD,ZG]有重叠。
- 第24课：背驰=A/B/C 三段，C 段 MACD 面积<A 段，B 回拉 0 轴。
- 第27/53课：1买=趋势背驰；盘整背驰≠1买。
- 第20/61课：3买卖=第一次回试不破 ZG，至少5段。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Direction(Enum):
    """走势方向（第17课：上涨/下跌/盘整）。"""

    UP = "up"
    DOWN = "down"


class FractalType(Enum):
    """分型类型（第67课：顶分型/底分型）。"""

    TOP = "top"
    BOTTOM = "bottom"


class TrendKind(Enum):
    """走势类型（第17课）：盘整=1中枢，趋势=≥2同向中枢。

    用 Enum 而非 str，避免 seg_mmd 那种 ``kind="none"`` 自创类别的污染
    （原文无 none 类，不足3段的是「未完成走势类型片段」）。
    """

    PANZHENG = "panzheng"  # 盘整：1 个中枢
    TREND_UP = "trend_up"  # 上涨趋势：≥2 同向中枢，方向向上
    TREND_DOWN = "trend_down"  # 下跌趋势：≥2 同向中枢，方向向下
    INCOMPLETE = "incomplete"  # 未完成走势类型片段（不足3段，原文无独立类别）

    @property
    def is_trend(self) -> bool:
        """第17课：趋势=≥2 中枢。"""
        return self in (TrendKind.TREND_UP, TrendKind.TREND_DOWN)

    @property
    def is_panzheng(self) -> bool:
        """第17课：盘整=1 中枢。"""
        return self == TrendKind.PANZHENG


class DivergenceKind(Enum):
    """背驰类型（第24/27/53课）。

    第27课：「第一类买点肯定是趋势背驰构成的」；
    第53课：「盘整背驰非第一类买卖点」。
    ⇒ 趋势背驰与盘整背驰是**不同类型**，下游据此区分是否第一类买卖点。
    """

    TREND = "trend"  # 趋势背驰（≥2 中枢，可构成1买）
    PANZHENG = "panzheng"  # 盘整背驰（1 中枢，≠1买）


class MMDType(Enum):
    """三类买卖点（第20/27/101课）。盘整背驰不标 1买（第53课）。"""

    BUY_1 = "buy1"  # 第一类买点（趋势背驰，第27课）
    BUY_2 = "buy2"  # 第二类买点（1买次级别回抽后，第101课）
    BUY_3 = "buy3"  # 第三类买点（第一次回试不破ZG，第20课）
    SELL_1 = "sell1"  # 第一类卖点
    SELL_2 = "sell2"
    SELL_3 = "sell3"
    # 盘整背驰买卖点：第53课明确「盘整背驰≠第一类买卖点」，单独标注
    PANZHENG_BUY = "panzheng_buy"
    PANZHENG_SELL = "panzheng_sell"

    @property
    def is_buy(self) -> bool:
        return self in (MMDType.BUY_1, MMDType.BUY_2, MMDType.BUY_3)

    @property
    def is_sell(self) -> bool:
        return self in (MMDType.SELL_1, MMDType.SELL_2, MMDType.SELL_3)

    @property
    def is_first_class(self) -> bool:
        """是否第一类买卖点（第27课：仅趋势背驰构成）。"""
        return self in (MMDType.BUY_1, MMDType.SELL_1)


@dataclass
class KLine:
    """原始 K 线（OHLCV）。"""

    index: int  # 在输入序列中的位置
    dt: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class MergedK:
    """K 线合并后的元素（第68课：K线包含关系处理）。

    合并方向（向上/向下）决定包含处理时的取法（第68课）：
    - 向上序列：高高取高、低低取高（取高高高高）
    - 向下序列：高高取低、低低取低
    """

    index: int  # 合并后序号
    dt_start: str  # 起始K线时间
    dt_end: str  # 结束K线时间
    high: float
    low: float
    raw_indices: list[int] = field(default_factory=list)  # 合并的原始K线index
    direction: Optional[Direction] = None  # 合并方向（向上/向下序列）

    @property
    def range(self) -> tuple[float, float]:
        return (self.low, self.high)


@dataclass
class Fractal:
    """分型（第67课：顶分型/底分型）。

    由连续三根合并K线构成：第二根K线高点最高=顶分型；低点最低=底分型。
    """

    index: int
    kind: FractalType
    value: float  # 顶=high，底=low
    k_index: int  # 对应 MergedK.index
    dt: str


@dataclass
class Move:
    """走势段（最小级别=笔的严格化；高级别=次级别走势类型）。

    第77课「笔」定义：由顶底分型交替连接构成，且满足「独立、相邻、相反」。
    chanlun2 用 ``Move`` 统一表示最小级别段与次级别走势类型，
    级别由所在分析层决定（递归）。
    """

    index: int
    direction: Direction  # 向上/向下
    start: Fractal  # 起点分型
    end: Fractal  # 终点分型
    start_k: int  # 起点MergedK.index
    end_k: int  # 终点MergedK.index
    high: float  # 段内最高
    low: float  # 段内最低
    # MACD 辅助（第24课）：段对应的黄白线dif/dea峰值、柱子面积
    macd_area: float = 0.0
    dif_peak: float = 0.0
    dea_peak: float = 0.0

    @property
    def is_up(self) -> bool:
        return self.direction == Direction.UP


@dataclass
class ZS:
    """缠中说禅走势中枢（第17/20课严格定义）。

    第20课：中枢区间 [ZD, ZG]=前两 Z 走势段重叠部分；
    GG=max(gn), G=min(gn), D=max(dn), DD=min(dn)，n 遍历所有 Z 走势段。
    Z 走势段=与中枢方向一致的次级别走势类型。

    第17课：中枢=「至少三个连续次级别走势类型所重叠的部分」。
    chanlun2 严格递归：高级别中枢由次级别走势类型(=Move)重叠构成；
    最低级别中枢由「至少三个该级别 K 线(MergedK)重叠部分」构成（非笔构中枢）。
    """

    index: int
    direction: Optional[Direction]  # 中枢形成方向（回升/回调）
    zg: float  # 中枢上沿 = min(g1, g2)
    zd: float  # 中枢下沿 = max(d1, d2)
    gg: float  # = max(gn) 所有Z段高点最大
    dd: float  # = min(dn) 所有Z段低点最小
    g: float  # = min(gn)
    d: float  # = max(dn)
    z_moves: list[Move] = field(default_factory=list)  # Z走势段（与方向一致）
    enter_move: Optional[Move] = None  # 进入段（离开中枢的反向走势）
    exit_move: Optional[Move] = None  # 离开段
    start_k: int = 0  # 起始K线
    end_k: int = 0  # 结束K线

    @property
    def interval(self) -> tuple[float, float]:
        """[ZD, ZG]（第20课）。"""
        return (self.zd, self.zg)

    @property
    def is_valid(self) -> bool:
        """第20课：中枢区间存在需 ZG > ZD。"""
        return self.zg > self.zd

    def overlaps_interval(self, lo: float, hi: float) -> bool:
        """中枢中心定理一：任意 [dn,gn] 与 [ZD,ZG] 有重叠 ⇒ 延伸。"""
        return self.zd <= hi and lo <= self.zg


@dataclass
class TrendSegment:
    """同级别分解的走势类型段（第38课）。

    第38课：把任何图形分解成一段段走势类型的连接。
    每段含一个或多个同向中枢（第17课：≥2中枢=趋势，1中枢=盘整）。
    """

    index: int
    kind: TrendKind
    direction: Optional[Direction]  # 趋势方向（盘整为None或形成方向）
    moves: list[Move] = field(default_factory=list)  # 段内走势
    zss: list[ZS] = field(default_factory=list)  # 段内中枢
    start_k: int = 0
    end_k: int = 0
    high: float = 0.0
    low: float = 0.0

    @property
    def is_trend(self) -> bool:
        """第17课：趋势=≥2 中枢（TrendKind.is_trend）。"""
        return self.kind.is_trend

    @property
    def is_panzheng(self) -> bool:
        """第17课：盘整=1 中枢。"""
        return self.kind.is_panzheng

    @property
    def zs_count(self) -> int:
        return len(self.zss)


@dataclass
class Divergence:
    """背驰（第24课）。

    A/B/C 三段同向趋势：A 之前已有中枢，B 是另一中枢（回拉0轴），
    C 段 MACD 面积 < A 段面积 ⇒ 标准背驰。
    """

    kind: DivergenceKind  # 趋势背驰 / 盘整背驰
    move_a: Move  # A 段
    move_c: Move  # C 段
    zs_b: Optional[ZS] = None  # B 中枢
    # 第24课：B 中枢把黄白线回拉 0 轴附近
    dif_returned_to_zero: bool = False
    # C 段面积 < A 段面积
    area_c: float = 0.0
    area_a: float = 0.0

    @property
    def is_divergent(self) -> bool:
        """第24课：C 段面积 < A 段面积 ⇒ 背驰。"""
        return self.area_c < self.area_a


@dataclass
class MMD:
    """买卖点（第20/27/101课）。"""

    index: int
    mmd_type: MMDType
    k_index: int  # 买卖点K线位置
    dt: str
    price: float
    direction: Direction  # 买=向下结束(底)，卖=向上结束(顶)
    divergence: Optional[Divergence] = None  # 关联背驰（1买/盘整背驰）
    zs: Optional[ZS] = None  # 关联中枢（3买卖点的被离开中枢）
    confidence: float = 1.0
    note: str = ""
