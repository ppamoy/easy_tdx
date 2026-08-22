"""缠论核心数据结构定义。

参考 chanlun-pro cl_interface.py，去除对 db/exchange 的依赖，
使用纯 dataclass + 类型注解，保持 mypy strict 兼容。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

# ── K 线 ──────────────────────────────────────────────────────────────────


@dataclass
class Kline:
    """原始 K 线。"""

    index: int
    date: datetime
    open: float
    close: float
    high: float
    low: float
    amount: float  # 成交量（股数）

    def __str__(self) -> str:
        return (
            f"Kline(i={self.index} {self.date:%Y-%m-%d} "
            f"o={self.open:.2f} c={self.close:.2f} "
            f"h={self.high:.2f} l={self.low:.2f})"
        )


@dataclass
class CLKline:
    """缠论 K 线（包含处理后的合并 K 线）。"""

    k_index: int  # 对应原始 K 线中最后一根的 index
    date: datetime  # 合并 K 线最后一根的时间
    open: float
    close: float
    high: float
    low: float
    amount: float
    index: int = 0  # 在缠论 K 线列表中的序号
    merged_count: int = 1  # 合并了几根原始 K 线
    has_gap: bool = False  # 是否有缺口
    direction: str = ""  # 合并方向 "up" / "down" / ""
    klines: list[Kline] = field(default_factory=list)  # 包含的原始 K 线

    def __str__(self) -> str:
        return (
            f"CLKline(i={self.index} ki={self.k_index} {self.date:%Y-%m-%d} "
            f"h={self.high:.2f} l={self.low:.2f} n={self.merged_count})"
        )


# ── 分型 ──────────────────────────────────────────────────────────────────


class FXType(str, Enum):
    """分型类型。"""

    DING = "ding"  # 顶分型
    DI = "di"  # 底分型


@dataclass
class FX:
    """分型对象。"""

    fx_type: FXType
    k: CLKline  # 分型中间那根缠论 K 线
    klines: list[CLKline]  # 构成分型的三根缠论 K 线 [左, 中, 右]
    val: float  # 分型值（顶分型取 high，底分型取 low）
    index: int = 0  # 分型序号
    done: bool = True  # 分型是否完成

    def __str__(self) -> str:
        return f"FX(i={self.index} {self.fx_type.value} {self.k.date:%Y-%m-%d} val={self.val:.2f})"


# ── 线（笔/线段基类）─────────────────────────────────────────────────────


class Direction(str, Enum):
    """方向。"""

    UP = "up"
    DOWN = "down"


@dataclass
class Line:
    """线的基本定义，笔和线段的基类。"""

    start: FX  # 起始分型
    end: FX  # 结束分型
    direction: Direction  # 方向
    index: int = 0  # 序号
    high: float = 0.0  # 区间最高价
    low: float = 0.0  # 区间最低价

    def is_done(self) -> bool:
        """线是否完成（结束分型已完成）。"""
        return self.end.done

    def __str__(self) -> str:
        return (
            f"Line(i={self.index} {self.direction.value} "
            f"{self.start.k.date:%Y-%m-%d}→{self.end.k.date:%Y-%m-%d} "
            f"h={self.high:.2f} l={self.low:.2f})"
        )


@dataclass
class BI(Line):
    """笔。"""

    pass


@dataclass
class XD(Line):
    """线段。"""

    pass


# ── 中枢 ──────────────────────────────────────────────────────────────────


@dataclass
class ZS:
    """中枢对象。"""

    lines: list[BI | XD] = field(default_factory=list)  # 构成中枢的线
    zg: float = 0.0  # 中枢上沿（重叠区间最高）
    zd: float = 0.0  # 中枢下沿（重叠区间最低）
    gg: float = 0.0  # 中枢最高点
    dd: float = 0.0  # 中枢最低点
    direction: str = ""  # 中枢方向 "up"/"down"/""
    index: int = 0  # 序号
    done: bool = False  # 中枢是否完成
    start: FX | None = None  # 起始分型
    end: FX | None = None  # 结束分型

    def add_line(self, line: BI | XD) -> None:
        self.lines.append(line)

    @property
    def line_count(self) -> int:
        return len(self.lines)

    def __str__(self) -> str:
        return (
            f"ZS(i={self.index} lines={self.line_count} "
            f"zg={self.zg:.2f} zd={self.zd:.2f} "
            f"gg={self.gg:.2f} dd={self.dd:.2f} "
            f"done={self.done})"
        )


# ── 买卖点 / 背驰 ─────────────────────────────────────────────────────────


class MMDType(str, Enum):
    """买卖点类型。"""

    BUY_1 = "1buy"
    BUY_2 = "2buy"
    BUY_2S = "2buy_s"  # 类二买
    BUY_3 = "3buy"
    SELL_1 = "1sell"
    SELL_2 = "2sell"
    SELL_2S = "2sell_s"  # 类二卖
    SELL_3 = "3sell"


@dataclass
class MMD:
    """买卖点。"""

    mmd_type: MMDType
    zs: ZS | None = None
    bi: BI | None = None  # 触发该买卖点的笔（用于可视化锚定日期）
    msg: str = ""
    confidence: float = 0.0  # 置信度 0-1，由分析器计算
    quality: object = None  # 质量评级，由分析器计算
    confluence_score: float = 0.0  # 多时间框架共振评分 0-1，由MultiLevelAnalyser设置

    # V14 enhancement fields
    _vol_spike: bool = False  # 成交量异常放大
    _gap_up: bool = False  # 向上缺口
    _gap_down: bool = False  # 向下缺口
    _gap_size: float = 0.0  # 缺口大小（%）
    _macd_slope_confirmed: bool = False  # MACD柱状图斜率确认
    _vol_profile_support: bool = False  # 成交量剖面支撑确认
    _vol_profile_resistance: bool = False  # 成交量剖面阻力确认

    # V15 enhancement fields
    _kline_pattern: str | None = None  # K线形态：hammer/bullish_engulfing/doji/bearish_engulfing
    _signal_aging: dict | None = None  # 信号衰减信息
    _retest_break: bool = False  # 二次回踩确认
    _retest_retracement: float = 50.0  # 回踩深度（%）

    # V21 enhancement fields
    _dynamic_support: float | None = None  # 动态支撑位
    _dynamic_resistance: float | None = None  # 动态阻力位
    _signal_combo: str | None = None  # 组合信号类型：none/1+2buy/1+2sell/3buy_multi等
    _combo_confidence_bonus: float = 0.0  # 组合信号置信度加成
    _decision_recommendation: dict[str, Any] | None = None  # 决策辅助建议

    # V23 enhancement fields
    _fib_retracement: dict[str, Any] | None = None  # Fibonacci回撤位信息（条件40）
    _rsi_zone: dict[str, Any] | None = None  # RSI区域分类（条件41）
    _macd_zero_cross: dict[str, Any] | None = None  # MACD零轴穿越信息（条件42）

    # V24 enhancement fields
    _bi_quality: dict[str, Any] | None = None  # 笔质量评分（条件43）
    _zs_strength: dict[str, Any] | None = None  # 中枢强度分析（条件44）
    _enhanced_divergence: dict[str, Any] | None = None  # 增强背离检测（条件45）
    _cross_validation: dict[str, Any] | None = None  # 信号交叉验证评分（条件46）

    # V25 enhancement fields
    _post_signal_confirm: dict[str, Any] | None = None  # 信号后确认验证（条件47）
    _momentum_decay: dict[str, Any] | None = None  # 动量衰减预警（条件48）
    _vol_regime_filter: dict[str, Any] | None = None  # 波动率自适应过滤（条件49）
    _composite_quality: dict[str, Any] | None = None  # 综合信号质量评分（条件50）

    def __str__(self) -> str:
        return f"MMD({self.mmd_type.value} conf={self.confidence:.0%} {self.msg})"


class BCType(str, Enum):
    """背驰类型。"""

    BI = "bi"  # 笔背驰
    PZ = "pz"  # 盘整背驰
    QS = "qs"  # 趋势背驰


@dataclass
class BC:
    """背驰。"""

    bc_type: BCType
    bc: bool = False  # 是否背驰
    zs: ZS | None = None
    curr: BI | XD | None = None  # 当前背驰笔/线段（用于可视化锚定日期）
    prev: BI | XD | None = None  # 前一同向笔/线段（力度对照基准）
    msg: str = ""

    def __str__(self) -> str:
        return f"BC({self.bc_type.value} {self.bc})"


# ── BOLL 指标 ───────────────────────────────────────────────────────────

@dataclass
class BOLLResult:
    """BOLL 布林带结果。"""
    
    upper: list[float] = field(default_factory=list)   # 上轨
    mid: list[float] = field(default_factory=list)     # 中轨
    lower: list[float] = field(default_factory=list)   # 下轨
    width: list[float] = field(default_factory=list)   # 带宽 (upper - lower) / mid
    percent_b: list[float] = field(default_factory=list)  # %B = (close - lower) / (upper - lower)
    
    @property
    def latest_upper(self) -> float:
        return self.upper[-1] if self.upper else 0.0
    
    @property
    def latest_mid(self) -> float:
        return self.mid[-1] if self.mid else 0.0
    
    @property
    def latest_lower(self) -> float:
        return self.lower[-1] if self.lower else 0.0
    
    @property
    def latest_percent_b(self) -> float:
        return self.percent_b[-1] if self.percent_b else 0.5
    
    @property
    def latest_width(self) -> float:
        return self.width[-1] if self.width else 0.0
