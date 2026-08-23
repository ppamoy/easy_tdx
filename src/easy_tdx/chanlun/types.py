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

    # V26 enhancement fields
    _signal_history: dict[str, Any] | None = None  # 信号历史验证评分（条件51）
    _dynamic_rr_optimization: dict[str, Any] | None = None  # 动态风险收益优化（条件52）
    _cross_stock_comparison: dict[str, Any] | None = None  # 多标的对比评分（条件53）

    # V27 enhancement fields
    _multi_tf_confluence: dict[str, Any] | None = None  # 多级别区间套共振验证（条件54）
    _structure_position: dict[str, Any] | None = None  # 买卖点结构位置评分（条件55）
    _stock_profile: dict[str, Any] | None = None  # 个股信号特征学习（条件56）

    # V28 enhancement fields
    _boll_squeeze: dict[str, Any] | None = None  # BOLL带宽压缩确认（条件57）
    _breakout_vol_price: dict[str, Any] | None = None  # 突破量价确认（条件58）
    _dynamic_atr_stop: dict[str, Any] | None = None  # 动态ATR止损位（条件59）

    # V29 enhancement fields
    _trend_continuity: dict[str, Any] | None = None  # 趋势方向持续性确认（条件60）
    _consolidation_divergence: dict[str, Any] | None = None  # 盘整区背离预警（条件61）

    # V30 enhancement fields
    _kline_pattern_confirm: dict[str, Any] | None = None  # K线形态反向确认（条件62）
    _zs_breakout_confirm: dict[str, Any] | None = None  # 中枢突破方向确认（条件63）
    _recent_range_stop: dict[str, Any] | None = None  # 近期波动区间止损优化（条件64）

    # V31 enhancement fields
    _ma_alignment: dict[str, Any] | None = None  # 均线排列确认（条件65）
    _macd_histogram_acceleration: dict[str, Any] | None = None  # MACD柱状图加速度（条件66）
    _signal_health_dashboard: dict[str, Any] | None = None  # 信号综合健康度报告（条件67）

    # V32 enhancement fields
    _vol_price_divergence_enhanced: dict[str, Any] | None = None  # 量价背离检测增强（条件68）
    _signal_priority: dict[str, Any] | None = None  # 信号优先级动态排序（条件69）
    _sr_breakout_confirm: dict[str, Any] | None = None  # 支撑阻力位突破确认（条件70）

    # V33 enhancement fields
    _obv_trend_confirm: dict[str, Any] | None = None  # OBV能量潮趋势确认（条件71）
    _macd_hist_area: dict[str, Any] | None = None  # MACD动能锥面积确认（条件72）
    _rsi_momentum_confirm: dict[str, Any] | None = None  # RSI动量确认（条件73）

    # V34 enhancement fields
    _trend_momentum_continuation: dict[str, Any] | None = None  # 趋势动能延续确认（条件74）
    _multi_indicator_resonance: dict[str, Any] | None = None  # 多指标共振强度评分（条件75）
    _volatility_regime: dict[str, Any] | None = None  # 波动率环境自适应阈值（条件76）

    # V35 enhancement fields
    _market_context_filter: dict[str, Any] | None = None  # 市场大环境过滤（条件77）
    _enhanced_signal_decay: dict[str, Any] | None = None  # 信号衰减模型增强（条件78）
    _false_signal_filter: dict[str, Any] | None = None  # 假信号过滤增强（条件79）
    _dynamic_sl_tp_enhanced: dict[str, Any] | None = None  # 动态止损止盈增强（条件80）
    _sector_rotation_context: dict[str, Any] | None = None  # 板块轮动上下文（条件81）
    _multi_dim_divergence: dict[str, Any] | None = None  # 多维度背离确认（条件82）

    # V36 enhancement fields
    _execution_window: dict[str, Any] | None = None  # 信号执行窗口优化（条件83）
    _tf_consistency: dict[str, Any] | None = None  # 多时间框架一致性验证（条件84）
    _risk_adjusted_return: dict[str, Any] | None = None  # 风险调整后收益预期（条件85）
    _urgency_score: dict[str, Any] | None = None  # 信号时效性紧急度评分（条件86）
    _market_composite: dict[str, Any] | None = None  # 市场环境综合评分（条件87）
    _strategy_recommendation: dict[str, Any] | None = None  # 买卖点策略推荐（条件88）

    # V37 enhancement fields
    _consecutive_confirmation: dict[str, Any] | None = None  # 连续确认过滤（条件89）
    _momentum_acceleration: dict[str, Any] | None = None  # 价格动能加速度（条件90）
    _volatility_regime_change: dict[str, Any] | None = None  # 波动率状态转换检测（条件91）
    _temporal_correlation: dict[str, Any] | None = None  # 买卖点时间序列关联分析（条件92）
    _multi_tf_momentum: dict[str, Any] | None = None  # 多时间框架动量一致性（条件93）
    _quality_ranking: dict[str, Any] | None = None  # 信号综合质量排名（条件94）

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
        return self.upper[-1] if len(self.upper) > 0 else 0.0

    @property
    def latest_mid(self) -> float:
        return self.mid[-1] if len(self.mid) > 0 else 0.0

    @property
    def latest_lower(self) -> float:
        return self.lower[-1] if len(self.lower) > 0 else 0.0

    @property
    def latest_percent_b(self) -> float:
        return self.percent_b[-1] if len(self.percent_b) > 0 else 0.5

    @property
    def latest_width(self) -> float:
        return self.width[-1] if len(self.width) > 0 else 0.0
